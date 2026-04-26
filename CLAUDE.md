# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run

```bash
cd /home/fanlai/Arena && .venv/bin/python main.py
```

No tests, no lint. Verification is manual: launch the game, select characters, observe behavior.

## Architecture

A local 2-player Pygame arena fighter. 800×800 window, 60 FPS. Two players select characters on a selection screen, then fight inside a circular arena (radius 350, center 400,400). Each player has 100 HP. Last one alive wins.

### State machine (`Game.state`)

`select_p1` → `select_p2` → `fighting` → `game_over` → (R key) back to `select_p1`

### Skill types

Each character can have **one or more** of these skill types. All are optional fields on `CharacterTemplate` (`characters.py`):

| Type | File | Entity | Lifetime | Spawn trigger |
|------|------|--------|----------|---------------|
| projectile | `projectile.py` | `Projectile` | time-based or permanent | timer on Player |
| lightning | `lightning.py` | `LightningBolt` | short duration | timer on Player |
| pet | `pet.py` | `Pet` | HP-based or time-based | timer on Player |
| weapon | `weapon.py` | `Weapon` (+ `Bullet`) | permanent (owner alive) | immediately in `start_match` |

**Projectile movement types** (`MovementType` enum): `STATIONARY`, `ORBIT` (around owner), `ROAM` (random walk with arena bounce), `BOUNCE` (straight line with arena bounce).

**SkillDef** also carries optional burn effect fields: `burn_duration`, `burn_dps`.

### Bullets duck-type into projectiles

`Bullet` (from `weapon.py`) has a `_SkillProxy` exposing `.damage` and `.radius`, so bullets can be mixed into `self.projectiles` and reuse the same update/expire/render/collision pipelines without modifying any existing logic.

### Entity pipelines (update → expire → collide → render)

Every frame, for each entity type:
1. Spawn new entities (timer check)
2. `entity.update(dt)`
3. Filter expired: `[e for e in entities if not e.is_expired()]`
4. Collision checks against other entity types
5. Render in z-order

### Collision matrix

Each entity type checks against players, pets, and sometimes other types:
- **projectile vs player** → damage + optional burn debuff + projectile expires
- **projectile vs pet** → pet takes damage + projectile expires
- **lightning vs player** → damage + slow debuff
- **lightning vs pet** → pet takes damage
- **pet vs player** → damage + pet dies
- **weapon (scythe) vs player** → damage (per-hit cooldown per target)
- **weapon (scythe) vs pet** → pet takes damage (per-hit cooldown)
- **trail (frost) vs player** → slow + DoT
- **trail (frost) vs pet** → slow + DoT

### Debuff system on Player

Debuffs are fields on `Player` with a timer and effect value:
- **Slow**: `slow_mult` + `slow_timer` — reduces velocity during timer
- **Damage reduction**: `dmg_reduction` + `dmg_reduction_timer` — reduces incoming damage
- **Burn**: `burn_timer` + `burn_dps` — DoT per frame, visual flame particles

Each debuff ticks down in `Player.update()` and clears itself when timer hits 0.

### Render order (z-index)

1. Arena background + boundary arcs
2. Trails (frost mage)
3. Lightning bolts
4. Pets
5. Projectiles (includes bullets)
6. Players
7. Weapons (on top of players)
8. HP bars / HUD / game-over overlay

### Adding a new character

1. Add a `CharacterTemplate` to the `CHARACTERS` list in `characters.py`
2. Assign one or more skill types via `skill`, `lightning_skill`, `pet_skill`, `weapon_skill`
3. If the character count changes, adjust `card_w` in `draw_selection_screen()` and add the new key in `handle_selection_input()` (in `main.py`)
4. The selection screen HUD and in-game HUD both use `if/elif` chains over skill types — add a branch if a new skill type is introduced

### Arena segments

The circular arena boundary is divided into 3 colored arcs (red/yellow/blue, each 120°). Collision with the boundary reflects the player and applies a segment effect:
- **Red**: 5 damage + 50% speed boost
- **Yellow**: no effect (reserved)
- **Blue**: heal 10% HP
