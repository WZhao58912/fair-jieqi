import React from 'react'

export const GLYPH = {
  R_SHUAI: '帅', B_JIANG: '将',
  R_JU: '车', B_JU: '車', R_MA: '马', B_MA: '馬',
  R_PAO: '炮', B_PAO: '砲', R_XIANG: '相', B_XIANG: '象',
  R_SHI: '仕', B_SHI: '士', R_BING: '兵', B_ZU: '卒',
}

// ---- board geometry: pieces sit on line intersections --------------------
const S = 56 // spacing between intersections
const M = 42 // outer margin
const W = 8 * S + 2 * M
const H = 9 * S + 2 * M
const X = (c) => M + c * S
const Y = (r) => M + r * S

const LINE = '#7c5a2b'

function GridLines() {
  const lines = []
  for (let r = 0; r <= 9; r++) {
    lines.push(<line key={`h${r}`} x1={X(0)} y1={Y(r)} x2={X(8)} y2={Y(r)} stroke={LINE} strokeWidth={r === 0 || r === 9 ? 2 : 1} />)
  }
  // verticals: outer files run full height, inner files break at the river
  for (let c = 0; c <= 8; c++) {
    if (c === 0 || c === 8) {
      lines.push(<line key={`v${c}`} x1={X(c)} y1={Y(0)} x2={X(c)} y2={Y(9)} stroke={LINE} strokeWidth={2} />)
    } else {
      lines.push(<line key={`vt${c}`} x1={X(c)} y1={Y(0)} x2={X(c)} y2={Y(4)} stroke={LINE} strokeWidth={1} />)
      lines.push(<line key={`vb${c}`} x1={X(c)} y1={Y(5)} x2={X(c)} y2={Y(9)} stroke={LINE} strokeWidth={1} />)
    }
  }
  // palace diagonals
  const diag = (a, b) => (
    <line key={`d${a}${b}`} x1={X(a[1])} y1={Y(a[0])} x2={X(b[1])} y2={Y(b[0])} stroke={LINE} strokeWidth={1} />
  )
  lines.push(diag([0, 3], [2, 5]), diag([0, 5], [2, 3]), diag([7, 3], [9, 5]), diag([7, 5], [9, 3]))
  return <g>{lines}</g>
}

// little corner ticks marking cannon / soldier points
function Markers() {
  const pts = [
    [2, 1], [2, 7], [7, 1], [7, 7],
    [3, 0], [3, 2], [3, 4], [3, 6], [3, 8],
    [6, 0], [6, 2], [6, 4], [6, 6], [6, 8],
  ]
  const d = 6, len = 9
  const out = []
  for (const [r, c] of pts) {
    for (const sx of [-1, 1]) {
      if ((c === 0 && sx === -1) || (c === 8 && sx === 1)) continue
      for (const sy of [-1, 1]) {
        const x = X(c) + sx * d, y = Y(r) + sy * d
        out.push(
          <path
            key={`${r},${c},${sx},${sy}`}
            d={`M ${x} ${y + sy * len} L ${x} ${y} L ${x + sx * len} ${y}`}
            stroke={LINE} strokeWidth={1.2} fill="none"
          />,
        )
      }
    }
  }
  return <g>{out}</g>
}

function RiverText() {
  const y = (Y(4) + Y(5)) / 2
  const style = { fontFamily: '"Kaiti SC","STKaiti","KaiTi","楷体",serif', fontSize: 34, fill: 'rgba(124,90,43,0.75)', letterSpacing: 12 }
  return (
    <g textAnchor="middle" dominantBaseline="central" style={style}>
      <text x={X(2)} y={y}>楚 河</text>
      <text x={X(6)} y={y}>汉 界</text>
    </g>
  )
}

// ---- pieces ---------------------------------------------------------------
function Piece({ cell, flipped, selected, capturable }) {
  const cls = []
  if (cell.state === 'DARK') {
    cls.push('jq-piece', cell.initial_owner === 'RED' ? 'jq-dark-red' : 'jq-dark-black')
    return (
      <div className={`${cls.join(' ')} ${selected ? 'jq-selected' : ''} ${capturable ? 'jq-capturable' : ''}`}>
        <span className="jq-dark-glyph">揭</span>
      </div>
    )
  }
  cls.push('jq-piece', cell.code.startsWith('R_') ? 'jq-red' : 'jq-black')
  return (
    <div className={`${cls.join(' ')} ${selected ? 'jq-selected' : ''} ${capturable ? 'jq-capturable' : ''} ${flipped ? 'animate-flip' : ''}`}>
      <span className="jq-glyph">{GLYPH[cell.code] || '?'}</span>
    </div>
  )
}

// board: 10x9 of null | {state:'DARK',initial_owner} | {state:'UP',code}
export default function ChessBoard({ board, selected, legalMoves, lastFlip, lastMove, onSquareClick, disabled }) {
  const isLegal = (r, c) => legalMoves.some(([mr, mc]) => mr === r && mc === c)
  const isSelected = (r, c) => selected && selected[0] === r && selected[1] === c
  const isLastFlip = (r, c) => lastFlip && lastFlip[0] === r && lastFlip[1] === c
  const isLastMove = (r, c) => lastMove && ((lastMove.from[0] === r && lastMove.from[1] === c) || (lastMove.to[0] === r && lastMove.to[1] === c))

  return (
    <div className="rounded-xl bg-[#3a2c17] p-2 shadow-2xl">
      <div className="relative select-none" style={{ width: W, height: H }}>
        <svg width={W} height={H} className="absolute inset-0 rounded-md" style={{ background: 'linear-gradient(135deg,#e8c98a 0%,#e2bd77 50%,#ddb26b 100%)' }}>
          <rect x={6} y={6} width={W - 12} height={H - 12} fill="none" stroke={LINE} strokeWidth={2.5} />
          <GridLines />
          <Markers />
          <RiverText />
        </svg>

        {board.map((row, r) =>
          row.map((cell, c) => (
            <button
              key={`${r}-${c}`}
              onClick={() => onSquareClick(r, c)}
              disabled={disabled}
              className="absolute jq-hit"
              style={{ left: X(c), top: Y(r), transform: 'translate(-50%,-50%)' }}
            >
              {isLastMove(r, c) && <span className="jq-lastmove" />}
              {cell
                ? <Piece cell={cell} flipped={isLastFlip(r, c)} selected={isSelected(r, c)} capturable={isLegal(r, c)} />
                : isLegal(r, c) && <span className="jq-dot" />}
            </button>
          )),
        )}
      </div>
    </div>
  )
}
