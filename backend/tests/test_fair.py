"""Tests for the provably-fair commitment + deterministic shuffle module."""

import json
from pathlib import Path

import pytest

from app.core.fair import (
    BLACK_DARK_POOL,
    RED_DARK_POOL,
    STANDARD_DARK_PIECES,
    commit_seed,
    deterministic_shuffle,
    generate_server_seed,
    sha256_hex,
    verify_game,
)

VECTORS_PATH = Path(__file__).parent / "test_vectors.json"


def test_pool_integrity():
    assert len(RED_DARK_POOL) == len(BLACK_DARK_POOL) == 15
    assert len(STANDARD_DARK_PIECES) == 30
    assert all(p.startswith("R_") for p in RED_DARK_POOL)
    assert all(p.startswith("B_") for p in BLACK_DARK_POOL)
    assert sorted(STANDARD_DARK_PIECES) == sorted([
        "R_JU", "R_JU", "R_MA", "R_MA", "R_PAO", "R_PAO", "R_XIANG", "R_XIANG",
        "R_SHI", "R_SHI", "R_BING", "R_BING", "R_BING", "R_BING", "R_BING",
        "B_JU", "B_JU", "B_MA", "B_MA", "B_PAO", "B_PAO", "B_XIANG", "B_XIANG",
        "B_SHI", "B_SHI", "B_ZU", "B_ZU", "B_ZU", "B_ZU", "B_ZU",
    ])


def test_shuffle_is_deterministic():
    a = deterministic_shuffle("aa" * 32, "player-one-seed", "player-two-seed")
    b = deterministic_shuffle("aa" * 32, "player-one-seed", "player-two-seed")
    assert a == b


def test_shuffle_is_a_permutation_of_the_pool():
    out = deterministic_shuffle("ab" * 32, "x", "y")
    assert sorted(out) == sorted(STANDARD_DARK_PIECES)


def test_shuffle_never_crosses_colors():
    """Standard Jieqi rule: each side's pieces shuffle only within their own
    half -- the first 15 outputs are always red, the last 15 always black."""
    for seeds in [("ab" * 32, "x", "y"), ("cd" * 32, "p1", "p2"), ("ef" * 32, "甲", "乙")]:
        out = deterministic_shuffle(*seeds)
        assert len(out) == 30
        assert all(p.startswith("R_") for p in out[:15]), seeds
        assert all(p.startswith("B_") for p in out[15:]), seeds
        assert sorted(out[:15]) == sorted(RED_DARK_POOL)
        assert sorted(out[15:]) == sorted(BLACK_DARK_POOL)


def test_different_entropy_changes_layout():
    base = deterministic_shuffle("aa" * 32, "p1", "p2")
    other_server = deterministic_shuffle("bb" * 32, "p1", "p2")
    other_player = deterministic_shuffle("aa" * 32, "p1", "p2-changed")
    assert base != other_server
    assert base != other_player


def test_server_seed_format_and_commitment():
    seed = generate_server_seed()
    assert len(seed) == 64
    int(seed, 16)  # valid hex
    assert commit_seed(seed) == sha256_hex(seed)
    assert generate_server_seed() != seed  # overwhelmingly likely


def test_verify_game_accepts_honest_game():
    server_seed, p1, p2 = "cd" * 32, "alice-seed", "bob-seed"
    layout = deterministic_shuffle(server_seed, p1, p2)
    ok, _ = verify_game(server_seed, commit_seed(server_seed), p1, p2, layout)
    assert ok


@pytest.mark.parametrize("tamper", ["seed", "hash", "layout"])
def test_verify_game_rejects_tampering(tamper):
    server_seed, p1, p2 = "ef" * 32, "alice", "bob"
    layout = deterministic_shuffle(server_seed, p1, p2)
    seed_hash = commit_seed(server_seed)
    if tamper == "seed":
        server_seed = "00" * 32
    elif tamper == "hash":
        seed_hash = "00" * 32
    else:
        layout = layout[::-1]
    ok, detail = verify_game(server_seed, seed_hash, p1, p2, layout)
    assert not ok
    assert detail


def test_shared_cross_language_vectors():
    """These vectors are also asserted by the frontend verifier (verifier.js)
    -- they pin Python and JavaScript to identical output."""
    vectors = json.loads(VECTORS_PATH.read_text())
    assert len(vectors) >= 3
    for v in vectors:
        assert deterministic_shuffle(v["server_seed"], v["p1_seed"], v["p2_seed"]) == v["layout"]
        assert sha256_hex(v["server_seed"]) == v["server_seed_hash"]
