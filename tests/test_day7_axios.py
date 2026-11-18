"""Offline tests of Day 7 adapter, rule evaluation and source pinning."""
import json
import pytest
from webstatecheck.day7_axios import REVISIONS, RULES, SCENARIOS, source_url, axios_facts, assess_probe


def rules():
    return json.loads(RULES.read_text())['rules']


def test_commits_are_full_and_distinct():
    assert len(set(REVISIONS.values()))==2
    assert all(len(s)==40 for s in REVISIONS.values())
    assert all('https://raw.githubusercontent.com/axios/axios/' in source_url(s) for s in REVISIONS.values())


def test_source_url_rejects_unpinned_revisions():
    with pytest.raises(ValueError): source_url('main')


def test_adapter_ignores_label_and_commit():
    base={'cancellation_requested':True,'all_listeners_notified':False,'unexpected_exception':True}
    a=axios_facts({**base,'label':'before','upstream_commit':'1'*40})
    b=axios_facts({**base,'label':'after','upstream_commit':'2'*40})
    assert a==b


def test_failed_notification_is_violation():
    record={'cancellation_requested':True,'all_listeners_notified':False,'unexpected_exception':True}
    assert assess_probe(record,rules())['verdict']=='violation'


def test_complete_notification_is_clear():
    record={'cancellation_requested':True,'all_listeners_notified':True,'unexpected_exception':False}
    assert assess_probe(record,rules())['verdict']=='clear'


def test_missing_evidence_is_inconclusive():
    record={'cancellation_requested':True,'all_listeners_notified':None,'unexpected_exception':None}
    assert assess_probe(record,rules())['verdict']=='inconclusive'


def test_no_cancel_is_not_covered():
    record={'cancellation_requested':False,'all_listeners_notified':False,'unexpected_exception':True}
    assert assess_probe(record,rules())['verdict']=='not_covered'


def test_scenarios_are_distinct():
    assert len(SCENARIOS)==2
