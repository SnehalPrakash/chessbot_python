#!/usr/bin/env python3
"""
ChessBot — Universal Chess Interface (UCI) Protocol Handler

Implements the standard UCI protocol for communication with chess GUIs
such as Arena, Cutechess, BanksiaGUI, and lichess-bot.

Usage:
    python main.py --uci

Protocol reference: https://backscattering.de/chess/uci/
"""

import sys
import chess
from engine import ChessEngine


ENGINE_NAME = "ChessBot"
ENGINE_AUTHOR = "ChessBot Team"


def uci_loop():
    """Main UCI command loop — reads from stdin, writes to stdout."""
    engine = ChessEngine()
    board = chess.Board()

    while True:
        try:
            line = input().strip()
        except EOFError:
            break

        if not line:
            continue

        tokens = line.split()
        cmd = tokens[0]

        if cmd == "uci":
            print(f"id name {ENGINE_NAME}")
            print(f"id author {ENGINE_AUTHOR}")
            print("uciok")
            sys.stdout.flush()

        elif cmd == "isready":
            print("readyok")
            sys.stdout.flush()

        elif cmd == "ucinewgame":
            engine.clear_tables()
            board = chess.Board()

        elif cmd == "position":
            board = _parse_position(tokens)

        elif cmd == "go":
            _handle_go(tokens, board, engine)

        elif cmd == "stop":
            engine.search_stopped = True

        elif cmd == "quit":
            break

        # Ignore unknown commands gracefully (per UCI spec)


def _parse_position(tokens: list[str]) -> chess.Board:
    """Parse 'position' command and return the resulting board.

    Formats:
        position startpos [moves e2e4 e7e5 ...]
        position fen <fen_string> [moves e2e4 e7e5 ...]
    """
    board = chess.Board()

    if len(tokens) < 2:
        return board

    idx = 2
    if tokens[1] == "startpos":
        board = chess.Board()
    elif tokens[1] == "fen":
        # Collect FEN parts (up to 6 tokens after "fen", until "moves" keyword)
        fen_parts = []
        while idx < len(tokens) and tokens[idx] != "moves":
            fen_parts.append(tokens[idx])
            idx += 1
        try:
            board = chess.Board(" ".join(fen_parts))
        except ValueError:
            board = chess.Board()

    # Find and apply moves
    if idx < len(tokens) and tokens[idx] == "moves":
        idx += 1

    while idx < len(tokens):
        try:
            move = chess.Move.from_uci(tokens[idx])
            if move in board.legal_moves:
                board.push(move)
            else:
                # Try promotion variants
                pushed = False
                for promo in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
                    pm = chess.Move(move.from_square, move.to_square, promotion=promo)
                    if pm in board.legal_moves:
                        board.push(pm)
                        pushed = True
                        break
                if not pushed:
                    break
        except ValueError:
            break
        idx += 1

    return board


def _handle_go(tokens: list[str], board: chess.Board, engine: ChessEngine):
    """Parse 'go' command and run the search."""
    params = _parse_go_params(tokens)

    # Handle depth-limited search by temporarily adjusting max_depth
    saved_max_depth = engine.max_depth
    if "depth" in params:
        engine.max_depth = params["depth"]

    time_limit = _compute_time_limit(params, board)

    def info_callback(info: dict):
        """Send UCI info lines during search."""
        score = info["score"]
        parts = [f"info depth {info['depth']}"]

        # Format score — detect mate scores (|score| > 90000)
        if abs(score) > 90000:
            mate_in = (100000 - abs(score) + 1) // 2
            if score < 0:
                mate_in = -mate_in
            parts.append(f"score mate {mate_in}")
        else:
            parts.append(f"score cp {score}")

        parts.append(f"nodes {info['nodes']}")
        parts.append(f"nps {info['nps']}")
        parts.append(f"time {int(info['time'] * 1000)}")

        if info.get("pv"):
            parts.append("pv " + " ".join(info["pv"]))

        print(" ".join(parts))
        sys.stdout.flush()

    move = engine.search(board, time_limit=time_limit, info_callback=info_callback)

    # Restore max depth after depth-limited search
    engine.max_depth = saved_max_depth

    if move:
        print(f"bestmove {move.uci()}")
    else:
        # Fallback — should not happen in normal play
        legal = list(board.legal_moves)
        if legal:
            print(f"bestmove {legal[0].uci()}")
        else:
            print("bestmove 0000")
    sys.stdout.flush()


def _parse_go_params(tokens: list[str]) -> dict:
    """Extract go sub-parameters into a dict."""
    params: dict[str, int] = {}
    i = 1
    while i < len(tokens):
        key = tokens[i]
        if key in ("movetime", "depth", "wtime", "btime", "winc", "binc", "movestogo"):
            if i + 1 < len(tokens):
                try:
                    params[key] = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
        elif key == "infinite":
            params["infinite"] = 1
        i += 1
    return params


def _compute_time_limit(params: dict, board: chess.Board) -> float:
    """Compute time limit in seconds from go parameters."""
    # Fixed move time (e.g., "go movetime 5000")
    if "movetime" in params:
        return params["movetime"] / 1000.0

    # Fixed depth — use generous time; iterative deepening stops at max_depth
    if "depth" in params:
        return 300.0

    # Infinite analysis
    if "infinite" in params:
        return 300.0

    # Clock-based time management (tournament play)
    if board.turn == chess.WHITE:
        remaining = params.get("wtime", 60000) / 1000.0
        increment = params.get("winc", 0) / 1000.0
    else:
        remaining = params.get("btime", 60000) / 1000.0
        increment = params.get("binc", 0) / 1000.0

    moves_to_go = params.get("movestogo", 30)

    # Allocate: remaining / moves_to_go + most of the increment
    time_for_move = remaining / moves_to_go + increment * 0.8

    # Safety: never use more than 1/3 of remaining time
    time_for_move = min(time_for_move, remaining / 3.0)

    # Minimum 0.1 seconds
    time_for_move = max(time_for_move, 0.1)

    return time_for_move
