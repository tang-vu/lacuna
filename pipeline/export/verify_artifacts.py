"""Verify the latest static artifact set without requiring ignored pipeline inputs.

This is the clean-clone/CI integrity gate. It proves that the files match the hashes in the
manifest and that the latest pointer resolves inside ``artifacts/``. It does not claim to rerun
the slow scientific validation, whose raw sweep is intentionally not committed.

Run: ``python -m pipeline.export.verify_artifacts``
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.paths import ARTIFACTS_DIR
from pipeline.provenance import sha256_payload


class ArtifactIntegrityError(RuntimeError):
    pass


def latest_artifact_dir() -> tuple[Path, dict]:
    latest = json.loads((ARTIFACTS_DIR / "latest.json").read_text(encoding="utf-8"))
    version = latest.get("version")
    if not isinstance(version, str) or not version:
        raise ArtifactIntegrityError("artifacts/latest.json has no version")
    version_dir = (ARTIFACTS_DIR / Path(version)).resolve()
    root = ARTIFACTS_DIR.resolve()
    if version_dir == root or root not in version_dir.parents:
        raise ArtifactIntegrityError("latest artifact version resolves outside artifacts/")
    manifest = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != version:
        raise ArtifactIntegrityError("latest pointer and manifest version disagree")
    return version_dir, manifest


def verify_latest() -> dict:
    version_dir, manifest = latest_artifact_dir()
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ArtifactIntegrityError("manifest does not pin artifact file hashes")

    for filename, metadata in files.items():
        path = (version_dir / filename).resolve()
        if path.parent != version_dir:
            raise ArtifactIntegrityError(f"unsafe artifact filename: {filename!r}")
        if not path.is_file():
            raise ArtifactIntegrityError(f"missing artifact file: {filename}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        actual = sha256_payload(payload)
        expected = metadata.get("sha256") if isinstance(metadata, dict) else None
        if actual != expected:
            raise ArtifactIntegrityError(f"artifact digest mismatch: {filename}")
    return manifest


def main() -> None:
    manifest = verify_latest()
    print(f"artifact set OK: {manifest['version']}")
    print(f"verified files: {len(manifest['files'])}")
    print(f"computed verdict: {manifest['computed_layer_verdict']}")


if __name__ == "__main__":
    main()
