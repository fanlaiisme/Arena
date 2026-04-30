import pygame
import random
import math

from characters import CharacterTemplate, CHARACTERS
from projectile import Projectile
from lightning import LightningBolt, LightningTrapBolt
from pet import Pet, SpiderPet, SnowmanPet, PetMovement
from weapon import Weapon, Bullet
from venue import Arena
from logger import MatchLogger


# ── Constants ────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 800, 800
CENTER = (WIDTH // 2, HEIGHT // 2)
ARENA_RADIUS = 350
FPS = 60

PLAYER_RADIUS = 20
INITIAL_HP = 100

ARENA_BG = (30, 30, 40)
ARENA_BORDER = (80, 80, 100)
TEXT_COLOR = (220, 220, 220)
SELECT_BG = (20, 20, 30)


# ── Player ───────────────────────────────────────────────────────────────────
class Player:
    def __init__(self, x, y, char: CharacterTemplate):
        self.x = float(x)
        self.y = float(y)
        self.vx = random.uniform(-1.5, 1.5)
        self.vy = random.uniform(-1.5, 1.5)
        self.char = char
        self.hp = INITIAL_HP
        self.radius = PLAYER_RADIUS
        self.alive = True
        self.skill_timer = 0.0  # counts up to skill.cooldown
        self.lightning_timer = 0.0  # counts up to lightning_skill.cooldown
        self.lightning_trap_timer = 0.0  # counts up to lightning_trap.cooldown
        self.pet_timer = 0.0       # counts up to pet_skill.cooldown
        self.trail_points: list[tuple[float, float]] = []
        self.max_trail_length = 600
        # Debuff state
        self.slow_mult = 1.0
        self.slow_timer = 0.0
        self.dmg_reduction = 0.0
        self.dmg_reduction_timer = 0.0
        # Burn debuff
        self.burn_timer = 0.0
        self.burn_dps = 0.0
        self._flame_seeds = [random.uniform(0, 100) for _ in range(18)]
        # Shock debuff
        self.shock_timer = 0.0
        self.shock_dps = 0.0
        self._shock_seeds = [random.uniform(0, 100) for _ in range(6)]

    def update(self, arena=None, dt=1/60):
        if not self.alive:
            return

        # Update debuff timers
        if self.slow_timer > 0:
            self.slow_timer = max(0.0, self.slow_timer - dt)
            if self.slow_timer == 0.0:
                self.slow_mult = 1.0
        if self.dmg_reduction_timer > 0:
            self.dmg_reduction_timer = max(0.0, self.dmg_reduction_timer - dt)
            if self.dmg_reduction_timer == 0.0:
                self.dmg_reduction = 0.0

        # Burn damage over time
        if self.burn_timer > 0:
            self.burn_timer = max(0.0, self.burn_timer - dt)
            self.take_damage(self.burn_dps * dt)

        # Shock damage over time
        if self.shock_timer > 0:
            self.shock_timer = max(0.0, self.shock_timer - dt)
            self.take_damage(self.shock_dps * dt)

        # Random acceleration (physics-based perturbation)
        ax = random.uniform(-0.25, 0.25)
        ay = random.uniform(-0.25, 0.25)

        # Occasionally apply a stronger directional change
        if random.random() < 0.02:
            ax += random.uniform(-0.7, 0.7)
            ay += random.uniform(-0.7, 0.7)

        self.vx += ax
        self.vy += ay

        # Friction damping
        self.vx *= 0.995
        self.vy *= 0.995

        # Speed cap from character template
        speed = math.hypot(self.vx, self.vy)
        if speed > self.char.speed:
            self.vx = self.vx / speed * self.char.speed
            self.vy = self.vy / speed * self.char.speed

        # Apply slow debuff before position update
        if self.slow_timer > 0:
            self.vx *= self.slow_mult
            self.vy *= self.slow_mult

        self.x += self.vx
        self.y += self.vy

        # Arena boundary collision (with segment effects)
        if arena is not None:
            segment = arena.resolve_boundary(self)
            if segment:
                arena.apply_effect(self, segment)

        # Record trail point
        self.trail_points.append((self.x, self.y))
        if len(self.trail_points) > self.max_trail_length:
            self.trail_points.pop(0)

    def draw(self, screen, font_small):
        # Fire effect (burning)
        if self.burn_timer > 0:
            self._draw_flames(screen)
        # Shock effect
        if self.shock_timer > 0:
            self._draw_shock(screen)

        pygame.draw.circle(screen, self.char.color, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(screen, (60, 60, 60), (int(self.x), int(self.y)), self.radius, 2)
        # Name label above player
        name_surf = font_small.render(self.char.name, True, self.char.color)
        screen.blit(name_surf, (self.x - name_surf.get_width() // 2, self.y - self.radius - 22))

    def _draw_flames(self, screen):
        """Draw flickering flame particles around the player when burning."""
        burn_ratio = min(1.0, self.burn_timer / 10.0)
        now = pygame.time.get_ticks() / 1000.0

        for i, seed in enumerate(self._flame_seeds):
            angle = (seed * 6.28318 + i * 0.349) % 6.28318
            base_dist = self.radius + 2 + (seed % 1.0) * 16 * burn_ratio
            flicker = math.sin(now * 9 + seed * 23) * 3 * burn_ratio
            dist = base_dist + flicker

            fx = self.x + math.cos(angle) * dist
            fy = self.y + math.sin(angle) * dist

            size = 2 + (seed % 1.0) * 4 * burn_ratio
            size += math.sin(now * 13 + seed * 17) * 1.5 * burn_ratio

            phase = (seed * 7.13) % 1.0
            if phase < 0.33:
                color = (255, int(60 + phase * 400), 0)
            elif phase < 0.66:
                color = (255, int(180 + (phase - 0.33) * 200), int((phase - 0.33) * 120))
            else:
                color = (255, 220, int(40 + (phase - 0.66) * 180))

            pygame.draw.circle(screen, color, (int(fx), int(fy)), max(1, int(size)))

    def _draw_shock(self, screen):
        """在被电击的角色身体表面绘制细小电流。"""
        shock_ratio = min(1.0, self.shock_timer / 2.0)
        now = pygame.time.get_ticks() / 1000.0

        for i, seed in enumerate(self._shock_seeds):
            base_angle = (seed * 6.28318 + now * 2.5 + i * 1.047) % 6.28318
            arc_span = 0.3 + (seed % 0.5) * 0.55

            num_segs = 4
            points = []
            for j in range(num_segs + 1):
                t = j / num_segs
                angle = base_angle + (t - 0.5) * arc_span
                flicker = math.sin(now * 22 + seed * 17 + j * 2.8) * 2.5 * shock_ratio
                r = self.radius + flicker
                px = self.x + math.cos(angle) * r
                py = self.y + math.sin(angle) * r
                points.append((int(px), int(py)))

            color = (255, 255, 110) if i % 2 == 0 else (200, 235, 255)
            width = max(1, int(1.5 * shock_ratio))
            if len(points) >= 2:
                pygame.draw.lines(screen, color, False, points, width)

    def take_damage(self, amount):
        if self.dmg_reduction_timer > 0:
            amount = amount * (1.0 - self.dmg_reduction)
        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self.alive = False


# ── Game ─────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("角斗场 Arena")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("WenQuanYi Micro Hei", 28, bold=True)
        self.font_small = pygame.font.SysFont("WenQuanYi Micro Hei", 16)
        self.font_large = pygame.font.SysFont("WenQuanYi Micro Hei", 56, bold=True)
        self.font_title = pygame.font.SysFont("WenQuanYi Micro Hei", 40, bold=True)
        self.running = True

        # State machine: "select_p1" | "select_p2" | "fighting" | "game_over"
        self.state = "select_p1"
        self.selection = [None, None]  # selected character indices for p1, p2
        self.player1 = None
        self.player2 = None
        self.projectiles: list[Projectile] = []
        self.lightning_bolts: list[LightningBolt] = []
        self.lightning_traps: list[LightningTrapBolt] = []
        self.pets: list[Pet] = []
        self.weapons: list[Weapon] = []
        self.arena = Arena()
        self.game_over = False
        self.winner = None
        self.logger = MatchLogger("output")

    # ── Selection screen ─────────────────────────────────────────────────────
    def handle_selection_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.running = False
            return
        if event.key not in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9):
            return

        idx = event.key - pygame.K_1
        if idx >= len(CHARACTERS):
            return

        if self.state == "select_p1":
            self.selection[0] = idx
            self.state = "select_p2"
        elif self.state == "select_p2":
            if idx == self.selection[0]:
                return  # can't pick same character
            self.selection[1] = idx
            self.start_match()

    def draw_selection_screen(self):
        self.screen.fill(SELECT_BG)

        # Title
        title = self.font_title.render("角斗场 — 选择出战角色", True, TEXT_COLOR)
        self.screen.blit(title, (CENTER[0] - title.get_width() // 2, 40))

        # Prompt
        if self.state == "select_p1":
            prompt_text = "按 1-9 选择 左方 角色"
        else:
            c = CHARACTERS[self.selection[0]]
            prompt_text = f"已选左方: {c.name}  —  按 1-9 选择 右方 角色（不可重复）"
        prompt = self.font.render(prompt_text, True, (180, 180, 180))
        self.screen.blit(prompt, (CENTER[0] - prompt.get_width() // 2, 70))

        # Character cards — two rows (5 + 4)
        card_w, card_h = 100, 240
        half = 5  # first row: 5 cards
        rows = [CHARACTERS[:half], CHARACTERS[half:]]
        row_y = [140, 390]

        for row_idx, row_chars in enumerate(rows):
            total_w = len(row_chars) * card_w + (len(row_chars) - 1) * 8
            start_x = CENTER[0] - total_w // 2
            card_y = row_y[row_idx]

            for col, char in enumerate(row_chars):
                i = row_idx * half + col
                cx = start_x + col * (card_w + 8)
                rect = pygame.Rect(cx, card_y, card_w, card_h)

                # Highlight selected character
                is_selected_p1 = self.selection[0] == i
                is_selected = is_selected_p1

                if is_selected:
                    border_color = (255, 215, 0)
                    bg_color = (50, 50, 60)
                elif self.state == "select_p2" and self.selection[0] == i:
                    border_color = (100, 100, 100)
                    bg_color = (35, 35, 45)
                else:
                    border_color = (70, 70, 80)
                    bg_color = (35, 35, 45)

                pygame.draw.rect(self.screen, bg_color, rect, border_radius=10)
                pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=10)

                # Character color circle
                circle_cx = cx + card_w // 2
                pygame.draw.circle(self.screen, char.color, (circle_cx, card_y + 40), 25)
                pygame.draw.circle(self.screen, (60, 60, 60), (circle_cx, card_y + 40), 25, 2)

                # Name
                name_surf = self.font_small.render(char.name, True, char.color)
                self.screen.blit(name_surf, (cx + card_w // 2 - name_surf.get_width() // 2, card_y + 78))

                # Skill info — collect all active skills for this character
                y_offset = card_y + 108
                skills: list[tuple[str, str, tuple[int, int, int]]] = []
                if char.skill is not None:
                    sk = char.skill
                    skills.append(("skill", f"{sk.name} CD:{sk.cooldown:.1f}s DMG:{sk.damage}", sk.color))
                    skills.append(("skill_sub", f"模式:{sk.movement_type.value}", (150, 150, 150)))
                if char.lightning_skill is not None:
                    lsk = char.lightning_skill
                    skills.append(("lightning", f"{lsk.name} CD:{lsk.cooldown:.1f}s DMG:{lsk.damage}", lsk.color))
                    skills.append(("lightning_sub", f"闪电 x{lsk.bolt_count}", (150, 150, 150)))
                if char.lightning_trap is not None:
                    tsk = char.lightning_trap
                    skills.append(("trap", f"{tsk.name} CD:{tsk.cooldown:.1f}s DMG:{tsk.damage}/s", tsk.trap_color))
                    skills.append(("trap_sub", f"陷阱 x{tsk.bolt_count} 减速{tsk.shock_duration}s", (150, 150, 150)))
                if char.pet_skill is not None:
                    psk = char.pet_skill
                    skills.append(("pet", f"{psk.name} CD:{psk.cooldown:.1f}s DMG:{psk.damage}", psk.color))
                    skills.append(("pet_sub", f"召唤 HP{psk.hp}", (150, 150, 150)))
                if char.weapon_skill is not None:
                    wsk = char.weapon_skill
                    skills.append(("weapon", f"{wsk.name} CD:{wsk.cooldown:.1f}s DMG:{wsk.damage}", wsk.color))
                    type_map = {"pistol": "手枪", "scythe": "镰刀", "shield": "盾牌", "boomerang": "回旋镖"}
                    skills.append(("weapon_sub", f"类型:{type_map.get(wsk.weapon_type.value, '武器')}", (150, 150, 150)))
                line_h = 15
                for j, (_, text, color) in enumerate(skills):
                    surf = self.font_small.render(text, True, color)
                    self.screen.blit(surf, (cx + card_w // 2 - surf.get_width() // 2, y_offset + j * line_h))

                # Speed
                speed_surf = self.font_small.render(f"速度: {char.speed:.1f}", True, (150, 150, 150))
                self.screen.blit(speed_surf, (cx + card_w // 2 - speed_surf.get_width() // 2, card_y + 190))

                # Key label
                key_surf = self.font.render(f"[{i + 1}]", True, TEXT_COLOR)
                self.screen.blit(key_surf, (cx + card_w // 2 - key_surf.get_width() // 2, card_y + card_h - 22))

    # ── Match start ──────────────────────────────────────────────────────────
    def start_match(self):
        p1_char = CHARACTERS[self.selection[0]]
        p2_char = CHARACTERS[self.selection[1]]
        self.player1 = Player(CENTER[0] - 100, CENTER[1], p1_char)
        self.player2 = Player(CENTER[0] + 100, CENTER[1], p2_char)

        # Give initial staggered cooldown so they don't fire at the same instant
        if p1_char.skill is not None:
            self.player1.skill_timer = random.uniform(0, p1_char.skill.cooldown * 0.5)
        if p1_char.lightning_skill is not None:
            self.player1.lightning_timer = random.uniform(0, p1_char.lightning_skill.cooldown * 0.5)
        if p2_char.skill is not None:
            self.player2.skill_timer = random.uniform(0, p2_char.skill.cooldown * 0.5)
        if p2_char.lightning_skill is not None:
            self.player2.lightning_timer = random.uniform(0, p2_char.lightning_skill.cooldown * 0.5)
        if p1_char.pet_skill is not None:
            self.player1.pet_timer = random.uniform(0, p1_char.pet_skill.cooldown * 0.5)
        if p2_char.pet_skill is not None:
            self.player2.pet_timer = random.uniform(0, p2_char.pet_skill.cooldown * 0.5)

        self.projectiles = []
        self.lightning_bolts = []
        self.lightning_traps = []
        self.pets = []
        self.weapons = []

        # Spawn persistent weapons immediately
        if p1_char.weapon_skill is not None:
            self.weapons.append(Weapon(self.player1, self.player2, p1_char.weapon_skill))
        if p2_char.weapon_skill is not None:
            self.weapons.append(Weapon(self.player2, self.player1, p2_char.weapon_skill))

        self.game_over = False
        self.winner = None
        self.state = "fighting"
        self.logger.start_match(p1_char, p2_char)

    # ── Skill spawning ───────────────────────────────────────────────────────
    def try_use_skill(self, player: Player):
        if not player.alive:
            return
        skill = player.char.skill
        if skill is None:
            return
        if player.skill_timer >= skill.cooldown:
            player.skill_timer = 0.0
            angle = random.uniform(0, 2 * math.pi)
            offset = player.radius + skill.radius + 2
            px = player.x + math.cos(angle) * offset
            py = player.y + math.sin(angle) * offset
            self.projectiles.append(
                Projectile(px, py, player.char.id, skill, owner=player)
            )

    # ── Lightning spawning ───────────────────────────────────────────────────

    def try_use_lightning(self, player: Player):
        if not player.alive:
            return
        ldef = player.char.lightning_skill
        if ldef is None:
            return
        if player.lightning_timer >= ldef.cooldown:
            player.lightning_timer = 0.0
            angles = [random.uniform(0, 2 * math.pi) for _ in range(ldef.bolt_count)]
            for angle in angles:
                self.lightning_bolts.append(
                    LightningBolt(player.x, player.y, angle, player.char.id, ldef)
                )
            # Apply self-debuffs during release
            player.slow_mult = ldef.self_speed_mult
            player.slow_timer = ldef.duration
            player.dmg_reduction = ldef.self_dmg_reduction
            player.dmg_reduction_timer = ldef.duration

    # ── Lightning trap spawning ─────────────────────────────────────────────

    def try_use_lightning_trap(self, player: Player):
        if not player.alive:
            return
        tdef = player.char.lightning_trap
        if tdef is None:
            return
        if player.lightning_trap_timer >= tdef.cooldown:
            player.lightning_trap_timer = 0.0
            angles = [random.uniform(0, 2 * math.pi) for _ in range(tdef.bolt_count)]
            for angle in angles:
                self.lightning_traps.append(
                    LightningTrapBolt(player.x, player.y, angle, player.char.id, tdef)
                )

    # ── Pet spawning ─────────────────────────────────────────────────────────
    def try_use_pet(self, player: Player):
        if not player.alive:
            return
        pdef = player.char.pet_skill
        if pdef is None:
            return
        if player.pet_timer >= pdef.cooldown:
            player.pet_timer = 0.0
            # Find opponent as target
            opponent = (self.player2 if player is self.player1 else self.player1)
            if opponent is not None and opponent.alive:
                target = opponent
            else:
                target = None
            if pdef.movement_type == PetMovement.SPIDER:
                self.pets.append(
                    SpiderPet(player.x, player.y, player.char.id, target, pdef)
                )
            elif pdef.movement_type == PetMovement.CHASE and pdef.body_length == 0:
                # Snowman pet — enforce max 6 per owner
                owned_snowmen = [p for p in self.pets
                                 if isinstance(p, SnowmanPet) and p.owner_id == player.char.id]
                if len(owned_snowmen) >= 6:
                    oldest = min(owned_snowmen, key=lambda p: p.age)
                    oldest.hp = 0  # melt the oldest
                self.pets.append(
                    SnowmanPet(player.x, player.y, player.char.id, target, pdef)
                )
            else:
                self.pets.append(
                    Pet(player.x, player.y, player.char.id, target, pdef)
                )

    # ── Player-to-player collision ──────────────────────────────────────────
    def resolve_player_collision(self):
        p1 = self.player1
        p2 = self.player2
        if not (p1.alive and p2.alive):
            return

        dx = p1.x - p2.x
        dy = p1.y - p2.y
        dist = math.hypot(dx, dy)
        min_dist = p1.radius + p2.radius

        if dist < min_dist and dist > 0.001:
            # Normal vector from p2 to p1
            nx = dx / dist
            ny = dy / dist

            # Separate players so they just touch
            overlap = min_dist - dist
            p1.x += nx * overlap / 2
            p1.y += ny * overlap / 2
            p2.x -= nx * overlap / 2
            p2.y -= ny * overlap / 2

            # Reflect velocities along collision normal (elastic collision)
            dvx = p1.vx - p2.vx
            dvy = p1.vy - p2.vy
            dv_dot_n = dvx * nx + dvy * ny

            if dv_dot_n < 0:  # moving toward each other
                p1.vx -= dv_dot_n * nx
                p1.vy -= dv_dot_n * ny
                p2.vx += dv_dot_n * nx
                p2.vy += dv_dot_n * ny

    # ── Projectile collision detection ───────────────────────────────────────

    def _get_pet_head(self, pet) -> tuple[float, float]:
        """Return (x, y) of a pet's head, works for both Pet and SpiderPet."""
        if isinstance(pet, SpiderPet):
            return pet.x, pet.y
        return pet.segments[0]

    def _get_pet_radius(self, pet) -> float:
        """Return collision radius of a pet's head."""
        if isinstance(pet, SpiderPet):
            return pet._body_radius()
        return pet._head_radius()

    def _set_pet_pos(self, pet, x: float, y: float):
        """Set a pet's head position. Works for Pet, SnowmanPet, and SpiderPet."""
        if isinstance(pet, SpiderPet):
            pet.x = x
            pet.y = y
        else:
            pet.segments[0] = (x, y)

    # ── Projectile collision detection (continued) ──────────────────────────
    def check_collisions(self):
        for proj in self.projectiles:
            # Player 1 takes damage from player 2's projectiles
            if (proj.owner_id != self.player1.char.id
                    and proj.collides_with(self.player1)
                    and self.player1.alive):
                self.player1.take_damage(proj.skill.damage)
                self._apply_burn(self.player1, proj)
                proj._hit = True
            # Player 2 takes damage from player 1's projectiles
            if (proj.owner_id != self.player2.char.id
                    and proj.collides_with(self.player2)
                    and self.player2.alive):
                self.player2.take_damage(proj.skill.damage)
                self._apply_burn(self.player2, proj)
                proj._hit = True

    def _apply_burn(self, player, proj):
        """If the projectile has burn effect, apply it to the player."""
        skill = getattr(proj, 'skill', None)
        if skill is not None and getattr(skill, 'burn_duration', 0) > 0:
            player.burn_timer = skill.burn_duration
            player.burn_dps = skill.burn_dps

    # ── Trail collision detection ──────────────────────────────────────────

    def _point_to_segment_dist(self, px, py, x1, y1, x2, y2):
        """Distance from point (px,py) to line segment (x1,y1)-(x2,y2)."""
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        cx = x1 + t * dx
        cy = y1 + t * dy
        return math.hypot(px - cx, py - cy)

    def check_trail_collisions(self):
        """Check if any player touches the opponent's movement trail."""
        threshold = PLAYER_RADIUS + 4  # 4px trail half-width
        for player, other in [(self.player1, self.player2),
                               (self.player2, self.player1)]:
            if not (player.alive and other.alive):
                continue
            if not other.char.trail_enabled:
                continue
            trail = other.trail_points
            if len(trail) < 2:
                continue
            # Check every 3rd segment for performance
            for i in range(0, len(trail) - 1, 3):
                dist = self._point_to_segment_dist(
                    player.x, player.y,
                    trail[i][0], trail[i][1],
                    trail[i + 1][0], trail[i + 1][1])
                if dist < threshold:
                    player.vx *= 0.975
                    player.vy *= 0.975
                    player.take_damage(0.05)
                    break

    # ── Lightning collision detection ──────────────────────────────────────

    def check_lightning_collisions(self):
        """Check if any player is touching an opponent's lightning bolt."""
        for bolt in self.lightning_bolts:
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if bolt.owner_id == player.char.id:
                    continue
                if bolt.collides_with(player):
                    player.take_damage(bolt.defn.damage)
                    player.slow_mult = bolt.defn.target_slow_mult
                    player.slow_timer = bolt.defn.target_slow_duration

    # ── Pet collision detection ───────────────────────────────────────────
    def check_pet_player_collisions(self):
        """Pet head touches opponent player → deal damage and expire."""
        for pet in self.pets:
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if pet.owner_id == player.char.id:
                    continue
                if pet.collides_with(player):
                    player.take_damage(pet.defn.damage)
                    pet.hp = 0  # disappear after dealing damage

    def check_pet_pet_collisions(self):
        """Pets from different owners collide → both take damage + bounce apart."""
        for i, pet_a in enumerate(self.pets):
            for pet_b in self.pets[i + 1:]:
                if pet_a.owner_id == pet_b.owner_id:
                    continue
                # Circle-circle collision between pet heads
                ax, ay = self._get_pet_head(pet_a)
                bx, by = self._get_pet_head(pet_b)
                ar = self._get_pet_radius(pet_a)
                br = self._get_pet_radius(pet_b)
                dx = ax - bx
                dy = ay - by
                dist = math.hypot(dx, dy)
                min_dist = ar + br
                if dist < min_dist and dist > 0.001:
                    # Damage: each deals its defn.damage to the other
                    pet_a.take_damage(pet_b.defn.damage)
                    pet_b.take_damage(pet_a.defn.damage)
                    # Separate to remove overlap
                    nx = dx / dist
                    ny = dy / dist
                    overlap = min_dist - dist
                    half = overlap / 2
                    self._set_pet_pos(pet_a, ax + nx * half, ay + ny * half)
                    self._set_pet_pos(pet_b, bx - nx * half, by - ny * half)

    def check_projectile_pet_collisions(self):
        """Projectiles from a player damage opponent's pets."""
        for proj in self.projectiles:
            for pet in self.pets:
                if proj.owner_id == pet.owner_id:
                    continue
                if pet.head_collides_with_circle(proj.x, proj.y, proj.skill.radius):
                    pet.take_damage(proj.skill.damage)
                    proj._hit = True

    def check_lightning_pet_collisions(self):
        """Lightning bolts from a player damage opponent's pets."""
        for bolt in self.lightning_bolts:
            for pet in self.pets:
                if bolt.owner_id == pet.owner_id:
                    continue
                head_x, head_y = self._get_pet_head(pet)
                if bolt.collides_with_point(head_x, head_y, self._get_pet_radius(pet)):
                    pet.take_damage(bolt.defn.damage)

    def check_lightning_trap_player_collisions(self):
        """TRAP状态的陷阱碰到敌方玩家 → apply shock + disappear."""
        for trap in self.lightning_traps:
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if trap.owner_id == player.char.id:
                    continue
                if trap.collides_with_player(player):
                    trap.apply_shock(player)

    def check_lightning_trap_pet_collisions(self):
        """TRAP状态的陷阱碰到敌方宠物 → apply shock + disappear."""
        for trap in self.lightning_traps:
            for pet in self.pets:
                if trap.owner_id == pet.owner_id:
                    continue
                if trap.collides_with_pet(pet):
                    trap.apply_shock(pet)

    def check_trail_pet_collisions(self):
        """Check if any pet touches the frost mage's trail (only frost has trail)."""
        threshold = PLAYER_RADIUS + 4
        for pet in self.pets:
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if not player.char.trail_enabled:
                    continue
                trail = player.trail_points
                if len(trail) < 2:
                    continue
                head_x, head_y = self._get_pet_head(pet)
                for i in range(0, len(trail) - 1, 3):
                    dist = self._point_to_segment_dist(
                        head_x, head_y,
                        trail[i][0], trail[i][1],
                        trail[i + 1][0], trail[i + 1][1])
                    if dist < threshold:
                        if isinstance(pet, SpiderPet):
                            pet.slow_timer = 0.15
                            pet.take_damage(0.05)
                        else:
                            pet.slow_mult *= 0.975
                            pet.slow_timer = 0.15
                            pet.take_damage(0.05)
                        break

    def check_spider_web_collisions(self):
        """检查玩家是否碰到对方蜘蛛的网。"""
        for pet in self.pets:
            if not isinstance(pet, SpiderPet):
                continue
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if pet.owner_id == player.char.id:
                    continue
                pet.check_web_player_collision(player)

    def check_spider_web_pet_collisions(self):
        """检查敌方宠物是否碰到蜘蛛网。"""
        for spider in self.pets:
            if not isinstance(spider, SpiderPet):
                continue
            for other in self.pets:
                if other is spider:
                    continue
                if other.owner_id == spider.owner_id:
                    continue
                spider.check_web_pet_collision(other)

    # ── Weapon collision detection ──────────────────────────────────────────
    def check_weapon_collisions(self):
        """Melee weapons deal contact damage to the opposing player."""
        for weapon in self.weapons:
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if weapon.owner_id == player.char.id:
                    continue
                if weapon.collides_with(player):
                    player.take_damage(weapon.defn.damage)
                    # 盾牌击退
                    if weapon._knockback_target is player:
                        dx = player.x - weapon.owner.x
                        dy = player.y - weapon.owner.y
                        dist = math.hypot(dx, dy)
                        if dist > 0.001:
                            player.vx = dx / dist * 200
                            player.vy = dy / dist * 200
                        else:
                            player.vx = -player.vx * 1.3
                            player.vy = -player.vy * 1.3
                        weapon._knockback_target = None

    def check_weapon_pet_collisions(self):
        """Melee weapons damage opponent's pets."""
        for weapon in self.weapons:
            for pet in self.pets:
                if weapon.owner_id == pet.owner_id:
                    continue
                if weapon.collides_with_pet(pet):
                    pet.take_damage(weapon.defn.damage)

    def check_shield_projectile_collisions(self):
        """盾牌格挡投射物：投射物碰到盾牌后被摧毁。"""
        for weapon in self.weapons:
            if weapon.defn.weapon_type.value != "shield":
                continue
            for proj in self.projectiles:
                if getattr(proj, 'owner_id', None) == weapon.owner_id:
                    continue
                # 圆-圆碰撞：盾牌中心 vs 投射物
                dx = weapon.x - proj.x
                dy = weapon.y - proj.y
                # 盾牌碰撞半径使用视觉尺寸的一半
                shield_r = (weapon.defn.length + weapon.defn.width) / 4
                proj_r = getattr(proj, 'radius', 5)
                if math.hypot(dx, dy) < shield_r + proj_r:
                    proj._hit = True

    # ── Win condition ────────────────────────────────────────────────────────
    def check_win_condition(self):
        if not self.player1.alive:
            self.game_over = True
            self.winner = self.player2.char.name
            self.state = "game_over"
            self.logger.end_match(self.player2.char.name, self.player1.char.name,
                                  self.player2.hp, self.player1.hp)
        elif not self.player2.alive:
            self.game_over = True
            self.winner = self.player1.char.name
            self.state = "game_over"
            self.logger.end_match(self.player1.char.name, self.player2.char.name,
                                  self.player1.hp, self.player2.hp)

    # ── Rendering ────────────────────────────────────────────────────────────
    def draw_arena(self):
        self.arena.draw(self.screen)

    def draw_hp(self):
        cx, cy = CENTER

        p1 = self.player1
        p2 = self.player2

        # P1 HP bar (left of center)
        hp_ratio_1 = p1.hp / INITIAL_HP
        bar_w, bar_h = 140, 18
        bar_x1 = cx - bar_w - 40
        bar_y = cy - 35

        name1 = self.font_small.render(p1.char.name, True, p1.char.color)
        self.screen.blit(name1, (bar_x1 + bar_w // 2 - name1.get_width() // 2, bar_y - 20))

        pygame.draw.rect(self.screen, (40, 40, 50), (bar_x1, bar_y, bar_w, bar_h), border_radius=4)
        hp_fill_w = int(bar_w * hp_ratio_1)
        if hp_fill_w > 0:
            pygame.draw.rect(self.screen, p1.char.color, (bar_x1, bar_y, hp_fill_w, bar_h), border_radius=4)
        pygame.draw.rect(self.screen, (80, 80, 90), (bar_x1, bar_y, bar_w, bar_h), 1, border_radius=4)

        hp_text1 = self.font_small.render(f"HP {p1.hp}/{INITIAL_HP}", True, TEXT_COLOR)
        self.screen.blit(hp_text1, (bar_x1 + bar_w // 2 - hp_text1.get_width() // 2, bar_y + 1))

        # P2 HP bar (right of center)
        hp_ratio_2 = p2.hp / INITIAL_HP
        bar_x2 = cx + 40
        bar_y = cy - 35

        name2 = self.font_small.render(p2.char.name, True, p2.char.color)
        self.screen.blit(name2, (bar_x2 + bar_w // 2 - name2.get_width() // 2, bar_y - 20))

        pygame.draw.rect(self.screen, (40, 40, 50), (bar_x2, bar_y, bar_w, bar_h), border_radius=4)
        hp_fill_w = int(bar_w * hp_ratio_2)
        if hp_fill_w > 0:
            pygame.draw.rect(self.screen, p2.char.color, (bar_x2, bar_y, hp_fill_w, bar_h), border_radius=4)
        pygame.draw.rect(self.screen, (80, 80, 90), (bar_x2, bar_y, bar_w, bar_h), 1, border_radius=4)

        hp_text2 = self.font_small.render(f"HP {p2.hp}/{INITIAL_HP}", True, TEXT_COLOR)
        self.screen.blit(hp_text2, (bar_x2 + bar_w // 2 - hp_text2.get_width() // 2, bar_y + 1))

        # Center VS
        vs_text = self.font.render("VS", True, TEXT_COLOR)
        self.screen.blit(vs_text, (cx - vs_text.get_width() // 2, cy - vs_text.get_height() // 2))

        # Skill info below center
        for p, bar_x in [(p1, bar_x1), (p2, bar_x2)]:
            infos: list[tuple[str, tuple[int, int, int]]] = []
            if p.char.skill is not None:
                infos.append((f"{p.char.skill.name} ({p.char.skill.cooldown:.1f}s)", p.char.skill.color))
            if p.char.lightning_skill is not None:
                infos.append((f"{p.char.lightning_skill.name} ({p.char.lightning_skill.cooldown:.1f}s)", p.char.lightning_skill.color))
            if p.char.lightning_trap is not None:
                infos.append((f"{p.char.lightning_trap.name} ({p.char.lightning_trap.cooldown:.1f}s)", p.char.lightning_trap.trap_color))
            if p.char.pet_skill is not None:
                infos.append((f"{p.char.pet_skill.name} ({p.char.pet_skill.cooldown:.1f}s)", p.char.pet_skill.color))
            if p.char.weapon_skill is not None:
                infos.append((f"{p.char.weapon_skill.name} ({p.char.weapon_skill.cooldown:.1f}s)", p.char.weapon_skill.color))
            for k, (info, color) in enumerate(infos):
                surf = self.font_small.render(info, True, color)
                self.screen.blit(surf, (bar_x + bar_w // 2 - surf.get_width() // 2, bar_y + bar_h + 10 + k * 14))

    def draw_game_over(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        go_text = self.font_large.render("游戏结束", True, (255, 80, 80))
        win_text = self.font.render(f"获胜方: {self.winner}", True, TEXT_COLOR)
        restart_text = self.font_small.render("按 R 重新选择 / 按 Q 退出", True, (180, 180, 180))

        self.screen.blit(go_text, (CENTER[0] - go_text.get_width() // 2, CENTER[1] - 80))
        self.screen.blit(win_text, (CENTER[0] - win_text.get_width() // 2, CENTER[1] - 10))
        self.screen.blit(restart_text, (CENTER[0] - restart_text.get_width() // 2, CENTER[1] + 40))

    # ── Reset ────────────────────────────────────────────────────────────────
    def reset(self):
        self.state = "select_p1"
        self.selection = [None, None]
        self.player1 = None
        self.player2 = None
        self.projectiles = []
        self.lightning_bolts = []
        self.lightning_traps = []
        self.pets = []
        self.weapons = []
        self.game_over = False
        self.winner = None

    def _update_fighting(self, dt):
        """单帧战斗逻辑更新（不含渲染），可供测试脚本复用。"""
        # Skill timers
        self.player1.skill_timer += dt
        self.player2.skill_timer += dt
        self.player1.lightning_timer += dt
        self.player2.lightning_timer += dt
        self.player1.lightning_trap_timer += dt
        self.player2.lightning_trap_timer += dt
        self.player1.pet_timer += dt
        self.player2.pet_timer += dt

        self.try_use_skill(self.player1)
        self.try_use_skill(self.player2)
        self.try_use_lightning(self.player1)
        self.try_use_lightning(self.player2)
        self.try_use_lightning_trap(self.player1)
        self.try_use_lightning_trap(self.player2)
        self.try_use_pet(self.player1)
        self.try_use_pet(self.player2)

        # Movement
        self.player1.update(self.arena, dt)
        self.player2.update(self.arena, dt)

        # Player-to-player bounce
        self.resolve_player_collision()

        # Update projectiles & lightning bolts, remove expired
        for proj in self.projectiles:
            proj.update(dt)
        self.projectiles = [p for p in self.projectiles if not p.is_expired()]
        for bolt in self.lightning_bolts:
            bolt.update(dt)
        self.lightning_bolts = [b for b in self.lightning_bolts if not b.is_expired()]
        for trap in self.lightning_traps:
            trap.update(dt)
        self.lightning_traps = [t for t in self.lightning_traps if not t.is_expired()]
        for pet in self.pets:
            pet.update(dt)
        self.pets = [p for p in self.pets if not p.is_expired()]
        for weapon in self.weapons:
            weapon.update(dt)
            if weapon.should_fire():
                self.projectiles.append(weapon.fire())
        self.weapons = [w for w in self.weapons if not w.is_expired()]

        # Collisions
        self.check_collisions()
        self.check_trail_collisions()
        self.check_spider_web_collisions()
        self.check_spider_web_pet_collisions()
        self.check_lightning_collisions()
        self.check_lightning_trap_player_collisions()
        self.check_lightning_trap_pet_collisions()
        self.check_pet_player_collisions()
        self.check_pet_pet_collisions()
        self.check_projectile_pet_collisions()
        self.check_lightning_pet_collisions()
        self.check_trail_pet_collisions()
        self.check_weapon_collisions()
        self.check_weapon_pet_collisions()
        self.check_shield_projectile_collisions()

        # Win condition
        self.check_win_condition()

    # ── Main loop ────────────────────────────────────────────────────────────
    def run(self):
        dt = 1.0 / FPS
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                if self.state in ("select_p1", "select_p2"):
                    self.handle_selection_input(event)

                if self.state == "game_over" and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        self.reset()
                    elif event.key == pygame.K_q:
                        self.running = False

            # ── Update ───────────────────────────────────────────────────────
            if self.state == "fighting" and not self.game_over:
                self._update_fighting(dt)

            # ── Render ───────────────────────────────────────────────────────
            if self.state in ("select_p1", "select_p2"):
                self.draw_selection_screen()
            else:
                self.draw_arena()

                # Draw trails behind projectiles and players
                for p in (self.player1, self.player2):
                    if p.alive and p.char.trail_enabled and len(p.trail_points) >= 2:
                        trail_color = (135, 206, 235)
                        for i in range(0, len(p.trail_points), 2):
                            x, y = p.trail_points[i]
                            pygame.draw.circle(self.screen, trail_color, (int(x), int(y)), p.radius)

                # Draw lightning bolts (between trails and projectiles)
                for bolt in self.lightning_bolts:
                    bolt.draw(self.screen)
                for trap in self.lightning_traps:
                    trap.draw(self.screen)

                # Draw pets
                for pet in self.pets:
                    pet.draw(self.screen)

                for proj in self.projectiles:
                    proj.draw(self.screen)

                if self.player1.alive:
                    self.player1.draw(self.screen, self.font_small)
                if self.player2.alive:
                    self.player2.draw(self.screen, self.font_small)

                # Draw weapons on top of players
                for weapon in self.weapons:
                    weapon.draw(self.screen)

                self.draw_hp()

                if self.game_over:
                    self.draw_game_over()

            pygame.display.flip()
            self.clock.tick(FPS)

        self.logger.close()
        pygame.quit()


if __name__ == "__main__":
    game = Game()
    game.run()
