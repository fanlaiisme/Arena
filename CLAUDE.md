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

Two active entry points, plus a web wrapper:

| Entry point | Command | Description |
|-------------|---------|-------------|
| **`role/main.py`** (primary) | `.venv/bin/python role/main.py` | No-Bob variant: two AI gamblers with pure text `<bid>`/`<deploy>` tags; used by web dashboard |
| **`role/test.py`** (legacy) | `.venv/bin/python role/test.py` | With Bob: three characters, tool-calling agents, LangChain tools |
| **`role/web_main.py`** | `.venv/bin/python role/web_main.py` | FastAPI server (port 8000) wrapping `main.py` in a background thread, SSE streaming to browser |

The old `role/peter.py` and `role/nerd.py` are **legacy** — not used by either active entry point. `Gambler` class in `role/gambler.py` replaces them.

Uses DeepSeek API (`deepseek-v4-flash`). Config in [role/config.py](role/config.py) loads `.env`.

### Key files under `role/`

| File | Purpose |
|------|---------|
| [role/main.py](role/main.py) | **Primary experiment runner** — no Bob, 3-day loop, text-parsing agents, visualizer hooks |
| [role/test.py](role/test.py) | Legacy experiment with Bob — tool-calling agents, 3-round loop |
| [role/gambler.py](role/gambler.py) | `Gambler` class + two system prompts (with-Bob and no-Bob, ~230 lines) |
| [role/agents.py](role/agents.py) | `ArenaAgent` — wraps a character + OpenAI client + tools + message_history |
| [role/squad.py](role/squad.py) | `Squad` + `SquadMember` — 3-gladiator roster with fatigue, HP scaling, point/pool |
| [role/auction.py](role/auction.py) | `AuctionSession` — sealed-bid auction: 9 from 20 gladiators, auto-fill, bid compare |
| [role/role_base.py](role/role_base.py) | `Role` base class (assets, chips, reward_pool), `Gambler` parent |
| [role/tools.py](role/tools.py) | `GameState` dataclass + LangChain `@tool` functions (Bob tools, player tools) |
| [role/match_runner.py](role/match_runner.py) | `run_headless_match()` — headless Arena fight via `SDL_VIDEODRIVER=dummy` |
| [role/evaluator.py](role/evaluator.py) | `Evaluator` — M1-M6 analysis (rule hallucination, factual accuracy, strategy, etc.) |
| [role/logger.py](role/logger.py) | `ExperimentLogger` — thread-safe JSONL logging to `role/output/` |
| [role/config.py](role/config.py) | DeepSeek client config, model name, `EXTRA_BODY` / `EXTRA_BODY_THINKING` |
| [role/visualizer.py](role/visualizer.py) | `Visualizer` — thread-safe `asyncio.Queue` event emitter for SSE |
| [role/web_main.py](role/web_main.py) | FastAPI app — serves dashboard, reflections, SSE, API |

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
  - Stored in Visualizer for reflections.html
  ↓
Phase 6: Evaluation (M1-M6)
  - Rule hallucination, factual accuracy, strategy quality, economic rationality,
    information utilization, opponent modeling
  ↓
Day advancement: squad.next_day() (fatigue recovery), deployments cleared
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

### `test.py` vs `main.py`

| Aspect | `test.py` (with Bob) | `main.py` (no Bob) |
|--------|---------------------|-------------------|
| Bob agent | Yes, with data tools | No |
| Agent interaction | Tool-calling (`auction_bid`, `deploy_first_match`, etc.) | Pure text parsing (`<bid>`, `<deploy>` tags) |
| System prompt | Short, assumes Bob consultation | ~230-line `SYSTEM_PROMPT_NO_BOB` |
| Visualizer support | No | Yes (`viz.emit()` throughout) |
| Parse retries | N/A (tools validate) | Up to 3 retries for missing tags |
| Low-chips handling | None | Explicit opponent notification |
| Daily preview count | Constant 5 | Variable 5/4/3 per day |

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
