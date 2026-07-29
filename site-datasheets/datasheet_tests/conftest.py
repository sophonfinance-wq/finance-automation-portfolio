"""Shared fixtures + package-wide marker for the datasheet test suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    """Every datasheet test is site tooling, not an engine test.

    NOTE: this hook receives the WHOLE session's items (pytest calls it once,
    with everything collected — not just this directory), so the marker must
    be scoped by path or a repo-root run would mark all engine tests too.
    """
    for item in items:
        try:
            item_path = Path(str(item.fspath)).resolve()
        except OSError:
            continue
        if item_path.is_relative_to(HERE):
            item.add_marker("site_tooling")


import datasheet_spec as ds  # noqa: E402
import generate_datasheets as gen  # noqa: E402
import pytest  # noqa: E402

#: Canonical §4 roster (design spec) — the single source of engine identity, so every
#: spec that lands (Triangulate now; the other eight in phase 2) is checked against one
#: authority. `engine_dir` is where that engine's own pytest suite lives (for the live
#: test-count cross-check).
ROSTER: dict[str, dict] = {
    "close":       {"num": 1, "part_no": "SFS-E01-CLS", "mnemonic": "CLS", "family": "Close Automation",           "name": "Month-End Close",             "engine_dir": "monthly-close-automation"},
    "recon":       {"num": 2, "part_no": "SFS-E02-RCN", "mnemonic": "RCN", "family": "Reconciliation",             "name": "Cash & Debt Reconciliation",  "engine_dir": "cash-reconciliation"},
    "tax":         {"num": 3, "part_no": "SFS-E03-PTX", "mnemonic": "PTX", "family": "Partnership Tax",            "name": "Partnership Tax · Form 1065", "engine_dir": "partnership-1065-automation"},
    "validation":  {"num": 4, "part_no": "SFS-E04-VAL", "mnemonic": "VAL", "family": "Read-Only Validation",       "name": "Validation Engine",           "engine_dir": "audit-automation"},
    "surplus":     {"num": 5, "part_no": "SFS-E05-SRP", "mnemonic": "SRP", "family": "Cross-Border Tax",           "name": "Tax Surplus / ACB",           "engine_dir": "tax-surplus-engine"},
    "triangulate": {"num": 6, "part_no": "SFS-E06-TRI", "mnemonic": "TRI", "family": "AI Validation",              "name": "Triangulate",                 "engine_dir": "ai-validation-framework"},
    "brain":       {"num": 7, "part_no": "SFS-E07-KBN", "mnemonic": "KBN", "family": "Cited Knowledge",            "name": "Knowledge Brain",             "engine_dir": "knowledge-brain-engine"},
    "atlas":       {"num": 8, "part_no": "SFS-E08-ATL", "mnemonic": "ATL", "family": "Documentation-as-Artifact",  "name": "Finance Operations Atlas",    "engine_dir": "finance-atlas"},
    "cash":        {"num": 9, "part_no": "SFS-E09-CSH", "mnemonic": "CSH", "family": "Cash Controls",              "name": "Cash Management",             "engine_dir": "cash-management"},
    "ap":          {"num": 10, "part_no": "SFS-E10-APX", "mnemonic": "APX", "family": "Payables Controls",        "name": "Accounts Payable",            "engine_dir": "accounts-payable-automation"},
    "draw":        {"num": 11, "part_no": "SFS-E11-DRW", "mnemonic": "DRW", "family": "Draw Controls",           "name": "Project Draw",                "engine_dir": "project-draw-automation"},
    "upgrade":     {"num": 12, "part_no": "SFS-E12-BUP", "mnemonic": "BUP", "family": "Revenue Recognition",     "name": "Buyer Upgrades",              "engine_dir": "buyer-upgrade-automation"},
    "warranty":    {"num": 13, "part_no": "SFS-E13-WRC", "mnemonic": "WRC", "family": "Insurance Claims",        "name": "Warranty Reimbursement",      "engine_dir": "warranty-reimbursement-automation"},
    "intercompany":{"num": 14, "part_no": "SFS-E14-ICO", "mnemonic": "ICO", "family": "Consolidation Controls",  "name": "Intercompany Reciprocity",    "engine_dir": "intercompany-automation"},
    "proptax":     {"num": 15, "part_no": "SFS-E15-PPT", "mnemonic": "PPT", "family": "Property Tax Controls",   "name": "Property Tax",                "engine_dir": "property-tax-automation"},
    "bond":        {"num": 16, "part_no": "SFS-E16-BND", "mnemonic": "BND", "family": "Surety & Collateral",     "name": "Surety Bond & Collateral",    "engine_dir": "surety-bond-automation"},
    "insurance":   {"num": 17, "part_no": "SFS-E17-INS", "mnemonic": "INS", "family": "Insurance Allocation",    "name": "Insurance Cost Allocation",   "engine_dir": "insurance-allocation-automation"},
    "coi":         {"num": 18, "part_no": "SFS-E18-COI", "mnemonic": "COI", "family": "Insurance Compliance",    "name": "Insurance Compliance",        "engine_dir": "coi-compliance-automation"},
    "expense":     {"num": 19, "part_no": "SFS-E19-EXP", "mnemonic": "EXP", "family": "Expense Controls",        "name": "Expense & P-Card",            "engine_dir": "expense-report-automation"},
    "labor":       {"num": 20, "part_no": "SFS-E20-LAB", "mnemonic": "LAB", "family": "Labor Allocation",        "name": "Project Labor Charge",        "engine_dir": "labor-charge-automation"},
    "lien":        {"num": 21, "part_no": "SFS-E21-LWV", "mnemonic": "LWV", "family": "Lien Waivers",            "name": "Lien Waiver Tracking",        "engine_dir": "lien-waiver-automation"},
    "waterfall":   {"num": 22, "part_no": "SFS-E22-WFL", "mnemonic": "WFL", "family": "Equity Waterfall",        "name": "Equity Waterfall & JV Promote", "engine_dir": "equity-waterfall-automation"},
    "proforma":    {"num": 23, "part_no": "SFS-E23-QPR", "mnemonic": "QPR", "family": "Proforma Integrity",      "name": "Project Proforma Integrity",  "engine_dir": "proforma-integrity-automation"},
    "grt":         {"num": 24, "part_no": "SFS-E24-GRT", "mnemonic": "GRT", "family": "Gross-Receipts Tax",      "name": "Gross-Receipts & Excise Tax", "engine_dir": "gross-receipts-tax-automation"},
    "filing":      {"num": 25, "part_no": "SFS-E25-DUE", "mnemonic": "DUE", "family": "Filing Compliance",       "name": "Filing Obligation Calendar",  "engine_dir": "filing-calendar-automation"},
    "energy":      {"num": 26, "part_no": "SFS-E26-EEH", "mnemonic": "EEH", "family": "Energy Tax Credit",       "name": "Energy-Efficient Home Credit", "engine_dir": "energy-credit-automation"},
    "interest":    {"num": 27, "part_no": "SFS-E27-INT", "mnemonic": "INT", "family": "Debt Service",            "name": "Interest Accrual & Loan Amortization", "engine_dir": "interest-accrual-automation"},
    "financing":   {"num": 28, "part_no": "SFS-E28-FEX", "mnemonic": "FEX", "family": "Financing Execution",     "name": "Financing Execution & Schedule Variance", "engine_dir": "financing-execution-automation"},
    "wire":        {"num": 29, "part_no": "SFS-E29-WRL", "mnemonic": "WRL", "family": "Payment Release",         "name": "Wire & Transfer Release Control", "engine_dir": "wire-release-automation"},
    "payroll":     {"num": 30, "part_no": "SFS-E30-PBR", "mnemonic": "PBR", "family": "Payroll Controls",        "name": "Payroll & Benefit Reconciliation", "engine_dir": "payroll-benefit-automation"},
    "withholding": {"num": 31, "part_no": "SFS-E31-NRW", "mnemonic": "NRW", "family": "Cross-Border Withholding", "name": "Non-Resident Withholding & 1042-S", "engine_dir": "withholding-automation"},
    "closing":     {"num": 32, "part_no": "SFS-E32-COE", "mnemonic": "COE", "family": "Closing Controls",        "name": "Home Sale Closing & Settlement Tie-Out", "engine_dir": "closing-settlement-automation"},
    "standing":    {"num": 33, "part_no": "SFS-E33-GDS", "mnemonic": "GDS", "family": "Entity Compliance",       "name": "Entity Good-Standing", "engine_dir": "good-standing-automation"},
    "sov":         {"num": 34, "part_no": "SFS-E34-SOV", "mnemonic": "SOV", "family": "Commitment Controls",     "name": "Subcontract SOV & Change Orders", "engine_dir": "sov-commitment-automation"},
    "pickup":      {"num": 35, "part_no": "SFS-E35-EPU", "mnemonic": "EPU", "family": "Equity Method",           "name": "Equity-Method Pickup & Eliminations", "engine_dir": "equity-pickup-automation"},
    "depreciation":{"num": 36, "part_no": "SFS-E36-DEP", "mnemonic": "DEP", "family": "Asset Register",          "name": "Depreciation & Prepaid Amortization", "engine_dir": "depreciation-register-automation"},
    "deposit":     {"num": 37, "part_no": "SFS-E37-EMD", "mnemonic": "EMD", "family": "Deposit Trust",           "name": "Earnest-Money Deposit Trust", "engine_dir": "deposit-trust-automation"},
    "spending":    {"num": 38, "part_no": "SFS-E38-SRG", "mnemonic": "SRG", "family": "Capital Authorization",   "name": "Capital Spending Request Gate", "engine_dir": "spending-gate-automation"},
    "capitalize":    {"num": 39, "part_no": "SFS-E39-CAP", "mnemonic": "CAP", "family": "Cost Capitalization", "name": "Section 263A Interest Capitalization", "engine_dir": "interest-capitalization-automation"},
    "franchise":     {"num": 40, "part_no": "SFS-E40-TXF", "mnemonic": "TXF", "family": "Franchise Tax", "name": "Franchise Tax Combined Apportionment", "engine_dir": "franchise-tax-automation"},
    "sizing":        {"num": 41, "part_no": "SFS-E41-DTS", "mnemonic": "DTS", "family": "Debt Sizing", "name": "Debt Term-Sheet Sizing & Loan Terms", "engine_dir": "debt-sizing-automation"},
    "unitsales":     {"num": 42, "part_no": "SFS-E42-USM", "mnemonic": "USM", "family": "Sales Administration", "name": "Unit Sales & Commission Tie-Out", "engine_dir": "unit-sales-automation"},
    "gaalloc":       {"num": 43, "part_no": "SFS-E43-GAA", "mnemonic": "GAA", "family": "Cost Allocation", "name": "G&A Expense Allocation", "engine_dir": "ga-allocation-automation"},
    "checkage":      {"num": 44, "part_no": "SFS-E44-OCA", "mnemonic": "OCA", "family": "Disbursement Controls", "name": "Outstanding Check Aging & Escheatment", "engine_dir": "check-aging-automation"},
    "variance":      {"num": 45, "part_no": "SFS-E45-PVR", "mnemonic": "PVR", "family": "Project Reporting", "name": "Project Variance & Business-Plan Compare", "engine_dir": "project-variance-automation"},
    "contingency":   {"num": 46, "part_no": "SFS-E46-CTG", "mnemonic": "CTG", "family": "Contingency Controls", "name": "Contingency Rollforward & Adequacy", "engine_dir": "contingency-rollforward-automation"},
    "inforeturn":    {"num": 47, "part_no": "SFS-E47-IRN", "mnemonic": "IRN", "family": "Information Returns", "name": "Information Return Issuance", "engine_dir": "info-return-automation"},
    "rollforward":   {"num": 48, "part_no": "SFS-E48-TBR", "mnemonic": "TBR", "family": "Workpaper Rollforward", "name": "Trial-Balance Roll-Forward", "engine_dir": "tb-rollforward-automation"},
    "investor":      {"num": 49, "part_no": "SFS-E49-IRP", "mnemonic": "IRP", "family": "Investor Reporting", "name": "JV Investor Reporting Package", "engine_dir": "investor-reporting-automation"},
}

SPECS_DIR = ROOT / "specs"


def present_slugs() -> list[str]:
    """Slugs that actually have a committed spec JSON (so tests cover new engines
    automatically as their specs land, without failing on the ones not built yet)."""
    return sorted(p.stem for p in SPECS_DIR.glob("*.json"))


@pytest.fixture(scope="session")
def spec() -> dict:
    return ds.load_spec("triangulate")


@pytest.fixture(scope="session")
def rendered() -> str:
    return gen.render("triangulate")
