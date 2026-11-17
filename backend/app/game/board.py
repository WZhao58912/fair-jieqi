"""Board data structure and initial-coordinate mapping for Jieqi.

Coordinate system (per design doc):
* 10 rows x 9 cols, row 0 is the RED back rank, row 9 the BLACK back rank.
* Red king (face-up) fixed at (0, 4); black king (face-up) fixed at (9, 4).
* Red dark pieces occupy the red half (rows 0-3, 15 slots excluding (0, 4)).
* Black dark pieces occupy the black half (rows 6-9, 15 slots excluding (9, 4)).

The shuffled 30-piece sequence fills ``ALL_DARK_SLOTS`` in order
(red slots row-major first, then black slots row-major).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

ROWS, COLS = 10, 9
RED, BLACK = "RED", "BLACK"

RED_KING_POS: Tuple[int, int] = (0, 4)
BLACK_KING_POS: Tuple[int, int] = (9, 4)

Coord = Tuple[int, int]


def _red_dark_slots() -> List[Coord]:
    slots: List[Coord] = []
    # Back rank (row 0) minus the king square.
    for c in (0, 1, 2, 3, 5, 6, 7, 8):
        slots.append((0, c))
    # Cannons.
    slots += [(2, 1), (2, 7)]
    # Soldiers.
    for c in (0, 2, 4, 6, 8):
        slots.append((3, c))
    return slots


def _black_dark_slots() -> List[Coord]:
    slots: List[Coord] = []
    # Soldiers.
    for c in (0, 2, 4, 6, 8):
        slots.append((6, c))
    # Cannons.
    slots += [(7, 1), (7, 7)]
    # Back rank (row 9) minus the king square.
    for c in (0, 1, 2, 3, 5, 6, 7, 8):
        slots.append((9, c))
    return slots


RED_DARK_SLOTS: List[Coord] = _red_dark_slots()
BLACK_DARK_SLOTS: List[Coord] = _black_dark_slots()
ALL_DARK_SLOTS: List[Coord] = RED_DARK_SLOTS + BLACK_DARK_SLOTS
assert len(ALL_DARK_SLOTS) == 30

# Traditional xiangqi piece governing the *blind move* from each dark slot.
# A dark piece has never moved, so its current square IS its initial square;
# its first move must follow the rules of the traditional piece posted there.
POSITION_RULE: Dict[Coord, str] = {}
for c, code in ((0, "JU"), (1, "MA"), (2, "XIANG"), (3, "SHI"),
                (5, "SHI"), (6, "XIANG"), (7, "MA"), (8, "JU")):
    POSITION_RULE[(0, c)] = f"R_{code}"
    POSITION_RULE[(9, c)] = f"B_{code}"
for c in (1, 7):
    POSITION_RULE[(2, c)] = "R_PAO"
    POSITION_RULE[(7, c)] = "B_PAO"
for c in (0, 2, 4, 6, 8):
    POSITION_RULE[(3, c)] = "R_BING"
    POSITION_RULE[(6, c)] = "B_ZU"


def color_of(piece_code: str) -> str:
    return RED if piece_code.startswith("R_") else BLACK


@dataclass
class Piece:
    """A piece on the board.

    ``code`` is the TRUE identity (e.g. "R_JU"). While ``face_up`` is False the
    true identity never leaves the server.
    """

    code: str
    face_up: bool
    initial_owner: str  # RED / BLACK -- the half the dark piece started on

    @property
    def color(self) -> str:
        return color_of(self.code)

    @property
    def kind(self) -> str:
        return self.code.split("_", 1)[1]


@dataclass
class Board:
    grid: List[List[Optional[Piece]]] = field(
        default_factory=lambda: [[None] * COLS for _ in range(ROWS)]
    )

    @classmethod
    def new_game(cls, shuffled: List[str]) -> "Board":
        """Build the initial position from a shuffled 30-piece sequence."""
        if len(shuffled) != len(ALL_DARK_SLOTS):
            raise ValueError("shuffled sequence must contain exactly 30 pieces")
        board = cls()
        board.set(RED_KING_POS, Piece("R_SHUAI", face_up=True, initial_owner=RED))
        board.set(BLACK_KING_POS, Piece("B_JIANG", face_up=True, initial_owner=BLACK))
        for slot, code in zip(ALL_DARK_SLOTS, shuffled):
            owner = RED if slot in RED_DARK_SLOTS else BLACK
            board.set(slot, Piece(code, face_up=False, initial_owner=owner))
        return board

    # -- basic accessors ----------------------------------------------------
    @staticmethod
    def in_bounds(coord: Coord) -> bool:
        r, c = coord
        return 0 <= r < ROWS and 0 <= c < COLS

    def get(self, coord: Coord) -> Optional[Piece]:
        r, c = coord
        return self.grid[r][c]

    def set(self, coord: Coord, piece: Optional[Piece]) -> None:
        r, c = coord
        self.grid[r][c] = piece

    def find_king(self, side: str) -> Optional[Coord]:
        target = "R_SHUAI" if side == RED else "B_JIANG"
        for r in range(ROWS):
            for c in range(COLS):
                p = self.grid[r][c]
                if p is not None and p.code == target:
                    return (r, c)
        return None

    # -- serialization ------------------------------------------------------
    def public_state(self) -> List[List[Optional[dict]]]:
        """What clients may see mid-game: dark pieces carry NO true identity."""
        out: List[List[Optional[dict]]] = []
        for r in range(ROWS):
            row: List[Optional[dict]] = []
            for c in range(COLS):
                p = self.grid[r][c]
                if p is None:
                    row.append(None)
                elif p.face_up:
                    row.append({"state": "UP", "code": p.code})
                else:
                    row.append({"state": "DARK", "initial_owner": p.initial_owner})
            out.append(row)
        return out
