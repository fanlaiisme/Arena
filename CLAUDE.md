# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Three systems live in this repo:

| System | Entry point | Runtime |
|--------|------------|---------|
| **Arena Game** — Pygame 2-player local fighter | `.venv/bin/python main.py` | Local, GUI |
| **Role Experiment** — LLM-driven gambling simulation | `.venv/bin/python role/main.py` | API (DeepSeek) |
| **Web Dashboard** — Real-time visualization for the experiment | `.venv/bin/python role/web_main.py` | FastAPI + SSE |

No linter, no tests. Verification is manual.

---

## Arena Game

800×800 window, 60 FPS. Two players select characters (mouse click on a 5-column grid), then fight in a circular arena (radius 350, center 400,400). Each player has 100 HP. Last alive wins.

### State machine (`Game.state`)

`select_p1` → `select_p2` → `fighting` → `game_over` → (R key) back to `select_p1`

### Key files

| File | Purpose |
|------|---------|
| [main.py](main.py) | `Game` class, `Player` class, main loop, collision/rendering pipelines |
| [characters.py](characters.py) | `CharacterTemplate` dataclass + `CHARACTERS` list (20 chars) + preset skill/weapon/pet/bomb definitions |
| [venue.py](venue.py) | `Arena` class — circular boundary with 3 colored arcs (red/yellow/blue) |
| [projectile.py](projectile.py) | `SkillDef` + `Projectile` — 4 movement types (STATIONARY/ORBIT/ROAM/BOUNCE) |
| [lightning.py](lightning.py) | `LightningDef`, `LightningBolt`, `LightningTrapDef`, `LightningTrapBolt` |
| [pet.py](pet.py) | `PetDef`, `Pet`, `SpiderPet`, `SnowmanPet`, `GhostPet` |
| [weapon.py](weapon.py) | `WeaponDef`, `Weapon`, `Bullet`, `BoomerangProjectile`, `HomingMissile`, `ShurikenProjectile` — 14 weapon types |
| [bomb.py](bomb.py) | `BombDef`, `Bomb`, `GasCloud` — 3 bomb types (NORMAL/CLUSTER/GAS) |
| [logger.py](logger.py) | `MatchLogger` — JSONL match logging to `output/` |

### Characters (20 total, selection grid: 5 columns × 4 rows)

| # | ID | Name | Key mechanics |
|---|----|------|---------------|
| 1 | snowman | 雪人召唤师 | Projectile snowballs + snowman pet |
| 2 | lava | 熔岩射手 | Bouncing lava balls with burn DoT |
| 3 | frost | 冰霜法师 | Orbiting ice spikes + frost trail (slow + DoT) |
| 4 | poison | 毒雾术士 | Roaming poison cloud + scythe weapon |
| 5 | thor | 雷神 | Lightning bolts (slow) + lightning traps (shock DoT) |
| 6 | venomancer | 制毒师 | Snake pets (hit-and-retire) |
| 7 | sharpshooter | 神枪手 | Pistol weapon |
| 8 | guardian | 盾卫 | Shield (blocks projectiles) + spider pet (web slow) |
| 9 | boomer | 回旋猎手 | Boomerang weapon |
| 10 | monk | 武僧 | Rapid palm strike (0.65s CD) + golden body (4s, 50% dmg reduction) |
| 11 | berserker | 狂战士 | Unstoppable (6s slow immune) + hunt mark (teleport AoE) + dual axes |
| 12 | ninja | 忍者 | Shadow clone (5s) + katana (2-slash melee) + shuriken (wall traps) |
| 13 | paladin | 圣骑士 | Holy sword (crescent beams + charged 3-beam attack every 18s) |
| 14 | necromancer | 亡灵法师 | Ghost pet (999 HP, 25s lifetime) + staff (speed-drain on hit) + fear marks |
| 15 | brawler | 潮汐使者 | Ocean vortex (10s AoE trap, sucks players in) + ripple waves |
| 16 | elf | 森林精灵 | Tree of life (healing) + leaf blade storm (orbiting) |
| 17 | orc | 兽人战士 | Very slow (speed 5.0), cone fist slam + rage stacks (+15% speed per stack) |
| 18 | hunter | 暗夜猎手 | Spider pet + bow (3-arrow spread) + stealth (6s invisibility) |
| 19 | weaponmaster | 武器大师 | No innate skills — picks up weapons from arena floor |
| 20 | bomber | 炸弹专家 | Cluster bomb (splits into 5) + gas bomb (persistent AoE cloud) |

### Skill types (optional fields on `CharacterTemplate`)

| Field | Entity class | Spawn trigger |
|-------|-------------|---------------|
| `skill` | `Projectile` | Timer on Player |
| `skill2` | `Projectile` | Timer on Player (second skill) |
| `lightning_skill` | `LightningBolt` | Timer on Player |
| `pet_skill` | `Pet` / `SpiderPet` / `SnowmanPet` / `GhostPet` | Timer on Player |
| `weapon_skill` | `Weapon` (+ bullets/missiles/shuriken) | Immediately in `start_match` |
| `weapon_skill2` | `Weapon` (+ bullets/missiles/shuriken) | Immediately in `start_match` |
| `bomb_skill` | `Bomb` (+ optional `GasCloud`) | Timer on Player |
| `bomb_skill2` | `Bomb` (+ optional `GasCloud`) | Timer on Player |
| `lightning_trap` | `LightningTrapBolt` | Timer on Player |

### Weapon types (14 total, in `weapon.py`)

| Type | Behavior |
|------|----------|
| PISTOL | Single bullet, standard cooldown |
| SCYTHE | Melee sweep, per-target cooldown |
| SHIELD | Blocks projectiles, melee damage |
| BOOMERANG | Flies out and returns, curve path |
| SNIPER | High damage, high speed, slows player while aiming |
| GATLING | Rapid fire (0.12s CD), 10-shot burst then 8s overheat |
| HOMING | Tracking missiles, one active at a time |
| KATANA | Two-slash melee combo (slash1→slash2→idle), deflects projectiles |
| SHURIKEN | Thrown stars spread, embed in arena wall as 10s traps |
| BOW | 3-arrow spread shot |
| CROSSBOW | 4-shot burst fire (0.12s interval), 0.8s burst cooldown |
| DUAL_AXE | Alternating left/right axe swings (0.75s cycle) |
| STAFF | Speed-triggered: fires when opponent speed > 13, drains speed on hit |
| HOLY_SWORD | Normal slash fires crescent beam; every 18s charges 3 vertical beams |

### Bomb types (in `bomb.py`)

| Type | Behavior |
|------|----------|
| NORMAL | Thrown in arc, lands, detonates after delay → AoE damage |
| CLUSTER | Parent bomb explodes → spawns 5 child bombs radially |
| GAS | Detonates → spawns `GasCloud` (persistent AoE: DoT + slow over duration) |

Bomb lifecycle: `THROW` (parabolic arc) → `PRIMED` (countdown with warning circle) → `EXPLODED` (flash + damage).

### Other entity types spawned during combat

| Entity | Source | Behavior |
|--------|--------|----------|
| `ShadowClone` | Ninja skill | Copies player movements, attacks, 5s lifetime |
| `GoldenPalm` | Monk skill2 | Short-range melee strike |
| `FistTrap` / `HuntMark` | Berserker skill2 | Teleport-triggered AoE damage |
| `VortexEntity` | Brawler skill | 10s AoE that sucks enemies toward center |
| `WaveEntity` | Brawler skill2 | Expanding ripple wave |
| `TreeEntity` | Elf skill | Stationary healing tree |
| `LeafBlade` | Elf skill2 | Orbiting leaf blades around tree |
| `WeaponPickup` | weaponmaster passive | Spawns on arena floor for pickup |

### Per-frame update order

1. Update skill/pet/bomb timers → spawn new entities
2. Player movement + arena boundary collision
3. Player-to-player bounce
4. Update all entities (`update(dt)`)
5. Filter expired entities
6. Run all collision checks
7. Check win condition

### Collision matrix

- projectile vs player → damage + optional burn + projectile expires
- projectile vs pet → pet takes damage + projectile expires
- lightning vs player → damage + slow debuff
- lightning vs pet → pet takes damage
- lightning_trap vs player → shock (DoT + slow) + trap expires
- pet vs player → damage + pet dies (some apply slow)
- pet vs pet (different owners) → both damaged + bounce apart
- weapon (scythe/shield/katana/dual_axe) vs player → damage (per-hit cooldown per target)
- weapon (scythe/shield/katana/dual_axe) vs pet → pet takes damage
- weapon (shield/katana) vs projectile → projectile destroyed/deflected
- trail (frost) vs player → slow + 0.05 DoT
- spider web vs player → slow (~0.5→0.8 multiplier) + damage
- bomb explosion vs player → AoE damage (falloff from center)
- bomb explosion vs pet → AoE damage
- gas cloud vs player → DoT + slow while inside radius
- vortex vs player → suction force + skill lock
- fist trap / hunt mark vs player → AoE damage on teleport trigger
- clone vs player → damage (mirrors ninja attacks)

### Debuff system on `Player`

| Debuff | Fields | Effect |
|--------|--------|--------|
| Slow | `slow_mult` + `slow_timer` | Reduces velocity during timer |
| Damage reduction | `dmg_reduction` + `dmg_reduction_timer` | Reduces incoming damage by fraction |
| Burn | `burn_timer` + `burn_dps` | DoT per frame, visual flame particles |
| Shock | `shock_timer` + `shock_dps` | DoT per frame, spark visuals |
| Golden body | `golden_body_timer` | Monk's 50% damage reduction for 4s |
| Unstoppable | `unstoppable_timer` | Berserker's slow immunity for 6s |
| Invisible | `invisible` + `invisible_timer` | Hunter stealth (homing missiles fly straight) |
| Rage | `rage_stacks` + `rage_timer` | Orc passive: +15% speed per stack, decays after 4s |
| Skill locked | `skill_locked` | Disabled while inside vortex |
| Fear marks | `_fear_mark_timers` | Necromancer stacking debuff, amplifies staff damage |
| Speed drain | `_staff_hit_timer` + `_staff_saved_speed` | Necro staff slows to 10% and deals damage proportional to saved speed |

### Render order (z-index)

1. Arena background + boundary arcs
2. Trails (frost mage)
3. Lightning bolts + traps
4. Weapon pickups (on arena floor)
5. Trees + vortexes + gas clouds
6. Fist traps + hunt marks
7. Pets + clones
8. Projectiles + bullets + missiles + shuriken + bombs + leaf blades
9. Waves + golden palms
10. Players
11. Weapons (on top of players)
12. HP bars / HUD / game-over overlay

### Adding a character

1. Add `CharacterTemplate` to `CHARACTERS` in [characters.py](characters.py)
2. If character count changes, adjust `cols` and `card_w` in `draw_selection_screen()` and key handling in `handle_selection_input()` (both in [main.py](main.py))
3. HUD branches in `draw_selection_screen()` and `draw_hp()` auto-render based on non-None skill fields

---

## Role Experiment

Three entry points:

| Entry point | Command | Description |
|-------------|---------|-------------|
| **`role/main.py`** (primary) | `.venv/bin/python role/main.py` | AI vs AI: two gamblers, 3-day loop, pure text `<bid>`/`<deploy>` tags, visualizer hooks |
| **`role/test.py`** (stats reporter) | `.venv/bin/python role/test.py [log]` | **实验统计报告**：解析 JSONL 日志，输出 M7 游戏币估计准确率 + M1-M6 全维度打分 |
| **`role/web_main.py`** | `.venv/bin/python role/web_main.py` | FastAPI server (port 8000) wrapping `main.py` in a background thread, SSE streaming |

The old `role/peter.py` and `role/nerd.py` are **legacy**. `Gambler` class in `role/gambler.py` replaces them.

Uses DeepSeek API (`deepseek-v4-flash`). Config in [role/config.py](role/config.py) loads `.env`.

### Key files under `role/`

| File | Purpose |
|------|---------|
| [role/main.py](role/main.py) | **Primary experiment runner** — AI vs AI and Human vs AI modes, text-parsing agents, visualizer |
| [role/test.py](role/test.py) | **统计报告脚本** — 解析 experiment_*.log，生成 M1-M7 打分表 + 游戏币估计准确率表 |
| [role/gambler.py](role/gambler.py) | `Gambler` class + two system prompts (with-Bob and no-Bob, ~230 lines) |
| [role/agents.py](role/agents.py) | `ArenaAgent` — OpenAI client wrapper + message_history + `on_response` callback + `label` 参数 |
| [role/squad.py](role/squad.py) | `Squad` + `SquadMember` — 3-gladiator roster with fatigue, HP scaling, point/pool |
| [role/auction.py](role/auction.py) | `AuctionSession` — sealed-bid auction: 9 from 20 gladiators, auto-fill, bid compare |
| [role/role_base.py](role/role_base.py) | `Role` base class (assets, chips, reward_pool), `Gambler` parent |
| [role/tools.py](role/tools.py) | `GameState` dataclass + LangChain `@tool` functions |
| [role/match_runner.py](role/match_runner.py) | `run_headless_match()` — headless Arena fight via `SDL_VIDEODRIVER=dummy` |
| [role/evaluator.py](role/evaluator.py) | `Evaluator` — M1-M7 评估（规则幻觉/数字幻觉/策略质量/经济理性/信息利用/对手建模/游戏币估计） |
| [role/logger.py](role/logger.py) | `ExperimentLogger` — thread-safe JSONL logging to `role/output/` |
| [role/config.py](role/config.py) | DeepSeek client, `MEMORY_API_KEY`, thinking mode `EXTRA_BODY` |
| [role/visualizer.py](role/visualizer.py) | `Visualizer` — thread-safe `asyncio.Queue` event emitter for SSE |
| [role/web_main.py](role/web_main.py) | FastAPI app — serves dashboard, reflections, SSE, API |
| [role/memory_subagent.py](role/memory_subagent.py) | **记忆模块** — `MemorySubagent` 后台渐进式提取，独立 API 调用 + read/edit 工具 |
| [role/memory_tools.py](role/memory_tools.py) | LangChain @tool: `read_memory` + `edit_memory`（区分填充空模板/修改已有内容） |
| [role/memory/](role/memory/) | 记忆目录：`opponent_model.md` + `gladiator_knowledge.md` + `day{N}.md`（每玩家独立） |

### Evaluator dimensions (M1-M7)

| 维度 | 方法 | 方式 | 说明 |
|------|------|------|------|
| **M1 规则幻觉** | `evaluate_rule_compliance()` | LLM | 检测是否误解拍卖暗标、奖励池、属性克制等规则 |
| **M2 数字幻觉** | `evaluate_factual_accuracy()` | LLM | 检测是否虚构胜率、花费、对手币量等数字 |
| **M3 策略质量** | `evaluate_strategy_quality()` | LLM | 拍卖+部署+疲劳+point管理，**含×1.5杠杆策略教育** |
| **M4 经济理性** | `evaluate_economic_rationality_v2()` | 程序化 | 花费占比、弃权率、死钱比例、破产风险 |
| **M5 信息利用** | `evaluate_information_utilization()` | LLM | 预览信息利用、匿名排名表填写质量 |
| **M6 对手建模** | `evaluate_opponent_modeling_v2()` | LLM | 对手出价/部署模式预测准确度 |
| **M7 游戏币估计** | `evaluate_chip_estimation()` | 程序化(正则) | 从 `##对手游戏币估计在**N~M**之间##` 提取，与 ground truth 比对 |

M7 正则三级匹配（`evaluator.py:894-900`）：
1. `^##对手游戏币估计在\*\*(\d+)\s*[~\-–—至到]\s*(\d+)\*\*之间##\s*$` — 独立成行
2. `##对手游戏币估计在\*\*(\d+)\s*[~\-–—至到]\s*(\d+)\*\*之间##` — 有 `##` 包裹
3. `对手游戏币估计在\*\*(\d+)\s*[~\-–—至到]\s*(\d+)\*\*之间` — 宽松兜底

### `main.py` experiment flow (3-day loop)

Each day:

```
Phase 0: Pre-game preview
  - Random gladiator win-rate previews (day 1:5, day 2:4, day 3:3, non-repeating)
  - Also shows "anonymous win-rate ranking" on day 1
  ↓
Phase 0.5: Rules interpretation (parallel)
  - Each player independently analyzes game mechanics
  ↓
Phase 1: Auction (sealed-bid, parallel threads)
  - 9 random gladiators from 20; shown one at a time
  - Both players output <bid>N</bid> tags (parsed by regex, max 3 retries)
  - Winner pays their bid (chips deducted), loser's bid → loser's reward_pool
  - When one side fills 3 slots, remaining auto-assigned at 85 chips each
  - Post-auction analysis: each player privately reviews opponent's bidding
  ↓
Phase 2: Deployment (parallel)
  - Players output <deploy slot="N">char_id</deploy> tags
  - Match 1 deployed first, then match 1 result feeds into match 2+3 deployment
  ↓
Phase 3: Matches (3 rounds)
  - Headless Arena fights via match_runner
  - Point transfer: winner seizes min(winner_point, loser_point)
  - Match 2 has ×1.5 multiplier
  - Point pool updated via settle_points_to_pool()
  ↓
Phase 4: Daily winner reward
  - Both players: point_pool → reward_pool (full transfer)
  - Daily winner (most match wins): converts from reward_pool to chips
     (≤0 → 0, <50 → all, ≥50 → 50)
  ↓
Phase 5: Day summary reflection (parallel, thinking mode)
  - Players fill anonymous ranking table + estimate opponent chips
  - Output format: ##对手游戏币估计在**下限~上限**之间##
  - Stored in Visualizer for reflections.html
  ↓
Phase 6: Evaluation (M1-M7)
  - M1 rule hallucination, M2 factual accuracy, M3 strategy quality,
    M4 economic rationality, M5 information utilization, M6 opponent modeling,
    M7 chip estimation (programmatic regex)
  ↓
Day advancement: squad.next_day() (fatigue recovery), deployments cleared
  ↓
Memory extraction: wait_all() — 确保两个 MemorySubagent 完成当天记忆写入
```

After 3 days: all `point_pool` + `reward_pool` → chips (1:1), compare totals for winner.

### Economy system (`main.py`)

Three currencies on each player:

| Variable | Owner | Source | Usage |
|----------|-------|--------|-------|
| `chips` | `Role` | Initial 800, daily winner conversion, final settlement | Auction bidding, auto-fill payment |
| `point_pool` | `Squad` | Match point settlement (can go negative) | Transferred to reward_pool at day end |
| `reward_pool` | `Role` | Auction loser bids + daily point_pool sweep | Daily winner conversion, final settlement |

**Auction flow**: Winner's bid → gladiator point (circulates through matches). Loser's bid → loser's own `reward_pool` (dead money, not usable for bidding).

**Low-chips notification**: When one player drops below 50 chips (can't bid), the other player gets an explicit system notification.

### `test.py` — 统计报告脚本

`test.py` 已重写为实验统计报告工具，不再运行 Bob 实验：

```bash
.venv/bin/python role/test.py [日志文件路径]
# 不带参数时自动选取 role/output/ 下最新的 experiment_*.log
```

输出三张表：
| 表 | 内容 |
|----|------|
| 表1 | M7 对手游戏币估计准确率（逐天：估计范围 vs 真实值 + 命中/偏离 + 得分） |
| 表2 | M1-M6 全维度打分明细（按玩家×天数×维度） |
| 表3 | 各玩家按维度汇总平均分 |

### Memory Module（记忆模块）

每个 AI 玩家拥有独立的记忆目录 `role/memory/{player_name}/`，包含三个 markdown 文件：

| 文件 | 类型 | frontmatter | 内容 |
|------|------|-------------|------|
| `opponent_model.md` | 跨天持久 | `type: opponent-model` | 对手出价模式、部署偏好、关键观察 |
| `gladiator_knowledge.md` | 跨天持久 | `type: gladiator-knowledge` | 胜率排名推测表、实战表现记录 |
| `day{N}.md` | 每日笔记 | `type: daily-memory` | 当天概述、教训、对手观察、明日策略 |

**工作流**：
1. `ArenaAgent.invoke()` 每次返回时 → `on_response(label, content)` 回调 → `MemorySubagent.submit()`
2. Subagent 后台独立 API 调用（无状态），使用 `read_memory` / `edit_memory` 工具渐进更新 md 文件
3. 每天结束 → `wait_all()` 阻塞等待所有记忆写入完成
4. 下一天开始 → `_inject_memory()` 将三个 md 文件注入 agent 的 `message_history`

**关键文件**：
| 文件 | 说明 |
|------|------|
| [role/memory_subagent.py](role/memory_subagent.py) | `MemorySubagent` 类：ThreadPoolExecutor 串行处理，最多 3 轮工具调用 |
| [role/memory_tools.py](role/memory_tools.py) | `read_memory` + `edit_memory` LangChain @tool，edit 返回值区分"填充空模板"/"修改已有内容" |
| [role/config.py](role/config.py) | `MEMORY_API_KEY`（从 .env 第二行读取，回退主 key）、`MEMORY_MODEL_NAME` |

### Key constants

- Initial chips: 800 per player (main.py)
- Auction: STARTING_PRICE=50, AUTO_FILL_PRICE=85, MAX_BID_CAP=150
- Daily winner: ≤0 no conversion, <50 all converted, ≥50 capped at 50
- 3 matches per day, match 2 has ×1.5 point transfer
- Fatigue: HP multiplier drops 1.0→0.9→0.8→0.6 with consecutive usage
- Players: 斑目貘 and 夜神月 (hardcoded in main.py:826-827)

### ArenaAgent architecture

`ArenaAgent.invoke()` in [role/agents.py](role/agents.py):
- Builds messages = `[system_prompt] + message_history + [user_message]`
- Tool calling loop (max 5 iterations) for test.py agents
- `allow_tools=False` forces text-only reply (used in main.py's text-parsing mode)
- `extra_body` controls DeepSeek thinking mode per-call
- `label` 参数：阶段标签，触发 `on_response` 回调 → 记忆 subagent
- `on_response` 回调：每次 invoke 返回时触发，用于渐进式记忆提取

---

## Web Dashboard

```bash
.venv/bin/python role/web_main.py
# Browser → http://localhost:8000
```

### Architecture

```
Browser                          FastAPI (port 8000)
───────                          ──────────────────
dashboard.html  ──SSE──►  GET /events → Visualizer.event_stream()
                           POST /start → spawns thread → main.run_experiment(visualizer=viz)
reflections.html ──poll─► GET /api/reflections → JSON {days, game_over}
                ──page──► GET /reflections → reflections.html
```

### SSE event types (emitted from `main.py` → consumed by `dashboard.html`)

| Event | When | Frontend action |
|-------|------|-----------------|
| `game_start` | Experiment begins | clearAll(), show rules |
| `progress` | Phase transitions | Update phase badge |
| `rules_done` | Rules interpretation complete | Hide rules panel |
| `preview` | Daily gladiator preview | Populate info cards, day separator |
| `auction_show` | Each auction round | Show gladiator image/name in center |
| `auction_bid` | Bids placed | Append to result area |
| `auction_result` | Auction won | Update status bar (chips, owned, reward_pool) |
| `squad_update` | After auto-assign | Update status bar with pool values |
| `deployment` | Player deploys | Append to chat log |
| `match_start` | Match begins | Show VS display in center |
| `match_result` | Match ends | Show winner, update point/reward pools |
| `agent_message` | Any agent response | Append to chat log (truncated to 1200 chars) |
| `daily_winner` | Daily reward | Update status bar, append result |
| `daily_summary` | Day reflection done | Append to chat log |
| `evaluation` | Evaluator runs | Append to chat log |
| `final_result` | Game over | Show winner avatar in center, stop button disable |

### Status bar (bottom)

Left: 游戏币(blue) | 角斗士 | point池(gold) | 蓄奖池(purple)
Right: 蓄奖池(purple) | point池(gold) | 角斗士 | 游戏币(red)

### Center panel scroll

`#center` uses `overflow: hidden` — only `#result-area` scrolls (`flex: 1; overflow-y: auto`). Auction card and match display stay fixed.

### Reflections page

`/reflections` shows both players' daily reflection texts (filled ranking tables, chip estimates) side-by-side, auto-refreshing every 3 seconds until `game_over`.

### Static mounts

- `/avatars/{char_id}.png` — character images
- `/players/{name}.png` — player avatars (斑目貘, 夜神月)

## Dependencies

```
pygame, langchain-openai>=1.1.0, langchain-core>=1.2.0, python-dotenv, fastapi, uvicorn
```
