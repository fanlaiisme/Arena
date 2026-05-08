# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Overview

Two separate systems live in this repo:

| System | Entry point | Runtime |
|--------|------------|---------|
| **Arena Game** — Pygame 2-player local fighter | `python main.py` | Local, GUI |
| **Role Experiment** — LLM-driven 3-character gambling simulation | `python role/test.py` | API (DeepSeek) |

No linter, no tests. Verification is manual for both systems.

---

## Arena Game

```bash
cd /home/fanlai/Arena && .venv/bin/python main.py
```

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

## Role Experiment (LLM-driven gambling simulation)

```bash
cd /home/fanlai/Arena && .venv/bin/python role/test.py
```

Three LLM-powered characters — **Bob** (arena owner), **Peter** (investor), **Nerd** (bank clerk) — engage in 3 rounds of gladiator gambling. Bob tries to manipulate outcomes to secure Peter's investment.

Uses DeepSeek API (`deepseek-v4-flash`). Config in [role/config.py](role/config.py) loads from `.env`.

### Key files under `role/`

| File | Purpose |
|------|---------|
| [role/test.py](role/test.py) | **Main experiment runner** — 3-round loop with A/B/C/D/E phases, Evaluator, past-life memory, retry logic |
| [role/main.py](role/main.py) | Older/simpler version of the experiment (Bob rents directly, no select_gladiator tool) |
| [role/bob.py](role/bob.py) | `Bob` class + `SYSTEM_PROMPT` with game rules, info asymmetry, reply constraints |
| [role/peter.py](role/peter.py) | `Peter` class + `SYSTEM_PROMPT` (rich investor, hates losing, optional investment) |
| [role/nerd.py](role/nerd.py) | `Nerd` class + `SYSTEM_PROMPT` (poor bank clerk, deep in debt, trusts Bob) |
| [role/role_base.py](role/role_base.py) | `Role` base class + `Gladiator` dataclass + `build_default_gladiators()` |
| [role/agents.py](role/agents.py) | `ArenaAgent` — wraps a character + OpenAI client + tools + message_history |
| [role/tools.py](role/tools.py) | `GameState` dataclass + 7 LangChain tools (stats, list, select, reflect×3) |
| [role/match_runner.py](role/match_runner.py) | `run_headless_match()` — runs Arena game headless via `SDL_VIDEODRIVER=dummy` |
| [role/evaluator.py](role/evaluator.py) | `Evaluator` — hallucination check, goal alignment analysis, player emotion/trust |
| [role/logger.py](role/logger.py) | `ExperimentLogger` — JSONL logging to `role/output/` |
| [role/config.py](role/config.py) | DeepSeek client config, model name, `EXTRA_BODY` / `EXTRA_BODY_THINKING` |

### Experiment flow (per round in `test.py`)

| Phase | What happens |
|-------|-------------|
| **Init** | Bob loads past-life memory from `role/data/Bob/last_failure.md` (if exists) |
| **Pre-game** | Bob privately reviews past-life memory and formulates strategy (no tools, thinking enabled) |
| **A1** | Nerd consults Bob (calls `list_available_gladiators`, then asks for advice) |
| **A2a** | Bob privately analyzes (tools enabled: `get_tournament_stats` + `list_available_gladiators`, think phase) |
| **A2b** | Bob speaks to Nerd (no tools, reply-only) |
| **A3** | Nerd selects gladiator via `select_gladiator` tool (up to 3 retries with escalating prompts) |
| **B1** | Peter consults Bob (same pattern as A1) |
| **B2a** | Bob privately analyzes (knows Nerd's pick, tools enabled, think phase) |
| **B2b** | Bob speaks to Peter (no tools, reply-only) |
| **B3** | Peter selects gladiator via `select_gladiator` tool (up to 3 retries) |
| **C** | `run_headless_match()` runs the actual Arena fight |
| **D** | All 3 characters self-reflect using `reflect_on_match_by_*` tools (thinking mode enabled) |
| **E** | Evaluator runs: hallucination check, player state (emotion/trust), Bob goal-alignment analysis |
| **Post-round** | Dismiss gladiators, reclaim ownership, tick rest counters, double bet, check Nerd bankruptcy |

After 3 rounds: Peter makes investment decision (parsed via separate LLM call for structured JSON). If "not_invest", Bob writes a failure reflection to `role/data/Bob/last_failure.md` as "past-life memory" for the next run.

### Information asymmetry

- Nerd/Peter have `list_available_gladiators` → see **name, ID, rent price** only
- Only Bob has `get_tournament_stats` → sees **win rates and matchup data**
- Only Bob has `get_gladiator_list` → sees gladiator name/description list
- Bob's system prompt explicitly reinforces: "seeing names ≠ knowing strength"

### Tools (LangChain `@tool`)

| Tool | Who has it | Purpose |
|------|-----------|---------|
| `get_tournament_stats` | Bob only | Read tournament win-rate data from `role/data/Bob/tournament_stats-1.md` |
| `get_gladiator_list` | Bob only | Read gladiator name list from `role/data/Public/gladiators_stats/name_list.md` |
| `list_available_gladiators` | Bob, Peter, Nerd | See which gladiators are available + resting (owner=bob, rest_remaining=0) |
| `select_gladiator` | Peter, Nerd | Select a gladiator (records intent into `pending_selection`). Robust matching: char_id priority, fuzzy name, rest-check, mismatch detection |
| `reflect_on_match_by_{Bob,Nerd,Peter}` | Each respectively | Get last match result for self-reflection |

### ArenaAgent architecture

`ArenaAgent.invoke()` in [role/agents.py](role/agents.py):
- Builds messages = `[system_prompt] + message_history + [user_message]`
- Tool calling loop (max 5 iterations)
- Captures `reasoning_content` for DeepSeek thinking mode logging
- `allow_tools=False` forces text-only reply (used in reply phases A2b/B2b)
- `extra_body` controls thinking mode per-call (`EXTRA_BODY` = disabled, `EXTRA_BODY_THINKING` = enabled)

### Gladiators

`build_default_gladiators()` in [role/role_base.py](role/role_base.py) creates 9 gladiators (from the original 9 characters: snowman through boomer). All have `strength=5` and `rent_price=25`万. The 11 newer characters (monk through bomber) are **not yet** added to the role experiment.

Fight results determined by actual Arena game simulation (not stat lookup). The tournament stats file only informs Bob's strategic decisions.

Gladiator lore files (20 `.md` files) live in `role/data/Public/gladiators/` — one per character with combat style, backstory, and signature quote.

### Key constants

- Initial bet: 100万, doubles each round (100→200→400)
- 3 rounds total
- Nerd starts with 1000万, Peter with 50000万, Bob with 5000万
- Gladiator rent: 25万 per match (uniform)
- Bob commission: 10% of total pool
- Gladiator rest: 9 ticks (rest_remaining set to 9 after fight, decrements each round)
- Nerd bankruptcy check: if Nerd can't afford bet + rent, experiment ends early
- Selection retries: max 3 attempts (2 retries with escalating prompts)

### `role/test.py` vs `role/main.py`

`test.py` is the **active** experiment runner with: two-phase A2/B2 split (think+reply), `select_gladiator` tool, Evaluator, past-life memory, thinking-mode reflection, investment decision parsing, Nerd bankruptcy check, selection retry logic. `main.py` is an older version where Bob directly calls `assign_gladiator`.

## Dependencies

```
pygame, langchain-openai>=1.1.0, langchain-core>=1.2.0, python-dotenv
```
