"""Cash & Debt Reconciliation Engine.

A self-contained, deterministic reconciliation engine for a fintech automation
portfolio. It generates fully synthetic (fictional) GL, bank, and lender data,
reconciles cash and debt **by account number**, applies a materiality threshold,
classifies each line as clean / timing / FLAG, and emits a 5-section evidence log
as Markdown and .xlsx.

All data is invented. No real entities, people, banks, figures, or paths.
"""

from __future__ import annotations

__all__ = [
    "__version__",
    "MATERIALITY_THRESHOLD",
    "PERIOD_LABEL",
]

__version__ = "1.0.0"

# Default materiality threshold (in dollars). Variances at or below this absolute
# value are treated as immaterial noise; larger variances are escalated.
MATERIALITY_THRESHOLD: float = 50.0

# Reporting period label used across outputs (fictional).
PERIOD_LABEL: str = "March 2026"
