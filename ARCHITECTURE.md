# ARCHITECTURE · 架构设计

## 总览

```
浏览器 A (React)                FastAPI 后端                 浏览器 B (React)
┌──────────────┐   WebSocket   ┌────────────────────┐   WebSocket  ┌──────────────┐
│ ChessBoard   │ ◄──────────► │ ws/manager.py      │ ◄──────────► │ ChessBoard   │
│ FairModal    │   JSON 消息   │  · 房间/状态机      │   JSON 消息   │ FairModal    │
│ verifier.js  │              │  · 信息隔离         │              │ verifier.js  │
└──────────────┘              │ game/engine.py     │              └──────────────┘
        ▲                     │  · 揭棋规则引擎      │                     ▲
        └────── 局后本地验牌 ──┤ game/board.py      │ ────── 局后公开数据 ┘
              (不再信任服务器) │  · 棋盘/初始映射     │
                              │ core/fair.py       │
                              │  · 承诺+确定性洗牌   │
                              └────────────────────┘
```

## 目录结构

```text
fair-jieqi/
├── README.md
├── ARCHITECTURE.md
├── backend/
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py              # FastAPI 入口，/health + /ws
│   │   ├── core/fair.py         # 承诺方案 + SHA-256 哈希链 Fisher-Yates + 局后验证
│   │   ├── game/board.py        # 10x9 棋盘、30 暗棋位映射、public_state() 脱敏序列化
│   │   ├── game/engine.py       # 揭棋规则引擎（盲走/翻开/易主/相仕过河/胜负）
│   │   └── ws/manager.py        # 房间匹配、LOBBY→SEED_COMMIT→SEED_REVEAL→PLAYING→GAME_OVER、广播
│   └── tests/
│       ├── test_fair.py         # 洗牌确定性、置换完整性、防篡改、共享向量
│       ├── test_engine.py       # 盲走规则、翻开易主、揭棋特权、吃王/困毙
│       ├── test_vectors.json    # 跨语言共享测试向量（Python 生成，JS 复算）
│       ├── generate_vectors.py  # 重新生成向量
│       └── e2e_smoke.py         # 双客户端 WebSocket 全流程冒烟
└── frontend/
    ├── package.json / vite.config.js / tailwind.config.js
    ├── check_vectors.mjs        # Node 侧 JS↔Python 一致性校验
    └── src/
        ├── App.jsx              # 大厅 / 对局 / 独立验牌器 Tab，WebSocket 客户端
        ├── components/ChessBoard.jsx   # 10x9 棋盘、暗子底色区分半场、翻子动画、合法点高亮
        ├── components/FairModal.jsx    # 局内承诺展示 + 局后一键本地验牌
        └── utils/
            ├── verifier.js      # 纯浏览器 SHA-256 + 同款洗牌 + verifyGame + runSelfTest
            └── test_vectors.json
```

## 公平性协议时序

| 阶段 | 服务端 | 客户端可见 |
|---|---|---|
| LOBBY | 建房/加入，房主执红先行 | room_id、执棋方 |
| SEED_COMMIT | 生成 `server_seed`，**只**广播 `SHA-256(server_seed)`；收双方 `SHA-256(p_seed)` 承诺并校验格式 | server_seed_hash、双方承诺进度 |
| SEED_REVEAL | 双方承诺齐后进入；校验每个揭示的 `SHA-256(p_seed)` 与承诺匹配，**超时未揭示者判负（SEED_ABORT）** | 双方 seed_hash、揭示进度、超时秒数 |
| PLAYING | `deterministic_shuffle` → Board/Engine；走子经引擎校验 | public_board（暗子零身份信息）、LEGAL_MOVES、MOVE_RESULT（仅公布翻开/被吃子身份） |
| GAME_OVER | 广播 `server_seed`、双方种子、完整 30 子序列与槽位顺序、失子与走子历史 | 一切验牌与复盘材料 |

关键不变式：
1. `server_seed` 明文只在 `GAME_OVER` 消息中出现；玩家种子明文只在双方承诺锁定之后才被接受。
2. `Board.public_state()` 是客户端棋盘数据的**唯一**出口，暗子字段不含 `code`。
3. 洗牌输入完全由"已承诺的 server_seed + 双方种子"决定，任何一方事后都无法替换；任何一方提交承诺时都无法预测布局（防磨种子）。
4. 布局前 15 子恒为红、后 15 子恒为黑（`test_shuffle_never_crosses_colors` 锁定）——棋子颜色永不改变。

## 规则引擎设计要点

- **盲走**：暗子按 `POSITION_RULE[当前坐标]`（传统该位兵种）生成走法；暗子未曾移动，当前坐标即初始坐标。暗子不会出现在帅/将位，故盲走规则只需覆盖车/马/炮/相/仕/兵。
- **半场独立混洗**：红/黑两个 15 子池分别用 `:R` / `:B` 后缀的独立哈希链洗牌，红池填入红方半场 15 位、黑池填入黑方半场 15 位——翻开后颜色必然不变，只隐藏兵种。
- **翻开**：首次合法走子（含吃子）落子后翻转，之后 `moves_for_rule(..., jieqi_privilege=True)`——相/象免河界、仕/士免九宫；盲走阶段仍受传统限制。
- **归属**：暗子 `initial_owner` 决定操作权与"敌我"判定（不可吃己方暗子）；翻开后颜色与 `initial_owner` 必然一致，归属永不改变。被吃暗子同样公布身份。
- **将军裁决**：`is_in_check` 用各类棋子的攻击规则（暗子按其盲走位置规则）检测王是否被攻击；`legal_moves` 逐走法做"模拟-撤销"过滤，任何令己方王被将的走法一律非法——被将军方被强制应将，也永远无法送将。暗子翻面在模拟中同步翻转再还原，保证过滤语义与真实走子一致。
- **胜负**：吃帅/将立即终局；每步之后检查对方是否存有任何合法走法，无则按是否被将军判 CHECKMATE（绝杀）或 STALEMATE（困毙），均直接判负。

## 协议升级路线

1. ~~防磨种子~~ ✅ 已实现：玩家种子 commit-reveal + 揭示超时判负。
2. **断线判负**：目前对局中断线仅通知对方，可扩展为读秒后判负（与 SEED_ABORT 共用机制）。
3. **状态持久化**：`RoomManager.rooms` 为内存字典，抽象出 `RoomStore` 接口即可平移 Redis。
4. **校验加固**：引入照面（飞将）、长打禁着与重复局面裁决，引擎层已按规则模块化拆分，新增校验只动 `engine.py`。
