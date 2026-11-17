import React, { useState } from 'react'
import { verifyGame } from '../utils/verifier.js'

// In-game: shows the committed server_seed_hash.
// Post-game: shows every seed + one-click local verification (no server round-trip).
export default function FairModal({ open, onClose, serverSeedHash, gameOverData }) {
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  if (!open) return null

  const auditable = Boolean(gameOverData && gameOverData.layout && gameOverData.p1_seed && gameOverData.p2_seed)

  const runVerify = async () => {
    setBusy(true)
    setResult(await verifyGame({
      serverSeed: gameOverData.server_seed,
      serverSeedHash: gameOverData.server_seed_hash,
      p1Seed: gameOverData.p1_seed,
      p2Seed: gameOverData.p2_seed,
      layout: gameOverData.layout,
    }))
    setBusy(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl bg-slate-800 p-6 shadow-2xl max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold mb-4">🔐 可验证公平性</h2>

        <div className="space-y-3 text-sm break-all">
          <div>
            <div className="text-slate-400 mb-1">Server Seed Hash（开局前承诺）</div>
            <code className="block rounded bg-slate-900 p-2 text-emerald-300">{serverSeedHash || '—'}</code>
          </div>

          {gameOverData ? (
            <>
              <div>
                <div className="text-slate-400 mb-1">Server Seed（局后揭示）</div>
                <code className="block rounded bg-slate-900 p-2">{gameOverData.server_seed}</code>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-slate-400 mb-1">P1 Seed（红方）</div>
                  <code className="block rounded bg-slate-900 p-2">{gameOverData.p1_seed ?? '（未揭示）'}</code>
                </div>
                <div>
                  <div className="text-slate-400 mb-1">P2 Seed（黑方）</div>
                  <code className="block rounded bg-slate-900 p-2">{gameOverData.p2_seed ?? '（未揭示）'}</code>
                </div>
              </div>

              {auditable ? (
                <button
                  onClick={runVerify}
                  disabled={busy}
                  className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 py-2 font-semibold"
                >
                  {busy ? '验牌中…' : '🧮 在本地一键验牌（不经过服务器）'}
                </button>
              ) : (
                <p className="text-xs text-slate-400">
                  本局在种子揭示阶段中止，未产生对局布局；可验证的只有 server_seed 承诺：
                  SHA-256(server_seed) 应与上方 hash 一致。
                </p>
              )}

              {result && (
                <div className={`rounded-lg p-3 ${result.ok ? 'bg-emerald-900/50 border border-emerald-500' : 'bg-red-900/50 border border-red-500'}`}>
                  <div className="font-bold mb-2">{result.ok ? '✅ 验证通过：本局发牌公平' : '❌ 验证失败：数据被篡改！'}</div>
                  {result.steps.map((s, i) => (
                    <div key={i} className="text-xs mb-1">
                      {s.ok ? '✓' : '✗'} {s.name} — {s.detail}
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-slate-400">
              对局结束后，服务端会公开 server_seed 与完整布局，届时可在此一键验证——全程只在你的浏览器里计算。
            </p>
          )}
        </div>

        <button onClick={onClose} className="mt-4 w-full rounded-lg bg-slate-700 hover:bg-slate-600 py-2">关闭</button>
      </div>
    </div>
  )
}
