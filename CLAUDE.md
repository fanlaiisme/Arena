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

800×800 window, 60 FPS. Two players select characters (keys 1-9), then fight in a circular arena (radius 350, center 400,400). Each player has 100 HP. Last alive wins.

### State machine (`Game.state`)

`select_p1` → `select_p2` → `fighting` → `game_over` → (R key) back to `select_p1`

### Key files

| File | Purpose |
|------|---------|
| [main.py](main.py) | `Game` class, `Player` class, main loop, collision/rendering pipelines |
| [characters.py](characters.py) | `CharacterTemplate` dataclass + `CHARACTERS` list (9 chars) |
| [venue.py](venue.py) | `Arena` class — circular boundary with 3 colored arcs (red/yellow/blue) |
| [projectile.py](projectile.py) | `SkillDef` + `Projectile` — 4 movement types (STATIONARY/ORBIT/ROAM/BOUNCE) |
| [lightning.py](lightning.py) | `LightningDef`, `LightningBolt`, `LightningTrapDef`, `LightningTrapBolt` |
| [pet.py](pet.py) | `PetDef`, `Pet`, `SpiderPet`, `SnowmanPet` |
| [weapon.py](weapon.py) | `WeaponDef`, `Weapon`, `Bullet`, `BoomerangProjectile` — 4 types (PISTOL/SCYTHE/SHIELD/BOOMERANG) |
| [logger.py](logger.py) | `MatchLogger` — JSONL match logging to `output/` |

### Skill types (optional fields on `CharacterTemplate`)

| Field | Entity class | Spawn trigger |
|-------|-------------|---------------|
| `skill` | `Projectile` | Timer on Player |
| `lightning_skill` | `LightningBolt` | Timer on Player |
| `pet_skill` | `Pet` / `SpiderPet` / `SnowmanPet` | Timer on Player |
| `weapon_skill` | `Weapon` (+ `Bullet` / `BoomerangProjectile`) | Immediately in `start_match` |
| `lightning_trap` | `LightningTrapBolt` | Timer on Player |

### Per-frame update order

1. Update skill/pet timers → spawn new entities
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
- weapon (scythe/shield) vs player → damage (per-hit cooldown per target)
- weapon (scythe/shield) vs pet → pet takes damage
- weapon (shield) vs projectile → projectile destroyed
- trail (frost) vs player → slow + 0.05 DoT
- spider web vs player → slow (~0.5→0.8 multiplier) + damage

### Debuff system on `Player`

| Debuff | Fields | Effect |
|--------|--------|--------|
| Slow | `slow_mult` + `slow_timer` | Reduces velocity during timer |
| Damage reduction | `dmg_reduction` + `dmg_reduction_timer` | Reduces incoming damage by fraction |
| Burn | `burn_timer` + `burn_dps` | DoT per frame, visual flame particles |
| Shock | `shock_timer` + `shock_dps` | DoT per frame, spark visuals |

### Render order (z-index)

1. Arena background + boundary arcs
2. Trails (frost mage)
3. Lightning bolts + traps
4. Pets
5. Projectiles (includes bullets/boomerang)
6. Players
7. Weapons (on top of players)
8. HP bars / HUD / game-over overlay

### Adding a character

1. Add `CharacterTemplate` to `CHARACTERS` in [characters.py](characters.py)
2. If character count changes, adjust `card_w` in `draw_selection_screen()` and key handling in `handle_selection_input()` (both in [main.py](main.py))
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
| [role/test.py](role/test.py) | **Main experiment runner** — 3-round loop with A/B/C/D/E phases, Evaluator, past-life memory |
| [role/main.py](role/main.py) | Older/simpler version of the experiment (Bob rents directly, no select_gladiator tool) |
| [role/bob.py](role/bob.py) | `Bob` class + 57-line `SYSTEM_PROMPT` with game rules, info asymmetry, reply constraints |
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
| **Pre-game** | If past-life memory exists, Bob privately reviews and formulates strategy |
| **A1** | Nerd talks to Bob, asks for gladiator advice |
| **A2a** | Bob privately analyzes (tools enabled, think phase) |
| **A2b** | Bob speaks to Nerd (no tools, reply-only) |
| **A3** | Nerd selects gladiator via `select_gladiator` tool |
| **B1** | Peter talks to Bob, asks for gladiator advice |
| **B2a** | Bob privately analyzes (knows Nerd's pick, think phase) |
| **B2b** | Bob speaks to Peter (no tools, reply-only) |
| **B3** | Peter selects gladiator via `select_gladiator` tool |
| **C** | `run_headless_match()` runs the actual Arena fight |
| **D** | All 3 characters reflect on the round (thinking mode enabled) |
| **E** | Evaluator runs hallucination + state + goal-alignment checks |
| **Post-round** | Dismiss gladiators, reclaim, tick rest counters, double bet |

After 3 rounds: Peter makes investment decision. If "not invest", Bob writes a failure reflection to `role/data/Bob/last_failure.md` as "past-life memory" for the next run.

### Information asymmetry

- Nerd/Peter have `list_available_gladiators` → see **name, ID, rent price** only
- Only Bob has `get_tournament_stats` → sees **win rates and matchup data**
- Bob's system prompt explicitly reinforces: "seeing names ≠ knowing strength"

### Tools (LangChain `@tool`)

| Tool | Who has it | Purpose |
|------|-----------|---------|
| `get_tournament_stats` | Bob only | Read tournament win-rate data from `role/data/Bob/tournament_stats-1.md` |
| `get_gladiator_list` | Bob only | Read gladiator name list |
| `list_available_gladiators` | Bob, Peter, Nerd | See which gladiators are available + resting |
| `select_gladiator` | Peter, Nerd | Select a gladiator (records intent, doesn't transfer ownership) |
| `reflect_on_match_by_{Bob,Nerd,Peter}` | Each respectively | Get last match result for self-reflection |

### ArenaAgent architecture

`ArenaAgent.invoke()` in [role/agents.py](role/agents.py):
- Builds messages = `[system_prompt] + message_history + [user_message]`
- Tool calling loop (max 5 iterations)
- Captures `reasoning_content` for DeepSeek thinking mode logging
- `allow_tools=False` forces text-only reply (used in reply phases)
- `extra_body` controls thinking mode per-call

### Gladiators (9 total, all rent 25万, all strength=5)

snowman, lava, frost, poison, thor, venomancer, sharpshooter, guardian, boomer

Fight results determined by actual Arena game simulation (not stat lookup). The tournament stats file only informs Bob's strategic decisions.

### Key constants

- Initial bet: 100万, doubles each round (100→200→400)
- Nerd starts with 1000万, Peter with 50000万, Bob with 5000万
- Gladiator rent: 25万 per match (uniform)
- Bob commission: 10% of total pool
- Gladiator rest: 9 ticks (rest_remaining set to 9 after fight, decrements each round)

### `role/test.py` vs `role/main.py`

`test.py` is the **active** experiment runner with: two-phase A2/B2 split (think+reply), `select_gladiator` tool, Evaluator, past-life memory, thinking-mode reflection, investment decision parsing. `main.py` is an older version where Bob directly calls `assign_gladiator`.

## Dependencies

```
pygame, langchain-openai>=1.1.0, langchain-core>=1.2.0, python-dotenv
```
