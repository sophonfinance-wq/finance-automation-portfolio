"""A deliberately tiny, safe arithmetic formula evaluator.

Workpaper formulas look like ``"=B2+B3-B4"`` -- references to other cells
joined by ``+``, ``-``, ``*`` and ``/`` with optional parentheses and numeric
literals. We do NOT use :func:`eval`. Instead we tokenise and run a small
shunting-yard evaluator, so a malicious or malformed formula can never execute
arbitrary code. This is what lets the deterministic audit re-derive every
cell's expected value safely.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Mapping

_TOKEN_RE = re.compile(
    r"""
    \s*(
        (?P<number>\d+(?:\.\d+)?)   |
        (?P<ref>[A-Z]+\d+)          |
        (?P<op>[+\-*/()])
    )
    """,
    re.VERBOSE,
)

_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}
_OPS: Dict[str, Callable[[float, float], float]] = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
}


class FormulaError(ValueError):
    """Raised when a formula is malformed or references a missing cell."""


def _tokenize(expr: str) -> List[str]:
    tokens: List[str] = []
    pos = 0
    while pos < len(expr):
        if expr[pos].isspace():
            pos += 1
            continue
        match = _TOKEN_RE.match(expr, pos)
        if not match or match.start() == match.end():
            raise FormulaError(f"Unexpected character at {pos}: {expr[pos:]!r}")
        token = match.group().strip()
        tokens.append(token)
        pos = match.end()
    return tokens


def evaluate(formula: str, values: Mapping[str, float]) -> float:
    """Evaluate ``formula`` against a mapping of cell ref -> numeric value.

    Args:
        formula: e.g. ``"=B2+B3"`` (leading ``=`` optional).
        values: mapping of cell references to their numeric values.

    Returns:
        The numeric result.

    Raises:
        FormulaError: if the formula is malformed or references a missing cell.
    """
    expr = formula.strip()
    if expr.startswith("="):
        expr = expr[1:]
    tokens = _tokenize(expr)

    output: List[float] = []
    ops: List[str] = []

    def apply_op() -> None:
        op = ops.pop()
        try:
            right = output.pop()
            left = output.pop()
        except IndexError as exc:
            raise FormulaError(f"Malformed formula: {formula!r}") from exc
        output.append(_OPS[op](left, right))

    for token in tokens:
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            output.append(float(token))
        elif re.fullmatch(r"[A-Z]+\d+", token):
            if token not in values or values[token] is None:
                raise FormulaError(f"Formula references missing cell {token!r}")
            output.append(float(values[token]))
        elif token in _PRECEDENCE:
            while (
                ops
                and ops[-1] in _PRECEDENCE
                and _PRECEDENCE[ops[-1]] >= _PRECEDENCE[token]
            ):
                apply_op()
            ops.append(token)
        elif token == "(":
            ops.append(token)
        elif token == ")":
            while ops and ops[-1] != "(":
                apply_op()
            if not ops:
                raise FormulaError(f"Unbalanced parentheses: {formula!r}")
            ops.pop()  # discard the '('
        else:  # pragma: no cover - defensive
            raise FormulaError(f"Unexpected token {token!r}")

    while ops:
        if ops[-1] in "()":
            raise FormulaError(f"Unbalanced parentheses: {formula!r}")
        apply_op()

    if len(output) != 1:
        raise FormulaError(f"Malformed formula: {formula!r}")
    return output[0]
