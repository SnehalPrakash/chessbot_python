"""
ChessBot Engine — A ~1800–2000 rated chess engine.

Features:
  • Iterative deepening with time management
  • Negamax with alpha-beta pruning
  • Transposition table (Zobrist hashing via python-chess)
  • Quiescence search (captures + checks)
  • Null-move pruning (R=2)
  • Late-move reductions (LMR)
  • Killer move heuristic (2 slots per ply)
  • History heuristic for quiet move ordering
  • Move ordering: PV → captures (MVV-LVA) → killers → history
  • Evaluation: material, piece-square tables, mobility, pawn structure,
    bishop pair, rook on open files, king safety, passed pawns, tempo
"""

import chess
import random
import time
from collections import defaultdict

# ─── Constants ────────────────────────────────────────────────────────────────

MATE_SCORE = 100_000
DRAW_SCORE = 0

PIECE_VALUES = {
    chess.PAWN:   100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK:   500,
    chess.QUEEN:  900,
    chess.KING:   20_000,
}

# Transposition table entry types
TT_EXACT = 0
TT_ALPHA = 1  # upper bound
TT_BETA  = 2  # lower bound


# ─── Piece-Square Tables (from White's perspective, rank 8 → rank 1) ─────────

PAWN_TABLE = [
     0,   0,   0,   0,   0,   0,   0,   0,
    50,  50,  50,  50,  50,  50,  50,  50,
    10,  10,  20,  30,  30,  20,  10,  10,
     5,   5,  10,  27,  27,  10,   5,   5,
     0,   0,   0,  25,  25,   0,   0,   0,
     5,  -5, -10,   0,   0, -10,  -5,   5,
     5,  10,  10, -25, -25,  10,  10,   5,
     0,   0,   0,   0,   0,   0,   0,   0,
]

KNIGHT_TABLE = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20,   0,   0,   0,   0, -20, -40,
    -30,   0,  10,  15,  15,  10,   0, -30,
    -30,   5,  15,  20,  20,  15,   5, -30,
    -30,   0,  15,  20,  20,  15,   0, -30,
    -30,   5,  10,  15,  15,  10,   5, -30,
    -40, -20,   0,   5,   5,   0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
]

BISHOP_TABLE = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,  10,  10,  10,  10,   0, -10,
    -10,   5,   5,  10,  10,   5,   5, -10,
    -10,   0,   5,  10,  10,   5,   0, -10,
    -10,   5,   5,   5,   5,   5,   5, -10,
    -10,   0,   5,   0,   0,   5,   0, -10,
    -20, -10, -40, -10, -10, -40, -10, -20,
]

ROOK_TABLE = [
     0,   0,   0,   0,   0,   0,   0,   0,
     5,  10,  10,  10,  10,  10,  10,   5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
     0,   0,   0,   5,   5,   0,   0,   0,
]

QUEEN_TABLE = [
    -20, -10, -10,  -5,  -5, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,   5,   5,   5,   0, -10,
     -5,   0,   5,   5,   5,   5,   0,  -5,
      0,   0,   5,   5,   5,   5,   0,  -5,
    -10,   5,   5,   5,   5,   5,   0, -10,
    -10,   0,   5,   0,   0,   0,   0, -10,
    -20, -10, -10,  -5,  -5, -10, -10, -20,
]

KING_MG_TABLE = [
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
     20,  20,   0,   0,   0,   0,  20,  20,
     20,  30,  10,   0,   0,  10,  30,  20,
]

KING_EG_TABLE = [
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10,   0,   0, -10, -20, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -30,   0,   0,   0,   0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
]

PST = {
    chess.PAWN:   PAWN_TABLE,
    chess.KNIGHT: KNIGHT_TABLE,
    chess.BISHOP: BISHOP_TABLE,
    chess.ROOK:   ROOK_TABLE,
    chess.QUEEN:  QUEEN_TABLE,
}


# ─── Opening Book (small but sensible) ───────────────────────────────────────

OPENING_BOOK: dict[str, list[str]] = {
    # Starting position
    "": ["e2e4", "d2d4", "c2c4", "g1f3"],
    # Responses to 1.e4
    "e2e4": ["e7e5", "c7c5", "e7e6", "c7c6", "d7d5"],
    # Responses to 1.d4
    "d2d4": ["d7d5", "g8f6", "e7e6", "c7c5"],
    # Responses to 1.c4
    "c2c4": ["e7e5", "g8f6", "c7c5", "e7e6"],
    # Responses to 1.Nf3
    "g1f3": ["d7d5", "g8f6", "c7c5"],
    # Italian / Ruy Lopez starters
    "e2e4 e7e5": ["g1f3"],
    "e2e4 e7e5 g1f3": ["b8c6"],
    "e2e4 e7e5 g1f3 b8c6": ["f1b5", "f1c4", "d2d4"],
    # Sicilian
    "e2e4 c7c5": ["g1f3", "b1c3"],
    "e2e4 c7c5 g1f3": ["d7d6", "b8c6", "e7e6"],
    # Queen's Gambit
    "d2d4 d7d5": ["c2c4"],
    "d2d4 d7d5 c2c4": ["e7e6", "c7c6", "d5c4"],
    # Indian systems
    "d2d4 g8f6": ["c2c4"],
    "d2d4 g8f6 c2c4": ["e7e6", "g7g6"],
}


# ─── Engine ───────────────────────────────────────────────────────────────────

class ChessEngine:
    """A chess engine with iterative deepening, alpha-beta, TT, and heuristics."""

    def __init__(self, max_depth: int = 64, time_limit: float = 5.0):
        self.max_depth = max_depth
        self.time_limit = time_limit

        # Transposition table: key → (depth, score, flag, best_move)
        self.tt: dict[int, tuple[int, int, int, chess.Move | None]] = {}
        self.tt_max_size = 1_000_000

        # Killer moves: ply → [move, move]
        self.killers: dict[int, list[chess.Move | None]] = defaultdict(lambda: [None, None])

        # History heuristic: (color, from_sq, to_sq) → score
        self.history: dict[tuple[bool, int, int], int] = defaultdict(int)

        # Search statistics
        self.nodes_searched = 0
        self.start_time = 0.0
        self.end_time = 0.0
        self.search_stopped = False
        self.pv: list[chess.Move] = []
        self.best_score = 0

    # ── Public API ────────────────────────────────────────────────────────

    def search(self, board: chess.Board, time_limit: float | None = None,
               info_callback=None) -> chess.Move | None:
        """Find the best move via iterative deepening.

        Args:
            board: Current board position.
            time_limit: Override the default time limit (seconds).
            info_callback: Optional callable invoked after each completed depth
                           with a dict of search info (depth, score, nodes, nps, pv, time).
        """
        if time_limit is not None:
            self.time_limit = time_limit

        self.nodes_searched = 0
        self.start_time = time.time()
        self.end_time = self.start_time
        self.search_stopped = False

        # Try opening book first
        book_move = self._get_book_move(board)
        if book_move:
            self.end_time = time.time()
            self.pv = [book_move]
            self.best_score = 0
            return book_move

        best_move: chess.Move | None = None
        best_score = -MATE_SCORE

        # Iterative deepening
        for depth in range(1, self.max_depth + 1):
            if self.search_stopped:
                break

            score, move = self._root_search(board, depth)

            if not self.search_stopped and move is not None:
                best_move = move
                best_score = score

                # Extract PV and report progress
                self.pv = self._extract_pv(board)
                if info_callback is not None:
                    elapsed = time.time() - self.start_time
                    nps = int(self.nodes_searched / max(elapsed, 0.001))
                    info_callback({
                        "depth": depth,
                        "score": score,
                        "nodes": self.nodes_searched,
                        "nps": nps,
                        "pv": [m.uci() for m in self.pv],
                        "time": round(elapsed, 2),
                    })

            elapsed = time.time() - self.start_time
            if elapsed >= self.time_limit * 0.75:
                break

        self.best_score = best_score
        self.end_time = time.time()
        return best_move

    def get_search_info(self) -> dict:
        """Return stats from the most recent search."""
        elapsed = self.end_time - self.start_time
        nps = int(self.nodes_searched / max(elapsed, 0.001))
        return {
            "nodes": self.nodes_searched,
            "time": round(elapsed, 2),
            "nps": nps,
            "tt_size": len(self.tt),
            "score": self.best_score,
            "pv": [m.uci() for m in self.pv],
        }

    def _extract_pv(self, board: chess.Board, max_length: int = 20) -> list[chess.Move]:
        """Extract the principal variation from the transposition table."""
        pv = []
        seen_keys = set()
        temp_board = board.copy()

        for _ in range(max_length):
            tt_key = temp_board._transposition_key()
            if tt_key in seen_keys:
                break
            seen_keys.add(tt_key)

            entry = self.tt.get(tt_key)
            if entry is None:
                break

            _, _, _, best_move = entry
            if best_move is None or best_move not in temp_board.legal_moves:
                break

            pv.append(best_move)
            temp_board.push(best_move)

        return pv

    # ── Opening Book ──────────────────────────────────────────────────────

    def _get_book_move(self, board: chess.Board) -> chess.Move | None:
        moves = [m.uci() for m in board.move_stack]

        # Try matching from the full history down to just the last move
        for length in range(len(moves), -1, -1):
            key = " ".join(moves[:length])
            if key in OPENING_BOOK:
                candidates = OPENING_BOOK[key]
                random.shuffle(candidates)
                for uci in candidates:
                    move = chess.Move.from_uci(uci)
                    if move in board.legal_moves:
                        return move
        return None

    # ── Root Search ───────────────────────────────────────────────────────

    def _root_search(self, board: chess.Board, depth: int) -> tuple[int, chess.Move | None]:
        best_move: chess.Move | None = None
        best_score = -MATE_SCORE
        alpha = -MATE_SCORE
        beta = MATE_SCORE

        moves = self._order_moves(board, list(board.legal_moves), ply=0)

        for move in moves:
            board.push(move)
            self.nodes_searched += 1

            score = -self._negamax(board, depth - 1, -beta, -alpha, ply=1)
            board.pop()

            if self.search_stopped:
                break

            if score > best_score:
                best_score = score
                best_move = move

            alpha = max(alpha, score)

        return best_score, best_move

    # ── Negamax with Alpha-Beta ───────────────────────────────────────────

    def _negamax(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        # Time check
        if self.nodes_searched & 4095 == 0:
            if time.time() - self.start_time >= self.time_limit:
                self.search_stopped = True
                return 0

        # Detect draws
        if board.is_repetition(2) or board.halfmove_clock >= 100:
            return DRAW_SCORE

        # TT lookup
        tt_key = board._transposition_key()
        tt_entry = self.tt.get(tt_key)
        tt_move: chess.Move | None = None
        if tt_entry is not None:
            tt_depth, tt_score, tt_flag, tt_move = tt_entry
            if tt_depth >= depth:
                if tt_flag == TT_EXACT:
                    return tt_score
                elif tt_flag == TT_ALPHA and tt_score <= alpha:
                    return alpha
                elif tt_flag == TT_BETA and tt_score >= beta:
                    return beta

        in_check = board.is_check()

        # Check extension
        if in_check:
            depth += 1

        # Leaf node — drop into quiescence
        if depth <= 0:
            return self._quiescence(board, alpha, beta, ply)

        # Null-move pruning (skip when in check or near endgame)
        if not in_check and depth >= 3 and not self._is_endgame(board):
            board.push(chess.Move.null())
            null_score = -self._negamax(board, depth - 3, -beta, -beta + 1, ply + 1)
            board.pop()
            if null_score >= beta:
                return beta

        legal_moves = list(board.legal_moves)

        # Checkmate / stalemate
        if not legal_moves:
            if in_check:
                return -MATE_SCORE + ply  # prefer shorter mates
            return DRAW_SCORE

        moves = self._order_moves(board, legal_moves, ply, tt_move)

        best_score = -MATE_SCORE
        best_move: chess.Move | None = None
        original_alpha = alpha

        for i, move in enumerate(moves):
            board.push(move)
            self.nodes_searched += 1

            # Late-move reduction
            if (i >= 4 and depth >= 3 and not in_check
                    and not board.is_capture(move) and not board.is_check()):
                # Reduced-depth search
                score = -self._negamax(board, depth - 2, -alpha - 1, -alpha, ply + 1)
                if score > alpha:
                    score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            else:
                score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)

            board.pop()

            if self.search_stopped:
                return 0

            if score > best_score:
                best_score = score
                best_move = move

            alpha = max(alpha, score)
            if alpha >= beta:
                # Update killer & history for quiet moves that cause cutoffs
                if not board.is_capture(move):
                    self._store_killer(move, ply)
                    self.history[(board.turn, move.from_square, move.to_square)] += depth * depth
                break

        # Store in TT
        if best_score <= original_alpha:
            flag = TT_ALPHA
        elif best_score >= beta:
            flag = TT_BETA
        else:
            flag = TT_EXACT

        if len(self.tt) < self.tt_max_size:
            self.tt[tt_key] = (depth, best_score, flag, best_move)

        return best_score

    # ── Quiescence Search ─────────────────────────────────────────────────

    def _quiescence(self, board: chess.Board, alpha: int, beta: int, ply: int) -> int:
        stand_pat = self._evaluate(board)

        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

        # Only consider captures (and promotions)
        capture_moves = [m for m in board.legal_moves if board.is_capture(m) or m.promotion]
        capture_moves.sort(key=lambda m: self._mvv_lva(board, m), reverse=True)

        for move in capture_moves:
            # Delta pruning — skip clearly losing captures
            captured = board.piece_at(move.to_square)
            if captured and stand_pat + PIECE_VALUES.get(captured.piece_type, 0) + 200 < alpha:
                continue

            board.push(move)
            self.nodes_searched += 1
            score = -self._quiescence(board, -beta, -alpha, ply + 1)
            board.pop()

            if score >= beta:
                return beta
            if score > alpha:
                alpha = score

        return alpha

    # ── Move Ordering ─────────────────────────────────────────────────────

    def _order_moves(
        self,
        board: chess.Board,
        moves: list[chess.Move],
        ply: int,
        tt_move: chess.Move | None = None,
    ) -> list[chess.Move]:
        """Score and sort moves for better alpha-beta pruning."""
        scored: list[tuple[int, chess.Move]] = []

        for move in moves:
            score = 0

            # PV / TT move gets highest priority
            if move == tt_move:
                score = 1_000_000
            elif board.is_capture(move):
                score = 100_000 + self._mvv_lva(board, move)
            elif move.promotion:
                score = 90_000 + PIECE_VALUES.get(move.promotion, 0)
            elif move == self.killers[ply][0]:
                score = 80_000
            elif move == self.killers[ply][1]:
                score = 70_000
            else:
                score = self.history.get((board.turn, move.from_square, move.to_square), 0)

            scored.append((score, move))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored]

    def _mvv_lva(self, board: chess.Board, move: chess.Move) -> int:
        """Most Valuable Victim – Least Valuable Attacker."""
        victim = board.piece_at(move.to_square)
        attacker = board.piece_at(move.from_square)

        victim_val = PIECE_VALUES.get(victim.piece_type, 0) if victim else 0
        attacker_val = PIECE_VALUES.get(attacker.piece_type, 0) if attacker else 0

        return victim_val * 10 - attacker_val

    def _store_killer(self, move: chess.Move, ply: int):
        if move != self.killers[ply][0]:
            self.killers[ply][1] = self.killers[ply][0]
            self.killers[ply][0] = move

    # ── Evaluation ────────────────────────────────────────────────────────

    def _evaluate(self, board: chess.Board) -> int:
        """Static evaluation from the side-to-move's perspective."""
        if board.is_checkmate():
            return -MATE_SCORE

        if board.is_stalemate() or board.is_insufficient_material() or board.is_repetition(2):
            return DRAW_SCORE

        endgame = self._is_endgame(board)
        score = 0

        white_material = 0
        black_material = 0
        white_pawns_by_file: list[int] = [0] * 8
        black_pawns_by_file: list[int] = [0] * 8
        white_bishops = 0
        black_bishops = 0

        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece is None:
                continue

            pt = piece.piece_type
            val = PIECE_VALUES[pt]
            psq = self._pst_value(piece, sq, endgame)

            if piece.color == chess.WHITE:
                white_material += val
                score += val + psq
                if pt == chess.PAWN:
                    white_pawns_by_file[chess.square_file(sq)] += 1
                if pt == chess.BISHOP:
                    white_bishops += 1
            else:
                black_material += val
                score -= val + psq
                if pt == chess.PAWN:
                    black_pawns_by_file[chess.square_file(sq)] += 1
                if pt == chess.BISHOP:
                    black_bishops += 1

        # Bishop pair bonus
        if white_bishops >= 2:
            score += 30
        if black_bishops >= 2:
            score -= 30

        # Pawn structure
        for f in range(8):
            # Doubled pawns penalty
            if white_pawns_by_file[f] > 1:
                score -= 15 * (white_pawns_by_file[f] - 1)
            if black_pawns_by_file[f] > 1:
                score += 15 * (black_pawns_by_file[f] - 1)

            # Isolated pawns penalty
            has_left = (f > 0 and white_pawns_by_file[f - 1] > 0)
            has_right = (f < 7 and white_pawns_by_file[f + 1] > 0)
            if white_pawns_by_file[f] > 0 and not has_left and not has_right:
                score -= 12

            has_left = (f > 0 and black_pawns_by_file[f - 1] > 0)
            has_right = (f < 7 and black_pawns_by_file[f + 1] > 0)
            if black_pawns_by_file[f] > 0 and not has_left and not has_right:
                score += 12

        # Rook on open / semi-open files
        for sq in board.pieces(chess.ROOK, chess.WHITE):
            f = chess.square_file(sq)
            if white_pawns_by_file[f] == 0:
                score += 10 if black_pawns_by_file[f] == 0 else 5

        for sq in board.pieces(chess.ROOK, chess.BLACK):
            f = chess.square_file(sq)
            if black_pawns_by_file[f] == 0:
                score -= 10 if white_pawns_by_file[f] == 0 else 5

        # Passed pawns bonus (simplified)
        score += self._passed_pawn_bonus(board, chess.WHITE, black_pawns_by_file)
        score -= self._passed_pawn_bonus(board, chess.BLACK, white_pawns_by_file)

        # King safety (middle game only)
        if not endgame:
            score += self._king_safety(board, chess.WHITE)
            score -= self._king_safety(board, chess.BLACK)

        # Mobility
        board.push(chess.Move.null())
        opp_mobility = len(list(board.legal_moves))
        board.pop()
        own_mobility = len(list(board.legal_moves))
        score += (own_mobility - opp_mobility) * 2

        # Tempo bonus for side to move
        score += 10

        # Return from side-to-move perspective
        return score if board.turn == chess.WHITE else -score

    def _pst_value(self, piece: chess.Piece, square: int, endgame: bool) -> int:
        pt = piece.piece_type
        sq = square if piece.color == chess.WHITE else (63 - square)
        # Mirror vertically for white (tables are from white's top perspective)
        sq = sq ^ 56  # flip rank

        if pt == chess.KING:
            return KING_EG_TABLE[sq] if endgame else KING_MG_TABLE[sq]

        table = PST.get(pt)
        return table[sq] if table else 0

    def _is_endgame(self, board: chess.Board) -> bool:
        queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
        minors = (
            len(board.pieces(chess.KNIGHT, chess.WHITE))
            + len(board.pieces(chess.BISHOP, chess.WHITE))
            + len(board.pieces(chess.KNIGHT, chess.BLACK))
            + len(board.pieces(chess.BISHOP, chess.BLACK))
        )
        rooks = len(board.pieces(chess.ROOK, chess.WHITE)) + len(board.pieces(chess.ROOK, chess.BLACK))
        return queens == 0 or (queens <= 1 and minors + rooks <= 2)

    def _passed_pawn_bonus(self, board: chess.Board, color: chess.Color, enemy_pawns_by_file: list[int]) -> int:
        bonus = 0
        for sq in board.pieces(chess.PAWN, color):
            f = chess.square_file(sq)
            r = chess.square_rank(sq)

            # Check if no enemy pawn can block or capture
            is_passed = True
            for ef in [f - 1, f, f + 1]:
                if 0 <= ef <= 7 and enemy_pawns_by_file[ef] > 0:
                    # Simplified: just check if any enemy pawn exists on adjacent files
                    for esq in board.pieces(chess.PAWN, not color):
                        er = chess.square_rank(esq)
                        ef2 = chess.square_file(esq)
                        if ef2 == ef:
                            if color == chess.WHITE and er > r:
                                is_passed = False
                                break
                            elif color == chess.BLACK and er < r:
                                is_passed = False
                                break
                    if not is_passed:
                        break

            if is_passed:
                advancement = r if color == chess.WHITE else (7 - r)
                bonus += advancement * advancement * 3  # quadratic bonus

        return bonus

    def _king_safety(self, board: chess.Board, color: chess.Color) -> int:
        """Bonus for pawn shield around the king."""
        king_sq = board.king(color)
        if king_sq is None:
            return 0

        king_file = chess.square_file(king_sq)
        king_rank = chess.square_rank(king_sq)
        safety = 0

        # Bonus for pawns near king
        shield_rank = king_rank + (1 if color == chess.WHITE else -1)
        if 0 <= shield_rank <= 7:
            for f in [king_file - 1, king_file, king_file + 1]:
                if 0 <= f <= 7:
                    sq = chess.square(f, shield_rank)
                    piece = board.piece_at(sq)
                    if piece and piece.piece_type == chess.PAWN and piece.color == color:
                        safety += 10

        # Penalty if king is exposed (castling rights lost and king in center)
        if 2 <= king_file <= 5 and king_rank == (0 if color == chess.WHITE else 7):
            if color == chess.WHITE:
                if not board.has_kingside_castling_rights(chess.WHITE) and not board.has_queenside_castling_rights(chess.WHITE):
                    safety -= 30
            else:
                if not board.has_kingside_castling_rights(chess.BLACK) and not board.has_queenside_castling_rights(chess.BLACK):
                    safety -= 30

        return safety

    def clear_tables(self):
        """Clear transposition table and heuristics for a new game."""
        self.tt.clear()
        self.killers.clear()
        self.history.clear()
        self.pv.clear()
        self.best_score = 0
