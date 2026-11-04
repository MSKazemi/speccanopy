"""Fixture proposer tests: deterministic, style-neutral and contract-checked."""

import json
from pathlib import Path

import pytest

from speccanopy.models import Component, SystemBrief
from speccanopy.proposer import ComponentProposal, ComponentProposer, FixtureComponentProposer

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "cli-utility.json"


def test_fixture_proposer_is_deterministic_and_does_not_modify_parent() -> None:
    brief = SystemBrief.model_validate(json.loads(EXAMPLE.read_text()))
    root = Component(id="system", name="CLI", responsibility="Orchestrate", boundary="Local process")
    proposal = ComponentProposal(id="input", name="Reader", responsibility="Read files",
                                 boundary="Filesystem", requirement_ids=["FR-001"], rationale="Input boundary")
    proposer = FixtureComponentProposer({"system": [proposal]})
    assert isinstance(proposer, ComponentProposer)
    first = proposer.propose(root, brief)
    second = proposer.propose(root, brief)
    assert first == second == [proposal]
    first[0].name = "Changed"
    assert proposer.propose(root, brief)[0].name == "Reader"
    assert root.status == "proposed"
    assert proposer.propose(Component(id="output", name="Output", responsibility="Write", boundary="Filesystem"), brief) == []


def test_proposer_rejects_unknown_requirements() -> None:
    brief = SystemBrief.model_validate(json.loads(EXAMPLE.read_text()))
    root = Component(id="system", name="CLI", responsibility="Orchestrate", boundary="Local process")
    proposal = ComponentProposal(id="reader", name="Reader", responsibility="Read", boundary="Filesystem",
                                 requirement_ids=["FR-999"], rationale="Input")
    with pytest.raises(ValueError, match="unknown requirements"):
        FixtureComponentProposer({"system": [proposal]}).propose(root, brief)


def test_proposer_rejects_duplicate_ids_across_parents() -> None:
    proposal = ComponentProposal(id="reused", name="Module", responsibility="Work", boundary="Internal",
                                 rationale="Necessary")
    with pytest.raises(ValueError, match="unique component IDs"):
        FixtureComponentProposer({"a": [proposal], "b": [proposal]})


def test_proposer_rejects_self_child() -> None:
    brief = SystemBrief.model_validate(json.loads(EXAMPLE.read_text()))
    root = Component(id="system", name="CLI", responsibility="Orchestrate", boundary="Local")
    proposal = ComponentProposal(id="system", name="Duplicate", responsibility="Bad", boundary="Internal",
                                 rationale="Incorrect")
    with pytest.raises(ValueError, match="cannot propose itself"):
        FixtureComponentProposer({"system": [proposal]}).propose(root, brief)
