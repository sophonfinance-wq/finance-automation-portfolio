"""Seeded generator of fictional fixed-width job-cost print reports.

Produces the text a construction ERP would print for "job cost detail by
transaction type by vendor", including the report's own per-job totals — which
the parser later uses to verify itself. Also produces a matching coverage
listing and a parallel ledger export that carries transaction dates the print
is blind to. Deterministic for a given seed; all names are fictional.
"""
from __future__ import annotations

import datetime as dt
import random

from .model import CoverageRecord, LedgerRow, TranType
from .money import format_cents

COMPANIES = ("Alderpoint Builders LLC", "Rivermont Homes Group", "Copperfield Yards LP")
VENDOR_POOL = (
    ("ACME01", "ACME CONCRETE CUTTING INC"),
    ("BRI002", "BRIDLEWOOD GLASS & GLAZING"),
    ("CED003", "CEDARFALL PLUMBING LLC"),
    ("DOV004", "DOVETAIL PAINT SUPPLY CO"),
    ("ELM005", "ELMGATE LAW GROUP PLLC"),
    ("FEN006", "FENWICK ELECTRIC LLP"),
    ("GRO007", "GROVEStone ROOFING INC"),
    ("HAV008", "HAVENPORT LANDSCAPES LLC"),
)
CLEARING = ("0000", "summary vendor")
JOB_NAMES = ("Warranty", "Customer Service", "Homeowner Care")
CC_POOL = (
    ("86-104", "Warranty - Third Party Repairs"),
    ("99-106", "Warranty - Materials & Tools"),
    ("99-202", "Warranty - CS Admin Costs"),
    ("99-203", "Warranty - Legal"),
    ("99-204", "Warranty - Entity Costs"),
)
PAGE_LINES = 46
_TXN_OFFSETS = (0, 1, 2, 5, 9, 14, 21, 31, -3)


def _date_between(rng: random.Random, lo: dt.date, hi: dt.date) -> dt.date:
    span = (hi - lo).days
    return lo + dt.timedelta(days=rng.randint(0, span))


def _fmt(d: dt.date) -> str:
    return f"{d.month:02d}-{d.day:02d}-{d.year % 100:02d}"


class GeneratedReport:
    def __init__(self, company: str, text: str, expected_job_totals: dict[str, int],
                 coverage: list[CoverageRecord], line_count: int,
                 ledger: list[LedgerRow] | None = None):
        self.company = company
        self.text = text
        self.expected_job_totals = expected_job_totals
        self.coverage = coverage
        self.line_count = line_count
        self.ledger = ledger if ledger is not None else []


def generate_report(seed: int, *, jobs: int = 4, defect: str | None = None) -> GeneratedReport:
    """Build a fictional print report.

    ``defect`` plants a specific flaw for the refusal tests:
      - "printed_total_off":   one printed job total is off by one cent
      - "missing_total_line":  one job's printed total line is absent
      - "malformed_amount":    one amount lacks its decimals
    """
    rng = random.Random(seed)
    company = COMPANIES[seed % len(COMPANIES)]
    lo, hi = dt.date(2025, 9, 1), dt.date(2026, 8, 14)
    out: list[str] = []
    expected: dict[str, int] = {}
    coverage: list[CoverageRecord] = []
    ledger: list[LedgerRow] = []
    page = 1
    line_count = 0

    def txn_for(acctg: dt.date) -> dt.date:
        return acctg - dt.timedelta(days=rng.choice(_TXN_OFFSETS))

    def header() -> None:
        out.extend([
            "Job Cost Detail by Tran Type by Vendor",
            company,
            f"Page {page}",
            "Accounting Dates from:", _fmt(lo), "to:", _fmt(hi),
            "Tran Type", "Acctg", "Vendor ID and Name", "Category", "Date",
            "Invoice", "Ref1", "Ref2", "Description", "Amount",
        ])

    header()
    defect_armed = defect
    for j in range(jobs):
        job = f"{7100 + seed % 50 + j}-99"
        out.append(f"Job: {job} Fictional {JOB_NAMES[j % len(JOB_NAMES)]}")
        job_total = 0
        n_codes = rng.randint(1, 3)
        for cc, ccdesc in rng.sample(CC_POOL, n_codes):
            out.append(f"{cc}  {ccdesc}")
            # AP block
            if rng.random() < 0.8:
                out.append(TranType.AP.value)
                vid, vname = rng.choice(VENDOR_POOL + (CLEARING,))
                n_ap = rng.randint(1, 3)
                for k in range(n_ap):
                    amount = rng.randint(500, 2_500_000)  # cents
                    d = _date_between(rng, lo, hi)
                    if k == 0:
                        out.extend([vid, vname])
                    amt_txt = format_cents(amount)
                    if defect_armed == "malformed_amount":
                        amt_txt = amt_txt.split(".")[0]
                        defect_armed = None
                    out.extend([_fmt(d), f"INV{rng.randint(1000, 99999)}",
                                f"FICTIONAL WORK ORDER {rng.randint(10, 99)}", amt_txt])
                    job_total += amount
                    line_count += 1
                    ledger.append(LedgerRow(
                        job=job, cost_code=cc, tran_type=TranType.AP,
                        txn_date=txn_for(d), acctg_date=d, amount_cents=amount))
                    if rng.random() < 0.15:  # reversal pair, vendor repeated
                        out.extend([vid, vname, _fmt(d), f"INV{rng.randint(1000, 99999)}",
                                    "(Rev) FICTIONAL REVERSAL", format_cents(-amount)])
                        job_total += -amount
                        line_count += 1
                        ledger.append(LedgerRow(
                            job=job, cost_code=cc, tran_type=TranType.AP,
                            txn_date=txn_for(d), acctg_date=d, amount_cents=-amount))
                if vname != CLEARING[1] and rng.random() < 0.9:
                    exp = _date_between(rng, dt.date(2025, 6, 1), dt.date(2027, 6, 1))
                    coverage.append(CoverageRecord(
                        vendor_name=vname.upper(), coverage="General",
                        effective=exp - dt.timedelta(days=365), expiration=exp,
                        limit_cents=100_000_000, received=True))
            # JC block
            if rng.random() < 0.7:
                out.append(TranType.JC.value)
                n_jc = rng.randint(1, 2)
                for _ in range(n_jc):
                    amount = rng.randint(100, 800_000)
                    d = _date_between(rng, lo, hi)
                    refs = ["lm", "lm"] if rng.random() < 0.6 else ["FICTIONAL NOTE"]
                    out.extend([_fmt(d), *refs, format_cents(amount)])
                    job_total += amount
                    line_count += 1
                    ledger.append(LedgerRow(
                        job=job, cost_code=cc, tran_type=TranType.JC,
                        txn_date=txn_for(d), acctg_date=d, amount_cents=amount))
        expected[job] = job_total
        printed = job_total
        if defect_armed == "printed_total_off":
            printed += 1
            defect_armed = None
        if defect_armed == "missing_total_line":
            defect_armed = None
        else:
            out.extend(["Primary Job", "Total:", format_cents(printed),
                        job, "Total:", format_cents(printed)])
        # page break boilerplate mid-stream, like a real print
        if len(out) // PAGE_LINES > page - 1:
            page += 1
            out.extend(["AP Cost = Invoices Only, JC Cost = Journal Entries",
                        "Category", "1-Labor, 2-Material, 3-Equipment, 4-Subcontractor, 5-Overhead, 6-Other"])
            header()
    out.extend(["AP Cost = Invoices Only, JC Cost = Journal Entries",
                "Category", "1-Labor, 2-Material, 3-Equipment, 4-Subcontractor, 5-Overhead, 6-Other"])
    return GeneratedReport(company, "\n".join(out), expected, coverage, line_count, ledger)
