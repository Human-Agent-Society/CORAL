#!/usr/bin/env python3
"""Fetch the pinned upstream task and dataset, regenerate the traces, verify every hash.

    export SKYSYNTH_PRIVATE=/path/outside/the/repo/and/outside/~/.cache
    python tools/prepare_data.py            # all four steps, idempotent
    python tools/prepare_data.py vendor     # or one step: vendor | dataset | traces | private

Nothing large or label-bearing is committed. ``upstream_manifest.json`` records
the upstream revision, a sha256 per vendored file, the dataset revision and
archive hash, and the hash and row count of every generated trace; this script
reproduces the inputs and refuses anything that does not match.

Steps:

vendor   Fetch ``skydiscover`` at the pinned commit (a shallow fetch of that one
         commit) and copy the ``llm-router`` task directory plus LICENSE into
         ``upstream/`` (gitignored). Every file must match the manifest.
dataset  Download LLMRouterBench's ``bench-release.tar.gz`` (about 1.2 GB) from
         the pinned dataset revision into ``$SKYSYNTH_PRIVATE/lrb/``, verify its
         sha256, and extract it under the private build tree.
traces   Copy the task into ``$SKYSYNTH_PRIVATE/build/llm-router/`` and run
         upstream's ``make_tenant_traces.py`` there, unchanged. The generated
         traces must match the manifest's hashes and row counts, and the
         regenerated manifests and workload cards must equal the vendored copies.
private  Assemble ``$SKYSYNTH_PRIVATE/router_private/`` (the TRAIN trace only,
         with its manifest). ``tools/build_seed.py`` adds the out-of-fold
         prediction table once ``tools/refit_predictions_oof.py`` has run.

The private root must live outside ``~/.cache``: CORAL's agent sandbox allows
``~/.cache`` back for uv and pip, so anything under it is readable by builders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MANIFEST = HERE / "upstream_manifest.json"
UPSTREAM = HERE / "upstream"

TRAIN_TRACE = "trace_merged_train.jsonl"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def private_root(arg: Path | None) -> Path:
    root = arg or (
        Path(os.environ["SKYSYNTH_PRIVATE"]) if os.environ.get("SKYSYNTH_PRIVATE") else None
    )
    if root is None:
        raise SystemExit(
            "pass --private or set SKYSYNTH_PRIVATE (a directory outside the repository and outside ~/.cache)"
        )
    root = root.resolve()
    cache = (Path.home() / ".cache").resolve()
    if root == cache or cache in root.parents:
        raise SystemExit(f"refusing: {root} is under ~/.cache, which the builder sandbox can read")
    if HERE.parents[1] in root.parents or root == HERE.parents[1]:
        raise SystemExit(f"refusing: {root} is inside the repository")
    root.mkdir(parents=True, exist_ok=True)
    return root


# --------------------------------------------------------------------------- #
# vendor                                                                      #
# --------------------------------------------------------------------------- #


def verify_vendored(quiet: bool = False) -> list[str]:
    want = manifest()["vendored_files"]
    problems = []
    for rel, digest in want.items():
        p = UPSTREAM / rel
        if not p.is_file():
            problems.append(f"missing upstream/{rel}")
        elif sha256(p) != digest:
            problems.append(f"hash mismatch upstream/{rel}")
    if not quiet and not problems:
        print(f"upstream/: {len(want)} files match upstream_manifest.json")
    return problems


def vendor(force: bool = False) -> None:
    if UPSTREAM.is_dir() and not force and not verify_vendored(quiet=True):
        print("upstream/: already vendored and verified")
        return
    up = manifest()["upstream"]
    with tempfile.TemporaryDirectory(prefix="skydiscover-") as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        run = lambda *cmd: subprocess.run(cmd, cwd=repo, check=True, capture_output=True, text=True)  # noqa: E731
        run("git", "init", "-q")
        run("git", "remote", "add", "origin", up["repo"])
        print(f"fetching {up['repo']} @ {up['revision'][:12]} (one commit)")
        run("git", "fetch", "-q", "--depth", "1", "origin", up["revision"])
        run("git", "checkout", "-q", "FETCH_HEAD")
        head = run("git", "rev-parse", "HEAD").stdout.strip()
        if head != up["revision"]:
            raise SystemExit(f"fetched {head}, expected {up['revision']}")
        src_task = repo / up["task_path"]
        if UPSTREAM.exists():
            shutil.rmtree(UPSTREAM)
        UPSTREAM.mkdir()
        for rel in manifest()["vendored_files"]:
            src = (repo / "LICENSE") if rel == "LICENSE" else (src_task / rel)
            if not src.is_file():
                raise SystemExit(
                    f"{rel} is not in the pinned revision; manifest and upstream disagree"
                )
            dst = UPSTREAM / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    problems = verify_vendored()
    if problems:
        raise SystemExit("vendored files do not match the manifest:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- #
# dataset                                                                     #
# --------------------------------------------------------------------------- #


def _download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "coral-skysynth-router/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        for chunk in iter(lambda: resp.read(1 << 20), b""):
            out.write(chunk)
            done += len(chunk)
            if total and done % (64 << 20) < (1 << 20):
                print(f"  {done / 1e9:.2f} / {total / 1e9:.2f} GB", flush=True)
    tmp.replace(dst)


def dataset(private: Path, force: bool = False) -> Path:
    ds = manifest()["dataset"]
    archive = private / "lrb" / ds["archive"]
    if archive.is_file() and not force and sha256(archive) == ds["archive_sha256"]:
        print(f"dataset archive present and verified: {archive}")
    else:
        url = (
            f"https://huggingface.co/datasets/{ds['repo']}/resolve/{ds['revision']}/{ds['archive']}"
        )
        print(f"downloading {url}")
        _download(url, archive)
        got = sha256(archive)
        if got != ds["archive_sha256"]:
            archive.unlink()
            raise SystemExit(f"archive sha256 {got} != recorded {ds['archive_sha256']}; deleted")
        print(f"dataset archive verified: {archive}")
    lrb_dir = _build_task_dir(private) / "evaluator" / "benchmark" / ".data" / "lrb"
    if (lrb_dir / "bench-release").is_dir() and not force:
        print(f"dataset already extracted: {lrb_dir / 'bench-release'}")
        return lrb_dir
    lrb_dir.mkdir(parents=True, exist_ok=True)
    print(f"extracting into {lrb_dir}")
    with tarfile.open(archive) as tar:
        for m in tar.getmembers():
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise SystemExit(f"refusing archive member {m.name}")
        tar.extractall(lrb_dir)  # noqa: S202 - members checked above
    if not (lrb_dir / "bench-release").is_dir():
        raise SystemExit(f"archive did not produce {lrb_dir / 'bench-release'}")
    return lrb_dir


# --------------------------------------------------------------------------- #
# traces                                                                      #
# --------------------------------------------------------------------------- #


def _build_task_dir(private: Path) -> Path:
    return private / "build" / "llm-router"


def verify_traces(private: Path, quiet: bool = False) -> list[str]:
    want = manifest()["generated_traces"]
    traces = _build_task_dir(private) / "evaluator" / "benchmark" / ".data" / "traces"
    problems = []
    for name, rec in want.items():
        p = traces / name
        if not p.is_file():
            problems.append(f"missing {name}")
            continue
        if sha256(p) != rec["sha256"]:
            problems.append(f"hash mismatch {name}")
        with open(p) as f:
            n = sum(1 for _ in f)
        if n != rec["rows"]:
            problems.append(f"row count {n} != {rec['rows']} for {name}")
    if not quiet and not problems:
        print(f"traces: {len(want)} files match upstream_manifest.json")
    return problems


def traces(private: Path, force: bool = False) -> None:
    if not force and not verify_traces(private, quiet=True):
        print("traces: already generated and verified")
        return
    if verify_vendored(quiet=True):
        raise SystemExit("upstream/ is missing or unverified; run `prepare_data.py vendor` first")
    build = _build_task_dir(private)
    lrb = build / "evaluator" / "benchmark" / ".data" / "lrb" / "bench-release"
    if not lrb.is_dir():
        raise SystemExit(f"dataset not extracted at {lrb}; run `prepare_data.py dataset` first")
    # Copy the vendored task over the build tree (never touching .data).
    for rel in manifest()["vendored_files"]:
        if rel == "LICENSE":
            continue
        dst = build / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(UPSTREAM / rel, dst)
    script = build / "evaluator" / "benchmark" / "data" / "make_tenant_traces.py"
    print(f"running upstream's {script.relative_to(private)} (unchanged)")
    log = private / "build" / "make_traces.log"
    with open(log, "w") as f:
        r = subprocess.run(
            [sys.executable, str(script)], cwd=build, stdout=f, stderr=subprocess.STDOUT
        )
    if r.returncode != 0:
        raise SystemExit(f"make_tenant_traces.py failed; see {log}")
    problems = verify_traces(private)
    if problems:
        raise SystemExit("generated traces do not match the manifest:\n  " + "\n  ".join(problems))
    # The regenerated manifests and cards must equal what upstream committed.
    drift = []
    for rel in manifest()["vendored_files"]:
        if "/data/manifests/" in rel or "/data/cards/" in rel:
            if sha256(build / rel) != sha256(UPSTREAM / rel):
                drift.append(rel)
    if drift:
        raise SystemExit(
            "regenerated manifests/cards differ from the vendored copies: " + ", ".join(drift)
        )
    print("regenerated manifests and workload cards equal the vendored copies")


# --------------------------------------------------------------------------- #
# private                                                                     #
# --------------------------------------------------------------------------- #


def private_data(private: Path) -> Path:
    if verify_traces(private, quiet=True):
        raise SystemExit("traces are missing or unverified; run `prepare_data.py traces` first")
    src = _build_task_dir(private) / "evaluator" / "benchmark" / ".data" / "traces" / TRAIN_TRACE
    rp = private / "router_private"
    (rp / "traces").mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, rp / "traces" / TRAIN_TRACE)
    with open(src) as f:
        rows = sum(1 for _ in f)
    existing = (
        json.loads((rp / "MANIFEST.json").read_text()) if (rp / "MANIFEST.json").is_file() else {}
    )
    files = dict(existing.get("files") or {})
    files[f"traces/{TRAIN_TRACE}"] = sha256(src)
    (rp / "MANIFEST.json").write_text(
        json.dumps(
            {
                "contents": "TRAIN split only; val/test are never copied into any run directory",
                "files": files,
                "rows": rows,
            },
            indent=1,
        )
        + "\n"
    )
    print(
        f"router_private: {rp} ({rows} train rows). Next: tools/refit_predictions_oof.py, then tools/build_seed.py"
    )
    return rp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "step", nargs="?", choices=("vendor", "dataset", "traces", "private", "all"), default="all"
    )
    ap.add_argument("--private", type=Path, help="owner-only data root (default $SKYSYNTH_PRIVATE)")
    ap.add_argument(
        "--force", action="store_true", help="redo the step even when its outputs verify"
    )
    a = ap.parse_args(argv)
    steps = ("vendor", "dataset", "traces", "private") if a.step == "all" else (a.step,)
    private = private_root(a.private) if any(s != "vendor" for s in steps) else None
    for step in steps:
        if step == "vendor":
            vendor(force=a.force)
        elif step == "dataset":
            dataset(private, force=a.force)  # type: ignore[arg-type]
        elif step == "traces":
            traces(private, force=a.force)  # type: ignore[arg-type]
        else:
            private_data(private)  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
