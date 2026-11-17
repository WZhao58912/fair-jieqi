// Pure-browser verifier: SHA-256 via Web Crypto + the same hash-chain
// Fisher-Yates shuffle as backend/app/core/fair.py. Identical seeds MUST
// produce a byte-identical layout in both languages (pinned by
// test_vectors.json, asserted by runSelfTest).
//
// Standard Jieqi rule: each side's 15 dark pieces shuffle ONLY within their
// own half -- a flipped piece always keeps its color; only its kind is hidden.

export const RED_DARK_POOL = [
  'R_JU', 'R_JU', 'R_MA', 'R_MA', 'R_PAO', 'R_PAO', 'R_XIANG', 'R_XIANG', 'R_SHI', 'R_SHI', 'R_BING', 'R_BING', 'R_BING', 'R_BING', 'R_BING',
]
export const BLACK_DARK_POOL = [
  'B_JU', 'B_JU', 'B_MA', 'B_MA', 'B_PAO', 'B_PAO', 'B_XIANG', 'B_XIANG', 'B_SHI', 'B_SHI', 'B_ZU', 'B_ZU', 'B_ZU', 'B_ZU', 'B_ZU',
]
export const STANDARD_DARK_PIECES = [...RED_DARK_POOL, ...BLACK_DARK_POOL]

export async function sha256Hex(message) {
  const msgBuffer = new TextEncoder().encode(message)
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function shufflePool(pool, baseSeed) {
  const pieces = [...pool]
  for (let i = pieces.length - 1; i > 0; i--) {
    const digest = await sha256Hex(`${baseSeed}:${i}`)
    // 48 bits < Number.MAX_SAFE_INTEGER (2^53) -- no precision loss.
    const randInt = parseInt(digest.slice(0, 12), 16)
    const j = randInt % (i + 1)
    ;[pieces[i], pieces[j]] = [pieces[j], pieces[i]]
  }
  return pieces
}

export async function deterministicShuffle(serverSeed, p1Seed, p2Seed) {
  const baseSeed = `${serverSeed}:${p1Seed}:${p2Seed}`
  const red = await shufflePool(RED_DARK_POOL, `${baseSeed}:R`)
  const black = await shufflePool(BLACK_DARK_POOL, `${baseSeed}:B`)
  return [...red, ...black]
}

// Full post-game audit. Returns { ok, steps: [{name, ok, detail}] }.
export async function verifyGame({ serverSeed, serverSeedHash, p1Seed, p2Seed, layout }) {
  const steps = []

  const recomputedHash = await sha256Hex(serverSeed)
  const hashOk = recomputedHash === serverSeedHash
  steps.push({
    name: '承诺校验 SHA-256(server_seed) === server_seed_hash',
    ok: hashOk,
    detail: hashOk ? '服务端无法事后换种子' : `期望 ${serverSeedHash}，实算 ${recomputedHash}`,
  })

  const recomputed = await deterministicShuffle(serverSeed, p1Seed, p2Seed)
  const layoutOk = JSON.stringify(recomputed) === JSON.stringify(layout)
  steps.push({
    name: '重算双方半场洗牌并比对本局 30 子序列',
    ok: layoutOk,
    detail: layoutOk ? '本地重算与当局实际布局逐子一致' : '重算结果与本局布局不一致！',
  })

  return { ok: steps.every((s) => s.ok), steps, recomputed }
}

// Consistency self-test: replay the shared cross-language vectors.
export async function runSelfTest(vectors) {
  const results = []
  for (const v of vectors) {
    const layout = await deterministicShuffle(v.server_seed, v.p1_seed, v.p2_seed)
    const hash = await sha256Hex(v.server_seed)
    results.push({
      ok: JSON.stringify(layout) === JSON.stringify(v.layout) && hash === v.server_seed_hash,
      server_seed: v.server_seed,
    })
  }
  return { ok: results.every((r) => r.ok), results }
}
