/* ═══════════════════════════════════════════════════════════════════
   ChessBot — Browser UI Controller
   Board rendering · Click & Drag · Sounds · Worker communication
   ═══════════════════════════════════════════════════════════════════ */

// ────────────────────────── Constants ─────────────────────────────

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
const PIECES = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟',
};
const INITIAL_PIECES = {
    P: 8, N: 2, B: 2, R: 2, Q: 1, K: 1,
    p: 8, n: 2, b: 2, r: 2, q: 1, k: 1,
};
const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

// ────────────────────────── State ─────────────────────────────────

const state = {
    fen: START_FEN,
    board: [],
    legalMoves: [],
    lastMove: null,
    isCheck: false,
    isGameOver: false,
    result: null,
    turn: 'white',
    selectedSquare: null,
    legalDestinations: [],
    flipped: false,
    playerColor: 'white',
    difficulty: 1.0,
    thinking: false,
    moveHistory: [],
    hintSquares: null,
    lastScore: 0,
};

// ────────────────────────── Audio (Web Audio API) ─────────────────

let audioCtx = null;

function ensureAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') audioCtx.resume();
}

function playSound(type) {
    try { ensureAudio(); } catch (e) { return; }
    const now = audioCtx.currentTime;

    switch (type) {
        case 'move': {
            const len = audioCtx.sampleRate * 0.04;
            const buf = audioCtx.createBuffer(1, len, audioCtx.sampleRate);
            const d = buf.getChannelData(0);
            for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.exp(-i / (len * 0.12));
            const src = audioCtx.createBufferSource();
            src.buffer = buf;
            const flt = audioCtx.createBiquadFilter();
            flt.type = 'bandpass'; flt.frequency.value = 1400; flt.Q.value = 1.2;
            const g = audioCtx.createGain(); g.gain.value = 0.25;
            src.connect(flt).connect(g).connect(audioCtx.destination);
            src.start(now);
            break;
        }
        case 'capture': {
            const len = audioCtx.sampleRate * 0.07;
            const buf = audioCtx.createBuffer(1, len, audioCtx.sampleRate);
            const d = buf.getChannelData(0);
            for (let i = 0; i < len; i++) {
                const t = i / audioCtx.sampleRate;
                d[i] = (Math.random() * 2 - 1) * Math.exp(-i / (len * 0.18))
                     + Math.sin(2 * Math.PI * 160 * t) * 0.25 * Math.exp(-t * 35);
            }
            const src = audioCtx.createBufferSource();
            src.buffer = buf;
            const g = audioCtx.createGain(); g.gain.value = 0.3;
            src.connect(g).connect(audioCtx.destination);
            src.start(now);
            break;
        }
        case 'check': {
            const osc = audioCtx.createOscillator();
            const g = audioCtx.createGain();
            osc.type = 'sine'; osc.frequency.value = 880;
            g.gain.setValueAtTime(0.12, now);
            g.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
            osc.connect(g).connect(audioCtx.destination);
            osc.start(now); osc.stop(now + 0.12);
            break;
        }
        case 'gameover': {
            [330, 262, 196].forEach((freq, i) => {
                const osc = audioCtx.createOscillator();
                const g = audioCtx.createGain();
                osc.type = 'triangle'; osc.frequency.value = freq;
                const t0 = now + i * 0.18;
                g.gain.setValueAtTime(0.1, t0);
                g.gain.exponentialRampToValueAtTime(0.001, t0 + 0.6);
                osc.connect(g).connect(audioCtx.destination);
                osc.start(t0); osc.stop(t0 + 0.6);
            });
            break;
        }
    }
}

// ────────────────────────── Worker ────────────────────────────────

const worker = new Worker('worker.js');

worker.onmessage = function (e) {
    const msg = e.data;

    switch (msg.type) {
        case 'ready':       onEngineReady(); break;
        case 'state':       onStateUpdate(msg); break;
        case 'move_ok':     onPlayerMoveOk(msg); break;
        case 'bestmove':    onBestMove(msg); break;
        case 'hint':        onHint(msg); break;
        case 'eval':        updateEvalBar(msg.score); break;
        case 'search_info': onSearchInfo(msg.data || msg); break;
        case 'error': {
            console.warn('Engine error:', msg.message);
            const statusEl = document.getElementById('load-status');
            if (statusEl) {
                statusEl.textContent = '⚠️ ' + msg.message;
                statusEl.style.color = 'var(--danger)';
            }
            break;
        }
        case 'load_progress': updateLoadProgress(msg); break;
    }
};

function onEngineReady() {
    document.getElementById('loading-screen').classList.add('fade-out');
    setTimeout(() => {
        document.getElementById('loading-screen').style.display = 'none';
        document.getElementById('app').classList.remove('hidden');
        // Force reflow before adding fade-in
        void document.getElementById('app').offsetHeight;
        document.getElementById('app').classList.add('fade-in');
    }, 500);
    worker.postMessage({ type: 'new_game' });
}

function onStateUpdate(msg) {
    state.fen = msg.fen;
    state.board = parseFEN(msg.fen);
    state.legalMoves = msg.legalMoves || [];
    state.lastMove = msg.lastMove
        ? { from: msg.lastMove.substring(0, 2), to: msg.lastMove.substring(2, 4) }
        : null;
    state.isCheck = msg.isCheck;
    state.isGameOver = msg.isGameOver;
    state.result = msg.result;
    state.turn = msg.turn;
    state.moveHistory = msg.moveHistory || [];

    renderBoard();
    updateMoveList();
    updateCaptured();
    updateStatus();

    if (state.isGameOver) {
        playSound('gameover');
        return;
    }

    // Auto-trigger engine move
    if (state.turn !== state.playerColor && !state.thinking) {
        requestEngineMove();
    }
}

function onPlayerMoveOk(msg) {
    playSound(msg.isCapture ? 'capture' : 'move');
    if (msg.isCheck) setTimeout(() => playSound('check'), 80);
    onStateUpdate(msg);
}

function onBestMove(msg) {
    state.thinking = false;
    enableControls(true);

    if (msg.uci) {
        playSound(msg.isCapture ? 'capture' : 'move');
        if (msg.isCheck) setTimeout(() => playSound('check'), 80);
    }
    if (msg.info) {
        state.lastScore = msg.info.score || 0;
        updateSearchStats(msg.info);
        updateEvalBar(msg.info.score || 0);
    }
    onStateUpdate(msg);
}

function onHint(msg) {
    state.thinking = false;
    enableControls(true);
    if (msg.from && msg.to) {
        state.hintSquares = { from: msg.from, to: msg.to };
        renderBoard();
        const statusEl = document.getElementById('status-text');
        statusEl.innerHTML = '<span style="color:var(--success)">💡 Hint: <strong>' + msg.san + '</strong></span>';
    }
}

function onSearchInfo(info) {
    updateSearchStats(info);
    if (info.score !== undefined) {
        state.lastScore = info.score;
        updateEvalBar(info.score);
    }
}

function updateLoadProgress(msg) {
    const fill = document.getElementById('load-progress');
    const status = document.getElementById('load-status');
    if (fill) fill.style.width = msg.pct + '%';
    if (status) status.textContent = msg.stage;
}

function requestEngineMove() {
    state.thinking = true;
    enableControls(false);
    updateStatus();
    worker.postMessage({ type: 'engine_go', timeLimit: state.difficulty });
}

// ────────────────────────── FEN Parsing ───────────────────────────

function parseFEN(fen) {
    const rows = fen.split(' ')[0].split('/');
    const board = [];
    for (const row of rows) {
        const r = [];
        for (const c of row) {
            if (c >= '1' && c <= '8') { for (let i = 0; i < +c; i++) r.push(null); }
            else r.push(c);
        }
        board.push(r);
    }
    return board; // board[0] = rank 8, board[7] = rank 1
}

function getPieceAt(sq) {
    const f = sq.charCodeAt(0) - 97;
    const r = 8 - parseInt(sq[1]);
    return (r >= 0 && r < 8 && f >= 0 && f < 8) ? state.board[r][f] : null;
}

function isWhitePiece(p) { return p && p === p.toUpperCase(); }

function hasPieceOfColor(sq, color) {
    const p = getPieceAt(sq);
    if (!p) return false;
    return color === 'white' ? isWhitePiece(p) : !isWhitePiece(p);
}

// ────────────────────────── Board Rendering ───────────────────────

function renderBoard() {
    const boardEl = document.getElementById('board');
    boardEl.innerHTML = '';

    const rankLabels = document.getElementById('rank-labels');
    const fileLabels = document.getElementById('file-labels');
    rankLabels.innerHTML = '';
    fileLabels.innerHTML = '';

    // Coordinate labels
    for (let i = 0; i < 8; i++) {
        const rk = document.createElement('span');
        rk.textContent = state.flipped ? (i + 1) : (8 - i);
        rankLabels.appendChild(rk);

        const fl = document.createElement('span');
        fl.textContent = state.flipped ? FILES[7 - i] : FILES[i];
        fileLabels.appendChild(fl);
    }

    const rowOrder = state.flipped ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];
    const colOrder = state.flipped ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];

    // King in check
    let checkSquare = null;
    if (state.isCheck) {
        const king = state.turn === 'white' ? 'K' : 'k';
        for (let r = 0; r < 8; r++)
            for (let c = 0; c < 8; c++)
                if (state.board[r][c] === king)
                    checkSquare = FILES[c] + (8 - r);
    }

    for (let dr = 0; dr < 8; dr++) {
        for (let dc = 0; dc < 8; dc++) {
            const br = rowOrder[dr];
            const bc = colOrder[dc];
            const rank = 8 - br;
            const file = bc;
            const sqName = FILES[file] + rank;
            const piece = state.board[br][bc];

            const sq = document.createElement('div');
            sq.className = 'square';
            sq.dataset.square = sqName;

            // Square colour
            const isLight = (file + rank) % 2 === 0;
            sq.classList.add(isLight ? 'light' : 'dark');

            // Highlights
            if (state.lastMove && (sqName === state.lastMove.from || sqName === state.lastMove.to))
                sq.classList.add('last-move');
            if (sqName === state.selectedSquare)
                sq.classList.add('selected');
            if (sqName === checkSquare)
                sq.classList.add('in-check');
            if (state.hintSquares && (sqName === state.hintSquares.from || sqName === state.hintSquares.to))
                sq.classList.add('hint');

            // Piece
            if (piece) {
                const span = document.createElement('span');
                span.className = 'piece ' + (isWhitePiece(piece) ? 'piece-white' : 'piece-black');
                span.textContent = PIECES[piece] || piece;
                sq.appendChild(span);
            }

            // Legal-move indicator
            if (state.legalDestinations.includes(sqName)) {
                const dot = document.createElement('div');
                dot.className = piece ? 'legal-ring' : 'legal-dot';
                sq.appendChild(dot);
            }

            // Events
            sq.addEventListener('mousedown', (e) => onSquareMouseDown(e, sqName));
            sq.addEventListener('touchstart', (e) => onSquareTouchStart(e, sqName), { passive: false });

            boardEl.appendChild(sq);
        }
    }
}

// ────────────────────────── Interaction ───────────────────────────

let dragState = null;

function onSquareMouseDown(e, sqName) {
    e.preventDefault();
    if (state.thinking || state.isGameOver || state.turn !== state.playerColor) return;

    state.hintSquares = null;

    if (state.selectedSquare) {
        const from = state.selectedSquare;
        if (from === sqName) { deselect(); return; }

        const promos = getPromotionMoves(from, sqName);
        if (promos.length > 0) { showPromotionDialog(from, sqName); return; }
        if (isLegalMove(from + sqName)) { sendMove(from + sqName); return; }

        // Re-select own piece
        if (hasPieceOfColor(sqName, state.playerColor)) {
            selectSquare(sqName);
            startDrag(e, sqName);
        } else {
            deselect();
        }
    } else {
        if (hasPieceOfColor(sqName, state.playerColor)) {
            selectSquare(sqName);
            startDrag(e, sqName);
        }
    }
}

function onSquareTouchStart(e, sqName) {
    e.preventDefault();
    const t = e.touches[0];
    onSquareMouseDown({ preventDefault() {}, clientX: t.clientX, clientY: t.clientY }, sqName);
}

function startDrag(e, sqName) {
    const piece = getPieceAt(sqName);
    if (!piece) return;

    const ghost = document.createElement('div');
    ghost.className = 'drag-ghost ' + (isWhitePiece(piece) ? 'piece-white' : 'piece-black');
    ghost.textContent = PIECES[piece];
    ghost.style.left = e.clientX + 'px';
    ghost.style.top = e.clientY + 'px';
    document.body.appendChild(ghost);

    // Hide the piece on the board square
    const sqEl = document.querySelector(`.square[data-square="${sqName}"] .piece`);
    if (sqEl) sqEl.style.opacity = '0.2';

    dragState = { from: sqName, ghost };
}

document.addEventListener('mousemove', (e) => {
    if (dragState) {
        dragState.ghost.style.left = e.clientX + 'px';
        dragState.ghost.style.top = e.clientY + 'px';
    }
});

document.addEventListener('touchmove', (e) => {
    if (dragState) {
        const t = e.touches[0];
        dragState.ghost.style.left = t.clientX + 'px';
        dragState.ghost.style.top = t.clientY + 'px';
    }
}, { passive: true });

function finishDrag(x, y) {
    if (!dragState) return;
    const to = getSquareFromPoint(x, y);
    if (to && to !== dragState.from) {
        const from = dragState.from;
        const promos = getPromotionMoves(from, to);
        if (promos.length > 0) showPromotionDialog(from, to);
        else if (isLegalMove(from + to)) sendMove(from + to);
    }
    // Restore piece visibility
    const sqEl = document.querySelector(`.square[data-square="${dragState.from}"] .piece`);
    if (sqEl) sqEl.style.opacity = '1';
    dragState.ghost.remove();
    dragState = null;
}

document.addEventListener('mouseup', (e) => finishDrag(e.clientX, e.clientY));
document.addEventListener('touchend', (e) => {
    if (dragState) {
        const t = e.changedTouches[0];
        finishDrag(t.clientX, t.clientY);
    }
});

function getSquareFromPoint(x, y) {
    const el = document.elementFromPoint(x, y);
    if (!el) return null;
    const sq = el.closest('.square');
    return sq ? sq.dataset.square : null;
}

function selectSquare(sqName) {
    state.selectedSquare = sqName;
    state.legalDestinations = getLegalDestinations(sqName);
    renderBoard();
}

function deselect() {
    state.selectedSquare = null;
    state.legalDestinations = [];
    renderBoard();
}

function getLegalDestinations(from) {
    return [...new Set(
        state.legalMoves
            .filter(m => m.startsWith(from))
            .map(m => m.substring(2, 4))
    )];
}

function isLegalMove(uci) { return state.legalMoves.includes(uci); }

function getPromotionMoves(from, to) {
    return state.legalMoves.filter(m => m.startsWith(from + to) && m.length === 5);
}

function sendMove(uci) {
    deselect();
    worker.postMessage({ type: 'player_move', uci });
}

// ────────────────────────── Promotion Dialog ─────────────────────

let pendingPromotion = null;

function showPromotionDialog(from, to) {
    pendingPromotion = { from, to };
    const modal = document.getElementById('promo-modal');
    modal.classList.remove('hidden');

    const pcs = state.playerColor === 'white'
        ? { q: '♕', r: '♖', b: '♗', n: '♘' }
        : { q: '♛', r: '♜', b: '♝', n: '♞' };
    document.querySelectorAll('.promo-btn').forEach(btn => {
        btn.textContent = pcs[btn.dataset.piece];
    });
}

function onPromotionSelect(piece) {
    if (pendingPromotion) {
        sendMove(pendingPromotion.from + pendingPromotion.to + piece);
        pendingPromotion = null;
    }
    document.getElementById('promo-modal').classList.add('hidden');
}

// ────────────────────────── UI Updates ────────────────────────────

function updateStatus() {
    const el = document.getElementById('status-text');
    const panel = document.getElementById('status-panel');

    if (state.isGameOver) {
        let txt = 'Game Over';
        if (state.result === '1-0') txt = '⚐ White wins!';
        else if (state.result === '0-1') txt = '⚐ Black wins!';
        else if (state.result === '1/2-1/2') txt = '½ Draw';
        el.innerHTML = '<strong>' + txt + '</strong>';
        panel.className = 'panel status-panel game-over';
    } else if (state.thinking) {
        el.innerHTML = '<span class="thinking">🤔 Engine thinking…</span>';
        panel.className = 'panel status-panel';
    } else if (state.isCheck) {
        const who = state.turn === 'white' ? 'White' : 'Black';
        el.innerHTML = '<strong>⚡ ' + who + ' is in check!</strong>';
        panel.className = 'panel status-panel in-check';
    } else {
        const who = state.turn === 'white' ? 'White' : 'Black';
        el.innerHTML = '● ' + who + ' to move';
        panel.className = 'panel status-panel';
    }
}

function updateMoveList() {
    const ml = document.getElementById('move-list');
    ml.innerHTML = '';
    for (let i = 0; i < state.moveHistory.length; i += 2) {
        const num = Math.floor(i / 2) + 1;
        const w = state.moveHistory[i] || '';
        const b = state.moveHistory[i + 1] || '';
        const row = document.createElement('div');
        row.className = 'move-row';
        row.innerHTML =
            '<span class="move-num">' + num + '.</span>' +
            '<span class="move-white">' + w + '</span>' +
            '<span class="move-black">' + b + '</span>';
        ml.appendChild(row);
    }
    ml.scrollTop = ml.scrollHeight;
}

function updateCaptured() {
    const placement = state.fen.split(' ')[0];
    const cur = {};
    for (const c of placement)
        if (c !== '/' && !(c >= '1' && c <= '8'))
            cur[c] = (cur[c] || 0) + 1;

    const wEl = document.getElementById('captured-white');
    const bEl = document.getElementById('captured-black');
    wEl.innerHTML = ''; bEl.innerHTML = '';

    // White's captures (black pieces off the board)
    for (const p of ['q', 'r', 'b', 'n', 'p']) {
        const n = (INITIAL_PIECES[p] || 0) - (cur[p] || 0);
        for (let i = 0; i < n; i++) {
            const s = document.createElement('span');
            s.className = 'captured-piece'; s.textContent = PIECES[p];
            wEl.appendChild(s);
        }
    }
    // Black's captures (white pieces off the board)
    for (const p of ['Q', 'R', 'B', 'N', 'P']) {
        const n = (INITIAL_PIECES[p] || 0) - (cur[p] || 0);
        for (let i = 0; i < n; i++) {
            const s = document.createElement('span');
            s.className = 'captured-piece'; s.textContent = PIECES[p];
            bEl.appendChild(s);
        }
    }
}

function updateEvalBar(scoreCp) {
    const clamped = Math.max(-500, Math.min(500, scoreCp));
    const pct = ((clamped + 500) / 1000) * 100;
    document.getElementById('eval-fill').style.height = pct + '%';

    const el = document.getElementById('eval-score');
    if (Math.abs(scoreCp) > 90000) {
        const m = Math.ceil((100000 - Math.abs(scoreCp)) / 2);
        el.textContent = (scoreCp > 0 ? '+' : '-') + 'M' + m;
    } else {
        const p = (scoreCp / 100).toFixed(1);
        el.textContent = (scoreCp >= 0 ? '+' : '') + p;
    }
}

function updateSearchStats(info) {
    document.getElementById('stat-depth').textContent = info.depth || '–';
    document.getElementById('stat-nodes').textContent = fmtNum(info.nodes);
    document.getElementById('stat-nps').textContent = fmtNum(info.nps);
    document.getElementById('stat-time').textContent = (info.time || 0) + 's';
}

function fmtNum(n) {
    if (n == null) return '–';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return '' + n;
}

function enableControls(on) {
    document.querySelectorAll('.controls-grid button').forEach(b => { b.disabled = !on; });
}

function clearSearchStats() {
    ['stat-depth', 'stat-nodes', 'stat-nps', 'stat-time'].forEach(id => {
        document.getElementById(id).textContent = '–';
    });
}

// ────────────────────────── Controls ─────────────────────────────

function setupControls() {
    document.getElementById('btn-new').addEventListener('click', () => {
        if (state.thinking) {
            worker.postMessage({ type: 'engine_stop' });
        }
        state.thinking = false;
        state.hintSquares = null;
        state.lastScore = 0;
        deselect();
        updateEvalBar(0);
        clearSearchStats();
        worker.postMessage({ type: 'new_game' });
    });

    document.getElementById('btn-undo').addEventListener('click', () => {
        if (!state.thinking) {
            state.hintSquares = null;
            worker.postMessage({ type: 'undo' });
        }
    });

    document.getElementById('btn-hint').addEventListener('click', () => {
        if (!state.thinking && !state.isGameOver && state.turn === state.playerColor) {
            state.thinking = true;
            enableControls(false);
            document.getElementById('status-text').innerHTML =
                '<span class="thinking">🔍 Analyzing…</span>';
            worker.postMessage({ type: 'get_hint', timeLimit: 2.0 });
        }
    });

    document.getElementById('btn-flip').addEventListener('click', () => {
        state.flipped = !state.flipped;
        renderBoard();
    });

    document.getElementById('difficulty').addEventListener('change', (e) => {
        state.difficulty = parseFloat(e.target.value);
    });

    // Side selection — starts a new game
    document.getElementById('btn-white').addEventListener('click', () => {
        if (state.playerColor === 'white') return;
        state.playerColor = 'white';
        state.flipped = false;
        document.getElementById('btn-white').classList.add('active');
        document.getElementById('btn-black').classList.remove('active');
        resetAndNewGame();
    });

    document.getElementById('btn-black').addEventListener('click', () => {
        if (state.playerColor === 'black') return;
        state.playerColor = 'black';
        state.flipped = true;
        document.getElementById('btn-black').classList.add('active');
        document.getElementById('btn-white').classList.remove('active');
        resetAndNewGame();
    });

    // Promotion dialog
    document.querySelectorAll('.promo-btn').forEach(btn => {
        btn.addEventListener('click', () => onPromotionSelect(btn.dataset.piece));
    });
    document.getElementById('promo-modal').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) {
            document.getElementById('promo-modal').classList.add('hidden');
            pendingPromotion = null;
        }
    });
}

function resetAndNewGame() {
    if (state.thinking) {
        worker.postMessage({ type: 'engine_stop' });
    }
    state.thinking = false;
    state.lastScore = 0;
    state.hintSquares = null;
    deselect();
    updateEvalBar(0);
    clearSearchStats();
    worker.postMessage({ type: 'new_game' });
}

// ────────────────────────── Init ─────────────────────────────────

function init() {
    state.board = parseFEN(START_FEN);
    setupControls();
    renderBoard();
}

document.addEventListener('DOMContentLoaded', init);
