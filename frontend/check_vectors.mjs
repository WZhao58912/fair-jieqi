// Node-side cross-language check: JS verifier vs. Python-generated vectors.
// Run: node check_vectors.mjs   (from frontend/)
import { deterministicShuffle, sha256Hex } from './src/utils/verifier.js'
import { readFileSync } from 'node:fs'

const vectors = JSON.parse(readFileSync(new URL('./src/utils/test_vectors.json', import.meta.url)))
let allOk = true
for (const [idx, v] of vectors.entries()) {
  const layout = await deterministicShuffle(v.server_seed, v.p1_seed, v.p2_seed)
  const hash = await sha256Hex(v.server_seed)
  const ok = JSON.stringify(layout) === JSON.stringify(v.layout) && hash === v.server_seed_hash
  allOk &&= ok
  console.log(`vector ${idx + 1}: ${ok ? 'OK' : 'MISMATCH'}`)
}
console.log(allOk ? 'ALL VECTORS MATCH (JS === Python)' : 'FAILURE')
process.exit(allOk ? 0 : 1)
