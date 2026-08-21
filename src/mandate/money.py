"""Money is integer paise, everywhere. No floats reach the evaluator."""
from decimal import Decimal, InvalidOperation
from typing import NewType

Paise = NewType("Paise", int)


def rupees(x: str | int | float) -> Paise:
    """Convert a rupee amount to paise. Rejects precision finer than one paise."""
    try:
        d = Decimal(str(x))
    except InvalidOperation as e:
        raise ValueError(f"not a rupee amount: {x!r}") from e
    scaled = d * 100
    if scaled != scaled.to_integral_value():
        raise ValueError(f"sub-paise precision not representable: {x!r}")
    return Paise(int(scaled))


def fmt(p: Paise) -> str:
    """Render paise as rupees with Indian digit grouping."""
    sign = "-" if p < 0 else ""
    whole, frac = divmod(abs(int(p)), 100)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{sign}₹{s}.{frac:02d}"
