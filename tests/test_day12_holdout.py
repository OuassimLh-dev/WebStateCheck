import json
import hashlib
from pathlib import Path

import pytest

from webstatecheck.day11_audit import FROZEN
from webstatecheck.day12_holdout import (
    assert_day11_lock, safe_id, scaffold, valid_public, valid_private, seal,
    verify, validate_plan, preflight, canonical_json,
)


def make_root(root: Path):
    files = {}
    for rel in FROZEN:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("frozen-contents-" + rel, encoding="utf-8")
        files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    (root / "research/day11_future_protocol_lock.json").write_text(
        canonical_json({"file_sha256": files}), encoding="utf-8")
    return root


def filled_target(root: Path, target_id="t01"):
    pub, priv = scaffold(root, target_id)
    public = json.loads(pub.read_text())
    public.update(interface_description="A task board lets users add a task, then open its details.",
                  allowed_actions=[{"type":"input","target":"task-title","values":["alpha","beta"]},
                                   {"type":"click","target":"submit-button"}],
                  observable_contracts=[{"name":"task-created","description":"A submitted title appears in the task list."}],
                  reset_strategy="Reset test database to its empty state before each scenario.")
    private = json.loads(priv.read_text())
    private.update(project_url="https://github.com/acme/example-project",
                   before_commit="a"*40, after_commit="b"*40,
                   issue_url="https://github.com/acme/example-project/issues/123",
                   bug_description="A known failure occurs after a certain request order.",
                   license="MIT upstream license", environment_notes="Run against a local isolated instance")
    pub.write_text(canonical_json(public))
    priv.write_text(canonical_json(private))
    return pub, priv


def make_plan(root: Path, target_id="t01", method="random"):
    plan = {"target_id":target_id,"method":method,
            "generator":{"name":"test","recorded_utc":"2026-11-18T00:00:00Z"},
            "plans":[{"plan_id":f"p-{i}","actions":[
                {"type":"input","target":"task-title","value":"alpha"},
                {"type":"click","target":"submit-button"}]} for i in range(4)]}
    if method == "llm":
        plan["generator"].update(model="example-model",prompt_sha256="c"*64,raw_response_sha256="d"*64)
    file = root / "research" / "generated_plan.json"
    file.write_text(canonical_json(plan))
    return file


def test_safe_ids():
    assert safe_id("target-02") == "target-02"
    for bad in ("T01", "../outside", "x", "a b", "_abc", "test/3"):
        with pytest.raises(ValueError): safe_id(bad)


def test_lock_check_and_drift(tmp_path):
    root = make_root(tmp_path)
    assert len(assert_day11_lock(root)) == 64
    (root / FROZEN[0]).write_text("drift")
    with pytest.raises(ValueError, match="changed"): assert_day11_lock(root)


def test_scaffold_is_explicitly_incomplete(tmp_path):
    root = make_root(tmp_path)
    pub, priv = scaffold(root, "t01")
    with pytest.raises(ValueError, match="Complete public"): valid_public(json.loads(pub.read_text()), "t01")
    with pytest.raises(ValueError, match="40-character"): valid_private(json.loads(priv.read_text()), "t01")
    with pytest.raises(FileExistsError): scaffold(root, "t01")


def test_seal_makes_nonleaking_generator_packet(tmp_path):
    root = make_root(tmp_path)
    filled_target(root)
    manifest = seal(root, "t01")
    assert len(manifest["file_sha256"]) == 3
    packet = (root / "research/holdout_sealed/t01/generator_packet.json").read_text()
    assert "A task board" in packet
    assert "issue_url" not in packet and "before_commit" not in packet
    assert "123" not in packet and "known failure" not in packet
    assert "github.com" not in packet
    assert verify(root, "t01")["target_id"] == "t01"
    with pytest.raises(FileExistsError): seal(root, "t01")


def test_seal_detects_bad_budget(tmp_path):
    root = make_root(tmp_path)
    pub, _ = filled_target(root)
    public = json.loads(pub.read_text())
    public["scenarios_per_method"] = 100
    pub.write_text(canonical_json(public))
    with pytest.raises(ValueError, match="Frozen nominal budget"): seal(root, "t01")


def test_public_spec_rejects_hidden_issue_leak(tmp_path):
    root = make_root(tmp_path)
    pub, _ = filled_target(root)
    public = json.loads(pub.read_text())
    public["interface_description"] += " This describes the fix commit."
    with pytest.raises(ValueError, match="leakage"): valid_public(public, "t01")


def test_seal_rejects_bad_private_commits(tmp_path):
    root = make_root(tmp_path)
    _, priv = filled_target(root)
    private = json.loads(priv.read_text())
    private["before_commit"] = "a"*8
    with pytest.raises(ValueError, match="40-character"): valid_private(private, "t01")


def test_detects_post_seal_tampering(tmp_path):
    root = make_root(tmp_path)
    filled_target(root)
    seal(root, "t01")
    dest = root / "research/holdout_sealed/t01/public_spec.json"
    dest.write_text(dest.read_text() + " ")
    with pytest.raises(ValueError, match="changed"): verify(root, "t01")


def test_plan_validates_budget_and_interface(tmp_path):
    root = make_root(tmp_path)
    filled_target(root)
    seal(root, "t01")
    p = make_plan(root)
    result = validate_plan(root, "t01", p, "random")
    assert (result["scenarios"],result["actions"]) == (4,8)
    data = json.loads(p.read_text())
    data["plans"][0]["actions"][0]["value"] = "prohibited"
    p.write_text(canonical_json(data))
    with pytest.raises(ValueError, match="unsupported input"): validate_plan(root, "t01", p, "random")


def test_llm_provenance_required(tmp_path):
    root = make_root(tmp_path)
    filled_target(root)
    seal(root, "t01")
    p = make_plan(root, method="llm")
    assert validate_plan(root, "t01", p, "llm")["method"] == "llm"
    data = json.loads(p.read_text()); del data["generator"]["raw_response_sha256"]
    p.write_text(canonical_json(data))
    with pytest.raises(ValueError, match="require model"): validate_plan(root, "t01", p, "llm")


def test_preflight_writes_only_reports(tmp_path):
    root = make_root(tmp_path)
    info = preflight(root)
    assert "PREFLIGHT ONLY" in info["status"]
    assert (root / "results/day12_preflight.md").is_file()
    assert not (root / "research/holdout_sealed").exists()
