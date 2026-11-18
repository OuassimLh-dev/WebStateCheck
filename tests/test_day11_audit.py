import json
from pathlib import Path

import pytest

from webstatecheck.day11_audit import audit, digest, freeze, report_md, verify, FROZEN
from webstatecheck.day9_plans import canonical_json


def create_fixture(root: Path):
    for d in ("research/day9_candidates", "results"):
        (root / d).mkdir(parents=True, exist_ok=True)
    for method in ("random", "heuristic", "llm"):
        payload = {"target_id":"local-search-development-only", "method": method,
                   "generator": {"name":"test", "recorded_utc":"2026-11-18T00:00:00Z"},
                   "plans": [{"plan_id": f"{method}-{i}", "queries": ["alpha", "beta"]} for i in range(4)]}
        if method == "llm":
            payload["generator"].update(model="test-model", prompt_sha256="test-digest")
        path = root / "research" / "day9_candidates" / f"{method}.json"
        path.write_bytes(canonical_json(payload))
        observations = []
        for mode in ("buggy", "fixed"):
            for p in payload["plans"]:
                observations.append({"mode_for_analysis_only":mode, "plan_id":p["plan_id"],
                                     "queries":p["queries"], "verdict":"clear", "issues":[],
                                     "ui_state":{"results":"Results for: beta", "loading":"", "error":""}})
        out = {"method":method, "plan_sha256":digest(path),
               "scenarios_per_version":4, "actions_per_version":8, "observations":observations}
        (root / "results" / f"day9_{method}_observations.json").write_text(json.dumps(out))


def test_clean_audit(tmp_path):
    create_fixture(tmp_path)
    result = audit(tmp_path)
    assert result["observation_count"] == 24
    assert all(v["buggy_violations"] == 0 for v in result["methods"].values())
    assert "NOT a new experiment" in report_md(result)


def test_detects_tampered_plan_hash(tmp_path):
    create_fixture(tmp_path)
    p = tmp_path / "research/day9_candidates/random.json"
    p.write_text(p.read_text() + " ")
    with pytest.raises(ValueError, match="hash mismatch"):
        audit(tmp_path)


def test_detects_tampered_oracle_verdict(tmp_path):
    create_fixture(tmp_path)
    p = tmp_path / "results/day9_llm_observations.json"
    v = json.loads(p.read_text())
    v["observations"][0]["verdict"] = "violation"
    p.write_text(json.dumps(v))
    with pytest.raises(ValueError, match="Oracle mismatch"):
        audit(tmp_path)


def test_detects_repeated_plan_id(tmp_path):
    create_fixture(tmp_path)
    p = tmp_path / "results/day9_random_observations.json"
    v = json.loads(p.read_text())
    v["observations"][1]["plan_id"] = v["observations"][0]["plan_id"]
    p.write_text(json.dumps(v))
    with pytest.raises(ValueError, match="IDs"):
        audit(tmp_path)


def test_freeze_and_verify_no_overwrite(tmp_path):
    create_fixture(tmp_path)
    for rel in FROZEN:
        p = tmp_path / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("test")
    info = freeze(tmp_path, timestamp="2026-11-18T00:00:00Z")
    assert len(info["file_sha256"]) == len(FROZEN)
    assert verify(tmp_path) == []
    with pytest.raises(FileExistsError):
        freeze(tmp_path)
    (tmp_path / FROZEN[0]).write_text("tampered")
    assert verify(tmp_path) == [FROZEN[0]]
