"""Provably-fair commitment scheme and deterministic shuffle for Jieqi.

Protocol lifecycle
------------------
1. Commitment: server generates a random 32-byte ``server_seed`` and publishes
   ``server_seed_hash = SHA256(server_seed)`` BEFORE any player seed is known.
2. Player entropy: both players submit ``p1_seed`` / ``p2_seed`` (optionally
   committed as hashes first -- see ``commit_seed``).
3. Deterministic shuffle: Fisher-Yates driven by a SHA-256 hash chain --
   reproducible bit-for-bit in JavaScript (Web Crypto) with identical input.
4. Verification: after the game the server reveals ``server_seed``; anyone can
   recompute the hash and the shuffle locally.

Piece pools (standard Jieqi rule)
---------------------------------
Each side's 15 dark pieces are shuffled ONLY within their own half: red's 15
pieces permute across the 15 red-half slots, black's across the black-half
slots. A flipped piece therefore always keeps its color -- only its kind is
hidden. Ownership never changes hands mid-game.

Implementation constraints
--------------------------
* Never use ``random.Random`` (Mersenne Twister is impractical to mirror in JS).
* Only the first 12 hex chars (48 bits) of each digest are consumed and reduced
  with an integer modulo -- well inside JS ``Number.MAX_SAFE_INTEGER`` (2^53),
  so Python and JS produce identical ``j`` values.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import List, Tuple

# Each side's 15 dark pieces. Kings (R_SHUAI / B_JIANG) are always face-up and
# fixed, so they are NOT part of the shuffled pools.
RED_DARK_POOL: List[str] = [
    "R_JU", "R_JU", "R_MA", "R_MA", "R_PAO", "R_PAO", "R_XIANG", "R_XIANG",
    "R_SHI", "R_SHI", "R_BING", "R_BING", "R_BING", "R_BING", "R_BING",
]
BLACK_DARK_POOL: List[str] = [
    "B_JU", "B_JU", "B_MA", "B_MA", "B_PAO", "B_PAO", "B_XIANG", "B_XIANG",
    "B_SHI", "B_SHI", "B_ZU", "B_ZU", "B_ZU", "B_ZU", "B_ZU",
]

# Combined pool (red 15 first, then black 15) -- matches the slot ordering in
# board.ALL_DARK_SLOTS (red slots row-major, then black slots row-major).
STANDARD_DARK_PIECES: List[str] = RED_DARK_POOL + BLACK_DARK_POOL

assert len(RED_DARK_POOL) == len(BLACK_DARK_POOL) == 15


def generate_server_seed() -> str:
    """Return a fresh 32-byte seed as 64 lowercase hex chars."""
    return secrets.token_hex(32)


def sha256_hex(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def commit_seed(seed: str) -> str:
    """Commitment hash for a seed (server seed and player seeds alike)."""
    return sha256_hex(seed)


def _shuffle_pool(pool: List[str], base_seed: str) -> List[str]:
    """Fisher-Yates, iterated backwards. Each step derives its randomness from
    an independent SHA-256 digest so the chain is trivially auditable."""
    pieces = pool.copy()
    for i in range(len(pieces) - 1, 0, -1):
        digest = sha256_hex(f"{base_seed}:{i}")
        rand_int = int(digest[:12], 16)  # 48 bits -- safe for JS Number
        j = rand_int % (i + 1)
        pieces[i], pieces[j] = pieces[j], pieces[i]
    return pieces


def deterministic_shuffle(server_seed: str, p1_seed: str, p2_seed: str) -> List[str]:
    """Shuffle both halves deterministically.

    Returns 30 pieces: the shuffled red pool (fills the 15 red-half slots,
    row-major) followed by the shuffled black pool (15 black-half slots).
    The two sub-shuffles use independent hash chains (``:R`` / ``:B`` suffix).
    """
    base_seed = f"{server_seed}:{p1_seed}:{p2_seed}"
    return (
        _shuffle_pool(RED_DARK_POOL, f"{base_seed}:R")
        + _shuffle_pool(BLACK_DARK_POOL, f"{base_seed}:B")
    )


def verify_game(
    server_seed: str,
    server_seed_hash: str,
    p1_seed: str,
    p2_seed: str,
    expected_layout: List[str],
) -> Tuple[bool, str]:
    """Post-game verification. Returns (ok, human-readable detail)."""
    if sha256_hex(server_seed) != server_seed_hash:
        return False, "server_seed does not match the committed server_seed_hash"
    layout = deterministic_shuffle(server_seed, p1_seed, p2_seed)
    if layout != list(expected_layout):
        return False, "recomputed shuffle does not match the revealed layout"
    return True, "commitment and shuffle both verified"
