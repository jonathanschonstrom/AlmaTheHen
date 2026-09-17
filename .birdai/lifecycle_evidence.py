"""Verify immutable registration and the retained paired experiment evidence."""
from __future__ import annotations

from pathlib import Path

from lifecycle_store import LifecycleError, digest, read_json


def registered_runtime(registration: dict) -> str | None:
    direct = registration.get("runtime_commit_at_registration")
    if direct:
        return str(direct)
    provenance = registration.get("provenance")
    if isinstance(provenance, dict):
        value = provenance.get("scientific_runtime_reference")
        if value:
            return str(value)
    return None


def registered_source_snapshot(registration: dict) -> dict:
    direct = registration.get("source_snapshot")
    if isinstance(direct, dict) and direct.get("path") and direct.get("sha256"):
        return direct
    provenance = registration.get("provenance")
    if isinstance(provenance, dict):
        value = provenance.get("source_snapshot")
        if isinstance(value, dict) and value.get("path") and value.get("sha256"):
            return value
    return {}


def verify_summary(spec: dict, summary_path: Path, expected_hash: str | None = None) -> dict:
    registration_path = Path(spec["registration_path"])
    if digest(registration_path) != spec["registration_sha256"]:
        raise LifecycleError("Preregistration changed; human registration is required.")
    registration = read_json(registration_path)
    if registration.get("experiment") != spec["experiment_id"]:
        raise LifecycleError("Preregistration belongs to another experiment.")
    summary_path = summary_path.resolve(strict=True)
    summary_hash = digest(summary_path)
    if expected_hash and summary_hash != expected_hash:
        raise LifecycleError("Summary changed after verification.")
    summary = read_json(summary_path)
    stages = {spec["stage"]}
    if registration.get("hypothesis_id"):
        stages.add(f"{spec['stage']}-{registration['hypothesis_id']}")
    if summary.get("stage") not in stages or summary.get("stage_validity") != "PASS":
        raise LifecycleError("Summary is not a valid result for this stage.")
    if summary.get("registration_sha256") != spec["registration_sha256"]:
        raise LifecycleError("Summary/registration hash mismatch.")
    runtime = registered_runtime(registration)
    if summary.get("runtime_commit") != runtime:
        raise LifecycleError("Summary used a different registered runtime.")
    snapshot = registered_source_snapshot(registration)
    if not snapshot.get("path") or digest(Path(snapshot["path"])) != snapshot.get("sha256"):
        raise LifecycleError("Registered source snapshot is missing or changed.")
    if summary.get("accepted_source_snapshot_sha256") != snapshot["sha256"]:
        raise LifecycleError("Summary used a different source snapshot.")
    seeds = registration.get("seed_set")
    pairs = summary.get("pairs")
    declared_pairs = registration.get("pairing", {}).get("pairs", [])
    if not isinstance(seeds, list) or not seeds or len(seeds) != len(set(seeds)):
        raise LifecycleError("Registration needs an explicit unique seed set.")
    if not isinstance(pairs, list) or [p.get("seed") for p in pairs] != seeds or summary.get("seed_set") != seeds:
        raise LifecycleError("Missing, reordered, additional or duplicated seed pairs.")
    if [p.get("seed") for p in declared_pairs] != seeds:
        raise LifecycleError("Registration pairing does not match its seed set.")
    expected_runs = sum(len(p.get("arms", [])) for p in declared_pairs)
    if (summary.get("pair_count_declared") != len(seeds)
            or summary.get("pair_count_completed") != len(seeds)
            or summary.get("run_count_declared") != expected_runs):
        raise LifecycleError("Incomplete experiment counts.")
    verdict = summary.get("hypothesis_result", summary.get("replication_result"))
    allowed = registration.get("hypothesis_result", {}).get("values", [])
    if verdict not in allowed:
        raise LifecycleError("Hypothesis verdict is outside the preregistered vocabulary.")
    for field in ("production_runtime_mutation", "neural_policy_change", "learning_rule_change"):
        if str(summary.get(field, "")).lower() != "none":
            raise LifecycleError(f"Protected change or missing declaration: {field}")

    root = summary_path.parent
    artifacts: dict[str, str] = {}

    def check_artifact(path_text, expected):
        path = Path(path_text).resolve(strict=True)
        if not path.is_relative_to(root):
            raise LifecycleError(f"Experiment artifact escapes evidence directory: {path}")
        if str(path) in artifacts:
            if artifacts[str(path)] != expected:
                raise LifecycleError("Conflicting hashes for one artifact.")
            return
        if digest(path) != expected:
            raise LifecycleError(f"Artifact hash mismatch: {path}")
        artifacts[str(path)] = expected
        if path.suffix.lower() == ".json":
            walk(read_json(path))

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("_path") and key[:-5] + "_sha256" in value:
                    check_artifact(item, value[key[:-5] + "_sha256"])
                elif isinstance(item, (dict, list)):
                    walk(item)

    for pair, declared in zip(pairs, declared_pairs):
        if pair.get("pair_validity") != "PASS":
            raise LifecycleError("Invalid pairs must not be silently dropped or accepted.")
        if not pair.get("pair_comparison_path") or not pair.get("pair_comparison_sha256"):
            raise LifecycleError("Pair comparison evidence is missing.")

        # Integrity alone is not enough: the retained comparison must semantically
        # agree with the summary that is being accepted.
        check_artifact(pair["pair_comparison_path"], pair["pair_comparison_sha256"])
        comparison = read_json(Path(pair["pair_comparison_path"]))
        if comparison.get("seed") != pair.get("seed") or comparison.get("pair_validity") != "PASS":
            raise LifecycleError("Pair comparison identity/validity disagrees with summary.")

        declared_arms = declared.get("arms", [])
        if not isinstance(declared_arms, list) or not declared_arms:
            raise LifecycleError("Registration pair is missing declared arms.")
        for arm in declared_arms:
            value = pair.get(arm, {})
            if value.get("status") != "PASS":
                raise LifecycleError(f"Summary arm is not PASS: {arm}")
            compared = comparison.get(arm)
            if not isinstance(compared, dict) or compared.get("status") != "PASS":
                raise LifecycleError(f"Pair comparison arm is not PASS: {arm}")
            if not value.get("capsule_path") or not value.get("capsule_sha256"):
                raise LifecycleError(f"Run capsule is missing: {arm}")
            capsule_path = Path(value["capsule_path"]).resolve(strict=True)
            if not capsule_path.is_relative_to(root):
                raise LifecycleError("Run capsule escapes the retained evidence directory.")
            if digest(capsule_path) != value["capsule_sha256"]:
                raise LifecycleError(f"Run capsule hash mismatch: {arm}")
            capsule = read_json(capsule_path)
            if (capsule.get("runtime_commit") != runtime
                    or capsule.get("registration_sha256") != spec["registration_sha256"]
                    or capsule.get("neural_seed") != pair["seed"]):
                raise LifecycleError("Run capsule identity mismatch.")
            if "status" in capsule and capsule.get("status") != "PASS":
                raise LifecycleError(f"Run capsule is not PASS: {arm}")
            if "capsule_path" in compared and Path(compared["capsule_path"]).resolve() != capsule_path:
                raise LifecycleError(f"Pair comparison references a different capsule: {arm}")
            if "capsule_sha256" in compared and compared["capsule_sha256"] != value["capsule_sha256"]:
                raise LifecycleError(f"Pair comparison capsule hash disagrees with summary: {arm}")
        walk(pair)
    return {
        "schema": 1, "experiment_id": spec["experiment_id"], "stage": spec["stage"],
        "execution_issue": spec["execution_issue"], "registration_sha256": spec["registration_sha256"],
        "runtime_commit": runtime, "source_snapshot_sha256": snapshot["sha256"],
        "stage_validity": "PASS", "hypothesis_result": verdict,
        "summary_path": str(summary_path), "summary_sha256": summary_hash,
        "valid_pair_count": len(pairs), "run_count": expected_runs,
        "artifacts": artifacts, "human_review_required_for_issue_close": True,
    }
