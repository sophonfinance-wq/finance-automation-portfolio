"""Self-verifying parser for fixed-width job-cost print reports.

The report prints its own per-job totals; parsing is only accepted when every
job's parsed sum ties those printed totals exactly. Anything else refuses -
an untied workpaper never leaves this module.
"""
from __future__ import annotations

import datetime as dt
import re

from .model import (CostLine, JobPrintTotal, ParsedReport, ParseRefusal,
                    ReconciliationFailure, TranType)
from .money import MoneyError, parse_cents

_AMOUNT = re.compile(r"^-?[\d,]*\.\d{2}$")
_DATE = re.compile(r"^\d{2}-\d{2}-\d{2}$")
_JOB = re.compile(r"^Job:\s*(\d{3,4}-\w+)\s*(.*)$")
_CC = re.compile(r"^(\d{2,3}-\d{3})\s\s*(.+)$")
_VENDID = re.compile(r"^(?:[A-Z][A-Z0-9&]{1,7}\d{0,2}|0{4})$")
_JOBTOTAL = re.compile(r"^\d{3,4}-99$")
_NOISE = ("Job Cost Detail", "Page ", "Accounting Dates", "Tran Type", "Acctg",
          "Vendor ID and Name", "Category", "Invoice", "Ref1", "Ref2",
          "Description", "Amount", "AP Cost = Invoices", "1-Labor")
_TRAN_TYPES = {t.value for t in TranType}


def _to_date(s: str) -> dt.date:
    m, d, y = (int(p) for p in s.split("-"))
    return dt.date(2000 + y, m, d)


def parse_report(text: str, company: str) -> ParsedReport:
    tokens: list[str] = []
    date_from = date_to = None
    lines_iter = [ln.strip() for ln in text.splitlines() if ln.strip()]
    i = 0
    while i < len(lines_iter):
        s = lines_iter[i]
        if s == "Accounting Dates from:" and i + 3 < len(lines_iter):
            date_from = _to_date(lines_iter[i + 1])
            date_to = _to_date(lines_iter[i + 3])
            i += 4
            continue
        if s == company or any(s.startswith(p) for p in _NOISE):
            i += 1
            continue
        tokens.append(s)
        i += 1
    if date_from is None or date_to is None:
        raise ParseRefusal([ReconciliationFailure("<header>", 0, None)])

    rows: list[CostLine] = []
    printed: dict[str, int] = {}
    job = job_name = cc = ccdesc = ""
    tran: TranType | None = None
    vend_id = vend_name = ""
    pend: list[str] = []

    def flush(amount_cents: int) -> None:
        nonlocal vend_id, vend_name
        if not job:
            return
        fields = list(pend)
        dates = [x for x in fields if _DATE.match(x)]
        rest = [x for x in fields if not _DATE.match(x)]
        acctg = _to_date(dates[0]) if dates else date_from
        v_id = v_name = invoice = ""
        desc = ""
        if tran is TranType.AP:
            if rest and _VENDID.match(rest[0]) and len(rest) >= 2:
                v_id, v_name, rest = rest[0], rest[1], rest[2:]
                vend_id, vend_name = v_id, v_name
            else:
                v_id, v_name = vend_id, vend_name
            if rest:
                invoice, desc = rest[0], " ".join(rest[1:])
        else:
            if len(rest) == 1:
                desc = rest[0]
            else:
                desc = " ".join(rest[2:]) if len(rest) > 2 else ""
        rows.append(CostLine(job=job, job_name=job_name, cost_code=cc,
                             cost_code_desc=ccdesc, tran_type=tran or TranType.JC,
                             acctg_date=acctg, vendor_id=v_id, vendor_name=v_name,
                             invoice=invoice, description=desc,
                             amount_cents=amount_cents))

    i = 0
    while i < len(tokens):
        s = tokens[i]
        m = _JOB.match(s)
        if m:
            job, job_name = m.group(1), m.group(2).strip()
            cc = ccdesc = ""
            tran = None
            vend_id = vend_name = ""
            pend = []
            i += 1
            continue
        m = _CC.match(s)
        if m and not _AMOUNT.match(s):
            cc, ccdesc = m.group(1), m.group(2).strip()
            pend = []
            i += 1
            continue
        if s in _TRAN_TYPES:
            tran = TranType(s)
            pend = []
            i += 1
            continue
        if s == "Primary Job":
            i += 1
            pend = []
            continue
        if s == "Total:":
            i += 2  # skip the "Primary Job Total" amount; job-total handled below
            pend = []
            continue
        if _JOBTOTAL.match(s) and i + 2 < len(tokens) and tokens[i + 1] == "Total:" \
                and _AMOUNT.match(tokens[i + 2]):
            printed[s] = parse_cents(tokens[i + 2])
            i += 3
            pend = []
            continue
        if _AMOUNT.match(s):
            flush(parse_cents(s))
            pend = []
            i += 1
            continue
        pend.append(s)
        i += 1

    # self-verification: every job must tie to its printed total - over the
    # UNION of parsed jobs and printed-total jobs, so a printed total with no
    # parsed lines (or vice versa) cannot slip through as "no failure".
    sums: dict[str, int] = {}
    for r in rows:
        sums[r.job] = sums.get(r.job, 0) + r.amount_cents
    all_jobs = sorted(set(sums) | set(printed))
    failures = [ReconciliationFailure(j, sums.get(j, 0), printed.get(j))
                for j in all_jobs
                if printed.get(j) is None or printed[j] != sums.get(j, 0)]
    if failures:
        raise ParseRefusal(failures)

    return ParsedReport(company=company, date_from=date_from, date_to=date_to,
                        lines=tuple(rows),
                        printed_totals=tuple(JobPrintTotal(j, c)
                                             for j, c in sorted(printed.items())))
