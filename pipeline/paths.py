"""Single source of truth for filesystem layout.

Every module resolves paths through here. Computing them ad hoc from __file__ produces directories
that differ depending on how deeply nested the caller is, which is how this project briefly ended
up with two separate data/ trees.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Regenerable intermediate state. Gitignored.
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
COOCCURRENCE_DIR = DATA_DIR / "cooccurrence"

# Published, versioned output the frontend reads. Committed.
ARTIFACTS_DIR = REPO_ROOT / "artifacts"

# Pre-metric benchmark definitions. Committed and reviewed before a candidate formula sees them.
BENCHMARKS_DIR = REPO_ROOT / "benchmarks"

TAXONOMY_PATH = DATA_DIR / "taxonomy.json"


def ensure_dirs() -> None:
    for path in (DATA_DIR, CACHE_DIR, COOCCURRENCE_DIR, ARTIFACTS_DIR):
        path.mkdir(parents=True, exist_ok=True)
