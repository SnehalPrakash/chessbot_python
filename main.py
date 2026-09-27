#!/usr/bin/env python3
"""
ChessBot — A Python Chess Engine with a Beautiful Terminal UI

Usage:
    python main.py              Play interactively against the engine
    python main.py --selfplay   Watch the engine play against itself
    python main.py --bench      Run a benchmark / perft test
    python main.py --help       Show this help message

Modules:
    engine.py   — The chess engine (search + evaluation)
    ui.py       — The Rich terminal user interface
"""

import sys
import chess
import time

from engine import ChessEngine


def selfplay(time_per_move: float = 3.0, max_moves: int = 200):
    """Watch two engine instances play against each other."""
    from rich.console import Console
    from rich.text import Text
    from rich import box
    from rich.panel import Panel
    from ui import render_board

    console = Console()
    console.clear()

    console.print(Panel(
        "[bold]♜ Engine vs Engine — Self-Play Mode ♜[/]",
        border_style="bright_cyan",
        box=box.DOUBLE,
        padding=(0, 2),
    ))

    board = chess.Board()
    engine_white = ChessEngine(time_limit=time_per_move)
    engine_black = ChessEngine(time_limit=time_per_move)

    last_move = None
    move_count = 0

    while not board.is_game_over() and move_count < max_moves:
        engine = engine_white if board.turn == chess.WHITE else engine_black
        color_name = "White" if board.turn == chess.WHITE else "Black"

        with console.status(f"[bold magenta]{color_name} thinking...[/]", spinner="dots12"):
            move = engine.search(board, time_limit=time_per_move)

        if move is None:
            console.print("[bold red]Engine returned no move![/]")
            break

        san = board.san(move)
        board.push(move)
        last_move = move
        move_count += 1
        info = engine.get_search_info()

        console.clear()
        console.print(Panel(
            "[bold]♜ Engine vs Engine — Self-Play Mode ♜[/]",
            border_style="bright_cyan",
            box=box.DOUBLE,
            padding=(0, 2),
        ))
        console.print()
        console.print(render_board(board, last_move))
        console.print()

        move_num = (move_count + 1) // 2
        dot = "." if board.turn == chess.BLACK else "..."
        console.print(
            f"  [bold]{move_num}{dot}[/] [bold white]{san}[/]"
            f"  [dim]({info['nodes']:,} nodes, {info['time']}s, {info['nps']:,} NPS)[/]"
        )

    console.print()
    console.print(f"  [bold]Game Over — Result: {board.result()}[/]")
    console.print(f"  [dim]Total moves: {move_count}[/]")
    console.print()


def benchmark():
    """Run a simple benchmark: search standard position at increasing depths."""
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    console.print("\n[bold cyan]♜ ChessBot Benchmark ♜[/]\n")

    positions = [
        ("Starting position", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
        ("Italian Game", "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"),
        ("Complex middlegame", "r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/R3KB1R w KQ - 2 9"),
        ("Endgame", "8/5pk1/6p1/3P4/1p6/1P3PP1/5K2/8 w - - 0 40"),
    ]

    table = Table(
        title="Search Benchmark",
        box=box.ROUNDED,
        border_style="cyan",
        show_lines=True,
    )
    table.add_column("Position", style="white", width=20)
    table.add_column("Depth", justify="center", style="cyan")
    table.add_column("Nodes", justify="right", style="yellow")
    table.add_column("Time (s)", justify="right", style="green")
    table.add_column("NPS", justify="right", style="magenta")
    table.add_column("Best Move", justify="center", style="bold white")

    for name, fen in positions:
        board = chess.Board(fen)
        engine = ChessEngine()

        for depth in [3, 5]:
            start = time.time()
            move = engine.search(board, time_limit=5.0)

            # We do a fixed-depth search by limiting time generously
            # The iterative deepening will naturally reach the depth
            info = engine.get_search_info()
            elapsed = time.time() - start

            move_str = board.san(move) if move else "—"
            table.add_row(
                name if depth == 3 else "",
                str(depth),
                f"{info['nodes']:,}",
                f"{elapsed:.2f}",
                f"{info['nps']:,}",
                move_str,
            )

    console.print(table)
    console.print()


def show_help():
    print(__doc__)


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        show_help()
    elif "--selfplay" in args:
        time_per_move = 3.0
        for i, arg in enumerate(args):
            if arg == "--time" and i + 1 < len(args):
                time_per_move = float(args[i + 1])
        selfplay(time_per_move=time_per_move)
    elif "--bench" in args:
        benchmark()
    else:
        # Default: interactive play
        from ui import main as ui_main
        ui_main()


if __name__ == "__main__":
    main()