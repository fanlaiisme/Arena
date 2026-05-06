import pygame
import random
import math

from characters import CharacterTemplate, CHARACTERS
from projectile import Projectile, ShadowClone, GoldenPalm, FistTrap, VortexEntity, WaveEntity, HuntMark, TreeEntity, LeafBlade, CrescentBeam, VerticalBeam

SHOW_SKILL_RANGES = True  # 是否显示技能触发范围
ORC_FIST_RANGE = 200       # 兽人双拳扇形范围半径（px）
ORC_FIST_SPAWN_DIST = 140  # 兽人双拳在扇形内的释放距离（px）
from lightning import LightningBolt, LightningTrapBolt
from pet import Pet, SpiderPet, SnowmanPet, GhostPet, PetMovement
from weapon import Weapon, WeaponType, Bullet, HomingMissile, WeaponPickup, ShurikenProjectile
from bomb import Bomb, BombDef, GasCloud
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
        self.skill2_timer = 0.0  # second skill
        self.golden_body_timer = 0.0  # 金身
        self.unstoppable_timer = 0.0  # 霸体
        self.fist_release_timer = 0.0  # 兽人双拳释放减速
        self._fist_saved_vx = 0.0
        self._fist_saved_vy = 0.0
        self._cone_facing = 0.0       # 扇形朝向
        self.skill_locked = False     # 被漩涡吸入时禁止技能
        self._self_slowed = False      # 自减速标记
        self._self_saved_vx = 0.0
        self._self_saved_vy = 0.0
        # 猎杀印记传送延迟
        self._hunt_teleport_timer = 0.0
        self._hunt_saved_vx = 0.0
        self._hunt_saved_vy = 0.0
        self._hunt_saved_speed = 0.0
        self._hunt_speed_trigger_cd = 0.0  # 速度触发冷却（3s 防连发）
        self._fear_mark_timers: list[float] = []  # 恐惧印记剩余时间
        self._staff_hit_timer = 0.0    # 法杖咒术心脏颤动计时
        self._staff_saved_speed = 0.0  # 法杖咒术保留的敌人速度
        self.lightning_timer = 0.0  # counts up to lightning_skill.cooldown
        self.lightning_trap_timer = 0.0  # counts up to lightning_trap.cooldown
        self.pet_timer = 0.0       # counts up to pet_skill.cooldown
        self.bomb_timer = 0.0       # counts up to bomb_skill.cooldown
        self.bomb_timer2 = 0.0      # counts up to bomb_skill2.cooldown
        self.trail_points: list[tuple[float, float]] = []
        self.max_trail_length = 600
        # Weapon speed cap
        self.weapon_speed_mult = 1.0
        # Pickup weapon state (weaponmaster)
        self.pickup_uses_left = 0
        self.pickup_timer = 0.0
        # Stealth state (hunter)
        self.invisible = False
        self.invisible_timer = 0.0
        self._mist_seeds = [random.uniform(0, 100) for _ in range(12)]
        # Rage passive (orc)
        self.rage_stacks = 0
        self.rage_timer = 0.0
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

    def update(self, arena=None, dt=1/60, seek_target=None):
        if not self.alive:
            return

        # Update rage decay (兽人被动：4秒未受伤则衰减)
        if self.rage_stacks > 0:
            self.rage_timer += dt
            if self.rage_timer >= 4.0:
                self.rage_stacks = max(0, self.rage_stacks - 1)
                self.rage_timer = 0.0
        # Update buff timers
        if self.golden_body_timer > 0:
            self.golden_body_timer = max(0.0, self.golden_body_timer - dt)
        if self.unstoppable_timer > 0:
            self.unstoppable_timer = max(0.0, self.unstoppable_timer - dt)
        if self.fist_release_timer > 0:
            self.fist_release_timer = max(0.0, self.fist_release_timer - dt)
            slow_vx = self._fist_saved_vx * 0.05
            slow_vy = self._fist_saved_vy * 0.05
            spd = math.hypot(self.vx, self.vy)
            if spd > math.hypot(slow_vx, slow_vy):
                self.vx = slow_vx
                self.vy = slow_vy
            if self.fist_release_timer == 0.0:
                self.vx = self._fist_saved_vx
                self.vy = self._fist_saved_vy
        # 猎杀印记传送延迟：冻结速度为 1%
        if self._hunt_teleport_timer > 0:
            self._hunt_teleport_timer = max(0.0, self._hunt_teleport_timer - dt)
            self.vx = self._hunt_saved_vx * 0.01
            self.vy = self._hunt_saved_vy * 0.01
        # 猎杀印记速度触发冷却
        if self._hunt_speed_trigger_cd > 0:
            self._hunt_speed_trigger_cd = max(0.0, self._hunt_speed_trigger_cd - dt)
        # Update invisibility timer
        if self.invisible_timer > 0:
            self.invisible_timer = max(0.0, self.invisible_timer - dt)
            if self.invisible_timer == 0.0:
                self.invisible = False
        # Update debuff timers
        if self.slow_timer > 0:
            self.slow_timer = max(0.0, self.slow_timer - dt)
            if self.slow_timer == 0.0:
                self.slow_mult = 1.0
                if self._self_slowed:
                    self.vx = self._self_saved_vx
                    self.vy = self._self_saved_vy
                    self._self_slowed = False
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

        # Movement: seek target or random walk
        effective_max_speed = self.char.speed * self.weapon_speed_mult * (1.0 + self.rage_stacks * 0.15)
        if seek_target is not None:
            dx = seek_target[0] - self.x
            dy = seek_target[1] - self.y
            dist = math.hypot(dx, dy)
            if dist > 5:
                seek_speed = self.char.speed / 3.0
                self.vx = dx / dist * seek_speed
                self.vy = dy / dist * seek_speed
            # else: close enough, let friction slow us down
        else:
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
            self.vx *= 0.997
            self.vy *= 0.997

            # Speed cap from character template (modified by weapon)
            # 恐惧印记期间跳过 speed cap
            if len(self._fear_mark_timers) == 0:
                speed = math.hypot(self.vx, self.vy)
                if speed > effective_max_speed:
                    self.vx = self.vx / speed * effective_max_speed
                    self.vy = self.vy / speed * effective_max_speed

        # Apply slow debuff before position update（霸体免疫）
        if self.slow_timer > 0 and self.unstoppable_timer <= 0:
            self.vx *= self.slow_mult
            self.vy *= self.slow_mult

        # 恐惧印记衰减
        for i in range(len(self._fear_mark_timers) - 1, -1, -1):
            self._fear_mark_timers[i] -= dt
            if self._fear_mark_timers[i] <= 0:
                self.vx /= 1.1
                self.vy /= 1.1
                self._fear_mark_timers.pop(i)

        # 法杖咒术心脏颤动衰减
        if self._staff_hit_timer > 0:
            self._staff_hit_timer = max(0.0, self._staff_hit_timer - dt)

        if not self.skill_locked:
            self.x += self.vx
            self.y += self.vy

        # Arena boundary collision (漩涡捕获时跳过)
        if arena is not None and not self.skill_locked:
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

        if self.invisible:
            self._draw_mist(screen)
            self._draw_skill_range(screen)
            return

        # 金身光晕
        if self.golden_body_timer > 0:
            alpha = int(60 + 30 * math.sin(pygame.time.get_ticks() * 0.005))
            for i in range(3):
                r = self.radius + 4 + i * 6
                glow = pygame.Surface((int(r * 2 + 4), int(r * 2 + 4)), pygame.SRCALPHA)
                pygame.draw.circle(glow, (255, 255, 240, alpha // (i + 2)),
                                 (int(r) + 2, int(r) + 2), int(r))
                screen.blit(glow, (int(self.x) - int(r) - 2, int(self.y) - int(r) - 2))

        # 霸体特效（暗红血气光晕，仿金身多层填充）
        if self.unstoppable_timer > 0:
            now = pygame.time.get_ticks() * 0.001
            for i in range(4):
                r = self.radius + 5 + i * 8 + math.sin(now * 10 + i * 2.5) * 4
                alpha = int(100 + 50 * math.sin(now * 7 + i * 1.7))
                glow = pygame.Surface((int(r * 2 + 4), int(r * 2 + 4)), pygame.SRCALPHA)
                # 内层亮红填充
                pygame.draw.circle(glow, (240, 70, 40, max(20, alpha // (i + 1))),
                                 (int(r) + 2, int(r) + 2), int(r))
                # 外层暗红描边增加层次
                pygame.draw.circle(glow, (180, 30, 20, max(15, alpha // (i + 2))),
                                 (int(r) + 2, int(r) + 2), int(r), 2)
                screen.blit(glow, (int(self.x) - int(r) - 2, int(self.y) - int(r) - 2))

        # 法杖咒术心脏颤动效果
        shake_x = shake_y = 0
        if self._staff_hit_timer > 0:
            now = pygame.time.get_ticks() * 0.001
            intensity = self._staff_hit_timer / 0.5
            shake_x = int(math.sin(now * 40.0) * 4 * intensity)
            shake_y = int(math.cos(now * 35.0) * 4 * intensity)
            # 三层红色脉冲扩散环
            for i in range(3):
                phase = (intensity + i * 0.3) % 1.0
                ping_r = int(self.radius + phase * 50)
                ping_alpha = int(180 * (1.0 - phase) // (i + 1))
                ping_surf = pygame.Surface((ping_r * 2 + 4, ping_r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(ping_surf, (220, 30, 50, ping_alpha),
                                   (ping_r + 2, ping_r + 2), ping_r, 2)
                screen.blit(ping_surf, (int(self.x) - ping_r - 2 + shake_x,
                                        int(self.y) - ping_r - 2 + shake_y))

        draw_x = int(self.x) + shake_x
        draw_y = int(self.y) + shake_y
        pygame.draw.circle(screen, self.char.color, (draw_x, draw_y), self.radius)
        pygame.draw.circle(screen, (60, 60, 60), (draw_x, draw_y), self.radius, 2)
        # Skill range visualization
        self._draw_skill_range(screen)
        # Name label above player
        name_surf = font_small.render(self.char.name, True, self.char.color)
        screen.blit(name_surf, (draw_x - name_surf.get_width() // 2, draw_y - self.radius - 22))

    def _draw_skill_range(self, screen):
        """绘制技能触发范围可视化（仅在 SHOW_SKILL_RANGES 开启时）。"""
        if not SHOW_SKILL_RANGES:
            return
        skill = self.char.skill
        if skill is None:
            return
        if skill.name == "金掌":
            # 武僧周围 100px 金色圆
            glow = pygame.Surface((204, 204), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 215, 0, 30), (102, 102), 100)
            pygame.draw.circle(glow, (255, 215, 0, 60), (102, 102), 100, 1)
            screen.blit(glow, (int(self.x) - 102, int(self.y) - 102))
        elif skill.name == "双拳":
            # 兽人面前 90° 锥形（始终朝向敌人）
            facing = self._cone_facing
            rng = ORC_FIST_RANGE
            surf_sz = rng * 2 + 20
            cone_surf = pygame.Surface((surf_sz, surf_sz), pygame.SRCALPHA)
            cx, cy = surf_sz // 2, surf_sz // 2
            pts = [(cx, cy)]
            for deg in range(-45, 46, 3):
                a = facing + math.radians(deg)
                pts.append((cx + math.cos(a) * rng, cy + math.sin(a) * rng))
            pygame.draw.polygon(cone_surf, (180, 140, 80, 25), pts)
            pygame.draw.circle(cone_surf, (0, 0, 0, 0), (cx, cy), 60)
            arc_rect = pygame.Rect(cx - rng, cy - rng, rng * 2, rng * 2)
            pygame.draw.arc(cone_surf, (180, 140, 80, 60), arc_rect,
                          -(facing + math.radians(45)), -(facing - math.radians(45)), 1)
            screen.blit(cone_surf, (int(self.x) - cx, int(self.y) - cy))

    def _draw_mist(self, screen):
        """隐身迷雾特效：扩散光晕 + 烟雾粒子。"""
        now = pygame.time.get_ticks() / 1000.0
        # 扩散圆环
        for i in range(3):
            r = self.radius + 6 + i * 8 + math.sin(now * 2.0 + i) * 4
            alpha = int(40 + 20 * (3 - i))
            glow_surf = pygame.Surface((int(r * 2 + 4), int(r * 2 + 4)), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (160, 170, 160, alpha),
                             (int(r) + 2, int(r) + 2), int(r))
            screen.blit(glow_surf, (int(self.x) - int(r) - 2, int(self.y) - int(r) - 2))
        # 烟雾粒子
        for i, seed in enumerate(self._mist_seeds):
            angle = (seed * 6.28318 + now * 0.8 + i * 0.7) % 6.28318
            dist = self.radius + 4 + (seed % 1.0) * 20 + math.sin(now * 2.5 + seed) * 6
            px = self.x + math.cos(angle) * dist
            py = self.y + math.sin(angle) * dist
            alpha = int(80 + 40 * math.sin(now * 3 + seed))
            size = 2 + (seed % 1.0) * 3
            color = (180, 190, 180, max(0, min(255, alpha)))
            s = pygame.Surface((int(size * 2 + 2), int(size * 2 + 2)), pygame.SRCALPHA)
            pygame.draw.circle(s, color, (int(size) + 1, int(size) + 1), int(size))
            screen.blit(s, (int(px) - int(size) - 1, int(py) - int(size) - 1))

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
        if self.golden_body_timer > 0:
            amount *= 0.5
        self.hp -= amount
        if amount > 0 and self.char.id == "berserker" and self.alive:
            self.rage_stacks = min(5, self.rage_stacks + 1)
            self.rage_timer = 0.0
            self.vx *= 1.25
            self.vy *= 1.25
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
        self.weapon_pickups: list[WeaponPickup] = []
        self.clones: list[ShadowClone] = []
        self.palms: list[GoldenPalm] = []
        self.fist_traps: list[FistTrap] = []
        self.vortexes: list[VortexEntity] = []
        self.waves: list[WaveEntity] = []
        self.hunt_marks: list[HuntMark] = []
        self.trees: list[TreeEntity] = []
        self.leaf_blades: list[LeafBlade] = []
        self._wave_burst_timer = 0.0
        self._wave_burst_remaining = 0
        self._wave_owner = None  # Player reference for burst spawn
        self._pickup_spawn_timer = random.uniform(3.0, 6.0)
        self._pickup_spawn_interval = 5.0
        self._max_pickups = 3
        self.bombs: list[Bomb] = []
        self.gas_clouds: list[GasCloud] = []
        self.arena = Arena()
        self.game_over = False
        self.winner = None
        self.logger = MatchLogger("output")

    # ── Selection screen ─────────────────────────────────────────────────────
    def handle_selection_input(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.running = False
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        mx, my = event.pos
        cols = 5
        card_w, card_h = 130, 80
        gap_x, gap_y = 10, 10
        total_w = cols * card_w + (cols - 1) * gap_x
        start_x = CENTER[0] - total_w // 2
        start_y = 130

        for i, char in enumerate(CHARACTERS):
            row = i // cols
            col = i % cols
            cx = start_x + col * (card_w + gap_x)
            cy = start_y + row * (card_h + gap_y)
            rect = pygame.Rect(cx, cy, card_w, card_h)

            if rect.collidepoint(mx, my):
                if self.state == "select_p1":
                    self.selection[0] = i
                    self.state = "select_p2"
                elif self.state == "select_p2":
                    if i == self.selection[0]:
                        return
                    self.selection[1] = i
                    self.start_match()
                return

    def draw_selection_screen(self):
        self.screen.fill(SELECT_BG)

        # Title
        title = self.font_title.render("角斗场 — 选择出战角色", True, TEXT_COLOR)
        self.screen.blit(title, (CENTER[0] - title.get_width() // 2, 18))

        # Prompt
        if self.state == "select_p1":
            prompt_text = "鼠标点击选择 左方 角色"
        else:
            c = CHARACTERS[self.selection[0]]
            prompt_text = f"已选左方: {c.name}  —  鼠标点击选择 右方 角色（不可重复）"
        prompt = self.font.render(prompt_text, True, (180, 180, 180))
        self.screen.blit(prompt, (CENTER[0] - prompt.get_width() // 2, 72))

        # Character grid — 5 cols × 4 rows
        cols = 5
        card_w, card_h = 130, 80
        gap_x, gap_y = 10, 10
        total_w = cols * card_w + (cols - 1) * gap_x
        start_x = CENTER[0] - total_w // 2
        start_y = 120

        mx, my = pygame.mouse.get_pos()

        for i, char in enumerate(CHARACTERS):
            row = i // cols
            col = i % cols
            cx = start_x + col * (card_w + gap_x)
            cy = start_y + row * (card_h + gap_y)
            rect = pygame.Rect(cx, cy, card_w, card_h)

            # Determine card appearance
            is_selected_p1 = self.selection[0] == i
            is_selected_p2 = self.selection[1] == i
            is_hovered = rect.collidepoint(mx, my)
            is_disabled = self.state == "select_p2" and self.selection[0] == i

            if is_selected_p1 or is_selected_p2:
                border_color = (255, 215, 0)
                bg_color = (50, 50, 60)
            elif is_disabled:
                border_color = (50, 50, 55)
                bg_color = (28, 28, 35)
            elif is_hovered:
                border_color = (180, 180, 200)
                bg_color = (45, 45, 55)
            else:
                border_color = (70, 70, 80)
                bg_color = (35, 35, 45)

            pygame.draw.rect(self.screen, bg_color, rect, border_radius=8)
            pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=8)

            # Color circle (left side)
            circle_cx = cx + 25
            circle_cy = cy + card_h // 2
            pygame.draw.circle(self.screen, char.color, (circle_cx, circle_cy), 18)
            pygame.draw.circle(self.screen, (60, 60, 60), (circle_cx, circle_cy), 18, 1)

            # Name (right of circle)
            name_x = cx + 52
            name_surf = self.font_small.render(char.name, True, char.color)
            self.screen.blit(name_surf, (name_x, cy + 21))

            # ID (below name)
            id_surf = self.font_small.render(char.id, True, (140, 140, 150))
            self.screen.blit(id_surf, (name_x, cy + 44))

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
        if p1_char.bomb_skill is not None:
            self.player1.bomb_timer = random.uniform(0, p1_char.bomb_skill.cooldown * 0.5)
        if p2_char.bomb_skill is not None:
            self.player2.bomb_timer = random.uniform(0, p2_char.bomb_skill.cooldown * 0.5)
        if p1_char.bomb_skill2 is not None:
            self.player1.bomb_timer2 = random.uniform(0, p1_char.bomb_skill2.cooldown * 0.5)
        if p2_char.bomb_skill2 is not None:
            self.player2.bomb_timer2 = random.uniform(0, p2_char.bomb_skill2.cooldown * 0.5)

        self.projectiles = []
        self.lightning_bolts = []
        self.lightning_traps = []
        self.pets = []
        self.weapons = []
        self.bombs = []
        self.gas_clouds = []
        self.weapon_pickups = []
        self.clones = []
        self.palms = []
        self.fist_traps = []
        self.vortexes = []
        self.waves = []
        self.hunt_marks = []
        self.trees = []
        self.leaf_blades = []
        self._wave_burst_remaining = 0
        self._pickup_spawn_timer = random.uniform(3.0, 6.0)

        # Spawn persistent weapons immediately
        if p1_char.weapon_skill is not None:
            self.weapons.append(Weapon(self.player1, self.player2, p1_char.weapon_skill))
        if p1_char.weapon_skill2 is not None:
            self.weapons.append(Weapon(self.player1, self.player2, p1_char.weapon_skill2))
        if p2_char.weapon_skill is not None:
            self.weapons.append(Weapon(self.player2, self.player1, p2_char.weapon_skill))
        if p2_char.weapon_skill2 is not None:
            self.weapons.append(Weapon(self.player2, self.player1, p2_char.weapon_skill2))

        self.game_over = False
        self.winner = None
        self.state = "fighting"
        self.logger.start_match(p1_char, p2_char)

    # ── Skill spawning ───────────────────────────────────────────────────────
    def try_use_skill(self, player: Player):
        if not player.alive or player.skill_locked:
            return
        skill = player.char.skill
        if skill is None:
            return
        # 兽人每帧更新扇形朝向（不受冷却限制）
        if player.char.id == "orc" and skill.name == "双拳":
            opponent = self.player1 if player is self.player2 else self.player2
            if opponent.alive:
                player._cone_facing = math.atan2(opponent.y - player.y, opponent.x - player.x)
        if player.skill_timer >= skill.cooldown:
            player.skill_timer = 0.0
            # 潮汐使者的海洋漩涡（随机位置）
            if player.char.id == "brawler" and skill.name == "海洋漩涡":
                angle = random.uniform(0, 2 * math.pi)
                r = random.uniform(30, ARENA_RADIUS - 130)
                vx = CENTER[0] + math.cos(angle) * r
                vy = CENTER[1] + math.sin(angle) * r
                self.vortexes.append(VortexEntity(vx, vy, player.char.id, skill))
                return
            # 森林精灵的生命之树（最多3棵，在精灵与圆心中点生成）
            if player.char.id == "elf" and skill.name == "生命之树":
                my_trees = len([t for t in self.trees if t.owner_id == player.char.id])
                if my_trees >= 3:
                    return
                tx = (player.x + CENTER[0]) / 2
                ty = (player.y + CENTER[1]) / 2
                self.trees.append(TreeEntity(tx, ty, player.char.id))
                return
            # 暗夜猎手的隐身技能
            if player.char.id == "hunter" and skill.name == "隐身":
                player.invisible = True
                player.invisible_timer = skill.lifetime
                return
            # 武僧的金掌技能（敌方玩家或宠物在圆形范围内触发）
            if player.char.id == "monk" and skill.name == "金掌":
                opponent = self.player1 if player is self.player2 else self.player2
                target_x, target_y = None, None
                if opponent.alive and math.hypot(opponent.x - player.x, opponent.y - player.y) <= 100:
                    target_x, target_y = opponent.x, opponent.y
                else:
                    for pet in self.pets:
                        if pet.owner_id == player.char.id:
                            continue
                        px, py = self._get_pet_head(pet)
                        if math.hypot(px - player.x, py - player.y) <= 100:
                            target_x, target_y = px, py
                            break
                if target_x is None:
                    return
                self.palms.append(GoldenPalm(target_x, target_y, player.char.id, skill))
                return
            # 兽人的双拳技能（敌人在面前锥形内触发，冷却就绪后等待敌人进范围）
            if player.char.id == "orc" and skill.name == "双拳":
                facing = player._cone_facing
                # 检查敌方玩家
                opponent = self.player1 if player is self.player2 else self.player2
                target_in_cone = False
                if opponent.alive:
                    dx = opponent.x - player.x
                    dy = opponent.y - player.y
                    dist = math.hypot(dx, dy)
                    ta = math.atan2(dy, dx)
                    ad = abs((ta - facing + math.pi) % (2 * math.pi) - math.pi)
                    if ad < math.radians(45) and 0 < dist < ORC_FIST_RANGE:
                        target_in_cone = True
                # 检查敌方宠物
                if not target_in_cone:
                    for pet in self.pets:
                        if pet.owner_id == player.char.id:
                            continue
                        px, py = self._get_pet_head(pet)
                        dx = px - player.x
                        dy = py - player.y
                        dist = math.hypot(dx, dy)
                        ta = math.atan2(dy, dx)
                        ad = abs((ta - facing + math.pi) % (2 * math.pi) - math.pi)
                        if ad < math.radians(45) and 0 < dist < ORC_FIST_RANGE:
                            target_in_cone = True
                            break
                if not target_in_cone:
                    player.skill_timer = skill.cooldown  # 保持就绪，不重置
                    return
                dist = ORC_FIST_SPAWN_DIST
                # 左右拳对称于扇形中轴线，在扇形范围内
                la = facing + math.radians(22)
                ra = facing - math.radians(22)
                lx = player.x + math.cos(la) * dist
                ly = player.y + math.sin(la) * dist
                rx = player.x + math.cos(ra) * dist
                ry = player.y + math.sin(ra) * dist
                self.fist_traps.append(FistTrap(lx, ly, rx, ry, player.char.id, skill, facing))
                player._fist_saved_vx = player.vx
                player._fist_saved_vy = player.vy
                player.fist_release_timer = skill.lifetime
                return
            # 狂战士的霸体技能
            if player.char.id == "berserker" and skill.name == "霸体":
                player.unstoppable_timer = skill.lifetime
                return
            # 忍者的影分身技能
            if player.char.id == "ninja" and skill.name == "影分身":
                # 移除旧分身并恢复其追踪目标
                for old in self.clones:
                    if old.owner_id == player.char.id:
                        self._restore_tracking_targets(old)
                self.clones = [c for c in self.clones if c.owner_id != player.char.id]
                clone = ShadowClone(player, player.x, player.y, skill)
                self.clones.append(clone)
                # 所有追踪实体重定向到分身
                self._redirect_tracking_to_clone(clone)
                # 忍者获得垂直于对称轴方向的速度提升 40%
                dx = player.x - CENTER[0]
                dy = player.y - CENTER[1]
                perp_x = dy
                perp_y = -dx
                perp_dist = math.hypot(perp_x, perp_y)
                if perp_dist > 0.001:
                    perp_x /= perp_dist
                    perp_y /= perp_dist
                boost = math.hypot(player.vx, player.vy) * 0.4
                player.vx += perp_x * boost
                player.vy += perp_y * boost
                return
            angle = random.uniform(0, 2 * math.pi)
            offset = player.radius + skill.radius + 2
            px = player.x + math.cos(angle) * offset
            py = player.y + math.sin(angle) * offset
            self.projectiles.append(
                Projectile(px, py, player.char.id, skill, owner=player)
            )

    # ── Second skill spawning ─────────────────────────────────────────────────

    def try_use_skill2(self, player: Player):
        if not player.alive or player.skill_locked:
            return
        skill = player.char.skill2
        if skill is None:
            return

        # 狂战士-猎杀印记：速度>=10且触发冷却就绪时释放
        if skill.name == "猎杀印记":
            speed = math.hypot(player.vx, player.vy)
            if speed >= 10 and player._hunt_speed_trigger_cd <= 0:
                player._hunt_speed_trigger_cd = 3.0
                player.skill2_timer = 0.0
                self._trigger_hunt_mark(player, speed)
                return

        if player.skill2_timer >= skill.cooldown:
            player.skill2_timer = 0.0
            # 狂战士-猎杀印记：冷却就绪释放
            if skill.name == "猎杀印记":
                speed = math.hypot(player.vx, player.vy)
                self._trigger_hunt_mark(player, speed)
                return
            # 武僧金身
            if skill.name == "金身":
                player.golden_body_timer = skill.lifetime
            # 潮汐使者的波纹（连续3波）
            if skill.name == "波纹":
                opponent = self.player1 if player is self.player2 else self.player2
                angle = math.atan2(opponent.y - player.y, opponent.x - player.x)
                self.waves.append(WaveEntity(player.x, player.y, angle, player.char.id, skill))
                self._wave_burst_timer = 0.5
                self._wave_burst_remaining = 2
                self._wave_owner = player
                player.skill2_timer = 0.0  # 波次开始后重置冷却
            # 森林精灵的叶刃风暴（4片叶子环绕）
            if skill.name == "叶刃风暴":
                opponent = self.player1 if player is self.player2 else self.player2
                for i in range(4):
                    angle = i * math.pi / 2
                    self.leaf_blades.append(
                        LeafBlade(player, opponent, angle, skill, i))
                return

    # ── HuntMark helper ─────────────────────────────────────────────────────────

    def _trigger_hunt_mark(self, player: Player, speed: float):
        """狂战士猎杀印记：保存速度、冻结玩家、在敌人位置生成印记。"""
        opponent = self.player1 if player is self.player2 else self.player2

        player._hunt_saved_vx = player.vx
        player._hunt_saved_vy = player.vy
        player._hunt_saved_speed = speed
        player._hunt_teleport_timer = 0.9

        # 速度冻结为 1%
        player.vx *= 0.01
        player.vy *= 0.01

        # 保存方向用于传送后速度恢复
        angle = math.atan2(player._hunt_saved_vy, player._hunt_saved_vx)

        # 在敌人当前位置生成印记
        tx = opponent.x if opponent.alive else player.x
        ty = opponent.y if opponent.alive else player.y

        self.hunt_marks.append(
            HuntMark(tx, ty, player.char.id, player.char.skill2,
                     saved_speed=speed, saved_angle=angle)
        )

    def _apply_hunt_mark_damage(self, hm: HuntMark):
        """猎杀印记AOE伤害：中心 multiplier=2.5 → 边缘 1.8 线性衰减。"""
        CENTER_MULT = 2.5
        EDGE_MULT = 1.8
        min_ratio = EDGE_MULT / CENTER_MULT  # 0.72

        for player in (self.player1, self.player2):
            if not player.alive or player.char.id == hm.owner_id:
                continue
            dist = math.hypot(player.x - hm.x, player.y - hm.y)
            if dist < hm.radius + player.radius:
                ratio = 1.0 - (1.0 - min_ratio) * (dist / hm.radius)
                ratio = max(min_ratio, min(1.0, ratio))
                damage = hm.saved_speed * CENTER_MULT * ratio
                player.take_damage(damage)

        for pet in self.pets:
            if isinstance(pet, GhostPet):
                continue
            if pet.owner_id == hm.owner_id:
                continue
            px, py = self._get_pet_head(pet)
            dist = math.hypot(px - hm.x, py - hm.y)
            pet_r = self._get_pet_radius(pet)
            if dist < hm.radius + pet_r:
                ratio = 1.0 - (1.0 - min_ratio) * (dist / hm.radius)
                ratio = max(min_ratio, min(1.0, ratio))
                damage = hm.saved_speed * CENTER_MULT * ratio
                pet.take_damage(damage)

        for clone in self.clones:
            if clone.owner_id == hm.owner_id or not clone.alive:
                continue
            dist = math.hypot(clone.x - hm.x, clone.y - hm.y)
            if dist < hm.radius + clone.radius:
                clone.alive = False

    # ── Lightning spawning ───────────────────────────────────────────────────

    def try_use_lightning(self, player: Player):
        if not player.alive or player.skill_locked:
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
            # Apply self-debuffs during release（霸体免疫自减速）
            if player.unstoppable_timer <= 0:
                player._self_slowed = True
                player._self_saved_vx = player.vx
                player._self_saved_vy = player.vy
                player.slow_mult = ldef.self_speed_mult
                player.slow_timer = ldef.duration
            player.dmg_reduction = ldef.self_dmg_reduction
            player.dmg_reduction_timer = ldef.duration

    # ── Lightning trap spawning ─────────────────────────────────────────────

    def try_use_lightning_trap(self, player: Player):
        if not player.alive or player.skill_locked:
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
        if not player.alive or player.skill_locked:
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
            elif pdef.name == "幽灵":
                self.pets.append(
                    GhostPet(player.x, player.y, player.char.id, target, pdef)
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

    # ── Bomb spawning ──────────────────────────────────────────────────────

    def _throw_bomb(self, player: Player, bdef: BombDef):
        """执行投掷炸弹（方向、距离计算 + arena 边界钳制）。"""
        opponent = self.player1 if player is self.player2 else self.player2
        # 对手隐身/死亡时随机投掷
        if opponent.alive and not getattr(opponent, 'invisible', False):
            dx = opponent.x - player.x
            dy = opponent.y - player.y
            dist = math.hypot(dx, dy)
            if dist > 0:
                dx /= dist
                dy /= dist
            else:
                angle = random.uniform(0, 2 * math.pi)
                dx = math.cos(angle)
                dy = math.sin(angle)
            throw_dist = min(bdef.throw_distance, dist * 0.7)
        else:
            angle = random.uniform(0, 2 * math.pi)
            dx = math.cos(angle)
            dy = math.sin(angle)
            throw_dist = bdef.throw_distance

        target_x = player.x + dx * throw_dist
        target_y = player.y + dy * throw_dist

        # 确保落点在竞技场内
        arena_dx = target_x - CENTER[0]
        arena_dy = target_y - CENTER[1]
        arena_dist = math.hypot(arena_dx, arena_dy)
        if arena_dist > ARENA_RADIUS - bdef.explosion_radius - 5:
            limit = ARENA_RADIUS - bdef.explosion_radius - 5
            if arena_dist > 0:
                target_x = CENTER[0] + arena_dx / arena_dist * limit
                target_y = CENTER[1] + arena_dy / arena_dist * limit

        self.bombs.append(
            Bomb(player.x, player.y, target_x, target_y, player.char.id, bdef)
        )

    def try_use_bomb(self, player: Player):
        if not player.alive or player.skill_locked:
            return
        bdef = player.char.bomb_skill
        if bdef is not None and player.bomb_timer >= bdef.cooldown:
            player.bomb_timer = 0.0
            self._throw_bomb(player, bdef)

    def try_use_bomb2(self, player: Player):
        if not player.alive or player.skill_locked:
            return
        bdef = player.char.bomb_skill2
        if bdef is not None and player.bomb_timer2 >= bdef.cooldown:
            player.bomb_timer2 = 0.0
            self._throw_bomb(player, bdef)

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
        """Return (x, y) of a pet's head."""
        if isinstance(pet, GhostPet):
            return pet.x, pet.y
        if isinstance(pet, SpiderPet):
            return pet.x, pet.y
        return pet.segments[0]

    def _get_pet_radius(self, pet) -> float:
        """Return collision radius of a pet's head."""
        if isinstance(pet, GhostPet):
            return pet._head_radius()
        if isinstance(pet, SpiderPet):
            return pet._body_radius()
        return pet._head_radius()

    def _set_pet_pos(self, pet, x: float, y: float):
        """Set a pet's head position."""
        if isinstance(pet, GhostPet):
            pet.x = x
            pet.y = y
        elif isinstance(pet, SpiderPet):
            pet.x = x
            pet.y = y
        else:
            pet.segments[0] = (x, y)

    # ── Projectile collision detection (continued) ──────────────────────────
    def check_collisions(self):
        for proj in self.projectiles:
            # 穿透型剑气由 check_beam_collisions 单独处理
            if isinstance(proj, (CrescentBeam, VerticalBeam)):
                continue
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

    def check_beam_collisions(self):
        """穿透型剑气碰撞（不消失，每目标有独立冷却）。"""
        for proj in self.projectiles:
            if not isinstance(proj, (CrescentBeam, VerticalBeam)):
                continue
            if proj.owner_id != self.player1.char.id and self.player1.alive:
                if proj.collides_with(self.player1):
                    self.player1.take_damage(proj.skill.damage)
            if proj.owner_id != self.player2.char.id and self.player2.alive:
                if proj.collides_with(self.player2):
                    self.player2.take_damage(proj.skill.damage)

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
                    if player.unstoppable_timer <= 0:
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
                    if player.unstoppable_timer <= 0:
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
                    if isinstance(pet, GhostPet):
                        # 幽灵：伤害 + 恐惧印记 + 消失
                        player.take_damage(pet.defn.damage)
                        player.vx *= 1.5
                        player.vy *= 1.5
                        player._fear_mark_timers.append(8.0)
                        if len(player._fear_mark_timers) > 5:
                            player._fear_mark_timers.pop(0)
                            player.vx /= 1.2
                            player.vy /= 1.2
                        pet._spent = True
                    else:
                        player.take_damage(pet.defn.damage)
                        pet.hp = 0  # disappear after dealing damage

    def check_pet_pet_collisions(self):
        """Pets from different owners collide → both take damage + bounce apart."""
        for i, pet_a in enumerate(self.pets):
            for pet_b in self.pets[i + 1:]:
                if isinstance(pet_a, GhostPet) or isinstance(pet_b, GhostPet):
                    continue
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
                if isinstance(pet, GhostPet):
                    continue
                if proj.owner_id == pet.owner_id:
                    continue
                # 穿透型剑气：使用专用的碰撞检测
                if isinstance(proj, (CrescentBeam, VerticalBeam)):
                    head_x, head_y = pet.segments[0] if hasattr(pet, 'segments') else (pet.x, pet.y)
                    head_r = pet.defn.body_width // 2
                    # 构造一个临时 player-like 对象用于 collides_with
                    if self._beam_hits_pet(proj, head_x, head_y, head_r, str(id(pet))):
                        pet.take_damage(proj.skill.damage)
                    continue
                if pet.head_collides_with_circle(proj.x, proj.y, proj.skill.radius):
                    pet.take_damage(proj.skill.damage)
                    proj._hit = True

    def _beam_hits_pet(self, beam, px: float, py: float, pr: float, target_id: str) -> bool:
        """检查穿透型剑气是否命中宠物（复用 beam 的碰撞逻辑）。"""
        if isinstance(beam, CrescentBeam):
            dx = beam.x - px
            dy = beam.y - py
            if math.hypot(dx, dy) > beam.R + pr:
                return False
            bx, by = beam._circle_B_center()
            dbx = bx - px
            dby = by - py
            if math.hypot(dbx, dby) + pr <= beam.R:
                return False
        elif isinstance(beam, VerticalBeam):
            pdx = px - beam.x
            pdy = py - beam.y
            cos_a = math.cos(beam.angle)
            sin_a = math.sin(beam.angle)
            along = abs(pdx * cos_a + pdy * sin_a)
            perp = abs(-pdx * sin_a + pdy * cos_a)
            if along > beam.half_w + pr or perp > beam.half_len + pr:
                return False
        last = beam._hit_targets.get(target_id, -999.0)
        if beam.age - last < beam._hit_cd:
            return False
        beam._hit_targets[target_id] = beam.age
        return True

    def check_lightning_pet_collisions(self):
        """Lightning bolts from a player damage and slow opponent's pets."""
        for bolt in self.lightning_bolts:
            for pet in self.pets:
                if isinstance(pet, GhostPet):
                    continue
                if bolt.owner_id == pet.owner_id:
                    continue
                head_x, head_y = self._get_pet_head(pet)
                if bolt.collides_with_point(head_x, head_y, self._get_pet_radius(pet)):
                    pet.take_damage(bolt.defn.damage)
                    pet.slow_mult = bolt.defn.target_slow_mult
                    pet.slow_timer = bolt.defn.target_slow_duration

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
                if isinstance(pet, GhostPet):
                    continue
                if trap.owner_id == pet.owner_id:
                    continue
                if trap.collides_with_pet(pet):
                    trap.apply_shock(pet)

    def check_trail_pet_collisions(self):
        """Check if any pet touches the frost mage's trail (only frost has trail)."""
        threshold = PLAYER_RADIUS + 4
        for pet in self.pets:
            if isinstance(pet, GhostPet):
                continue
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
                if isinstance(other, GhostPet):
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
                    # 武器大师：近战命中递减使用次数
                    if weapon.owner.char.id == "weaponmaster":
                        weapon.owner.pickup_uses_left -= 1
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

    def _redirect_tracking_to_clone(self, clone):
        """将所有追踪忍者（clone.owner）的实体重定向到影分身。"""
        from weapon import HomingMissile
        owner = clone.owner
        # HomingMissile
        for proj in self.projectiles:
            if isinstance(proj, HomingMissile) and getattr(proj, '_target', None) is owner:
                proj._target = clone
        # 追踪型宠物
        for pet in self.pets:
            if getattr(pet, 'target', None) is owner:
                pet.target = clone

    def _restore_tracking_targets(self, clone):
        """分身消失后将追踪实体的目标恢复为原主人。"""
        from weapon import HomingMissile
        owner = clone.owner
        for proj in self.projectiles:
            if isinstance(proj, HomingMissile) and getattr(proj, '_target', None) is clone:
                proj._target = owner
        for pet in self.pets:
            if getattr(pet, 'target', None) is clone:
                pet.target = owner

    def check_clone_collisions(self):
        """影分身被任何非Projectile类的实体碰到后消失。"""
        from projectile import Projectile as ProjClass
        for clone in self.clones[:]:
            if not clone.alive:
                continue
            destroyed = False
            # 子弹/飞镖/追踪弹/回旋镖 (weapon.py 的投射物)
            for proj in self.projectiles:
                if isinstance(proj, ProjClass):
                    continue
                if getattr(proj, 'owner_id', None) == clone.owner_id:
                    continue
                # 穿透型剑气：摧毁影子但不消失
                if isinstance(proj, (CrescentBeam, VerticalBeam)):
                    if proj.collides_with_player_circle(clone.x, clone.y, clone.radius):
                        destroyed = True
                        break
                    continue
                pr = getattr(proj, 'radius', 5)
                if math.hypot(proj.x - clone.x, proj.y - clone.y) < clone.radius + pr:
                    proj._hit = True
                    destroyed = True
                    break
            if destroyed:
                clone.alive = False
                continue
            # 宠物
            for pet in self.pets:
                if pet.owner_id == clone.owner_id:
                    continue
                head_x, head_y = self._get_pet_head(pet)
                if math.hypot(head_x - clone.x, head_y - clone.y) < self._get_pet_radius(pet) + clone.radius:
                    destroyed = True
                    break
            if destroyed:
                clone.alive = False
                continue
            # 近战武器
            for weapon in self.weapons:
                if weapon.owner_id == clone.owner_id:
                    continue
                wt = weapon.defn.weapon_type
                if wt not in (WeaponType.SCYTHE, WeaponType.SHIELD, WeaponType.KATANA, WeaponType.DUAL_AXE, WeaponType.HOLY_SWORD):
                    continue
                if wt == WeaponType.DUAL_AXE:
                    if weapon._check_either_axe_hits(clone.x, clone.y, clone.radius):
                        destroyed = True
                        break
                else:
                    if math.hypot(weapon.x - clone.x, weapon.y - clone.y) < clone.radius + weapon.defn.length / 2:
                        destroyed = True
                        break
            if destroyed:
                clone.alive = False
                continue
            # 闪电
            for bolt in self.lightning_bolts:
                if bolt.owner_id == clone.owner_id:
                    continue
                if bolt.collides_with_point(clone.x, clone.y, clone.radius):
                    destroyed = True
                    break
            if destroyed:
                clone.alive = False

    def check_tree_collisions(self):
        """投射物/宠物/武器/闪电击中树 → 树掉血（长方形碰撞）。"""
        for tree in self.trees:
            for proj in self.projectiles:
                if getattr(proj, 'owner_id', None) == tree.owner_id:
                    continue
                pr = getattr(proj, 'radius', 5)
                if tree.collides_with_point(proj.x, proj.y, pr):
                    dmg = getattr(getattr(proj, 'skill', None), 'damage', 10)
                    tree.take_damage(dmg)
                    if hasattr(proj, '_hit'):
                        proj._hit = True
            for pet in self.pets:
                if isinstance(pet, GhostPet):
                    continue
                if pet.owner_id == tree.owner_id:
                    continue
                px, py = self._get_pet_head(pet)
                if tree.collides_with_point(px, py, self._get_pet_radius(pet)):
                    # 宠物弹开，不对树造成伤害
                    hit, nx, ny, overlap = tree._rect_vs_circle(px, py, self._get_pet_radius(pet))
                    if hit and hasattr(pet, 'segments') and pet.segments:
                        pet.segments[0] = (px + nx * overlap, py + ny * overlap)
            for weapon in self.weapons:
                if weapon.owner_id == tree.owner_id:
                    continue
                wt = weapon.defn.weapon_type
                if wt not in (WeaponType.SCYTHE, WeaponType.SHIELD, WeaponType.KATANA, WeaponType.DUAL_AXE, WeaponType.HOLY_SWORD):
                    continue
                wid = id(weapon)
                last_hit = tree._weapon_hit_times.get(wid, -999.0)
                if tree.age - last_hit < 0.5:  # 每武器每0.5s最多命中一次
                    continue
                hit = False
                if wt == WeaponType.KATANA:
                    hit = weapon._katana_slash_collides(tree.x, tree.y, tree.radius, id(tree))
                elif wt == WeaponType.DUAL_AXE:
                    hit = weapon._check_either_axe_hits(tree.x, tree.y, tree.radius)
                else:
                    hit = tree.collides_with_point(weapon.x, weapon.y, weapon.defn.length / 2)
                if hit:
                    tree.take_damage(weapon.defn.damage)
                    tree._weapon_hit_times[wid] = tree.age
            for bolt in self.lightning_bolts:
                if bolt.owner_id == tree.owner_id:
                    continue
                if bolt.collides_with_point(tree.x, tree.y, tree.radius):
                    tree.take_damage(bolt.defn.damage)

    def check_weapon_pet_collisions(self):
        """Melee weapons damage opponent's pets."""
        for weapon in self.weapons:
            for pet in self.pets:
                if isinstance(pet, GhostPet):
                    continue
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

    # ── Weapon pickup collision ─────────────────────────────────────────────

    def check_pickup_collisions(self):
        for pickup in self.weapon_pickups[:]:
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if player.char.id != "weaponmaster":
                    continue
                if pickup.collides_with(player):
                    # 移除旧拾取武器
                    self.weapons = [w for w in self.weapons if w.owner_id != player.char.id]
                    # 创建新武器
                    opponent = self.player1 if player is self.player2 else self.player2
                    new_weapon = Weapon(player, opponent, pickup.defn)
                    self.weapons.append(new_weapon)
                    # 设置拾取状态
                    player.pickup_uses_left = 2
                    player.pickup_timer = 0.0
                    # 删除图标
                    self.weapon_pickups.remove(pickup)
                    break

    # ── Katana projectile destruction ─────────────────────────────────────

    def check_katana_projectile_collisions(self):
        for weapon in self.weapons:
            if weapon.defn.weapon_type.value not in ("katana", "holy_sword"):
                continue
            if weapon._slash_state == "idle":
                continue
            for proj in self.projectiles:
                if getattr(proj, 'owner_id', None) == weapon.owner_id:
                    continue
                # 不抵消炸弹
                if hasattr(proj, 'state') and getattr(proj, 'defn', None) is not None:
                    continue
                if weapon.collides_with_projectile(proj):
                    proj._hit = True

    # ── Stuck shuriken collision ───────────────────────────────────────────

    def check_stuck_shuriken_collisions(self, dt):
        for proj in self.projectiles:
            if not isinstance(proj, ShurikenProjectile):
                continue
            if not proj._stuck:
                continue
            # 伤害玩家
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if player.char.id == proj.owner_id:
                    continue
                if proj.collides_with(player):
                    dmg = proj.try_stuck_damage(player, id(player), dt)
                    if dmg > 0:
                        player.take_damage(dmg)
            # 伤害宠物
            for pet in self.pets:
                if pet.owner_id == proj.owner_id:
                    continue
                pet_x, pet_y = self._get_pet_head(pet)
                pet_r = self._get_pet_radius(pet)
                dx = proj.x - pet_x
                dy = proj.y - pet_y
                if math.hypot(dx, dy) < pet_r + proj.radius:
                    dmg = proj.try_stuck_damage(pet, id(pet), dt)
                    if dmg > 0:
                        pet.take_damage(dmg)

    # ── Bomb explosion detection ────────────────────────────────────────────

    def check_bomb_explosions(self):
        for bomb in self.bombs:
            if bomb.state != "EXPLODED" or bomb._explosion_processed:
                continue
            bomb._explosion_processed = True

            # 伤害玩家
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if player.char.id == bomb.owner_id:
                    continue
                dist = math.hypot(player.x - bomb.target_x,
                                  player.y - bomb.target_y)
                eff_radius = bomb.defn.explosion_radius + player.radius
                if dist < eff_radius:
                    ratio = 1.0 - (1.0 - bomb.defn.min_damage_ratio) * (dist / bomb.defn.explosion_radius)
                    ratio = max(bomb.defn.min_damage_ratio, min(1.0, ratio))
                    player.take_damage(bomb.defn.damage * ratio)

            # 伤害宠物
            for pet in self.pets:
                if isinstance(pet, GhostPet):
                    continue
                if pet.owner_id == bomb.owner_id:
                    continue
                pet_x, pet_y = self._get_pet_head(pet)
                dist = math.hypot(pet_x - bomb.target_x,
                                  pet_y - bomb.target_y)
                head_r = self._get_pet_radius(pet)
                if dist < bomb.defn.explosion_radius + head_r:
                    ratio = 1.0 - (1.0 - bomb.defn.min_damage_ratio) * (dist / bomb.defn.explosion_radius)
                    ratio = max(bomb.defn.min_damage_ratio, min(1.0, ratio))
                    pet.take_damage(bomb.defn.damage * ratio)

            # 摧毁投射物
            for proj in self.projectiles:
                if getattr(proj, 'owner_id', None) == bomb.owner_id:
                    continue
                proj_skill = getattr(proj, 'skill', None)
                if proj_skill is not None:
                    proj_r = proj_skill.radius
                else:
                    proj_r = getattr(proj, 'radius', 5)
                dist = math.hypot(proj.x - bomb.target_x,
                                  proj.y - bomb.target_y)
                if dist < bomb.defn.explosion_radius + proj_r:
                    proj._hit = True

            # 伤害树
            for tree in self.trees:
                if tree.owner_id == bomb.owner_id:
                    continue
                dist = math.hypot(tree.x - bomb.target_x, tree.y - bomb.target_y)
                if dist < bomb.defn.explosion_radius + tree.radius:
                    ratio = 1.0 - (1.0 - bomb.defn.min_damage_ratio) * (dist / bomb.defn.explosion_radius)
                    ratio = max(bomb.defn.min_damage_ratio, min(1.0, ratio))
                    tree.take_damage(bomb.defn.damage * ratio)

            # ── 集束炸弹：母弹爆炸后分裂子炸弹 ──
            if bomb.defn.bomb_type.value == "cluster" and not bomb.is_child:
                count = bomb.defn.cluster_count
                spread_speed = bomb.defn.cluster_spread_speed
                spread_dist = bomb.defn.cluster_spread_distance
                child_radius = bomb.defn.cluster_child_radius
                child_damage = bomb.defn.cluster_child_damage

                # 构建子炸弹定义
                child_def = BombDef(
                    name=f"{bomb.defn.name}-子",
                    cooldown=0.0,
                    damage=child_damage,
                    color=bomb.defn.color,
                    bomb_radius=bomb.defn.bomb_radius * 0.6,
                    throw_speed=spread_speed,
                    throw_distance=spread_dist,
                    detonate_delay=0.15,
                    explosion_radius=child_radius,
                    explosion_color=bomb.defn.explosion_color,
                    min_damage_ratio=bomb.defn.min_damage_ratio,
                )

                for _ in range(count):
                    angle = random.uniform(0, 2 * math.pi)
                    child_tx = bomb.target_x + math.cos(angle) * spread_dist
                    child_ty = bomb.target_y + math.sin(angle) * spread_dist

                    # Arena clamp for child
                    arena_dx = child_tx - CENTER[0]
                    arena_dy = child_ty - CENTER[1]
                    arena_dist = math.hypot(arena_dx, arena_dy)
                    if arena_dist > ARENA_RADIUS - child_radius - 5:
                        limit = ARENA_RADIUS - child_radius - 5
                        if arena_dist > 0:
                            child_tx = CENTER[0] + arena_dx / arena_dist * limit
                            child_ty = CENTER[1] + arena_dy / arena_dist * limit

                    self.bombs.append(
                        Bomb(bomb.target_x, bomb.target_y, child_tx, child_ty,
                             bomb.owner_id, child_def, is_child=True)
                    )

            # ── 毒气弹：爆炸后生成持续毒雾 ──
            if bomb.defn.bomb_type.value == "gas":
                self.gas_clouds.append(
                    GasCloud(bomb.target_x, bomb.target_y, bomb.owner_id, bomb.defn)
                )

    # ── Gas cloud effects ───────────────────────────────────────────────────

    def check_gas_cloud_effects(self, dt):
        for cloud in self.gas_clouds:
            for player in (self.player1, self.player2):
                if not player.alive:
                    continue
                if player.char.id == cloud.owner_id:
                    continue
                if cloud.contains(player.x, player.y, player.radius):
                    player.take_damage(cloud.dps * dt)
                    if player.unstoppable_timer <= 0:
                        player.slow_mult = cloud.slow_mult
                        player.slow_timer = 0.15

            for pet in self.pets:
                if isinstance(pet, GhostPet):
                    continue
                if pet.owner_id == cloud.owner_id:
                    continue
                pet_x, pet_y = self._get_pet_head(pet)
                pet_r = self._get_pet_radius(pet)
                if cloud.contains(pet_x, pet_y, pet_r):
                    pet.take_damage(cloud.dps * dt)
                    pet.slow_mult = cloud.slow_mult
                    pet.slow_timer = 0.15

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
            if p.char.weapon_skill2 is not None:
                infos.append((f"{p.char.weapon_skill2.name} ({p.char.weapon_skill2.cooldown:.1f}s)", p.char.weapon_skill2.color))
            if p.char.bomb_skill is not None:
                infos.append((f"{p.char.bomb_skill.name} ({p.char.bomb_skill.cooldown:.1f}s)", p.char.bomb_skill.explosion_color))
            if p.char.bomb_skill2 is not None:
                infos.append((f"{p.char.bomb_skill2.name} ({p.char.bomb_skill2.cooldown:.1f}s)", p.char.bomb_skill2.explosion_color))
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
        self.weapon_pickups = []
        self.clones = []
        self.palms = []
        self.fist_traps = []
        self.vortexes = []
        self.waves = []
        self.hunt_marks = []
        self.trees = []
        self.leaf_blades = []
        self._wave_burst_remaining = 0
        self._pickup_spawn_timer = random.uniform(3.0, 6.0)
        self.bombs = []
        self.gas_clouds = []
        self.game_over = False
        self.winner = None

    def _find_nearest_pickup(self, player):
        """找到距离玩家最近的武器图标。"""
        best, best_dist = None, float('inf')
        for p in self.weapon_pickups:
            d = math.hypot(p.x - player.x, p.y - player.y)
            if d < best_dist:
                best_dist, best = d, p
        return best

    def _spawn_weapon_pickups(self, dt):
        self._pickup_spawn_timer -= dt
        if self._pickup_spawn_timer > 0:
            return
        self._pickup_spawn_timer = self._pickup_spawn_interval

        # 仅当武器大师上场时才生成武器图标
        wm_on_field = ((self.player1 and self.player1.char.id == "weaponmaster" and self.player1.alive)
                       or (self.player2 and self.player2.char.id == "weaponmaster" and self.player2.alive))
        if not wm_on_field:
            return

        if len(self.weapon_pickups) >= self._max_pickups:
            return

        from characters import (GATLING_GUN, SNIPER_RIFLE, HOMING_LAUNCHER,
                                GUARDIAN_SHIELD, SHARPSHOOTER_PISTOL,
                                POISON_SCYTHE, BOOMER_BOOMERANG,
                                NINJA_KATANA, NINJA_SHURIKEN,
                                HUNTER_BOW, HUNTER_CROSSBOW, DUAL_AXE)
        pool = [GATLING_GUN, SNIPER_RIFLE, HOMING_LAUNCHER,
                GUARDIAN_SHIELD, SHARPSHOOTER_PISTOL,
                POISON_SCYTHE, BOOMER_BOOMERANG,
                NINJA_KATANA, NINJA_SHURIKEN,
                HUNTER_BOW, HUNTER_CROSSBOW, DUAL_AXE]
        defn = random.choice(pool)

        angle = random.uniform(0, 2 * math.pi)
        r = random.uniform(0, ARENA_RADIUS - 60)
        px = CENTER[0] + math.cos(angle) * r
        py = CENTER[1] + math.sin(angle) * r

        self.weapon_pickups.append(WeaponPickup(px, py, defn))

    # ── Fighting update ────────────────────────────────────────────────────────
    def _update_fighting(self, dt):
        """单帧战斗逻辑更新（不含渲染），可供测试脚本复用。"""
        # Skill timers（技能锁期间暂停冷却）
        for p in (self.player1, self.player2):
            if p.skill_locked:
                continue
            p.skill_timer += dt
            p.skill2_timer += dt
            p.lightning_timer += dt
            p.lightning_trap_timer += dt
            p.pet_timer += dt
            p.bomb_timer += dt
            p.bomb_timer2 += dt

        self.try_use_skill(self.player1)
        self.try_use_skill(self.player2)
        self.try_use_skill2(self.player1)
        self.try_use_skill2(self.player2)
        self.try_use_lightning(self.player1)
        self.try_use_lightning(self.player2)
        self.try_use_lightning_trap(self.player1)
        self.try_use_lightning_trap(self.player2)
        self.try_use_pet(self.player1)
        self.try_use_pet(self.player2)
        self.try_use_bomb(self.player1)
        self.try_use_bomb(self.player2)
        self.try_use_bomb2(self.player1)
        self.try_use_bomb2(self.player2)

        # Spawn weapon pickups
        self._spawn_weapon_pickups(dt)

        # Apply weapon speed multipliers before movement
        for p in (self.player1, self.player2):
            p.weapon_speed_mult = 1.0
            for w in self.weapons:
                if w.owner == p:
                    p.weapon_speed_mult = min(p.weapon_speed_mult, w.defn.speed_mult)

        # Compute seek targets for weaponmaster when empty-handed
        seek = {id(self.player1): None, id(self.player2): None}
        for p in (self.player1, self.player2):
            if p.char.id == "weaponmaster" and p.pickup_uses_left <= 0 and p.alive:
                nearest = self._find_nearest_pickup(p)
                if nearest:
                    seek[id(p)] = (nearest.x, nearest.y)

        # Movement
        self.player1.update(self.arena, dt, seek_target=seek[id(self.player1)])
        self.player2.update(self.arena, dt, seek_target=seek[id(self.player2)])

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
                result = weapon.fire()
                if result is not None:
                    if isinstance(result, list):
                        self.projectiles.extend(result)
                        if weapon.owner.char.id == "weaponmaster":
                            weapon.owner.pickup_uses_left -= len(result)
                    else:
                        self.projectiles.append(result)
                        if weapon.owner.char.id == "weaponmaster":
                            weapon.owner.pickup_uses_left -= 1
        self.weapons = [w for w in self.weapons if not w.is_expired()]

        # 武器大师：检查拾取武器过期（次数用完 or 10秒）
        for p in (self.player1, self.player2):
            if p.char.id == "weaponmaster" and p.pickup_uses_left > 0:
                p.pickup_timer += dt
                if p.pickup_uses_left <= 0 or p.pickup_timer >= 10.0:
                    self.weapons = [w for w in self.weapons if w.owner_id != p.char.id]
                    p.pickup_uses_left = 0
                    p.pickup_timer = 0.0
        for bomb in self.bombs:
            bomb.update(dt)
        self.bombs = [b for b in self.bombs if not b.is_expired()]
        for clone in self.clones:
            clone.update(dt)
        # 每帧将所有追踪实体重定向到活跃分身
        for clone in self.clones:
            if clone.alive:
                self._redirect_tracking_to_clone(clone)
        # 克隆消失时恢复追踪目标
        expired_clones = [c for c in self.clones if c.is_expired()]
        for c in expired_clones:
            self._restore_tracking_targets(c)
        self.clones = [c for c in self.clones if not c.is_expired()]
        for palm in self.palms:
            palm.update(dt)
            if not palm._damage_done:
                for player in (self.player1, self.player2):
                    if not player.alive or player.char.id == palm.owner_id:
                        continue
                    if math.hypot(palm.x - player.x, palm.y - player.y) < palm.radius + player.radius:
                        player.take_damage(palm.skill.damage)
                for pet in self.pets:
                    if pet.owner_id == palm.owner_id:
                        continue
                    px, py = self._get_pet_head(pet)
                    if math.hypot(palm.x - px, palm.y - py) < palm.radius + self._get_pet_radius(pet):
                        pet.take_damage(palm.skill.damage)
                for clone in self.clones:
                    if clone.owner_id == palm.owner_id:
                        continue
                    if math.hypot(palm.x - clone.x, palm.y - clone.y) < palm.radius + clone.radius:
                        clone.alive = False
                palm._damage_done = True
        self.palms = [p for p in self.palms if not p.is_expired()]
        for ft in self.fist_traps:
            ft.update(dt)
            # 首帧砸落伤害
            if not ft._damage_done:
                for player in (self.player1, self.player2):
                    if not player.alive or player.char.id == ft.owner_id:
                        continue
                    if math.hypot(ft.x - player.x, ft.y - player.y) < ft.radius + player.radius:
                        player.take_damage(ft.skill.damage)
                for pet in self.pets:
                    if pet.owner_id == ft.owner_id:
                        continue
                    px, py = self._get_pet_head(pet)
                    if math.hypot(ft.x - px, ft.y - py) < ft.radius + self._get_pet_radius(pet):
                        pet.take_damage(ft.skill.damage)
                for clone in self.clones:
                    if clone.owner_id == ft.owner_id:
                        continue
                    if math.hypot(ft.x - clone.x, ft.y - clone.y) < ft.radius + clone.radius:
                        clone.alive = False
                ft._damage_done = True
        self.fist_traps = [f for f in self.fist_traps if not f.is_expired()]
        # 猎杀印记：更新 + 0.9s传送 + AOE伤害
        for hm in self.hunt_marks:
            hm.update(dt)
            if hm.age >= 0.9 and not hm._teleport_done:
                hm._teleport_done = True
                owner = (self.player1 if self.player1.char.id == hm.owner_id
                         else self.player2)
                if owner.alive:
                    owner.x = hm.x
                    owner.y = hm.y
                    owner.vx = math.cos(hm.saved_angle) * 5.0
                    owner.vy = math.sin(hm.saved_angle) * 5.0
                    owner._hunt_teleport_timer = 0.0
                if not hm._damage_done:
                    hm._damage_done = True
                    self._apply_hunt_mark_damage(hm)
        self.hunt_marks = [hm for hm in self.hunt_marks if not hm.is_expired()]
        # 生命之树：更新 + 治疗 + 碰撞弹开
        for tree in self.trees:
            tree.update(dt)
            for player in (self.player1, self.player2):
                if player.alive:
                    tree.try_heal(player, dt)
                    tree.bounce_player(player)
        self.trees = [t for t in self.trees if not t.is_expired()]
        # 叶刃风暴：重定向检测目标 + 更新 + 碰撞
        for lb in self.leaf_blades:
            # 影分身→瞄准分身；隐身→不瞄准
            if lb.opponent and lb.opponent.alive:
                for clone in self.clones:
                    if clone.owner_id == lb.opponent.char.id and clone.alive:
                        lb._detect_target = clone
                        break
                else:
                    lb._detect_target = lb.opponent
            else:
                lb._detect_target = None
            lb.update(dt)
            if lb.state == LeafBlade.FIRING and not lb._hit:
                for player in (self.player1, self.player2):
                    if not player.alive or player.char.id == lb.owner_id:
                        continue
                    if math.hypot(lb.x - player.x, lb.y - player.y) < lb.radius + player.radius:
                        player.take_damage(lb.damage)
                        lb._hit = True
                        break
                if not lb._hit:
                    for pet in self.pets:
                        if isinstance(pet, GhostPet):
                            continue
                        if pet.owner_id == lb.owner_id:
                            continue
                        px, py = self._get_pet_head(pet)
                        if math.hypot(lb.x - px, lb.y - py) < lb.radius + self._get_pet_radius(pet):
                            pet.take_damage(lb.damage)
                            lb._hit = True
                            break
            elif lb.state == LeafBlade.ORBIT:
                for player in (self.player1, self.player2):
                    if not player.alive or player.char.id == lb.owner_id:
                        continue
                    if math.hypot(lb.x - player.x, lb.y - player.y) < lb.radius + player.radius:
                        tid = id(player)
                        last = lb._orbit_hit_cooldown.get(tid, -999.0)
                        if lb.age - last >= 0.5:
                            player.take_damage(lb.damage)
                            lb._orbit_hit_cooldown[tid] = lb.age
                for pet in self.pets:
                    if isinstance(pet, GhostPet):
                        continue
                    if pet.owner_id == lb.owner_id:
                        continue
                    px, py = self._get_pet_head(pet)
                    if math.hypot(lb.x - px, lb.y - py) < lb.radius + self._get_pet_radius(pet):
                        tid = id(pet)
                        last = lb._orbit_hit_cooldown.get(tid, -999.0)
                        if lb.age - last >= 0.5:
                            pet.take_damage(lb.damage)
                            lb._orbit_hit_cooldown[tid] = lb.age
        self.leaf_blades = [lb for lb in self.leaf_blades if not lb.is_expired()]
        # 漩涡：更新 + 施加力 + 过期恢复
        expired_vortexes = []
        for v in self.vortexes:
            v.update(dt)
            if v.is_expired():
                expired_vortexes.append(v)
                continue
            for player in (self.player1, self.player2):
                if v.apply_to_player(player):
                    player.take_damage(v.skill.damage * dt)
            for pet in self.pets:
                if isinstance(pet, GhostPet):
                    continue
                if v.apply_to_pet(pet):
                    pet.take_damage(v.skill.damage * dt)
        for v in expired_vortexes:
            for player in (self.player1, self.player2):
                tid = id(player)
                if tid in v._captured:
                    player.vx = v._captured_vx.get(tid, player.vx)
                    player.vy = v._captured_vy.get(tid, player.vy)
                    player.skill_locked = False
            for pet in self.pets:
                tid = id(pet)
                if tid in v._captured:
                    if hasattr(pet, 'vx'):
                        pet.vx = v._captured_vx.get(tid, 0)
                        pet.vy = v._captured_vy.get(tid, 0)
        self.vortexes = [v for v in self.vortexes if not v.is_expired()]
        # 波纹：更新 + 碰撞 + 后续波次生成
        for wave in self.waves:
            wave.update(dt)
            if not wave.is_expired():
                for player in (self.player1, self.player2):
                    if wave.collides_with_player(player):
                        player.take_damage(wave.damage)
                        angle = math.atan2(player.y - wave.y, player.x - wave.x)
                        player.x += math.cos(angle) * wave.knockback
                        player.y += math.sin(angle) * wave.knockback
                for pet in self.pets:
                    if isinstance(pet, GhostPet):
                        continue
                    if wave.collides_with_pet(pet):
                        pet.take_damage(wave.damage)
                        px, py = self._get_pet_head(pet)
                        angle = math.atan2(py - wave.y, px - wave.x)
                        if hasattr(pet, 'segments') and pet.segments:
                            hx, hy = pet.segments[0]
                            pet.segments[0] = (hx + math.cos(angle) * wave.knockback,
                                               hy + math.sin(angle) * wave.knockback)
        self.waves = [w for w in self.waves if not w.is_expired()]
        # 波纹连发计时
        if self._wave_burst_remaining > 0 and self._wave_owner:
            self._wave_burst_timer -= dt
            if self._wave_burst_timer <= 0:
                owner = self._wave_owner
                opponent = self.player1 if owner is self.player2 else self.player2
                angle = math.atan2(opponent.y - owner.y, opponent.x - owner.x)
                self.waves.append(WaveEntity(owner.x, owner.y, angle, owner.char.id, owner.char.skill2))
                self._wave_burst_remaining -= 1
                if self._wave_burst_remaining > 0:
                    self._wave_burst_timer = 0.5
        for cloud in self.gas_clouds:
            cloud.update(dt)
        self.gas_clouds = [c for c in self.gas_clouds if not c.is_expired()]
        for pickup in self.weapon_pickups:
            pickup.update(dt)
        self.weapon_pickups = [p for p in self.weapon_pickups if not p.is_expired()]

        # Collisions
        self.check_collisions()
        self.check_beam_collisions()
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
        self.check_clone_collisions()
        self.check_tree_collisions()
        self.check_shield_projectile_collisions()
        self.check_katana_projectile_collisions()
        self.check_stuck_shuriken_collisions(dt)
        self.check_bomb_explosions()
        self.check_gas_cloud_effects(dt)
        self.check_pickup_collisions()

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

                # Draw shadow clones
                for clone in self.clones:
                    clone.draw(self.screen)

                for palm in self.palms:
                    palm.draw(self.screen)
                for ft in self.fist_traps:
                    ft.draw(self.screen)

                for v in self.vortexes:
                    v.draw(self.screen)

                for wave in self.waves:
                    wave.draw(self.screen)

                for hm in self.hunt_marks:
                    hm.draw(self.screen)

                for tree in self.trees:
                    tree.draw(self.screen)

                for lb in self.leaf_blades:
                    lb.draw(self.screen)

                for bomb in self.bombs:
                    bomb.draw(self.screen)

                for cloud in self.gas_clouds:
                    cloud.draw(self.screen)

                for proj in self.projectiles:
                    proj.draw(self.screen)

                # Draw weapon pickups on arena floor
                for pickup in self.weapon_pickups:
                    pickup.draw(self.screen)

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
