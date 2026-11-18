"""Offline tests; browser execution must be run on user's machine."""
import json
import pytest
from webstatecheck.day9_plans import prepare, validate_plan, get_path, PLAN_COUNT, ACTIONS_PER_PLAN


def test_prepare_and_validate_equal_budgets(tmp_path):
    prepare(root=tmp_path, seed=11)
    for name in ("random", "heuristic"):
        p=json.loads(get_path(name, tmp_path).read_text())
        assert validate_plan(p, name)["actions"] == PLAN_COUNT * ACTIONS_PER_PLAN


def test_prepare_refuses_overwrite(tmp_path):
    prepare(root=tmp_path)
    with pytest.raises(FileExistsError):
        prepare(root=tmp_path)


def valid_payload():
    return {"target_id":"local-search-development-only", "method":"llm",
            "generator":{"name":"human recorded model run", "recorded_utc":"2026-11-18T00:00:00Z", "model":"example model", "prompt_sha256":"sample"},
            "plans":[{"plan_id":f"p{i}", "queries":["old","new"]} for i in range(4)]}


def test_llm_requires_provenance():
    p=valid_payload(); assert validate_plan(p, "llm")["scenarios"] == 4
    p["generator"].pop("model")
    with pytest.raises(ValueError, match="model"):
        validate_plan(p, "llm")


def test_no_self_reported_verdicts():
    p=valid_payload(); p["plans"][0]["expected_bug"]="yes"
    with pytest.raises(ValueError, match="ONLY"):
        validate_plan(p)


def test_rejects_extra_or_unsupported_actions():
    p=valid_payload(); p["plans"][1]["queries"]=["delete everything","fail"]
    with pytest.raises(ValueError):
        validate_plan(p)


def test_rejects_wrong_budget():
    p=valid_payload(); p["plans"][0]["queries"]=["old"]
    with pytest.raises(ValueError, match="exactly"):
        validate_plan(p)


def test_rejects_duplicate_plan_ids():
    p=valid_payload(); p["plans"][1]["plan_id"]="p0"
    with pytest.raises(ValueError, match="Duplicate"):
        validate_plan(p)


def test_rejects_wrong_target():
    p=valid_payload(); p["target_id"]="real-website"
    with pytest.raises(ValueError, match="target_id"):
        validate_plan(p)


def test_seeds_are_reproducible(tmp_path):
    prepare(root=tmp_path, seed=4)
    first=json.loads(get_path("random", tmp_path).read_text())["plans"]
    prepare(root=tmp_path, seed=4, force=True)
    second=json.loads(get_path("random", tmp_path).read_text())["plans"]
    assert first==second


def test_different_method_rejected():
    with pytest.raises(ValueError, match="method"):
        validate_plan(valid_payload(), "random")
