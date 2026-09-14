from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str) -> str:
    p = ROOT / path
    assert p.exists(), f"Missing required governance file: {path}"
    return p.read_text(encoding="utf-8")


def test_required_governance_files_exist():
    require("AGENTS.md")
    require(".birdai/governance.yaml")
    require(".birdai/roadmap.yaml")
    require("BIRDAI-NEUROSCIENCE-REFERENCE.md")


def test_current_phase_is_p1():
    governance = require(".birdai/governance.yaml")
    roadmap = require(".birdai/roadmap.yaml")
    assert "current_phase: P1" in governance
    assert "milestone: P1" in roadmap
    assert "objective: verified_neural_baseline" in roadmap
    assert "title: Persistent individual" in roadmap
    assert "status: complete" in roadmap
    assert "title: Verified neural baseline" in roadmap
    assert "status: active" in roadmap


def test_core_safety_rules_are_declared():
    governance = require(".birdai/governance.yaml")
    for rule in (
        "do_not_skip_roadmap_phases",
        "do_not_change_biology_to_make_tests_pass",
        "do_not_expand_scope_without_new_issue",
        "preserve_neural_decision_authority",
        "utility_must_not_become_hidden_control_fallback",
        "implementing_agent_must_not_self_merge",
    ):
        assert rule in governance, f"Missing hard rule: {rule}"


def test_e0_contains_persistence_contract():
    roadmap = require(".birdai/roadmap.yaml")
    for requirement in (
        "canonical_user_data_path",
        "working_memory_does_not_restore",
        "legacy_res_data_migration_is_defensive_and_non_destructive",
        "no_silent_data_loss",
    ):
        assert requirement in roadmap, f"Missing E0 requirement: {requirement}"
