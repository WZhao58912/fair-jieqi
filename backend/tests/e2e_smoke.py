"""End-to-end smoke test over real WebSockets.

Requires a running server with a short reveal timeout:
    JIEQI_REVEAL_TIMEOUT=3 uvicorn app.main:app --port 8000
Run:  python tests/e2e_smoke.py

Covers: room setup, server commitment, player commit-reveal (anti-grinding),
commitment-mismatch rejection, information isolation, move flow, and the
reveal-timeout forfeit (SEED_ABORT).
"""

import asyncio
import hashlib
import json

import websockets

URL = "ws://localhost:8000/ws"


async def recv_until(ws, mtype):
    while True:
        msg = json.loads(await ws.recv())
        if msg["type"] == mtype:
            return msg
        if msg["type"] == "ERROR":
            raise AssertionError(f"server error: {msg}")


async def wait_error(ws):
    while True:
        msg = json.loads(await ws.recv())
        if msg["type"] == "ERROR":
            return msg


def sha(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


async def scenario_full_game():
    async with websockets.connect(URL) as red, websockets.connect(URL) as black:
        await red.send(json.dumps({"type": "CREATE_ROOM"}))
        created = await recv_until(red, "ROOM_CREATED")
        room_id = created["room_id"]

        await black.send(json.dumps({"type": "JOIN_ROOM", "room_id": room_id}))
        await recv_until(black, "ROOM_JOINED")

        # step 1: server commitment arrives before any player entropy
        commit_r = await recv_until(red, "SEED_COMMIT")
        commit_b = await recv_until(black, "SEED_COMMIT")
        assert commit_r["server_seed_hash"] == commit_b["server_seed_hash"]
        assert commit_r["stage"] == "COMMIT"
        assert "server_seed" not in commit_r

        # step 2: hash commitments only -- no plaintext on the wire
        await red.send(json.dumps({"type": "SUBMIT_SEED_COMMIT", "seed_hash": sha("e2e-red-seed")}))
        await black.send(json.dumps({"type": "SUBMIT_SEED_COMMIT", "seed_hash": sha("e2e-black-seed")}))
        reveal_r = await recv_until(red, "SEED_REVEAL_BEGIN")
        assert reveal_r["p1_seed_hash"] == sha("e2e-red-seed")
        assert reveal_r["p2_seed_hash"] == sha("e2e-black-seed")

        # revealing a seed that does NOT match the commitment is rejected
        await red.send(json.dumps({"type": "SUBMIT_SEED", "seed": "wrong-seed"}))
        err = await wait_error(red)
        assert "commitment" in err["detail"]

        # premature plain submit would have been rejected pre-commitments too
        await red.send(json.dumps({"type": "SUBMIT_SEED", "seed": "e2e-red-seed"}))
        await black.send(json.dumps({"type": "SUBMIT_SEED", "seed": "e2e-black-seed"}))

        # step 3: game start -- board must not leak any dark identity
        start_r = await recv_until(red, "GAME_START")
        await recv_until(black, "GAME_START")
        dark_cells = [c for row in start_r["board"] for c in row if c and c["state"] == "DARK"]
        assert len(dark_cells) == 30
        assert all(set(c) == {"state", "initial_owner"} for c in dark_cells), "identity leak!"

        await red.send(json.dumps({"type": "LEGAL_MOVES", "coord": [3, 0]}))
        legal = await recv_until(red, "LEGAL_MOVES")
        assert legal["moves"] == [[4, 0]]

        await red.send(json.dumps({"type": "MOVE", "from": [3, 0], "to": [4, 0]}))
        move_b = await recv_until(black, "MOVE_RESULT")
        assert move_b["flipped"] is not None and move_b["flipped"].startswith("R_")
        remaining = [c for row in move_b["board"] for c in row if c and c["state"] == "DARK"]
        assert len(remaining) == 29
        assert "captures" in move_b
        print(f"  scenario 1 (full game flow): OK, flipped={move_b['flipped']}")


async def scenario_seed_abort():
    async with websockets.connect(URL) as red, websockets.connect(URL) as black:
        await red.send(json.dumps({"type": "CREATE_ROOM"}))
        created = await recv_until(red, "ROOM_CREATED")
        await black.send(json.dumps({"type": "JOIN_ROOM", "room_id": created["room_id"]}))
        await recv_until(black, "ROOM_JOINED")
        await recv_until(red, "SEED_COMMIT")
        await red.send(json.dumps({"type": "SUBMIT_SEED_COMMIT", "seed_hash": sha("abort-red")}))
        await black.send(json.dumps({"type": "SUBMIT_SEED_COMMIT", "seed_hash": sha("abort-black")}))
        await recv_until(red, "SEED_REVEAL_BEGIN")

        # red reveals; black refuses (abort attack) -> black must forfeit
        await red.send(json.dumps({"type": "SUBMIT_SEED", "seed": "abort-red"}))
        over = await recv_until(red, "GAME_OVER")
        assert over["reason"] == "SEED_ABORT", over
        assert over["winner"] == "RED", over
        assert over["layout"] is None
        assert over["server_seed"]  # server still honours its commitment
        assert sha(over["server_seed"]) == over["server_seed_hash"]
        print("  scenario 2 (reveal-timeout forfeit): OK")


async def main():
    await scenario_full_game()
    await scenario_seed_abort()
    print("ALL E2E CHECKS PASSED")


asyncio.run(main())
