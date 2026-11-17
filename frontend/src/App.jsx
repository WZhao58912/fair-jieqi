import React, { useEffect, useMemo, useRef, useState } from 'react'
import ChessBoard, { GLYPH } from './components/ChessBoard.jsx'
import FairModal from './components/FairModal.jsx'
import { verifyGame, runSelfTest, sha256Hex, STANDARD_DARK_PIECES } from './utils/verifier.js'
import vectors from './utils/test_vectors.json'

const REASON_LABEL = { KING_CAPTURED: '擒王', CHECKMATE: '绝杀', STALEMATE: '困毙', SEED_ABORT: '超时未揭示种子判负' }
const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
const randomSeed = () => Array.from(crypto.getRandomValues(new Uint8Array(16))).map((b) => b.toString(16).padStart(2, '0')).join('')

function VerifierTab({ gameOverData }) {
  const [form, setForm] = useState({ serverSeed: '', serverSeedHash: '', p1Seed: '', p2Seed: '', layout: '' })
  const [result, setResult] = useState(null)
  const [selfTest, setSelfTest] = useState(null)

  const fillFromLastGame = () => {
    if (!gameOverData) return
    setForm({
      serverSeed: gameOverData.server_seed,
      serverSeedHash: gameOverData.server_seed_hash,
      p1Seed: gameOverData.p1_seed,
      p2Seed: gameOverData.p2_seed,
      layout: gameOverData.layout.join(','),
    })
  }

  const run = async () => {
    const layout = form.layout.split(/[,\s]+/).filter(Boolean)
    setResult(await verifyGame({ ...form, layout }))
  }

  const field = (key, label, mono = true) => (
    <label className="block text-sm">
      <span className="text-slate-400">{label}</span>
      <input
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value.trim() })}
        className={`mt-1 w-full rounded bg-slate-900 border border-slate-700 px-2 py-1.5 ${mono ? 'font-mono text-xs' : ''}`}
      />
    </label>
  )

  return (
    <div className="max-w-xl mx-auto space-y-3">
      <p className="text-sm text-slate-400">
        独立验牌器：不依赖本局客户端，任何人拿到局后公开的四项数据都能在这里（纯浏览器本地）重算并比对。
      </p>
      {gameOverData && (
        <button onClick={fillFromLastGame} className="rounded bg-sky-700 hover:bg-sky-600 px-3 py-1.5 text-sm">
          ⤵ 填入最近一局的公开数据
        </button>
      )}
      {field('serverSeed', 'server_seed（局后揭示）')}
      {field('serverSeedHash', 'server_seed_hash（开局承诺）')}
      {field('p1Seed', 'p1_seed（红方种子）')}
      {field('p2Seed', 'p2_seed（黑方种子）')}
      {field('layout', '本局 30 子序列（逗号分隔，按 ALL_DARK_SLOTS 顺序）')}
      <button onClick={run} className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 py-2 font-semibold">
        🧮 本地验证
      </button>
      {result && (
        <div className={`rounded-lg p-3 text-sm ${result.ok ? 'bg-emerald-900/50 border border-emerald-500' : 'bg-red-900/50 border border-red-500'}`}>
          <div className="font-bold mb-1">{result.ok ? '✅ 验证通过' : '❌ 验证失败'}</div>
          {result.steps.map((s, i) => (
            <div key={i} className="text-xs">{s.ok ? '✓' : '✗'} {s.name} — {s.detail}</div>
          ))}
        </div>
      )}
      <hr className="border-slate-700" />
      <button onClick={async () => setSelfTest(await runSelfTest(vectors))} className="rounded bg-slate-700 hover:bg-slate-600 px-3 py-1.5 text-sm">
        ⚙️ 前后端一致性自检（共享测试向量 × {vectors.length}）
      </button>
      {selfTest && (
        <div className={`text-sm ${selfTest.ok ? 'text-emerald-400' : 'text-red-400'}`}>
          {selfTest.ok ? `✅ ${selfTest.results.length} 组向量全部与后端 Python 实现逐子一致` : '❌ 自检失败：前后端实现不一致！'}
        </div>
      )}
    </div>
  )
}

// Dev preview harness: open /?demo to see the board with a sample position
// (no server needed).
function demoBoard() {
  const b = Array.from({ length: 10 }, () => Array(9).fill(null))
  const dark = (owner) => ({ state: 'DARK', initial_owner: owner })
  for (const c of [0, 1, 2, 3, 5, 6, 7, 8]) { b[0][c] = dark('RED'); b[9][c] = dark('BLACK') }
  b[2][1] = dark('RED'); b[2][7] = dark('RED')
  b[7][1] = dark('BLACK'); b[7][7] = dark('BLACK')
  for (const c of [0, 2, 4, 6, 8]) { b[3][c] = dark('RED'); b[6][c] = dark('BLACK') }
  b[0][4] = { state: 'UP', code: 'R_SHUAI' }
  b[9][4] = { state: 'UP', code: 'B_JIANG' }
  b[4][4] = { state: 'UP', code: 'R_BING' }
  b[5][4] = { state: 'UP', code: 'B_ZU' }
  b[4][1] = { state: 'UP', code: 'R_JU' }
  b[5][7] = { state: 'UP', code: 'B_PAO' }
  return b
}

function DemoBoard() {
  return (
    <div className="min-h-screen p-6 flex flex-col items-center gap-6">
      <ChessBoard
        board={demoBoard()}
        selected={[4, 4]}
        legalMoves={[[3, 4], [4, 3], [4, 5], [5, 4]]}
        lastFlip={[5, 7]}
        lastMove={{ from: [6, 4], to: [5, 4] }}
        onSquareClick={() => {}}
        disabled={false}
      />
      <div className="w-72">
        <CapturesPanel captures={['B_ZU', 'R_MA', 'B_PAO', 'B_ZU', 'R_BING', 'B_XIANG', 'R_SHI']} />
      </div>
    </div>
  )
}

// Ordered lost-pieces panel: each side's losses in capture order.
function CapturesPanel({ captures }) {
  const row = (label, hint, list, cls) => (
    <div>
      <div className="text-slate-400 text-xs mb-1">
        {label} <span className="text-slate-500">（{hint}）· {list.length} 子</span>
      </div>
      <div className="flex flex-wrap gap-1 min-h-[30px] items-center">
        {list.length === 0
          ? <span className="text-slate-600 text-xs">尚无</span>
          : list.map((code, i) => <span key={i} className={`jq-chip ${cls}`}>{GLYPH[code]}</span>)}
      </div>
    </div>
  )
  return (
    <div className="rounded-xl bg-slate-800 p-4 text-sm space-y-3">
      <div className="font-semibold">⚰️ 失子记录 <span className="text-xs text-slate-500 font-normal">按被吃顺序</span></div>
      {row('红方失子', '黑方战绩', captures.filter((c) => c.startsWith('R_')), 'jq-chip-red')}
      {row('黑方失子', '红方战绩', captures.filter((c) => c.startsWith('B_')), 'jq-chip-black')}
    </div>
  )
}

// ---- post-game replay (复盘) ------------------------------------------------
// Rebuilds every board position locally from the publicly revealed layout +
// move history. No server round-trip, fully auditable alongside verification.
function buildReplay({ layout, layout_slots, moves }) {
  const grid = new Map()
  const key = (r, c) => `${r},${c}`
  grid.set(key(0, 4), { code: 'R_SHUAI', faceUp: true, owner: 'RED' })
  grid.set(key(9, 4), { code: 'B_JIANG', faceUp: true, owner: 'BLACK' })
  layout.forEach((code, i) => {
    const [r, c] = layout_slots[i]
    grid.set(key(r, c), { code, faceUp: false, owner: r <= 3 ? 'RED' : 'BLACK' })
  })
  const snap = () => {
    const b = Array.from({ length: 10 }, () => Array(9).fill(null))
    for (const [k, p] of grid) {
      const [r, c] = k.split(',').map(Number)
      b[r][c] = p.faceUp ? { state: 'UP', code: p.code } : { state: 'DARK', initial_owner: p.owner }
    }
    return b
  }
  const boards = [snap()]
  const caps = [[]]
  const soFar = []
  for (const m of moves) {
    const piece = grid.get(key(m.from[0], m.from[1]))
    grid.delete(key(m.from[0], m.from[1]))
    const target = grid.get(key(m.to[0], m.to[1]))
    if (target) soFar.push(target.code)
    grid.set(key(m.to[0], m.to[1]), piece)
    if (m.flipped) piece.faceUp = true
    boards.push(snap())
    caps.push([...soFar])
  }
  return { boards, caps }
}

function ReplayModal({ open, onClose, data }) {
  const [ply, setPly] = useState(0)
  const replay = useMemo(() => (data ? buildReplay(data) : null), [data])
  useEffect(() => { if (open) setPly(data?.moves?.length ?? 0) }, [open, data])
  if (!open || !replay) return null

  const total = data.moves.length
  const cur = ply > 0 ? data.moves[ply - 1] : null
  const describe = (m, i) => {
    let t = `第 ${i} 手 · ${m.side === 'RED' ? '红方' : '黑方'} (${m.from}) → (${m.to})`
    if (m.flipped) t += `，翻开 ${GLYPH[m.flipped]}`
    if (m.captured) t += `，吃 ${GLYPH[m.captured]}`
    return t
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 p-4" onClick={onClose}>
      <div className="mx-auto w-fit" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between rounded-xl bg-slate-800 px-4 py-2">
          <div className="font-bold">📼 对局复盘 <span className="text-sm text-slate-400 font-normal">{ply === 0 ? '初始布局' : describe(cur, ply)}（{ply}/{total}）</span></div>
          <button onClick={onClose} className="ml-6 rounded bg-slate-700 hover:bg-slate-600 px-3 py-1 text-sm">关闭</button>
        </div>
        <div className="flex gap-4 items-start flex-wrap justify-center">
          <ChessBoard
            board={replay.boards[ply]}
            selected={null}
            legalMoves={[]}
            lastFlip={cur && cur.flipped ? cur.to : null}
            lastMove={cur ? { from: cur.from, to: cur.to } : null}
            onSquareClick={() => {}}
            disabled
          />
          <div className="w-72 space-y-3">
            <div className="rounded-xl bg-slate-800 p-4 space-y-3">
              <div className="flex justify-between gap-1">
                <button onClick={() => setPly(0)} disabled={ply === 0} className="flex-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40 py-1.5">⏮</button>
                <button onClick={() => setPly((p) => Math.max(0, p - 1))} disabled={ply === 0} className="flex-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40 py-1.5">◀</button>
                <button onClick={() => setPly((p) => Math.min(total, p + 1))} disabled={ply === total} className="flex-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40 py-1.5">▶</button>
                <button onClick={() => setPly(total)} disabled={ply === total} className="flex-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40 py-1.5">⏭</button>
              </div>
              <input
                type="range" min={0} max={total} value={ply}
                onChange={(e) => setPly(Number(e.target.value))}
                className="w-full accent-emerald-500"
              />
              {ply === total && (
                <div className="text-center text-amber-300 font-bold text-sm">
                  🏁 终局：{data.winner === 'RED' ? '红方' : '黑方'}胜（{{ KING_CAPTURED: '擒王', CHECKMATE: '绝杀', STALEMATE: '困毙' }[data.reason] || data.reason}）
                </div>
              )}
            </div>
            <CapturesPanel captures={replay.caps[ply]} />
          </div>
        </div>
      </div>
    </div>
  )
}

const DEMO_SLOTS = [
  [0, 0], [0, 1], [0, 2], [0, 3], [0, 5], [0, 6], [0, 7], [0, 8], [2, 1], [2, 7], [3, 0], [3, 2], [3, 4], [3, 6], [3, 8],
  [6, 0], [6, 2], [6, 4], [6, 6], [6, 8], [7, 1], [7, 7], [9, 0], [9, 1], [9, 2], [9, 3], [9, 5], [9, 6], [9, 7], [9, 8],
]

const DEMO_GAME_OVER = {
  winner: 'RED',
  reason: 'CHECKMATE',
  layout: STANDARD_DARK_PIECES,
  layout_slots: DEMO_SLOTS,
  moves: [
    { side: 'RED', from: [3, 0], to: [4, 0], flipped: 'R_BING', captured: null },
    { side: 'BLACK', from: [6, 0], to: [5, 0], flipped: 'B_JU', captured: null },
    { side: 'RED', from: [4, 0], to: [5, 0], flipped: null, captured: 'B_JU' },
    { side: 'BLACK', from: [9, 1], to: [7, 2], flipped: 'B_SHI', captured: null },
    { side: 'RED', from: [2, 1], to: [2, 4], flipped: 'R_SHI', captured: null },
    { side: 'BLACK', from: [6, 4], to: [5, 4], flipped: 'B_MA', captured: null },
    { side: 'RED', from: [2, 4], to: [5, 4], flipped: null, captured: 'B_MA' },
  ],
}

function DemoReplay() {
  return (
    <div className="min-h-screen p-6">
      <ReplayModal open onClose={() => {}} data={DEMO_GAME_OVER} />
    </div>
  )
}

export default function App() {
  const demo = new URLSearchParams(location.search).get('demo')
  if (demo === 'replay') return <DemoReplay />
  if (demo !== null) return <DemoBoard />
  return <RealApp />
}

function RealApp() {
  const [tab, setTab] = useState('game')
  const [ws, setWs] = useState(null)
  const [log, setLog] = useState([])
  const [roomId, setRoomId] = useState('')
  const [joinId, setJoinId] = useState('')
  const [side, setSide] = useState(null)
  const [phase, setPhase] = useState('LOBBY') // LOBBY | WAITING | SEED | PLAYING | OVER
  const [seedInput, setSeedInput] = useState(randomSeed())
  const [seedStage, setSeedStage] = useState('COMMIT') // COMMIT | REVEAL
  const [seedLocked, setSeedLocked] = useState(false)
  const [seedRevealed, setSeedRevealed] = useState(false)
  const [revealTimeout, setRevealTimeout] = useState(null)
  const [serverSeedHash, setServerSeedHash] = useState('')
  const [board, setBoard] = useState(null)
  const [turn, setTurn] = useState(null)
  const [checkSide, setCheckSide] = useState(null)
  const [selected, setSelected] = useState(null)
  const [legalMoves, setLegalMoves] = useState([])
  const [lastFlip, setLastFlip] = useState(null)
  const [lastMove, setLastMove] = useState(null)
  const [captures, setCaptures] = useState([])
  const [gameOverData, setGameOverData] = useState(null)
  const [fairOpen, setFairOpen] = useState(false)
  const [replayOpen, setReplayOpen] = useState(false)
  const sideRef = useRef(side)
  sideRef.current = side

  const say = (text) => setLog((l) => [text, ...l].slice(0, 30))
  const send = (msg) => ws && ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg))

  useEffect(() => {
    const socket = new WebSocket(WS_URL)
    socket.onmessage = (e) => {
      const m = JSON.parse(e.data)
      switch (m.type) {
        case 'ROOM_CREATED':
          setRoomId(m.room_id); setSide(m.side); setPhase('WAITING')
          say(`房间 ${m.room_id} 已创建，你是红方，等待对手…`); break
        case 'ROOM_JOINED':
          setRoomId(m.room_id); setSide(m.side); say(`已加入房间 ${m.room_id}，你是黑方`); break
        case 'OPPONENT_JOINED':
          say('对手已加入'); break
        case 'SEED_COMMIT':
          setServerSeedHash(m.server_seed_hash); setPhase('SEED'); setSeedStage('COMMIT')
          say('服务端已提交种子承诺（hash），请锁定你的种子承诺'); break
        case 'SEED_REVEAL_BEGIN':
          setSeedStage('REVEAL'); setRevealTimeout(m.timeout)
          say('双方种子承诺已锁定，请揭示种子明文'); break
        case 'SEED_RECEIVED':
          say(`${m.side === 'RED' ? '红方' : '黑方'}${m.stage === 'COMMIT' ? '种子承诺已锁定' : '种子已揭示'}`); break
        case 'GAME_START':
          setBoard(m.board); setTurn(m.turn); setCheckSide(m.check ?? null); setPhase('PLAYING')
          setLastMove(null); setLastFlip(null); setCaptures([])
          say('双方种子齐备，洗牌完成，对局开始！红方先行'); break
        case 'LEGAL_MOVES':
          setLegalMoves(m.moves); break
        case 'MOVE_RESULT': {
          setBoard(m.board); setTurn(m.turn); setCheckSide(m.check ?? null)
          setSelected(null); setLegalMoves([])
          setLastFlip(m.flipped ? m.to : null)
          setLastMove({ from: m.from, to: m.to })
          if (m.captures) setCaptures(m.captures)
          const who = m.side === 'RED' ? '红方' : '黑方'
          let text = `${who} (${m.from}) → (${m.to})`
          if (m.flipped) text += `，翻开：${GLYPH[m.flipped]}`
          if (m.captured) text += `，吃掉 ${GLYPH[m.captured.code]}`
          if (m.check) text += ` —— 将军！`
          say(text); break
        }
        case 'GAME_OVER':
          setGameOverData(m); setPhase('OVER'); setCheckSide(null)
          say(m.winner
            ? `对局结束：${m.winner === 'RED' ? '红方' : '黑方'}胜（${REASON_LABEL[m.reason] || m.reason}）`
            : '对局流局：双方均未揭示种子'); break
        case 'OPPONENT_LEFT':
          say('对手已离开'); break
        case 'ERROR':
          say(`⚠️ ${m.detail}`); break
        default:
      }
    }
    setWs(socket)
    return () => socket.close()
  }, [])

  const onSquareClick = (r, c) => {
    if (phase !== 'PLAYING' || turn !== side) return
    if (selected && legalMoves.some(([mr, mc]) => mr === r && mc === c)) {
      send({ type: 'MOVE', from: selected, to: [r, c] })
    } else {
      const cell = board[r][c]
      if (!cell) return setSelected(null), setLegalMoves([])
      const mine = cell.state === 'DARK' ? cell.initial_owner === side : cell.code.startsWith(side === 'RED' ? 'R_' : 'B_')
      if (!mine) return setSelected(null), setLegalMoves([])
      setSelected([r, c])
      send({ type: 'LEGAL_MOVES', coord: [r, c] })
    }
  }

  return (
    <div className="min-h-screen p-4">
      <header className="max-w-5xl mx-auto flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">可验证公平揭棋 <span className="text-emerald-400 text-sm font-normal">Provably Fair · No Trust Needed</span></h1>
        <nav className="space-x-2">
          <button onClick={() => setTab('game')} className={`px-3 py-1 rounded ${tab === 'game' ? 'bg-sky-700' : 'bg-slate-700'}`}>对局</button>
          <button onClick={() => setTab('verify')} className={`px-3 py-1 rounded ${tab === 'verify' ? 'bg-sky-700' : 'bg-slate-700'}`}>验牌器</button>
        </nav>
      </header>

      {tab === 'verify' ? (
        <VerifierTab gameOverData={gameOverData} />
      ) : (
        <div className="max-w-5xl mx-auto flex gap-6 items-start flex-wrap">
          <div className="space-y-3 w-72">
            {phase === 'LOBBY' && (
              <div className="rounded-xl bg-slate-800 p-4 space-y-2">
                <button onClick={() => send({ type: 'CREATE_ROOM' })} className="w-full rounded-lg bg-red-700 hover:bg-red-600 py-2 font-semibold">
                  创建房间（执红先行）
                </button>
                <div className="flex gap-2">
                  <input value={joinId} onChange={(e) => setJoinId(e.target.value)} placeholder="房间号"
                    className="flex-1 rounded bg-slate-900 border border-slate-700 px-2 py-1.5" />
                  <button onClick={() => send({ type: 'JOIN_ROOM', room_id: joinId })} className="rounded-lg bg-slate-600 hover:bg-slate-500 px-3">
                    加入
                  </button>
                </div>
              </div>
            )}

            {phase === 'WAITING' && (
              <div className="rounded-xl bg-slate-800 p-4 text-sm">
                房间号 <span className="text-2xl font-mono text-amber-300">{roomId}</span> — 把它发给对手。
              </div>
            )}

            {phase === 'SEED' && (
              <div className="rounded-xl bg-slate-800 p-4 space-y-2 text-sm">
                <div className="text-slate-400">
                  你的随机种子{seedStage === 'COMMIT' && !seedLocked ? '（可手动修改）' : '（已锁定）'}：
                </div>
                <input value={seedInput} onChange={(e) => setSeedInput(e.target.value)}
                  disabled={seedLocked}
                  className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1.5 font-mono text-xs disabled:opacity-60" />
                {seedStage === 'COMMIT' ? (
                  <div className="flex gap-2">
                    <button onClick={() => setSeedInput(randomSeed())} disabled={seedLocked}
                      className="rounded bg-slate-700 px-3 py-1.5 disabled:opacity-40">🎲 重摇</button>
                    <button
                      onClick={async () => {
                        const hash = await sha256Hex(seedInput)
                        send({ type: 'SUBMIT_SEED_COMMIT', seed_hash: hash })
                        setSeedLocked(true)
                      }}
                      disabled={seedLocked || !seedInput}
                      className="flex-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 py-1.5 font-semibold"
                    >
                      {seedLocked ? '🔒 承诺已锁定，等待对方…' : '① 锁定种子承诺'}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="text-xs text-amber-300">
                      ⏱ {revealTimeout ?? 60} 秒内未揭示者判负（防磨种子）
                    </div>
                    <button
                      onClick={() => { send({ type: 'SUBMIT_SEED', seed: seedInput }); setSeedRevealed(true) }}
                      disabled={seedRevealed}
                      className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 py-1.5 font-semibold"
                    >
                      {seedRevealed ? '✓ 已揭示，等待对方…' : '② 揭示种子明文'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {(phase === 'PLAYING' || phase === 'OVER') && (
              <div className="rounded-xl bg-slate-800 p-4 text-sm space-y-2">
                <div>你执 <b className={side === 'RED' ? 'text-red-400' : 'text-slate-300'}>{side === 'RED' ? '红' : '黑'}</b></div>
                {phase === 'PLAYING' && (
                  <div>当前行棋：<b className={turn === 'RED' ? 'text-red-400' : 'text-slate-200'}>{turn === 'RED' ? '红方' : '黑方'}</b>{turn === side ? '（轮到你了）' : ''}</div>
                )}
                {phase === 'PLAYING' && checkSide && (
                  <div className={`rounded-lg px-3 py-2 font-bold text-center animate-pulse ${checkSide === side ? 'bg-red-700 text-white' : 'bg-amber-600 text-white'}`}>
                    ⚡ 将军！{checkSide === side ? '你被将军，必须应将' : '对方被将军'}
                  </div>
                )}
                {phase === 'OVER' && gameOverData && (
                  <div className="text-amber-300 font-bold">
                    🏁 {gameOverData.winner
                      ? `${gameOverData.winner === 'RED' ? '红方' : '黑方'}获胜（${REASON_LABEL[gameOverData.reason] || gameOverData.reason}）`
                      : '流局（双方均未揭示种子）'}
                  </div>
                )}
                <button onClick={() => setFairOpen(true)} className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-500 py-2 font-semibold">
                  🔐 公平性 {phase === 'OVER' ? '· 一键验牌' : '承诺信息'}
                </button>
                {phase === 'OVER' && gameOverData?.moves?.length > 0 && (
                  <button onClick={() => setReplayOpen(true)} className="w-full rounded-lg bg-amber-600 hover:bg-amber-500 py-2 font-semibold">
                    📼 复盘回放（{gameOverData.moves.length} 手）
                  </button>
                )}
              </div>
            )}

            {(phase === 'PLAYING' || phase === 'OVER') && <CapturesPanel captures={captures} />}

            <div className="rounded-xl bg-slate-800 p-3 text-xs text-slate-400 space-y-1 max-h-64 overflow-y-auto">
              {log.map((l, i) => <div key={i}>{l}</div>)}
            </div>
          </div>

          <div>
            {board ? (
              <ChessBoard
                board={board}
                selected={selected}
                legalMoves={legalMoves}
                lastFlip={lastFlip}
                lastMove={lastMove}
                onSquareClick={onSquareClick}
                disabled={phase !== 'PLAYING'}
              />
            ) : (
              <div className="w-[532px] h-[592px] rounded-xl bg-slate-800 flex items-center justify-center text-slate-500">
                棋盘将在对局开始后显示
              </div>
            )}
          </div>
        </div>
      )}

      <FairModal open={fairOpen} onClose={() => setFairOpen(false)} serverSeedHash={serverSeedHash} gameOverData={gameOverData} />
      <ReplayModal open={replayOpen} onClose={() => setReplayOpen(false)} data={gameOverData} />
    </div>
  )
}
