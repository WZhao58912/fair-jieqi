"""Regenerate tests/test_vectors.json (cross-language shuffle vectors).

Run from the backend/ directory:  python tests/generate_vectors.py
The same file is consumed by the frontend verifier's self-test.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.fair import commit_seed, deterministic_shuffle  # noqa: E402

CASES = [
    ("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2", "alice-lucky-seed", "bob-random-seed"),
    ("00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff", "p1", "p2"),
    ("deadbeef" * 8, "玩家一的种子", "player two seed with spaces"),
]

vectors = [
    {
        "server_seed": s,
        "server_seed_hash": commit_seed(s),
        "p1_seed": p1,
        "p2_seed": p2,
        "layout": deterministic_shuffle(s, p1, p2),
    }
    for s, p1, p2 in CASES
]

out = Path(__file__).parent / "test_vectors.json"
out.write_text(json.dumps(vectors, ensure_ascii=False, indent=2))
print(f"wrote {out}")
