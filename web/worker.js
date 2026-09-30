/* ═══════════════════════════════════════════════════════════════════
   ChessBot — Pyodide Web Worker
   Runs the Python chess engine entirely in WebAssembly.
   Communicates with app.js via postMessage.
   ═══════════════════════════════════════════════════════════════════ */

importScripts('https://cdn.jsdelivr.net/pyodide/v0.26.2/full/pyodide.js');

let pyodide = null;

// Global function callable from Python via `js.sendSearchInfo(jsonStr)`
// Fires during engine search to stream live depth/nodes/eval info.
self.sendSearchInfo = function (jsonStr) {
    self.postMessage({ type: 'search_info', data: JSON.parse(jsonStr) });
};

// ────────────────────────── Initialisation ────────────────────────

async function init() {
    try {
        self.postMessage({ type: 'load_progress', stage: 'Loading Pyodide runtime…', pct: 10 });
        pyodide = await loadPyodide({
            indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.2/full/'
        });

        self.postMessage({ type: 'load_progress', stage: 'Installing chess library…', pct: 35 });
        await pyodide.loadPackage('micropip');
        const micropip = pyodide.pyimport('micropip');
        await micropip.install('chess');

        self.postMessage({ type: 'load_progress', stage: 'Loading ChessBot engine…', pct: 65 });
        let resp = await fetch('../engine.py');
        if (!resp.ok) resp = await fetch('engine.py');
        if (!resp.ok) throw new Error('Failed to fetch engine.py: ' + resp.status);
        const engineSource = await resp.text();
        pyodide.runPython(engineSource);

        self.postMessage({ type: 'load_progress', stage: 'Setting up bridge…', pct: 85 });
        pyodide.runPython(BRIDGE_CODE);

        self.postMessage({ type: 'load_progress', stage: 'Ready!', pct: 100 });
        self.postMessage({ type: 'ready' });
    } catch (err) {
        self.postMessage({ type: 'error', message: 'Engine load failed: ' + err.message });
    }
}

// ────────────────────────── Python Bridge ─────────────────────────
// All functions return JSON strings to avoid Pyodide FFI conversion issues.

const BRIDGE_CODE = `
import chess
import json
import js

_engine = ChessEngine()
_board = chess.Board()

def _to_json(obj):
    return json.dumps(obj)

def _get_state():
    legal = [m.uci() for m in _board.legal_moves]
    last = _board.move_stack[-1].uci() if _board.move_stack else None

    # Rebuild SAN move history
    history = []
    temp = chess.Board()
    for move in _board.move_stack:
        history.append(temp.san(move))
        temp.push(move)

    return {
        "fen": _board.fen(),
        "legalMoves": legal,
        "lastMove": last,
        "isCheck": _board.is_check(),
        "isGameOver": _board.is_game_over(claim_draw=True),
        "result": _board.result(claim_draw=True) if _board.is_game_over(claim_draw=True) else None,
        "turn": "white" if _board.turn else "black",
        "moveHistory": history,
    }

# ── Commands ──────────────────────────────────────────────────────

def cmd_new_game():
    global _board
    _board = chess.Board()
    _engine.clear_tables()
    return _to_json({"type": "state", **_get_state()})

def cmd_set_fen(fen):
    global _board
    try:
        _board = chess.Board(fen)
        _engine.clear_tables()
        return _to_json({"type": "state", **_get_state()})
    except ValueError:
        return _to_json({"type": "error", "message": "Invalid FEN"})

def cmd_player_move(uci_str):
    global _board
    try:
        move = chess.Move.from_uci(uci_str)
        if move in _board.legal_moves:
            san = _board.san(move)
            is_capture = _board.is_capture(move)
            _board.push(move)
            st = _get_state()
            return _to_json({
                "type": "move_ok",
                "san": san,
                "isCapture": is_capture,
                "isCheck": st["isCheck"],
                **st,
            })
        return _to_json({"type": "error", "message": "Illegal move: " + uci_str})
    except ValueError:
        return _to_json({"type": "error", "message": "Invalid move format: " + uci_str})

def cmd_engine_go(time_limit):
    global _board

    search_turn = _board.turn
    def info_cb(info):
        try:
            send_info = dict(info)
            if search_turn == chess.BLACK and "score" in send_info:
                send_info["score"] = -send_info["score"]
            js.sendSearchInfo(json.dumps(send_info))
        except Exception:
            pass

    move = _engine.search(_board, time_limit=time_limit, info_callback=info_cb)

    if move:
        san = _board.san(move)
        uci = move.uci()
        is_capture = _board.is_capture(move)
        _board.push(move)
        info = _engine.get_search_info()
        if search_turn == chess.BLACK and "score" in info:
            info["score"] = -info["score"]
        st = _get_state()
        return _to_json({
            "type": "bestmove",
            "uci": uci,
            "san": san,
            "isCapture": is_capture,
            "isCheck": st["isCheck"],
            "info": info,
            **st,
        })
    st = _get_state()
    return _to_json({"type": "bestmove", "uci": None, "san": None, **st})

def cmd_engine_stop():
    _engine.search_stopped = True
    return _to_json({"type": "stopped"})

def cmd_get_hint(time_limit):
    global _board
    move = _engine.search(_board, time_limit=time_limit)
    if move:
        return _to_json({
            "type": "hint",
            "from": chess.square_name(move.from_square),
            "to": chess.square_name(move.to_square),
            "san": _board.san(move),
        })
    return _to_json({"type": "hint", "from": None, "to": None, "san": None})

def cmd_undo():
    global _board
    count = 0
    while count < 2 and _board.move_stack:
        _board.pop()
        count += 1
    _engine.clear_tables()
    return _to_json({"type": "state", **_get_state()})

def cmd_eval():
    global _board
    score = _engine._evaluate(_board)
    if _board.turn == chess.BLACK:
        score = -score
    return _to_json({"type": "eval", "score": score})
`;

// ────────────────────────── Message Handler ──────────────────────

self.onmessage = async function (e) {
    const msg = e.data;
    if (!pyodide) return;

    let result;
    try {
        switch (msg.type) {
            case 'new_game':
                result = pyodide.runPython('cmd_new_game()');
                break;
            case 'player_move':
                result = pyodide.runPython('cmd_player_move(' + JSON.stringify(msg.uci) + ')');
                break;
            case 'engine_go':
                result = pyodide.runPython('cmd_engine_go(' + Number(msg.timeLimit) + ')');
                break;
            case 'engine_stop':
                result = pyodide.runPython('cmd_engine_stop()');
                break;
            case 'get_hint':
                result = pyodide.runPython('cmd_get_hint(' + Number(msg.timeLimit) + ')');
                break;
            case 'undo':
                result = pyodide.runPython('cmd_undo()');
                break;
            case 'set_fen':
                result = pyodide.runPython('cmd_set_fen(' + JSON.stringify(msg.fen) + ')');
                break;
            case 'eval':
                result = pyodide.runPython('cmd_eval()');
                break;
        }
        if (result) {
            self.postMessage(JSON.parse(result));
        }
    } catch (err) {
        self.postMessage({ type: 'error', message: err.message });
    }
};

// Start
init();
