"""What the user actually signs. Not the YAML, and not their own prose."""
from pathlib import Path

from mandate.money import Paise, fmt
from mandate.policy.loader import dump
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Policy

FLAG = "  (I inferred this, is it right?)"
# A rule the law imposes is not the user's to confirm or decline, so it is
# labelled rather than questioned. Asking "is this right?" about a statutory
# floor invites an answer the gateway would have to refuse.
LAW = "  (required by law)"


def _line(cid: C, spec) -> str:
    match cid:
        case C.BUDGET_TOTAL:
            return f"Spend at most {fmt(Paise(spec['max']))} in total"
        case C.BUDGET_PER_TRANSACTION:
            return f"At most {fmt(Paise(spec['max']))} in any single order"
        case C.BUDGET_PER_ITEM:
            return f"At most {fmt(Paise(spec['max']))} on any one item"
        case C.MERCHANT_ALLOW:
            return f"Buy only from: {', '.join(spec)}"
        case C.CATEGORY_DENY:
            return f"Never buy: {', '.join(spec)}"
        case C.ITEM_DENY_RECENT:
            return f"Nothing you already bought in the last {spec['window_days']} days"
        case C.VELOCITY:
            n = spec["max_actions"]
            return f"At most {n} order{'s' if n != 1 else ''} in total"
        case C.TIME_WINDOW:
            return "Only while this permission is active"
        case C.QUANTITY_MAX_PER_ITEM:
            return f"At most {spec['max']} units of any one item"
        case C.AFA_REQUIRED:
            return (f"Ask you to approve anything over {fmt(Paise(spec['threshold']))} "
                    "before it is paid")
    return f"{cid}: {spec}"


def render(p: Policy) -> str:
    lines = [f'You said: "{p.source_text}"', "", "Here is what I understood:", ""]
    for cid in sorted(p.constraints, key=str):
        if cid in p.provenance.regulatory:
            suffix = LAW
        elif cid in p.provenance.inferred:
            suffix = FLAG
        else:
            suffix = ""
        lines.append(f"  - {_line(cid, p.constraints[cid])}{suffix}")
    lines += ["", f"  This permission ends at {p.expires.strftime('%H:%M on %d %b %Y')}.",
              "", "Sign this and the agent can act inside these limits, and nowhere else."]
    return "\n".join(lines)


def sign(p: Policy, path: Path) -> Path:
    dump(p, path)
    return path
