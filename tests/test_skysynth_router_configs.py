"""The router study's inputs are fetched and verified, never trusted from disk.

These tests need no model, no network and no private data: they exercise the
manifest verification, the private-root rules, the config generator and the
environment-driven private path.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "examples" / "skysynth_router"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# prepare_data: the manifest is the contract                                  #
# --------------------------------------------------------------------------- #


def test_manifest_pins_upstream_dataset_and_every_trace():
    m = json.loads((TASK / "upstream_manifest.json").read_text())
    assert m["upstream"]["license"] == "Apache-2.0"
    assert len(m["upstream"]["revision"]) == 40 and len(m["dataset"]["revision"]) == 40
    assert len(m["dataset"]["archive_sha256"]) == 64
    assert "LICENSE" in m["vendored_files"] and "task.md" in m["vendored_files"]
    assert all(len(h) == 64 for h in m["vendored_files"].values())
    assert set(m["generated_traces"]) == {
        f"trace_{who}_{split}.jsonl"
        for split in ("train", "val", "test")
        for who in ("merged", "tenantA", "tenantB")
    }
    assert all(rec["rows"] > 0 for rec in m["generated_traces"].values())


def test_vendored_file_verification_reports_missing_and_tampered(tmp_path, monkeypatch):
    pd = _load(TASK / "tools" / "prepare_data.py")
    fake = tmp_path / "upstream"
    fake.mkdir()
    (fake / "task.md").write_text("contract")
    (fake / "LICENSE").write_text("apache")
    manifest = {
        "vendored_files": {
            "task.md": hashlib.sha256(b"contract").hexdigest(),
            "LICENSE": hashlib.sha256(b"apache").hexdigest(),
            "evaluator/replay.py": "0" * 64,
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(pd, "UPSTREAM", fake)
    monkeypatch.setattr(pd, "MANIFEST", tmp_path / "manifest.json")
    assert pd.verify_vendored(quiet=True) == ["missing upstream/evaluator/replay.py"]
    (fake / "task.md").write_text("edited")
    problems = pd.verify_vendored(quiet=True)
    assert "hash mismatch upstream/task.md" in problems and len(problems) == 2


def test_trace_verification_checks_hash_and_row_count(tmp_path, monkeypatch):
    pd = _load(TASK / "tools" / "prepare_data.py")
    private = tmp_path / "priv"
    traces = private / "build" / "llm-router" / "evaluator" / "benchmark" / ".data" / "traces"
    traces.mkdir(parents=True)
    body = '{"a":1}\n{"a":2}\n'
    (traces / "trace_merged_train.jsonl").write_text(body)
    manifest = {
        "generated_traces": {
            "trace_merged_train.jsonl": {
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "rows": 2,
            },
            "trace_merged_val.jsonl": {"sha256": "0" * 64, "rows": 1},
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(pd, "MANIFEST", tmp_path / "manifest.json")
    assert pd.verify_traces(private, quiet=True) == ["missing trace_merged_val.jsonl"]
    (traces / "trace_merged_train.jsonl").write_text(body + '{"a":3}\n')
    problems = pd.verify_traces(private, quiet=True)
    assert any("hash mismatch trace_merged_train" in p for p in problems)
    assert any("row count 3 != 2" in p for p in problems)


def test_private_root_refuses_the_cache_and_the_repository(tmp_path, monkeypatch):
    pd = _load(TASK / "tools" / "prepare_data.py")
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(SystemExit, match="~/.cache"):
        pd.private_root(tmp_path / ".cache" / "priv")
    with pytest.raises(SystemExit, match="inside the repository"):
        pd.private_root(ROOT / "results" / "priv")
    ok = pd.private_root(tmp_path / "elsewhere")
    assert ok.is_dir()
    monkeypatch.delenv("SKYSYNTH_PRIVATE", raising=False)
    with pytest.raises(SystemExit, match="SKYSYNTH_PRIVATE"):
        pd.private_root(None)


# --------------------------------------------------------------------------- #
# make_configs: arms identical where agents can see, private path from env    #
# --------------------------------------------------------------------------- #


def _configs(tmp_path: Path):
    mc = _load(TASK / "tools" / "make_configs.py")
    out = tmp_path / "configs"
    for arm in ("static", "adaptive"):
        mc.write(arm, mc.build(arm, "claude-opus-4-8", 15.0), out)
    return out


def test_generated_arms_differ_only_inside_grader_args(tmp_path):
    out = _configs(tmp_path)
    cfgs = {
        arm: yaml.safe_load((out / arm / "task.yaml").read_text()) for arm in ("static", "adaptive")
    }
    a, b = cfgs["static"], cfgs["adaptive"]
    assert (
        a["task"] == b["task"]
        and a["agents"] == b["agents"]
        and a["run"] == b["run"]
        and a["workspace"] == b["workspace"]
    )
    ga = {k: v for k, v in a["grader"].items() if k not in ("args", "entrypoint")}
    gb = {k: v for k, v in b["grader"].items() if k not in ("args", "entrypoint")}
    assert ga == gb and a["grader"]["hide_args"] is True
    assert "checkpoints" not in a["grader"]["args"] and b["grader"]["args"]["checkpoints"] == [
        8,
        12,
        16,
    ]
    assert b["grader"]["args"]["train_predictions"] == "predictions_train_oof.json"
    for arm in cfgs:
        assert (out / arm / "seed").is_symlink()
        assert (out / arm / "seed").resolve() == (TASK / "seed").resolve()
        text = (out / arm / "task.yaml").read_text()
        assert "/Users/" not in text and "nvm" not in text, (
            "machine-specific path leaked into a config"
        )


def test_committed_configs_are_what_the_generator_emits(tmp_path):
    out = _configs(tmp_path)
    for arm in ("static", "adaptive"):
        assert (TASK / "configs" / arm / "task.yaml").read_text() == (
            out / arm / "task.yaml"
        ).read_text()
        assert (TASK / "configs" / arm / "seed").is_symlink()


def test_private_paths_resolve_from_the_environment_and_fail_without_it(tmp_path, monkeypatch):
    from coral.config import CoralConfig

    out = _configs(tmp_path)
    monkeypatch.setenv("SKYSYNTH_PRIVATE", str(tmp_path / "priv"))
    cfg = CoralConfig.from_yaml(out / "static" / "task.yaml")
    assert cfg.grader.private == [str(tmp_path / "priv" / "router_private")]
    assert cfg.agents.sandbox.deny_read == [str(tmp_path / "priv")]
    assert cfg.agents.sandbox.enabled is True
    monkeypatch.delenv("SKYSYNTH_PRIVATE")
    with pytest.raises(Exception):  # noqa: B017 - OmegaConf's interpolation error type is internal
        CoralConfig.from_yaml(out / "static" / "task.yaml")


def test_seed_static_files_match_their_manifest_and_carry_no_held_out_split():
    manifest = json.loads((TASK / "seed" / "SEED_MANIFEST.json").read_text())
    for rel, digest in manifest.items():
        if rel.startswith("data/"):
            continue  # fetched, not committed
        p = TASK / "seed" / rel
        assert p.is_file(), rel
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, rel
    for rel in manifest:
        assert not any(tok in rel for tok in ("_val", "_test", "bench-release")), rel
    assert set(manifest) >= {
        "solution.py",
        "task/task.md",
        "task/LICENSE.upstream",
        "tools/replay_pair.py",
        "data/trace_merged_train.jsonl",
        "data/predictions_train.json",
    }
