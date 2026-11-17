"""Room matchmaking, game state machine and broadcast -- with strict
information isolation so dark-piece identities never leave the server early.

State machine per room:
    LOBBY -> SEED_COMMIT -> SEED_REVEAL -> PLAYING -> GAME_OVER

Fairness timeline (commit-reveal for ALL seeds, anti-grinding):
    1. Both players connect   -> server generates server_seed and broadcasts
       ONLY its SHA-256 commitment (``SEED_COMMIT``).
    2. Both players submit hash commitments of their seeds
       (``SUBMIT_SEED_COMMIT``). Neither seed is visible to anyone yet, so
       nobody can grind a seed against the others' entropy.
    3. Once BOTH commitments are locked, players reveal plaintext seeds
       (``SUBMIT_SEED``); the server verifies SHA-256(seed) == commitment.
       A player who refuses to reveal within ``REVEAL_TIMEOUT`` seconds
       forfeits the game (``SEED_ABORT``) -- aborting costs the game.
    4. Server shuffles deterministically, starts the game (``GAME_START``).
    5. On game end the server reveals server_seed, both player seeds and the
       full 30-piece layout so anyone can verify locally.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
from typing import Dict, List, Optional

from fastapi import WebSocket

from ..core.fair import commit_seed, deterministic_shuffle, generate_server_seed
from ..game.board import ALL_DARK_SLOTS, BLACK, RED, Board
from ..game.engine import JieqiEngine

LOBBY, SEED_COMMIT, SEED_REVEAL, PLAYING, GAME_OVER = (
    "LOBBY", "SEED_COMMIT", "SEED_REVEAL", "PLAYING", "GAME_OVER",
)
SIDES = (RED, BLACK)

# Seconds a player has to reveal their seed after both commitments are in.
# Configurable for tests: JIEQI_REVEAL_TIMEOUT=3
REVEAL_TIMEOUT = float(os.environ.get("JIEQI_REVEAL_TIMEOUT", "60"))


def _valid_hash(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


class Player:
    def __init__(self, ws: WebSocket, side: str):
        self.ws = ws
        self.side = side
        self.seed_hash: Optional[str] = None  # commitment (SHA-256 of the seed)
        self.seed: Optional[str] = None       # revealed plaintext


class Room:
    def __init__(self, room_id: str):
        self.id = room_id
        self.state = LOBBY
        self.players: Dict[str, Player] = {}
        self.server_seed: Optional[str] = None
        self.server_seed_hash: Optional[str] = None
        self.engine: Optional[JieqiEngine] = None
        self.layout: Optional[List[str]] = None  # full 30-piece sequence, secret until game over
        self.captures: List[str] = []  # piece codes in capture order, for the lost-pieces panel
        self.moves: List[dict] = []    # full move history, revealed at game over for replay
        self.reveal_timer: Optional[asyncio.Task] = None

    # -- helpers ------------------------------------------------------------
    async def broadcast(self, message: dict) -> None:
        for player in list(self.players.values()):
            await player.ws.send_text(json.dumps(message, ensure_ascii=False))

    async def send(self, side: str, message: dict) -> None:
        player = self.players.get(side)
        if player:
            await player.ws.send_text(json.dumps(message, ensure_ascii=False))

    def public_board(self):
        assert self.engine is not None
        return self.engine.board.public_state()

    def opponent_of(self, side: str) -> str:
        return BLACK if side == RED else RED

    def cancel_timer(self) -> None:
        if self.reveal_timer and not self.reveal_timer.done():
            self.reveal_timer.cancel()
        self.reveal_timer = None


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self._counter = itertools.count(1)

    # -- connection lifecycle ------------------------------------------------
    async def handle(self, ws: WebSocket) -> None:
        await ws.accept()
        room: Optional[Room] = None
        side: Optional[str] = None
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await self._error(ws, "malformed JSON")
                    continue
                mtype = msg.get("type")

                if mtype == "CREATE_ROOM" and room is None:
                    room, side = self._create(ws)
                    await self._send(ws, {"type": "ROOM_CREATED", "room_id": room.id, "side": side})
                elif mtype == "JOIN_ROOM" and room is None:
                    room, side = await self._join(ws, str(msg.get("room_id", "")))
                elif room is None:
                    await self._error(ws, "create or join a room first")
                elif mtype == "SUBMIT_SEED_COMMIT":
                    await self._submit_seed_commit(room, side, str(msg.get("seed_hash", "")))
                elif mtype == "SUBMIT_SEED":
                    await self._submit_seed(room, side, str(msg.get("seed", "")))
                elif mtype == "MOVE":
                    await self._move(room, side, msg.get("from"), msg.get("to"))
                elif mtype == "LEGAL_MOVES":
                    await self._legal_moves(room, side, msg.get("coord"))
                else:
                    await self._error(ws, f"unsupported message type: {mtype}")
        except Exception:
            pass  # disconnect or broken pipe
        finally:
            if room is not None and side is not None:
                await self._disconnect(room, side)

    # -- room setup ----------------------------------------------------------
    def _create(self, ws: WebSocket):
        room_id = f"{next(self._counter):04d}"
        room = Room(room_id)
        room.players[RED] = Player(ws, RED)  # creator plays red, moves first
        self.rooms[room_id] = room
        return room, RED

    async def _join(self, ws: WebSocket, room_id: str):
        room = self.rooms.get(room_id)
        if room is None or room.state != LOBBY or BLACK in room.players:
            await self._error(ws, "room not found or already full")
            return None, None
        room.players[BLACK] = Player(ws, BLACK)
        await self._send(ws, {"type": "ROOM_JOINED", "room_id": room.id, "side": BLACK})
        await room.send(RED, {"type": "OPPONENT_JOINED"})

        # Step 1 -- server commitment: publish the hash, keep the seed secret.
        room.server_seed = generate_server_seed()
        room.server_seed_hash = commit_seed(room.server_seed)
        room.state = SEED_COMMIT
        await room.broadcast({
            "type": "SEED_COMMIT",
            "stage": "COMMIT",
            "server_seed_hash": room.server_seed_hash,
            "message": "服务端已承诺种子。双方提交各自种子的 SHA-256 承诺。",
        })
        return room, BLACK

    # -- seed phase 1: commitments --------------------------------------------
    async def _submit_seed_commit(self, room: Room, side: str, seed_hash: str) -> None:
        if room.state != SEED_COMMIT:
            await self._error(room.players[side].ws, "not accepting seed commitments right now")
            return
        player = room.players[side]
        if player.seed_hash is not None:
            await self._error(player.ws, "seed commitment already locked")
            return
        if not _valid_hash(seed_hash):
            await self._error(player.ws, "seed_hash must be 64 lowercase/uppercase hex chars")
            return
        player.seed_hash = seed_hash.lower()
        await room.broadcast({"type": "SEED_RECEIVED", "side": side, "stage": "COMMIT"})
        if all(p.seed_hash for p in room.players.values()):
            # Both commitments locked -> switch to reveal, armed with a timer.
            room.state = SEED_REVEAL
            await room.broadcast({
                "type": "SEED_REVEAL_BEGIN",
                "p1_seed_hash": room.players[RED].seed_hash,
                "p2_seed_hash": room.players[BLACK].seed_hash,
                "timeout": REVEAL_TIMEOUT,
                "message": "双方承诺已锁定，请揭示种子明文。超时未揭示者判负。",
            })
            room.reveal_timer = asyncio.create_task(self._reveal_timeout(room))

    async def _reveal_timeout(self, room: Room) -> None:
        try:
            await asyncio.sleep(REVEAL_TIMEOUT)
        except asyncio.CancelledError:
            return
        if room.state != SEED_REVEAL:
            return
        room.state = GAME_OVER
        revealed = [s for s in SIDES if s in room.players and room.players[s].seed]
        winner = revealed[0] if len(revealed) == 1 else None
        await room.broadcast({
            "type": "GAME_OVER",
            "winner": winner,
            "reason": "SEED_ABORT",
            "server_seed": room.server_seed,
            "server_seed_hash": room.server_seed_hash,
            "p1_seed": room.players[RED].seed,
            "p2_seed": room.players[BLACK].seed,
            "layout": None,   # game never started -- nothing to audit
            "captures": [],
            "moves": [],
        })

    # -- seed phase 2: reveal --------------------------------------------------
    async def _submit_seed(self, room: Room, side: str, seed: str) -> None:
        if room.state != SEED_REVEAL:
            await self._error(room.players[side].ws, "not accepting seed reveals right now")
            return
        player = room.players[side]
        if player.seed is not None:
            await self._error(player.ws, "seed already revealed")
            return
        if commit_seed(seed) != player.seed_hash:
            await self._error(player.ws, "seed does not match your commitment")
            return
        player.seed = seed
        await room.broadcast({"type": "SEED_RECEIVED", "side": side, "stage": "REVEAL"})
        if all(p.seed for p in room.players.values()):
            room.cancel_timer()
            await self._start_game(room)

    async def _start_game(self, room: Room) -> None:
        p1_seed = room.players[RED].seed
        p2_seed = room.players[BLACK].seed
        # Deterministic shuffle from three committed entropy sources.
        room.layout = deterministic_shuffle(room.server_seed, p1_seed, p2_seed)
        room.engine = JieqiEngine(Board.new_game(room.layout))
        room.state = PLAYING
        await room.broadcast({
            "type": "GAME_START",
            "board": room.public_board(),
            "turn": RED,
            "check": None,
            "server_seed_hash": room.server_seed_hash,
        })

    # -- moves ----------------------------------------------------------------
    async def _legal_moves(self, room: Room, side: str, coord) -> None:
        moves: List[list] = []
        if room.state == PLAYING and coord is not None:
            try:
                moves = [list(m) for m in room.engine.legal_moves(tuple(coord), side)]
            except (TypeError, ValueError):
                moves = []
        await room.send(side, {"type": "LEGAL_MOVES", "coord": coord, "moves": moves})

    async def _move(self, room: Room, side: str, frm, to) -> None:
        if room.state != PLAYING:
            await self._error(room.players[side].ws, "game is not in progress")
            return
        try:
            frm, to = tuple(frm), tuple(to)
        except TypeError:
            await self._error(room.players[side].ws, "bad coordinates")
            return
        result = room.engine.apply_move(frm, to, side)
        if not result.ok:
            await self._error(room.players[side].ws, result.error or "illegal move")
            return
        if result.captured:
            room.captures.append(result.captured["code"])  # chronological order
        room.moves.append({
            "side": side,
            "from": list(frm),
            "to": list(to),
            "flipped": result.flipped,
            "captured": result.captured["code"] if result.captured else None,
        })
        # Which side is now in check (None once the game is over)?
        check = None
        if not result.game_over:
            check = room.engine.turn if room.engine.is_in_check(room.engine.turn) else None
        await room.broadcast({
            "type": "MOVE_RESULT",
            "side": side,
            "from": list(frm),
            "to": list(to),
            "flipped": result.flipped,     # revealed ONLY on a legal move
            "captured": result.captured,   # captured dark pieces are revealed
            "captures": room.captures,     # full ordered lost-pieces log
            "board": room.public_board(),
            "turn": room.engine.turn,
            "check": check,
            "game_over": result.game_over,
        })
        if result.game_over:
            # Reveal everything needed for local verification + replay.
            room.state = GAME_OVER
            await room.broadcast({
                "type": "GAME_OVER",
                "winner": result.winner,
                "reason": result.reason,
                "server_seed": room.server_seed,
                "server_seed_hash": room.server_seed_hash,
                "p1_seed": room.players[RED].seed,
                "p2_seed": room.players[BLACK].seed,
                "layout": room.layout,
                "layout_slots": [list(c) for c in ALL_DARK_SLOTS],
                "captures": room.captures,
                "moves": room.moves,  # full replay history
            })

    # -- teardown -------------------------------------------------------------
    async def _disconnect(self, room: Room, side: str) -> None:
        room.players.pop(side, None)
        if room.state in (PLAYING, SEED_COMMIT, SEED_REVEAL):
            other = self.opponent_of(side)
            if other in room.players:
                await room.send(other, {"type": "OPPONENT_LEFT"})
        if not room.players:
            room.cancel_timer()
            self.rooms.pop(room.id, None)

    @staticmethod
    async def _send(ws: WebSocket, message: dict) -> None:
        await ws.send_text(json.dumps(message, ensure_ascii=False))

    async def _error(self, ws: WebSocket, detail: str) -> None:
        await self._send(ws, {"type": "ERROR", "detail": detail})


manager = RoomManager()
