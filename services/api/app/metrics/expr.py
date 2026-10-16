"""Bộ phân tích biểu thức an toàn cho chỉ số `ratio`/`derived` khác mart (spec 03 §4.2). Không dùng `eval`.

Chỉ gồm tên chỉ số, số, `+ - * / ( )`. Chia cho 0 hoặc thiếu toán hạng trả `None`.
"""

from __future__ import annotations

import re
from decimal import Decimal, DivisionByZero, InvalidOperation

TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([a-z_][a-z0-9_]*)|([-+*/()]))")
PREC = {"+": 1, "-": 1, "*": 2, "/": 2}


def tokenize(formula: str) -> list[str]:
    out: list[str] = []
    pos = 0
    while pos < len(formula):
        if not formula[pos:].strip():
            break
        m = TOKEN.match(formula, pos)
        if not m:
            raise ValueError(f"ký tự không hợp lệ: {formula[pos : pos + 10]!r}")
        out.append(next(g for g in m.groups() if g is not None))
        pos = m.end()
    return out


def to_rpn(tokens: list[str]) -> list[str]:
    out: list[str] = []
    ops: list[str] = []
    prev = None
    for t in tokens:
        if t == "(":
            ops.append(t)
        elif t == ")":
            while ops and ops[-1] != "(":
                out.append(ops.pop())
            if not ops:
                raise ValueError("thiếu dấu (")
            ops.pop()
        elif t in PREC:
            if t == "-" and (prev is None or prev in PREC or prev == "("):
                out.append("0")  # dấu trừ một ngôi
            while ops and ops[-1] in PREC and PREC[ops[-1]] >= PREC[t]:
                out.append(ops.pop())
            ops.append(t)
        else:
            out.append(t)
        prev = t
    while ops:
        op = ops.pop()
        if op == "(":
            raise ValueError("thiếu dấu )")
        out.append(op)
    return out


def evaluate(formula: str, values: dict[str, Decimal | None]) -> Decimal | None:
    stack: list[Decimal | None] = []
    for t in to_rpn(tokenize(formula)):
        if t in PREC:
            b = stack.pop()
            a = stack.pop()
            if a is None or b is None:
                stack.append(None)
                continue
            try:
                if t == "+":
                    stack.append(a + b)
                elif t == "-":
                    stack.append(a - b)
                elif t == "*":
                    stack.append(a * b)
                else:
                    stack.append(None if b == 0 else a / b)
            except (DivisionByZero, InvalidOperation):
                stack.append(None)
        elif re.match(r"^\d", t):
            stack.append(Decimal(t))
        else:
            stack.append(values.get(t))
    return stack[0] if stack else None


def names(formula: str) -> list[str]:
    return [t for t in tokenize(formula) if re.match(r"^[a-z_]", t)]
