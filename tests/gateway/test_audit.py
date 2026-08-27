import json
from datetime import datetime, timedelta, timezone

import pytest

from mandate.gateway.action import Action, ActionType
from mandate.gateway.audit import AuditChainBroken, AuditLog, replay_verdict
from mandate.gateway.state import ClauseResult, Verdict
from mandate.money import rupees

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=IST)


def _act(amount=None):
    if amount is None:
        amount = rupees(100)
    return Action(type=ActionType.CREATE_ORDER, amount=amount, merchant="zepto", items=[])

def _append(log, verdict=Verdict.ALLOW, amount=None):
    if amount is None:
        amount = rupees(100)
    return log.append(ts=NOW, mandate_id="mnd_1", policy_hash="sha256:aa",
                      idem_key="idm_1", action=_act(amount), verdict=verdict,
                      clauses=[ClauseResult(id="budget.total", result=verdict)],
                      downstream=None)

def test_sequence_numbers_increment(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    assert [_append(log).seq, _append(log).seq] == [1, 2]

def test_chain_links_each_record_to_the_previous(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    a, b = _append(log), _append(log)
    assert b.prev_hash == a.record_hash

def test_verify_chain_passes_on_an_untouched_log(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    _append(log); _append(log); _append(log)
    log.verify_chain()

def test_editing_a_record_breaks_the_chain(tmp_path):
    p = tmp_path / "a.jsonl"
    log = AuditLog(p)
    _append(log); _append(log)
    lines = p.read_text().splitlines()
    d = json.loads(lines[0]); d["verdict"] = "ALLOW"; d["action"]["amount"] = 999999
    lines[0] = json.dumps(d); p.write_text("\n".join(lines) + "\n")
    with pytest.raises(AuditChainBroken):
        AuditLog(p).verify_chain()

def test_deleting_a_record_breaks_the_chain(tmp_path):
    p = tmp_path / "a.jsonl"
    log = AuditLog(p)
    _append(log); _append(log); _append(log)
    lines = p.read_text().splitlines()
    p.write_text("\n".join([lines[0], lines[2]]) + "\n")
    with pytest.raises(AuditChainBroken):
        AuditLog(p).verify_chain()

def test_verdict_replays_from_stored_clauses_without_re_running(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    rec = log.append(ts=NOW, mandate_id="m", policy_hash="sha256:aa", idem_key="i",
                     action=_act(), verdict=Verdict.DENY,
                     clauses=[ClauseResult(id="budget.total", result=Verdict.ALLOW),
                              ClauseResult(id="velocity", result=Verdict.DENY)],
                     downstream=None)
    assert replay_verdict(rec) is Verdict.DENY
