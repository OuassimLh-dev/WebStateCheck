"""Metadata/protocol tests only: NOT execution of third-party upstream code."""
from pathlib import Path
from webstatecheck import day5_realworld as d5


def test_pinned_commits_differ():
    assert d5.REVISIONS == {'before': 'ec4de30', 'after': 'b56bf28'}


def test_upstream_reproduction_script_is_present():
    assert (d5.CASE / 'probe.cjs').exists()


def test_does_not_bundle_mock_implementation():
    text = (d5.CASE / 'probe.cjs').read_text()
    assert 'require(path.resolve(artifact))' in text
    assert 'new Promise(resolve => queue.push' in text


def test_no_claim_of_generalized_detection():
    source = Path(d5.__file__).read_text()
    assert 'not autonomous discovery' in source.lower()
