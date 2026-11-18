import json
import pytest
from pathlib import Path
from webstatecheck.day10_compare import render_md, summarize
from webstatecheck.day9_plans import prepare, get_path, canonical_json
import hashlib


def test_comparison_requires_every_result(tmp_path):
    prepare(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        summarize(tmp_path)


def test_render_marked_development_only():
    text=render_md({"rows": []})
    assert "Development-only" in text and "NOT a clean independent model session" in text


def test_comparison_with_3_equal_budget_reports(tmp_path):
    prepare(root=tmp_path)
    out=tmp_path/"research"/"day9_candidates"
    payload={"target_id":"local-search-development-only", "method":"llm",
             "generator":{"name":"GPT-6 ChatGPT context-contaminated", "model":"GPT-6",
                          "recorded_utc":"2026-11-18T00:00:00Z", "prompt_sha256":"demo"},
             "plans":[{"plan_id":f"llm-{i}","queries":["old","new"]} for i in range(4)]}
    get_path("llm", tmp_path).write_bytes(canonical_json(payload))
    (tmp_path/"results").mkdir()
    for method in ("random", "heuristic", "llm"):
        observations=[]
        for mode in ("buggy", "fixed"):
            for i in range(4):
                observations.append({"mode_for_analysis_only":mode, "verdict":"violation" if mode=="buggy" and i==0 else "clear", "issues":["fake"] if mode=="buggy" and i==0 else [], "elapsed_ms":100})
        sha=hashlib.sha256(get_path(method,tmp_path).read_bytes()).hexdigest()
        result={"method":method,"plan_sha256":sha,"scenarios_per_version":4,"actions_per_version":8,"observations":observations}
        (tmp_path/"results"/f"day9_{method}_observations.json").write_text(json.dumps(result))
    result=summarize(tmp_path)
    assert len(result["rows"]) == 6
    assert [v["violations"] for v in result["rows"]] == [1,0,1,0,1,0]


def test_comparison_rejects_plan_hash_change(tmp_path):
    prepare(root=tmp_path)
    (tmp_path/"results").mkdir()
    (tmp_path/"results"/"day9_random_observations.json").write_text(json.dumps({"method":"random","plan_sha256":"bad"}))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        summarize(tmp_path)
