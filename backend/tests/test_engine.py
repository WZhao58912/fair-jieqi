"""Tests for the Jieqi rule engine."""

import pytest

from app.core.fair import STANDARD_DARK_PIECES
from app.game.board import (
    ALL_DARK_SLOTS,
    BLACK,
    BLACK_KING_POS,
    RED,
    RED_KING_POS,
    Board,
    Piece,
)
from app.game.engine import JieqiEngine


def fresh_engine() -> JieqiEngine:
    """A real game built from the (unshuffled) standard pool."""
    return JieqiEngine(Board.new_game(STANDARD_DARK_PIECES.copy()))


def dark(code: str, owner: str) -> Piece:
    return Piece(code, face_up=False, initial_owner=owner)


def up(code: str) -> Piece:
    owner = RED if code.startswith("R_") else BLACK
    return Piece(code, face_up=True, initial_owner=owner)


# ---------------------------------------------------------------------------
# initial layout
# ---------------------------------------------------------------------------

def test_initial_layout():
    eng = fresh_engine()
    assert eng.board.get(RED_KING_POS).code == "R_SHUAI"
    assert eng.board.get(BLACK_KING_POS).code == "B_JIANG"
    darks = [(s, eng.board.get(s)) for s in ALL_DARK_SLOTS]
    assert all(p is not None and not p.face_up for _, p in darks)
    assert sum(1 for s, _ in darks if s[0] <= 3) == 15
    for slot, piece in darks:
        assert piece.initial_owner == (RED if slot[0] <= 3 else BLACK)
    # public state must not leak identities
    public = eng.board.public_state()
    assert public[0][0] == {"state": "DARK", "initial_owner": "RED"}
    assert public[0][4] == {"state": "UP", "code": "R_SHUAI"}


# ---------------------------------------------------------------------------
# blind-move rules (first move follows the piece posted at that square)
# ---------------------------------------------------------------------------

def test_blind_ju_slides_like_rook():
    eng = fresh_engine()
    moves = eng.legal_moves((0, 0), RED)
    assert (1, 0) in moves and (2, 0) in moves  # column clear until soldier row
    assert (3, 0) not in moves                  # own dark soldier blocks
    assert (1, 1) not in moves                  # no diagonal rook move


def test_blind_ma_hobbled_leg():
    eng = fresh_engine()
    # (0,1) horse: leg (0,2) occupied -> (1,3) blocked; (2,0)/(2,2) open.
    assert sorted(eng.legal_moves((0, 1), RED)) == [(2, 0), (2, 2)]


def test_blind_pao_needs_screen_to_capture():
    eng = fresh_engine()
    moves = eng.legal_moves((2, 1), RED)
    assert (1, 1) in moves and (6, 1) in moves  # free slide down the file
    assert (7, 1) not in moves                  # enemy dark pao, but no screen
    assert (2, 7) not in moves                  # own dark piece
    res = eng.apply_move((2, 1), (7, 1), RED)
    assert not res.ok


def test_blind_pao_captures_over_exactly_one_screen():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((2, 1), dark("R_PAO", RED))
    board.set((4, 1), up("B_BING"))             # the screen
    board.set((6, 1), up("B_ZU"))               # target behind the screen
    eng = JieqiEngine(board)
    assert (6, 1) in eng.legal_moves((2, 1), RED)
    res = eng.apply_move((2, 1), (6, 1), RED)
    assert res.ok and res.captured["code"] == "B_ZU"


def test_blind_xiang_and_shi_follow_classical_limits():
    eng = fresh_engine()
    assert sorted(eng.legal_moves((0, 2), RED)) == [(2, 0), (2, 4)]  # elephant
    assert eng.legal_moves((0, 3), RED) == [(1, 4)]                  # advisor, palace-bound


def test_blind_bing_moves_forward_only():
    eng = fresh_engine()
    assert eng.legal_moves((3, 0), RED) == [(4, 0)]   # not across the river yet
    assert eng.legal_moves((6, 4), BLACK) == [(5, 4)]


def test_blind_move_rejects_wrong_rule():
    eng = fresh_engine()
    res = eng.apply_move((0, 0), (1, 1), RED)  # rook square, diagonal move
    assert not res.ok and "illegal" in res.error


# ---------------------------------------------------------------------------
# flipping and ownership transfer
# ---------------------------------------------------------------------------

def test_first_move_flips_but_color_never_changes():
    """A flipped piece reveals only its kind; ownership stays with the mover."""
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((3, 0), dark("R_JU", RED))  # red-side dark piece, truly a red rook
    eng = JieqiEngine(board)

    res = eng.apply_move((3, 0), (4, 0), RED)  # blind soldier step
    assert res.ok and res.flipped == "R_JU"
    piece = eng.board.get((4, 0))
    assert piece.face_up and piece.color == RED
    assert eng.operable(piece, RED)           # still ours -- never handed over
    assert not eng.operable(piece, BLACK)

    res = eng.apply_move((9, 4), (8, 4), BLACK)  # black king steps up
    assert res.ok
    res = eng.apply_move((4, 0), (4, 8), RED)  # now a real rook, still red
    assert res.ok


def test_real_game_flips_stay_in_their_half_color():
    """Every flip in a real game must reveal a piece of the mover's color."""
    eng = fresh_engine()
    for frm, to, side in [
        ((3, 0), (4, 0), RED),
        ((6, 0), (5, 0), BLACK),
        ((3, 4), (4, 4), RED),
        ((6, 4), (5, 4), BLACK),
    ]:
        res = eng.apply_move(frm, to, side)
        assert res.ok and res.flipped is not None
        prefix = "R_" if side == RED else "B_"
        assert res.flipped.startswith(prefix), (side, res.flipped)


def test_cannot_move_opponents_dark_piece():
    eng = fresh_engine()
    res = eng.apply_move((6, 0), (5, 0), RED)  # black-half dark piece
    assert not res.ok


def test_cannot_capture_own_dark_piece():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((4, 0), up("R_JU"))
    board.set((4, 3), dark("B_MA", BLACK))  # enemy dark piece is capturable
    board.set((4, 6), dark("R_MA", RED))   # own dark piece blocks the file
    eng = JieqiEngine(board)
    moves = eng.legal_moves((4, 0), RED)
    assert (4, 3) in moves and (4, 2) in moves
    assert (4, 6) not in moves              # cannot capture your own dark piece
    res = eng.apply_move((4, 0), (4, 3), RED)
    assert res.ok and res.captured == {"state": "DARK", "code": "B_MA"}


def test_turn_alternation():
    eng = fresh_engine()
    assert eng.turn == RED
    res = eng.apply_move((3, 0), (4, 0), RED)
    assert res.ok and eng.turn == BLACK
    res = eng.apply_move((4, 0), (5, 0), RED)
    assert not res.ok and "turn" in res.error


# ---------------------------------------------------------------------------
# jieqi privileges after flipping
# ---------------------------------------------------------------------------

def test_flipped_xiang_may_cross_river():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((4, 4), up("R_XIANG"))
    eng = JieqiEngine(board)
    moves = eng.legal_moves((4, 4), RED)
    assert (6, 2) in moves and (6, 6) in moves  # across the river
    assert (2, 2) in moves


def test_flipped_shi_may_leave_palace():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((4, 4), up("B_SHI"))
    eng = JieqiEngine(board, first=BLACK)
    moves = eng.legal_moves((4, 4), BLACK)
    assert sorted(moves) == [(3, 3), (3, 5), (5, 3), (5, 5)]


def test_flipped_soldier_obeys_its_true_color():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((4, 4), up("B_ZU"))  # black soldier deep in red's half: crossed
    eng = JieqiEngine(board, first=BLACK)
    moves = eng.legal_moves((4, 4), BLACK)
    assert (3, 4) in moves                    # forward (toward row 0)
    assert (4, 3) in moves and (4, 5) in moves  # sideways after crossing
    assert (5, 4) not in moves                # never backward


# ---------------------------------------------------------------------------
# victory conditions
# ---------------------------------------------------------------------------

def test_king_capture_wins():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((9, 0), up("R_JU"))
    eng = JieqiEngine(board)
    res = eng.apply_move((9, 0), (9, 4), RED)
    assert res.ok and res.game_over and res.winner == RED
    assert res.reason == "KING_CAPTURED"
    assert not eng.apply_move((0, 4), (1, 4), BLACK).ok  # game over


def test_stalemate_loses():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((5, 0), up("R_JU"))
    # Black king boxed in by its own pieces; the (8,4) dark piece sits on a
    # non-slot square so it has no blind rule and cannot move.
    board.set((8, 4), dark("B_SHI", BLACK))
    board.set((9, 3), dark("B_SHI", BLACK))
    board.set((9, 5), dark("B_SHI", BLACK))
    eng = JieqiEngine(board)
    assert not eng.has_any_move(BLACK)
    res = eng.apply_move((5, 0), (5, 1), RED)
    assert res.ok and res.game_over and res.winner == RED
    assert res.reason == "STALEMATE"


# ---------------------------------------------------------------------------
# check, forced resolution, checkmate
# ---------------------------------------------------------------------------

def test_check_is_detected_and_must_be_resolved():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((2, 4), up("B_JU"))  # black rook checking the red king along file 4
    board.set((2, 0), up("R_JU"))  # red rook can capture the checker along row 2
    eng = JieqiEngine(board)

    assert eng.is_in_check(RED)
    assert not eng.is_in_check(BLACK)

    rook_moves = eng.legal_moves((2, 0), RED)
    assert (2, 4) in rook_moves       # capturing the checker resolves the check
    assert (3, 0) not in rook_moves   # anything else leaves the king in check

    king_moves = eng.legal_moves((0, 4), RED)
    assert (1, 4) not in king_moves   # still on the checking file
    assert (0, 3) in king_moves and (0, 5) in king_moves

    res = eng.apply_move((2, 0), (3, 0), RED)
    assert not res.ok and "illegal" in res.error  # ignored the check -> rejected

    res = eng.apply_move((2, 0), (2, 4), RED)     # capture the checker
    assert res.ok and not eng.is_in_check(RED)


def test_cannot_move_into_check():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((5, 5), up("B_JU"))  # controls file 5
    eng = JieqiEngine(board)
    assert (0, 5) not in eng.legal_moves((0, 4), RED)  # walking onto the file
    res = eng.apply_move((0, 4), (0, 5), RED)
    assert not res.ok


def test_pinned_piece_cannot_abandon_its_king():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((2, 4), up("R_SHI"))  # red advisor pinning itself on file 4
    board.set((6, 4), up("B_JU"))   # black rook behind it on the same file
    eng = JieqiEngine(board)
    assert not eng.is_in_check(RED)               # advisor currently blocks
    assert eng.legal_moves((2, 4), RED) == []     # every advisor move exposes the king


def test_dark_pieces_threaten_per_positional_rule():
    """A dark piece exerts attack per its blind-move rule (synthetic position:
    the red king is placed mid-board purely to sit on the dark cannon's file)."""
    board = Board()
    board.set((4, 1), up("R_SHUAI"))         # synthetic king position
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((7, 1), dark("B_JU", BLACK))   # black dark piece on a cannon slot
    eng = JieqiEngine(board)
    assert not eng.is_in_check(RED)          # no screen -> cannon cannot capture

    board.set((5, 1), up("B_XIANG"))         # exactly one screen appears
    assert eng.is_in_check(RED)              # cannon now threatens the king

    board.set((6, 1), up("R_XIANG"))         # a second piece -> two screens
    assert not eng.is_in_check(RED)


def test_checkmate_ends_the_game():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((1, 7), up("B_JU"))  # controls row 1
    board.set((9, 0), up("B_JU"))
    eng = JieqiEngine(board, first=BLACK)
    res = eng.apply_move((9, 0), (0, 0), BLACK)  # back-rank mate
    assert res.ok and res.game_over and res.winner == BLACK
    assert res.reason == "CHECKMATE"
    assert not eng.apply_move((0, 4), (0, 3), RED).ok  # game over


def test_stalemate_without_check_is_still_a_loss():
    board = Board()
    board.set(RED_KING_POS, up("R_SHUAI"))
    board.set(BLACK_KING_POS, up("B_JIANG"))
    board.set((5, 0), up("R_JU"))
    board.set((8, 4), dark("B_SHI", BLACK))
    board.set((9, 3), dark("B_SHI", BLACK))
    board.set((9, 5), dark("B_SHI", BLACK))
    eng = JieqiEngine(board)
    assert not eng.is_in_check(BLACK)
    res = eng.apply_move((5, 0), (5, 1), RED)
    assert res.ok and res.game_over and res.winner == RED
    assert res.reason == "STALEMATE"
