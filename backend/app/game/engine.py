"""Jieqi (Dark Chess) rule engine.

Special rules vs. classical xiangqi (per design doc):
1. A DARK (face-down) piece may only be operated by its ``initial_owner`` side.
   Its first move/capture must follow the classical rules of the piece
   traditionally posted at its current (== initial) square -- the "blind move".
2. After its first legal move/capture the piece flips face-up, reveals its true
   code, and from then on obeys its TRUE kind and TRUE color -- which may hand
   the piece to the opponent.
3. Flipped XIANG/SHI (elephants/advisors) gain the Jieqi privilege: they may
   cross the river / leave the palace. (Blind moves from elephant/advisor
   squares still obey the classical restrictions.)
4. Check adjudication (xiangqi-style):
   * A side whose king is attacked is IN CHECK and the client is notified.
   * A move that leaves your OWN king in check is illegal (you must resolve
     the check; you may never walk into one).
   * If the side to move has no legal move at all: CHECKMATE when in check,
     STALEMATE otherwise -- both lose immediately.
   * Capturing the king remains a safety-net win condition.

Simplification (documented in README): no flying-general rule, no perpetual-
check / repetition adjudication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .board import (
    BLACK,
    COLS,
    RED,
    ROWS,
    Board,
    Coord,
    Piece,
    POSITION_RULE,
    color_of,
)

# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

RED_PALACE = (range(0, 3), range(3, 6))    # rows 0-2, cols 3-5
BLACK_PALACE = (range(7, 10), range(3, 6))  # rows 7-9, cols 3-5


def in_palace(coord: Coord, side: str) -> bool:
    rows, cols = RED_PALACE if side == RED else BLACK_PALACE
    return coord[0] in rows and coord[1] in cols


def crossed_river(coord: Coord, side: str) -> bool:
    return coord[0] >= 5 if side == RED else coord[0] <= 4


def own_half(coord: Coord, side: str) -> bool:
    return coord[0] <= 4 if side == RED else coord[0] >= 5


def _enemy(piece: Piece, side: str) -> bool:
    """Is ``piece`` a legal capture target for ``side``?"""
    if piece.face_up:
        return piece.color != side
    return piece.initial_owner != side  # never capture your own dark pieces


# ---------------------------------------------------------------------------
# movement generation
# ---------------------------------------------------------------------------

def _slide_moves(board: Board, coord: Coord, side: str, captures_only: bool = False) -> List[Coord]:
    """Rook-style sliding; cannon capture logic handled separately."""
    moves: List[Coord] = []
    r, c = coord
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        while board.in_bounds((nr, nc)):
            target = board.get((nr, nc))
            if target is None:
                if not captures_only:
                    moves.append((nr, nc))
            else:
                if not captures_only and _enemy(target, side):
                    moves.append((nr, nc))
                break
            nr, nc = nr + dr, nc + dc
    return moves


def _pao_moves(board: Board, coord: Coord, side: str) -> List[Coord]:
    moves: List[Coord] = []
    r, c = coord
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        jumped = False
        while board.in_bounds((nr, nc)):
            target = board.get((nr, nc))
            if not jumped:
                if target is None:
                    moves.append((nr, nc))
                else:
                    jumped = True  # this piece becomes the screen
            else:
                if target is not None:
                    if _enemy(target, side):
                        moves.append((nr, nc))
                    break
            nr, nc = nr + dr, nc + dc
    return moves


def _ma_moves(board: Board, coord: Coord, side: str) -> List[Coord]:
    r, c = coord
    moves: List[Coord] = []
    # (leg square, destination)
    patterns = (
        ((r, c + 1), (r - 1, c + 2)), ((r, c + 1), (r + 1, c + 2)),
        ((r, c - 1), (r - 1, c - 2)), ((r, c - 1), (r + 1, c - 2)),
        ((r + 1, c), (r + 2, c - 1)), ((r + 1, c), (r + 2, c + 1)),
        ((r - 1, c), (r - 2, c - 1)), ((r - 1, c), (r - 2, c + 1)),
    )
    for leg, dest in patterns:
        if not board.in_bounds(dest):
            continue
        if board.get(leg) is not None:  # hobbled horse leg
            continue
        target = board.get(dest)
        if target is None or _enemy(target, side):
            moves.append(dest)
    return moves


def _xiang_moves(board: Board, coord: Coord, side: str, may_cross_river: bool) -> List[Coord]:
    r, c = coord
    moves: List[Coord] = []
    for dr, dc in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
        dest = (r + dr, c + dc)
        eye = (r + dr // 2, c + dc // 2)
        if not board.in_bounds(dest):
            continue
        if not may_cross_river and not own_half(dest, side):
            continue
        if board.get(eye) is not None:  # blocked elephant eye
            continue
        target = board.get(dest)
        if target is None or _enemy(target, side):
            moves.append(dest)
    return moves


def _shi_moves(board: Board, coord: Coord, side: str, may_leave_palace: bool) -> List[Coord]:
    r, c = coord
    moves: List[Coord] = []
    for dr, dc in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        dest = (r + dr, c + dc)
        if not board.in_bounds(dest):
            continue
        if not may_leave_palace and not in_palace(dest, side):
            continue
        target = board.get(dest)
        if target is None or _enemy(target, side):
            moves.append(dest)
    return moves


def _king_moves(board: Board, coord: Coord, side: str) -> List[Coord]:
    r, c = coord
    moves: List[Coord] = []
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        dest = (r + dr, c + dc)
        if not board.in_bounds(dest) or not in_palace(dest, side):
            continue
        target = board.get(dest)
        if target is None or _enemy(target, side):
            moves.append(dest)
    return moves


def _soldier_moves(board: Board, coord: Coord, side: str) -> List[Coord]:
    r, c = coord
    forward = 1 if side == RED else -1
    candidates = [(r + forward, c)]
    if crossed_river(coord, side):
        candidates += [(r, c - 1), (r, c + 1)]
    moves: List[Coord] = []
    for dest in candidates:
        if not board.in_bounds(dest):
            continue
        target = board.get(dest)
        if target is None or _enemy(target, side):
            moves.append(dest)
    return moves


def moves_for_rule(board: Board, coord: Coord, rule_code: str, jieqi_privilege: bool) -> List[Coord]:
    """Generate legal destinations for a piece moving under ``rule_code``.

    ``jieqi_privilege`` is True for face-up pieces (elephants may cross the
    river, advisors may leave the palace) and False for blind moves.
    """
    side = color_of(rule_code)
    kind = rule_code.split("_", 1)[1]
    if kind == "JU":
        return _slide_moves(board, coord, side)
    if kind == "PAO":
        return _pao_moves(board, coord, side)
    if kind == "MA":
        return _ma_moves(board, coord, side)
    if kind == "XIANG":
        return _xiang_moves(board, coord, side, may_cross_river=jieqi_privilege)
    if kind == "SHI":
        return _shi_moves(board, coord, side, may_leave_palace=jieqi_privilege)
    if kind in ("SHUAI", "JIANG"):
        return _king_moves(board, coord, side)
    if kind in ("BING", "ZU"):
        return _soldier_moves(board, coord, side)
    raise ValueError(f"unknown piece kind: {rule_code}")


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------

@dataclass
class MoveResult:
    ok: bool
    error: Optional[str] = None
    flipped: Optional[str] = None          # true code, when the mover flipped
    captured: Optional[dict] = None        # {"state": ..., "code": ...}
    game_over: bool = False
    winner: Optional[str] = None
    reason: Optional[str] = None           # "KING_CAPTURED" | "CHECKMATE" | "STALEMATE"


class JieqiEngine:
    def __init__(self, board: Board, first: str = RED):
        self.board = board
        self.turn = first
        self.game_over = False
        self.winner: Optional[str] = None

    # -- queries ------------------------------------------------------------
    def operable(self, piece: Piece, side: str) -> bool:
        if piece.face_up:
            return piece.color == side
        return piece.initial_owner == side

    def _pseudo_legal_moves(self, coord: Coord, side: str) -> List[Coord]:
        """Movement-rule destinations, ignoring king safety."""
        piece = self.board.get(coord)
        if piece is None or not self.operable(piece, side):
            return []
        if piece.face_up:
            return moves_for_rule(self.board, coord, piece.code, jieqi_privilege=True)
        rule = POSITION_RULE.get(coord)
        if rule is None:  # a dark piece can only ever sit on a dark slot
            return []
        return moves_for_rule(self.board, coord, rule, jieqi_privilege=False)

    def legal_moves(self, coord: Coord, side: str) -> List[Coord]:
        """Fully legal destinations: never leaves your own king in check."""
        piece = self.board.get(coord)
        if piece is None or not self.operable(piece, side):
            return []
        moves: List[Coord] = []
        for to in self._pseudo_legal_moves(coord, side):
            undo = self._simulate(coord, to)
            safe = not self.is_in_check(side)
            self._undo_simulate(coord, to, undo)
            if safe:
                moves.append(to)
        return moves

    # -- check detection ------------------------------------------------------
    def is_in_check(self, side: str) -> bool:
        """Is ``side``'s king attacked by any enemy piece?

        Enemy dark pieces threaten per their blind-move (positional) rule --
        consistent with how they could actually capture.
        """
        king = self.board.find_king(side)
        if king is None:
            return False  # king already captured; game over handles it
        enemy = BLACK if side == RED else RED
        for r in range(ROWS):
            for c in range(COLS):
                p = self.board.grid[r][c]
                if p is None:
                    continue
                if p.face_up:
                    if p.color != enemy:
                        continue
                    rule, privilege = p.code, True
                else:
                    if p.initial_owner != enemy:
                        continue
                    rule = POSITION_RULE.get((r, c))
                    if rule is None:
                        continue
                    privilege = False
                if king in moves_for_rule(self.board, (r, c), rule, privilege):
                    return True
        return False

    # -- move simulation (for king-safety filtering) --------------------------
    def _simulate(self, frm: Coord, to: Coord):
        piece = self.board.get(frm)
        captured = self.board.get(to)
        was_face_up = piece.face_up
        self.board.set(to, piece)
        self.board.set(frm, None)
        if not was_face_up:
            piece.face_up = True  # a real move would flip it
        return captured, was_face_up

    def _undo_simulate(self, frm: Coord, to: Coord, undo) -> None:
        captured, was_face_up = undo
        piece = self.board.get(to)
        self.board.set(frm, piece)
        self.board.set(to, captured)
        piece.face_up = was_face_up

    def has_any_move(self, side: str) -> bool:
        for r in range(ROWS):
            for c in range(COLS):
                piece = self.board.grid[r][c]
                if piece is not None and self.operable(piece, side):
                    if self.legal_moves((r, c), side):
                        return True
        return False

    # -- mutation -----------------------------------------------------------
    def apply_move(self, frm: Coord, to: Coord, side: str) -> MoveResult:
        if self.game_over:
            return MoveResult(ok=False, error="game is over")
        if side != self.turn:
            return MoveResult(ok=False, error="not your turn")
        piece = self.board.get(frm)
        if piece is None:
            return MoveResult(ok=False, error="no piece at source")
        if not self.operable(piece, side):
            return MoveResult(ok=False, error="piece is not operable by you")
        if to not in self.legal_moves(frm, side):
            return MoveResult(ok=False, error="illegal move for this piece")

        target = self.board.get(to)
        captured: Optional[dict] = None
        if target is not None:
            # Captured dark pieces are revealed to both players.
            captured = {"state": "UP" if target.face_up else "DARK", "code": target.code}

        self.board.set(to, piece)
        self.board.set(frm, None)

        flipped: Optional[str] = None
        if not piece.face_up:
            piece.face_up = True
            flipped = piece.code

        result = MoveResult(ok=True, flipped=flipped, captured=captured)

        # victory: king captured
        if target is not None and target.code in ("R_SHUAI", "B_JIANG"):
            self.game_over = True
            self.winner = side
            result.game_over, result.winner, result.reason = True, side, "KING_CAPTURED"
            return result

        # victory: opponent has no legal move -- checkmate if in check,
        # stalemate otherwise; both lose immediately.
        opponent = BLACK if side == RED else RED
        if not self.has_any_move(opponent):
            self.game_over = True
            self.winner = side
            reason = "CHECKMATE" if self.is_in_check(opponent) else "STALEMATE"
            result.game_over, result.winner, result.reason = True, side, reason
            return result

        self.turn = opponent
        return result
