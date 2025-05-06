import chess
import chess.engine
import random
import time
import math


class ChessBot1600:
    def __init__(self):
        self.board = chess.Board()
        # Some common openings
        self.opening_book = {
            "": ["e2e4", "d2d4", "c2c4", "g1f3"],
            "e2e4": ["e7e5", "c7c5", "e7e6", "c7c6"],
            "d2d4": ["d7d5", "g8f6", "e7e6", "c7c5"],
            "c2c4": ["e7e5", "g8f6", "c7c5"],
            "g1f3": ["d7d5", "g8f6", "c7c5"]
        }

        self.piece_values = {
            chess.PAWN: 100,
            chess.KNIGHT: 320,
            chess.BISHOP: 330,
            chess.ROOK: 500,
            chess.QUEEN: 900,
            chess.KING: 20000
        }

        # Position scoring tables - positive values are good
        self.pawn_table = [
            0, 0, 0, 0, 0, 0, 0, 0,
            50, 50, 50, 50, 50, 50, 50, 50,
            10, 10, 20, 30, 30, 20, 10, 10,
            5, 5, 10, 25, 25, 10, 5, 5,
            0, 0, 0, 20, 20, 0, 0, 0,
            5, -5, -10, 0, 0, -10, -5, 5,
            5, 10, 10, -20, -20, 10, 10, 5,
            0, 0, 0, 0, 0, 0, 0, 0
        ]

        self.knight_table = [
            -50, -40, -30, -30, -30, -30, -40, -50,
            -40, -20, 0, 0, 0, 0, -20, -40,
            -30, 0, 10, 15, 15, 10, 0, -30,
            -30, 5, 15, 20, 20, 15, 5, -30,
            -30, 0, 15, 20, 20, 15, 0, -30,
            -30, 5, 10, 15, 15, 10, 5, -30,
            -40, -20, 0, 5, 5, 0, -20, -40,
            -50, -40, -30, -30, -30, -30, -40, -50
        ]

        self.bishop_table = [
            -20, -10, -10, -10, -10, -10, -10, -20,
            -10, 0, 0, 0, 0, 0, 0, -10,
            -10, 0, 10, 10, 10, 10, 0, -10,
            -10, 5, 5, 10, 10, 5, 5, -10,
            -10, 0, 5, 10, 10, 5, 0, -10,
            -10, 5, 5, 5, 5, 5, 5, -10,
            -10, 0, 5, 0, 0, 5, 0, -10,
            -20, -10, -10, -10, -10, -10, -10, -20
        ]

        self.rook_table = [
            0, 0, 0, 0, 0, 0, 0, 0,
            5, 10, 10, 10, 10, 10, 10, 5,
            -5, 0, 0, 0, 0, 0, 0, -5,
            -5, 0, 0, 0, 0, 0, 0, -5,
            -5, 0, 0, 0, 0, 0, 0, -5,
            -5, 0, 0, 0, 0, 0, 0, -5,
            -5, 0, 0, 0, 0, 0, 0, -5,
            0, 0, 0, 5, 5, 0, 0, 0
        ]

        self.queen_table = [
            -20, -10, -10, -5, -5, -10, -10, -20,
            -10, 0, 0, 0, 0, 0, 0, -10,
            -10, 0, 5, 5, 5, 5, 0, -10,
            -5, 0, 5, 5, 5, 5, 0, -5,
            0, 0, 5, 5, 5, 5, 0, -5,
            -10, 5, 5, 5, 5, 5, 0, -10,
            -10, 0, 5, 0, 0, 0, 0, -10,
            -20, -10, -10, -5, -5, -10, -10, -20
        ]

        self.king_table = [
            -30, -40, -40, -50, -50, -40, -40, -30,
            -30, -40, -40, -50, -50, -40, -40, -30,
            -30, -40, -40, -50, -50, -40, -40, -30,
            -30, -40, -40, -50, -50, -40, -40, -30,
            -20, -30, -30, -40, -40, -30, -30, -20,
            -10, -20, -20, -20, -20, -20, -20, -10,
            20, 20, 0, 0, 0, 0, 20, 20,
            20, 30, 10, 0, 0, 10, 30, 20
        ]

        self.king_endgame_table = [
            -50, -40, -30, -20, -20, -30, -40, -50,
            -30, -20, -10, 0, 0, -10, -20, -30,
            -30, -10, 20, 30, 30, 20, -10, -30,
            -30, -10, 30, 40, 40, 30, -10, -30,
            -30, -10, 30, 40, 40, 30, -10, -30,
            -30, -10, 20, 30, 30, 20, -10, -30,
            -30, -30, 0, 0, 0, 0, -30, -30,
            -50, -30, -30, -30, -30, -30, -30, -50
        ]

    def make_move(self, board=None, time_limit=2):
        if board:
            self.board = board

        # Try to play from opening book first
        book_move = self._get_book_move()
        if book_move:
            return book_move

        # Search for best move
        depth = 3  # Typical depth for ~1600 rated player

        # Add randomness to simulate 1600-level play
        if random.random() < 0.15:  # 15% chance to reduce depth
            depth -= 1

        best_move = None
        best_value = -float('inf')
        alpha = -float('inf')
        beta = float('inf')

        legal_moves = list(self.board.legal_moves)
        random.shuffle(legal_moves)  # Mix up the move order

        for move in legal_moves:
            self.board.push(move)
            value = -self._negamax(depth - 1, -beta, -alpha)
            self.board.pop()

            # Apply some randomness to evaluation to simulate human imperfection
            value += random.normalvariate(0, 10)

            if value > best_value:
                best_value = value
                best_move = move

            alpha = max(alpha, best_value)

        return best_move

    def _negamax(self, depth, alpha, beta):
        if depth == 0 or self.board.is_game_over():
            return self._evaluate()

        best_value = -float('inf')
        legal_moves = list(self.board.legal_moves)

        # Sort moves to improve pruning (captures first)
        legal_moves.sort(key=lambda move: 1000 if self.board.is_capture(move) else 0, reverse=True)

        for move in legal_moves:
            self.board.push(move)
            value = -self._negamax(depth - 1, -beta, -alpha)
            self.board.pop()

            best_value = max(best_value, value)
            alpha = max(alpha, best_value)

            if alpha >= beta:
                break

        return best_value

    def _evaluate(self):
        # Return large value for checkmate
        if self.board.is_checkmate():
            return -10000

        # Draw is neutral
        if self.board.is_stalemate() or self.board.is_insufficient_material():
            return 0

        value = 0

        # Material count
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if not piece:
                continue

            piece_value = self.piece_values[piece.piece_type]

            # Add position value based on piece-square tables
            position_value = self._get_position_value(piece, square)

            # Add or subtract value based on piece color
            if piece.color == self.board.turn:
                value += piece_value + position_value
            else:
                value -= piece_value + position_value

        # Check and attack bonuses
        if self.board.is_check():
            value += 50

        # Development bonus in opening
        if self._is_opening():
            value += self._development_score() * 10

        # Mobility (number of legal moves)
        mobility = len(list(self.board.legal_moves))
        value += mobility * 2

        # Return value relative to side to move
        return value

    def _get_position_value(self, piece, square):
        piece_type = piece.piece_type

        # Flip table for black pieces
        if piece.color == chess.BLACK:
            square = 63 - square

        if piece_type == chess.PAWN:
            return self.pawn_table[square]
        elif piece_type == chess.KNIGHT:
            return self.knight_table[square]
        elif piece_type == chess.BISHOP:
            return self.bishop_table[square]
        elif piece_type == chess.ROOK:
            return self.rook_table[square]
        elif piece_type == chess.QUEEN:
            return self.queen_table[square]
        elif piece_type == chess.KING:
            # Use different tables for endgame
            if self._is_endgame():
                return self.king_endgame_table[square]
            else:
                return self.king_table[square]
        return 0

    def _is_opening(self):
        # Simple check if we're in opening phase
        return self.board.fullmove_number < 10

    def _is_endgame(self):
        # Check if we're in an endgame
        queens = 0
        minors = 0

        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if not piece:
                continue

            if piece.piece_type == chess.QUEEN:
                queens += 1
            elif piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                minors += 1

        return queens == 0 or (queens <= 1 and minors <= 2)

    def _development_score(self):
        # Score based on piece development from starting squares
        score = 0

        # Knights and bishops developed
        if not self.board.piece_at(chess.B1) and self.board.turn == chess.WHITE:
            score += 1
        if not self.board.piece_at(chess.G1) and self.board.turn == chess.WHITE:
            score += 1
        if not self.board.piece_at(chess.C1) and self.board.turn == chess.WHITE:
            score += 1
        if not self.board.piece_at(chess.F1) and self.board.turn == chess.WHITE:
            score += 1

        if not self.board.piece_at(chess.B8) and self.board.turn == chess.BLACK:
            score += 1
        if not self.board.piece_at(chess.G8) and self.board.turn == chess.BLACK:
            score += 1
        if not self.board.piece_at(chess.C8) and self.board.turn == chess.BLACK:
            score += 1
        if not self.board.piece_at(chess.F8) and self.board.turn == chess.BLACK:
            score += 1

        return score

    def _get_book_move(self):
        # Get move from opening book if possible
        move_history = ""
        for move in self.board.move_stack[-4:]:  # Check only last few moves
            move_history += move.uci() + " "
        move_history = move_history.strip()

        # Check if current position is in our opening book
        if move_history in self.opening_book:
            moves = self.opening_book[move_history]
            # Pick a random move from the book for this position
            book_move_uci = random.choice(moves)
            return chess.Move.from_uci(book_move_uci)

        # If board is in starting position
        elif len(self.board.move_stack) == 0 and "" in self.opening_book:
            book_move_uci = random.choice(self.opening_book[""])
            return chess.Move.from_uci(book_move_uci)

        return None


# Example usage
def play_game():
    bot = ChessBot1600()
    board = chess.Board()

    while not board.is_game_over():
        if board.turn == chess.WHITE:
            move = bot.make_move(board)
        else:
            # Get move from human player
            valid_move = False
            while not valid_move:
                try:
                    user_input = input("Enter your move (e.g. e2e4): ")
                    move = chess.Move.from_uci(user_input)
                    if move in board.legal_moves:
                        valid_move = True
                    else:
                        print("Illegal move, try again")
                except ValueError:
                    print("Invalid format, use format like 'e2e4'")

        print(f"Move: {move.uci()}")
        board.push(move)
        print(board)
        print("\n")

    print("Game over")
    print(f"Result: {board.result()}")


if __name__ == "__main__":
    play_game()