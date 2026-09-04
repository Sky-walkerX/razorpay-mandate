"""Build the web console's payload from measured artefacts.

The console used to hold its own literals: a max quantity of 4 against a signed
policy that says 5, a policy hash matching no document, and a banner apologising
that the sweep had not been run. This module is the single path from the files
that were actually produced to the screen a judge reads, so those cannot drift
again. `tests/harness/test_evidence.py` compares every bound against the policy.

Nothing here computes a score. Scores come from `score()` and are read.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mandate.policy import rails, regulatory
from mandate.policy.canonical import policy_hash
from mandate.policy.labels import PART_LABELS
from mandate.policy.loader import load as load_policy

VERDICT = {"ALLOW": "allow", "DENY": "deny", "UNKNOWN": "unknown"}

# The feed replays one run end to end rather than a selection across runs, so
# there is no cherry-picking step to argue with. This is the longest enforced
# budget.salami run: the agent proposes 53 times and is refused 50.
DEFAULT_FEED_RUN = "enforce/budget_salami_005"


def _rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"


def _bound(key: str, spec: dict | list | None) -> str:
    """The bound as a person reads it, derived from the signed value."""
    if spec is None:
        return "Not set"
    if key == "velocity":
        # `window: mandate` is the policy's word for "over the whole mandate",
        # and printing it made the chip read "3 per mandate" on a page whose
        # whole job is to avoid saying "mandate" at a stranger.
        window = spec.get("window", "mandate")
        if window == "mandate":
            return f"{spec['max_actions']} orders"
        return f"{spec['max_actions']} per {window}"
    if key == "quantity.max_per_item":
        return f"{spec['max']} per item"
    if key.startswith("budget."):
        return _rupees(int(spec["max"]))
    if isinstance(spec, list):
        return ", ".join(s.title() for s in spec) if spec else "Not set"
    return "Set"


def _parts(pol) -> list[dict[str, Any]]:
    stated = {str(c) for c in pol.provenance.stated}
    inferred = {str(c) for c in pol.provenance.inferred}
    regulatory = {str(c) for c in pol.provenance.regulatory}
    out = []
    for n, meta in enumerate(PART_LABELS, start=1):
        key = meta["key"]
        spec = pol.constraints.get(key)
        source = ("stated" if key in stated else "inferred" if key in inferred
                  else "regulatory" if key in regulatory else "unset")
        part: dict[str, Any] = {**meta, "n": n, "source": source}
        if key == "time.window":
            part["bound"] = pol.expires.strftime("%-d %b %Y")
        else:
            part["bound"] = _bound(key, spec)
        # The raw signed value travels beside the reading of it, so a test can
        # compare the two without parsing prose.
        if isinstance(spec, dict) and "max" in spec:
            part["max"] = int(spec["max"])
        if isinstance(spec, list):
            part["values"] = list(spec)
        if key == "velocity" and spec:
            part["max"] = int(spec["max_actions"])
        out.append(part)
    return out


def _arm_scores(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text().replace("NaN", "null"))
    return raw


def _containment(scores: dict) -> dict[str, Any]:
    out = {}
    for arm, s in scores.items():
        n = s["n_attacks"]
        if not n:
            continue
        pct = s["containment"]
        out[arm] = {
            "total": n,
            "contained": round(pct * n),
            "pct": pct,
            "ci": [s["containment_ci"]["lo"], s["containment_ci"]["hi"]],
            "per_family": s.get("per_family", {}),
        }
    return out


def _false_block(scores: dict) -> dict[str, Any]:
    out = {}
    for arm, s in scores.items():
        n = s["n_legit"]
        if not n:
            continue
        rate = s["false_block"]
        out[arm] = {
            "total": n,
            "blocked": round(rate * n),
            "executed": n - round(rate * n),
            "pct": rate,
        }
    return out


def _feed(audit_path: Path, run_label: str) -> dict[str, Any]:
    recs = [json.loads(l) for l in audit_path.read_text().splitlines() if l.strip()]
    decisions = []
    for r in recs:
        act = r["action"]
        items = act.get("items") or []
        blocking = next(
            (c for c in r.get("clauses", []) if c["result"] != "ALLOW"), None
        )
        n = len(items)
        decisions.append({
            "seq": r["seq"],
            "verdict": VERDICT[r["verdict"]],
            "items": f"{n} item" if n == 1 else f"{n} items",
            "reason": _reason(blocking),
            "amountPaise": int(act["amount"]),
            "seller": act["merchant"],
            "note": items[0]["title"] if items else "",
            "hash": r["record_hash"],
            "executed": r.get("downstream") is not None,
        })
    counts = {
        "evaluated": len(decisions),
        "allowed": sum(1 for d in decisions if d["verdict"] == "allow"),
        "refused": sum(1 for d in decisions if d["verdict"] == "deny"),
        "escalated": sum(1 for d in decisions if d["verdict"] == "unknown"),
    }
    return {"run": run_label, "counts": counts, "decisions": decisions}


def _reason(clause: dict | None) -> str:
    if clause is None:
        return ""
    n = next((i for i, m in enumerate(PART_LABELS, 1) if m["key"] == clause["id"]), 0)
    label = next((m["label"] for m in PART_LABELS if m["key"] == clause["id"]), clause["id"])
    limit = clause.get("limit")
    if limit is None:
        return f"Part {n} · {label}"
    if clause["id"].startswith("budget."):
        return f"Part {n} · {label}, {_rupees(int(limit))}"
    return f"Part {n} · {label}, {limit}"


def _alignment(pol, pol_hash: str) -> dict[str, Any]:
    """The rails projection and the regulatory posture, both computed.

    Neither half is typed into the console. `rails.diff` decides what survives AP2
    and Reserve Pay, `regulatory.posture` decides what the RBI framework asks of a
    gateway, and this only reshapes them for the screen. The two are kept apart in
    the payload because they answer opposite questions; see the docstring on
    `mandate.policy.regulatory`.
    """
    d = rails.diff(pol, policy_hash=pol_hash)
    reg = regulatory.posture(pol)
    labels = {m["key"]: m["label"] for m in PART_LABELS}
    return {
        "rails": {
            "total_clauses": d.total_clauses,
            "ap2_held": d.ap2_held,
            "ap2_lost": d.ap2_lost,
            "reserve_pay_held": d.reserve_pay_held,
            "reserve_pay_lost": d.reserve_pay_lost,
            "fates": [
                {**f.model_dump(), "label": labels.get(f.clause, f.clause)}
                for f in d.fates
            ],
        },
        "ap2_export": {
            "intent_mandate": rails.to_ap2_intent_mandate(pol),
            "payment_constraints": rails.to_ap2_payment_constraints(pol),
            "endpoint": "/v1/mandate/ap2",
            "cli": "mandate ap2-export",
        },
        "reserve_pay": rails.to_reserve_pay(pol),
        "regulatory": reg.model_dump(),
    }


def build_evidence(
    root: Path,
    containment_dir: str = "results-heldout-g37-hardened",
    false_block_dir: str = "results-falseblock-hardened",
    conformance: str = "results-conformance/conformance_results.json",
    feed_run: str = DEFAULT_FEED_RUN,
) -> dict[str, Any]:
    root = Path(root)
    pol = load_policy(root / "policies" / "policy.yaml")
    cont = _arm_scores(root / containment_dir / "scores.json")
    fb = _arm_scores(root / false_block_dir / "scores.json")
    conf = json.loads((root / conformance).read_text())

    def _run_id(d: str) -> str:
        rows = (root / d / "results.jsonl").read_text().splitlines()
        return json.loads(rows[0])["run_id"]

    def _model(d: str) -> str:
        rows = (root / d / "results.jsonl").read_text().splitlines()
        return json.loads(rows[0])["model"]

    return {
        "source": {
            "model": _model(containment_dir),
            "containment_run": _run_id(containment_dir),
            "containment_dir": containment_dir,
            "false_block_run": _run_id(false_block_dir),
            "false_block_dir": false_block_dir,
            "conformance_file": conformance,
            "feed_file": f"{containment_dir}/{feed_run}/audit.jsonl",
            "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "policy": {
            "mandate_id": pol.mandate_id,
            "principal": pol.principal,
            "agent": pol.agent,
            "policy_hash": policy_hash(pol),
            "issued": pol.issued.isoformat(),
            "expires": pol.expires.isoformat(),
            "signed_on": pol.issued.strftime("%-d %B %Y"),
            "source_text": pol.source_text,
            "parts": _parts(pol),
        },
        "scoreboard": {
            "containment": _containment(cont),
            "false_block": _false_block(fb),
            "conformance": {
                "total": conf["total"],
                "blocked": conf["blocked"],
                "escaped": conf["escaped"],
                "vacuous": conf["vacuous"],
                "race_trials": conf["race_trials"],
            },
        },
        "alignment": _alignment(pol, policy_hash(pol)),
        "feed": _feed(root / containment_dir / feed_run / "audit.jsonl", feed_run),
    }
