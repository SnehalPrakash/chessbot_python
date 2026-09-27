"""
ChessBot — Rich Terminal UI

A beautiful, full-featured terminal interface for playing chess against the engine.

Features:
  • Colorful board with Unicode pieces and rank/file labels
  • Move history panel with algebraic notation
  • Captured pieces display
  • Engine thinking stats (nodes, NPS, time)
  • Undo/redo support
  • Game save/load (PGN format)
  • Difficulty levels (time-based)
  • Animated thinking spinner
  • Input validation with helpful error messages
"""

import chess
import chess.pgn
import os
import io
import time
import datetime
from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel

from rich.text import Text
from rich.columns import Columns
from rich.prompt import Prompt
from rich.layout import Layout
from rich.live import Live
from rich.spinner import Spinner
from rich import box

from engine import ChessEngine

console = Console()

# ─── Theme / Constants ────────────────────────────────────────────────────────

PIECE_UNICODE = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}

LIGHT_SQUARE = "on grey85"
DARK_SQUARE  = "on grey42"

PIECE_STYLE = {
    True:  "bold bright_white",  # White pieces
    False: "bold grey23",        # Black pieces — dark but visible on both square colors
}

DIFFICULTY_LEVELS = {
    "beginner":     {"time": 1.0,  "label": "Beginner",      "elo": "~1200"},
    "intermediate": {"time": 3.0,  "label": "Intermediate",  "elo": "~1600"},
    "advanced":     {"time": 6.0,  "label": "Advanced",       "elo": "~1900"},
    "expert":       {"time": 10.0, "label": "Expert",         "elo": "~2100"},
}

SAVE_DIR = Path(__file__).parent / "saved_games"
SAVE_DIR.mkdir(exist_ok=True)


# ─── UI Helpers ───────────────────────────────────────────────────────────────

def render_board(board: chess.Board, last_move: chess.Move | None = None, flipped: bool = False) -> Text:
    """Render a colorful chess board as a Rich Text object."""
    output = Text()

    ranks = range(8) if flipped else range(7, -1, -1)

    for rank in ranks:
        # Rank label
        output.append(f" {rank + 1} ", style="bold cyan")

        files = range(7, -1, -1) if flipped else range(8)
        for file in files:
            sq = chess.square(file, rank)
            is_light = (file + rank) % 2 != 0
            bg = LIGHT_SQUARE if is_light else DARK_SQUARE

            # Highlight last move squares
            if last_move and sq in (last_move.from_square, last_move.to_square):
                bg = "on dark_goldenrod"

            piece = board.piece_at(sq)
            if piece:
                symbol = PIECE_UNICODE.get(piece.symbol(), "?")
                fg = PIECE_STYLE[piece.color]
                output.append(f" {symbol} ", style=f"{fg} {bg}")
            else:
                output.append("   ", style=bg)

        output.append("\n")

    # File labels
    output.append("   ", style="")  # offset for rank label
    files_str = "abcdefgh" if not flipped else "hgfedcba"
    for ch in files_str:
        output.append(f" {ch} ", style="bold cyan")

    return output


def render_captured(board: chess.Board) -> Panel:
    """Show captured pieces for each side."""
    all_pieces = {
        chess.WHITE: {chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1, chess.KING: 1},
        chess.BLACK: {chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1, chess.KING: 1},
    }

    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece:
            all_pieces[piece.color][piece.piece_type] -= 1

    white_captured = []
    black_captured = []

    piece_chars = {chess.PAWN: "♟", chess.KNIGHT: "♞", chess.BISHOP: "♝", chess.ROOK: "♜", chess.QUEEN: "♛"}

    for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]:
        white_captured.extend([piece_chars[pt]] * all_pieces[chess.BLACK][pt])  # White captured black pieces
        black_captured.extend([piece_chars[pt]] * all_pieces[chess.WHITE][pt])  # Black captured white pieces

    w_line = Text("White captured: ", style="dim")
    w_line.append(" ".join(white_captured) if white_captured else "—", style="bold white")

    b_line = Text("Black captured: ", style="dim")
    b_line.append(" ".join(black_captured) if black_captured else "—", style="bold grey50")

    return Panel(
        Group(w_line, b_line),
        title="[bold magenta]⚔ Captures[/]",
        border_style="magenta",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def render_move_history(board: chess.Board) -> Panel:
    """Show move history in algebraic notation, two columns."""
    moves = []
    temp_board = chess.Board()
    for move in board.move_stack:
        san = temp_board.san(move)
        moves.append(san)
        temp_board.push(move)

    lines = []
    for i in range(0, len(moves), 2):
        move_num = i // 2 + 1
        white_move = moves[i]
        black_move = moves[i + 1] if i + 1 < len(moves) else ""
        lines.append(f"[cyan]{move_num:>3}.[/] [bold white]{white_move:<8}[/] [bold grey50]{black_move}[/]")

    # Show last 15 moves to avoid overflow
    if len(lines) > 15:
        lines = ["    [dim]...[/]"] + lines[-15:]

    content = "\n".join(lines) if lines else "[dim]No moves yet[/]"
    return Panel(
        content,
        title="[bold yellow]📜 Moves[/]",
        border_style="yellow",
        box=box.ROUNDED,
        width=28,
        padding=(0, 1),
    )


def render_status(board: chess.Board, engine_info: dict | None = None, difficulty: str = "intermediate") -> Panel:
    """Show game status and engine info."""
    if board.is_checkmate():
        winner = "Black" if board.turn == chess.WHITE else "White"
        status = f"[bold red]♚ CHECKMATE — {winner} wins![/]"
    elif board.is_stalemate():
        status = "[bold yellow]½ STALEMATE — Draw![/]"
    elif board.is_insufficient_material():
        status = "[bold yellow]½ DRAW — Insufficient material[/]"
    elif board.can_claim_threefold_repetition():
        status = "[bold yellow]½ Threefold repetition available[/]"
    elif board.is_check():
        who = "White" if board.turn == chess.WHITE else "Black"
        status = f"[bold red]⚡ {who} is in CHECK![/]"
    else:
        who = "White" if board.turn == chess.WHITE else "Black"
        status = f"[bold green]● {who} to move[/]"

    level = DIFFICULTY_LEVELS[difficulty]
    info_text = f"Difficulty: [bold]{level['label']}[/] ({level['elo']})"

    if engine_info:
        info_text += (
            f"\n[dim]Last search: {engine_info['nodes']:,} nodes in {engine_info['time']}s"
            f" ({engine_info['nps']:,} NPS) | TT: {engine_info['tt_size']:,}[/]"
        )

    return Panel(
        f"{status}\n{info_text}",
        title="[bold blue]♛ Status[/]",
        border_style="blue",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def render_help() -> Panel:
    """Show available commands."""
    cmds = [
        ("[bold cyan]e2e4[/]  or  [bold cyan]Nf3[/]", "Make a move (UCI or SAN)"),
        ("[bold cyan]undo[/]", "Undo last full move"),
        ("[bold cyan]hint[/]", "Get a move suggestion"),
        ("[bold cyan]flip[/]", "Flip the board"),
        ("[bold cyan]save[/]", "Save game to PGN file"),
        ("[bold cyan]load[/]", "Load game from PGN file"),
        ("[bold cyan]level[/]", "Change difficulty"),
        ("[bold cyan]eval[/]", "Show position evaluation"),
        ("[bold cyan]resign[/]", "Resign the game"),
        ("[bold cyan]new[/]", "Start a new game"),
        ("[bold cyan]quit[/]", "Exit the program"),
    ]
    content = "\n".join(f"  {cmd:<30s} {desc}" for cmd, desc in cmds)
    return Panel(
        content,
        title="[bold green]⌨ Commands[/]",
        border_style="green",
        box=box.ROUNDED,
        padding=(0, 1),
    )


# ─── Game Logic ───────────────────────────────────────────────────────────────

class ChessGame:
    def __init__(self):
        self.board = chess.Board()
        self.engine = ChessEngine()
        self.difficulty = "intermediate"
        self.flipped = False
        self.last_move: chess.Move | None = None
        self.engine_info: dict | None = None
        self.undo_stack: list[chess.Move] = []
        self.player_color = chess.WHITE

    def display(self):
        """Render the full game view."""
        board_widget = render_board(self.board, self.last_move, self.flipped)
        history_widget = render_move_history(self.board)
        status_widget = render_status(self.board, self.engine_info, self.difficulty)
        captured_widget = render_captured(self.board)

        # Layout: board + history side by side, status below
        board_panel = Panel(
            board_widget,
            title="[bold white]♜ ChessBot ♜[/]",
            border_style="bright_white",
            box=box.DOUBLE,
            padding=(0, 1),
        )

        main_row = Columns([board_panel, history_widget], padding=1)
        console.print()
        console.print(main_row)
        console.print(Columns([status_widget, captured_widget], padding=1))

    def engine_move(self):
        """Let the engine play its move with a thinking animation."""
        time_limit = DIFFICULTY_LEVELS[self.difficulty]["time"]

        with console.status("[bold magenta]🤔 Engine is thinking...[/]", spinner="dots12"):
            move = self.engine.search(self.board, time_limit=time_limit)

        if move:
            san = self.board.san(move)
            self.board.push(move)
            self.last_move = move
            self.engine_info = self.engine.get_search_info()
            self.undo_stack.clear()
            console.print(f"  [bold magenta]Engine plays:[/] [bold white]{san}[/]")
        else:
            console.print("[bold red]Engine could not find a move![/]")

    def player_move(self, input_str: str) -> bool:
        """Try to parse and play the player's move. Returns True on success."""
        input_str = input_str.strip()

        # Try SAN first (e.g. "Nf3", "e4", "O-O")
        try:
            move = self.board.parse_san(input_str)
            if move in self.board.legal_moves:
                self.board.push(move)
                self.last_move = move
                self.undo_stack.clear()
                return True
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError, ValueError):
            pass

        # Try UCI (e.g. "e2e4")
        try:
            move = chess.Move.from_uci(input_str)
            if move in self.board.legal_moves:
                self.board.push(move)
                self.last_move = move
                self.undo_stack.clear()
                return True
            # Try with promotion
            for promo in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
                promo_move = chess.Move(move.from_square, move.to_square, promotion=promo)
                if promo_move in self.board.legal_moves:
                    self.board.push(promo_move)
                    self.last_move = promo_move
                    self.undo_stack.clear()
                    return True
        except ValueError:
            pass

        console.print(f"  [bold red]✗ Invalid move:[/] [yellow]{input_str}[/]")
        console.print("  [dim]Use algebraic (Nf3, e4, O-O) or UCI (e2e4) notation[/]")
        return False

    def undo(self):
        """Undo the last full move (player + engine)."""
        count = 0
        while count < 2 and self.board.move_stack:
            move = self.board.pop()
            self.undo_stack.append(move)
            count += 1

        self.last_move = self.board.move_stack[-1] if self.board.move_stack else None
        console.print(f"  [bold yellow]↩ Undid {count} move(s)[/]")

    def get_hint(self):
        """Show a hint from the engine."""
        with console.status("[bold cyan]🔍 Analyzing...[/]", spinner="dots12"):
            move = self.engine.search(self.board, time_limit=3.0)

        if move:
            san = self.board.san(move)
            console.print(f"  [bold cyan]💡 Suggested move:[/] [bold white]{san}[/]")
        else:
            console.print("  [dim]No suggestion available[/]")

    def show_eval(self):
        """Show position evaluation."""
        from engine import ChessEngine as _CE

        temp_engine = _CE()
        with console.status("[bold cyan]📊 Evaluating...[/]", spinner="dots12"):
            move = temp_engine.search(self.board, time_limit=3.0)

        info = temp_engine.get_search_info()
        # Get raw evaluation
        score = temp_engine._evaluate(self.board)
        # Convert to white's perspective
        if self.board.turn == chess.BLACK:
            score = -score
        score_pawns = score / 100

        bar_len = 30
        # Map score to bar position (clamp between -5 and +5 pawns)
        clamped = max(-500, min(500, score))
        white_portion = int(bar_len * (clamped + 500) / 1000)
        black_portion = bar_len - white_portion

        bar = "█" * white_portion + "░" * black_portion

        eval_text = f"+{score_pawns:.2f}" if score_pawns >= 0 else f"{score_pawns:.2f}"
        console.print(f"  [bold]Evaluation:[/] [{'green' if score >= 0 else 'red'}]{eval_text}[/] (White's perspective)")
        console.print(f"  [bold white]{bar}[/]")
        console.print(f"  [dim]Searched {info['nodes']:,} nodes in {info['time']}s[/]")

    def save_game(self):
        """Save the current game as a PGN file."""
        game = chess.pgn.Game()
        game.headers["Event"] = "ChessBot Game"
        game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        game.headers["White"] = "Player" if self.player_color == chess.WHITE else "ChessBot"
        game.headers["Black"] = "ChessBot" if self.player_color == chess.WHITE else "Player"
        game.headers["Result"] = self.board.result() if self.board.is_game_over() else "*"

        node = game
        temp = chess.Board()
        for move in self.board.move_stack:
            node = node.add_variation(move)
            temp.push(move)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = SAVE_DIR / f"game_{timestamp}.pgn"
        with open(filename, "w") as f:
            print(game, file=f)

        console.print(f"  [bold green]✓ Game saved to:[/] [underline]{filename}[/]")

    def load_game(self):
        """Load a game from a PGN file."""
        pgn_files = sorted(SAVE_DIR.glob("*.pgn"), reverse=True)

        if not pgn_files:
            console.print("  [bold red]✗ No saved games found[/]")
            return

        console.print("\n  [bold yellow]Saved games:[/]")
        for i, f in enumerate(pgn_files[:10]):
            console.print(f"    [cyan]{i + 1}.[/] {f.name}")

        choice = Prompt.ask("  Select game number", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(pgn_files):
                with open(pgn_files[idx]) as f:
                    game = chess.pgn.read_game(f)

                if game:
                    self.board = game.board()
                    for move in game.mainline_moves():
                        self.board.push(move)
                    self.last_move = self.board.move_stack[-1] if self.board.move_stack else None
                    self.engine.clear_tables()
                    self.undo_stack.clear()
                    console.print(f"  [bold green]✓ Game loaded:[/] {pgn_files[idx].name}")
                else:
                    console.print("  [bold red]✗ Could not parse PGN file[/]")
            else:
                console.print("  [bold red]✗ Invalid selection[/]")
        except ValueError:
            console.print("  [bold red]✗ Invalid input[/]")

    def change_difficulty(self):
        """Let the player change the difficulty level."""
        console.print("\n  [bold yellow]Difficulty levels:[/]")
        for key, val in DIFFICULTY_LEVELS.items():
            marker = " ◀" if key == self.difficulty else ""
            console.print(f"    [cyan]{key:<15}[/] {val['label']} ({val['elo']}){marker}")

        choice = Prompt.ask("  Select level", choices=list(DIFFICULTY_LEVELS.keys()), default=self.difficulty)
        self.difficulty = choice
        console.print(f"  [bold green]✓ Difficulty set to {DIFFICULTY_LEVELS[choice]['label']}[/]")

    def new_game(self):
        """Start a new game."""
        self.board = chess.Board()
        self.engine.clear_tables()
        self.last_move = None
        self.engine_info = None
        self.undo_stack.clear()
        console.print("  [bold green]✓ New game started![/]")


# ─── Main Loop ────────────────────────────────────────────────────────────────

def main():
    console.clear()

    # Welcome screen
    title = Text()
    title.append("♜ ", style="bold white")
    title.append("C H E S S B O T", style="bold bright_white")
    title.append(" ♜", style="bold white")

    console.print(Panel(
        Group(
            title,
            Text(""),
            Text("  A Python chess engine with a beautiful terminal UI", style="dim"),
            Text("  Type 'help' at any time to see available commands", style="dim"),
            Text(""),
        ),
        border_style="bright_cyan",
        box=box.DOUBLE,
        padding=(1, 3),
    ))

    game = ChessGame()

    # Choose color
    console.print()
    color_choice = Prompt.ask(
        "  [bold]Play as[/]",
        choices=["white", "black"],
        default="white",
    )
    game.player_color = chess.WHITE if color_choice == "white" else chess.BLACK
    if game.player_color == chess.BLACK:
        game.flipped = True

    # Choose difficulty
    game.change_difficulty()

    # Main game loop
    while True:
        console.print()
        game.display()

        if game.board.is_game_over():
            result = game.board.result()
            console.print(f"\n  [bold]Game Over — Result: {result}[/]")
            console.print()
            action = Prompt.ask("  [bold]Play again?[/]", choices=["yes", "no"], default="yes")
            if action == "yes":
                game.new_game()
                continue
            else:
                console.print("\n  [bold cyan]Thanks for playing! 👋[/]\n")
                break

        if game.board.turn == game.player_color:
            # Player's turn
            console.print()
            user_input = Prompt.ask("  [bold green]Your move[/]").strip().lower()

            if user_input in ("quit", "exit", "q"):
                console.print("\n  [bold cyan]Thanks for playing! 👋[/]\n")
                break
            elif user_input == "help":
                console.print(render_help())
            elif user_input == "undo":
                game.undo()
            elif user_input == "hint":
                game.get_hint()
            elif user_input == "flip":
                game.flipped = not game.flipped
                console.print("  [bold yellow]↻ Board flipped[/]")
            elif user_input == "save":
                game.save_game()
            elif user_input == "load":
                game.load_game()
            elif user_input == "level":
                game.change_difficulty()
            elif user_input == "eval":
                game.show_eval()
            elif user_input == "resign":
                winner = "Black" if game.player_color == chess.WHITE else "White"
                console.print(f"  [bold red]You resigned. {winner} wins.[/]")
                action = Prompt.ask("  [bold]Play again?[/]", choices=["yes", "no"], default="yes")
                if action == "yes":
                    game.new_game()
                else:
                    console.print("\n  [bold cyan]Thanks for playing! 👋[/]\n")
                    break
            elif user_input == "new":
                game.new_game()
            else:
                game.player_move(user_input)
        else:
            # Engine's turn
            game.engine_move()


if __name__ == "__main__":
    main()
