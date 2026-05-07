"""武器系统 —— 角色可装备的持久性武器（手枪发射子弹、镰刀绕身旋转）。"""

import math
import random
from dataclasses import dataclass, field
from enum import Enum

import pygame

from venue import ARENA_CENTER, ARENA_RADIUS
from projectile import CrescentBeam, VerticalBeam


class WeaponType(Enum):
    PISTOL = "pistol"
    SCYTHE = "scythe"
    SHIELD = "shield"
    BOOMERANG = "boomerang"
    SNIPER = "sniper"
    GATLING = "gatling"
    HOMING = "homing"
    SHURIKEN = "shuriken"
    KATANA = "katana"
    BOW = "bow"
    CROSSBOW = "crossbow"
    DUAL_AXE = "dual_axe"
    STAFF = "staff"
    HOLY_SWORD = "holy_sword"


@dataclass
class WeaponDef:
    """定义武器的完整属性，覆盖手枪和镰刀两种类型。"""

    name: str                              # 武器名称
    cooldown: float                        # 手枪：射击间隔 / 镰刀：命中冷却
    damage: float                          # 单次伤害
    color: tuple[int, int, int]            # 武器绘制颜色
    weapon_type: WeaponType                # 武器类型判别

    width: int = 4                         # 视觉线宽 / 刀刃厚度
    length: int = 30                       # 手枪枪管视觉长度 / 镰刀碰撞半径

    # 手枪专用
    bullet_speed: float = 0.0              # 子弹速度 (px/s)
    bullet_radius: int = 0                 # 子弹碰撞半径
    bullet_lifetime: float = 0.0           # 子弹存留时间（秒）
    bullet_color: tuple[int, int, int] | None = None  # 子弹颜色，None 则用 weapon.color

    # 镰刀 / 盾牌 / 回旋镖待机 专用
    orbit_radius: float = 0.0              # 环绕半径
    orbit_speed: float = 0.0               # 环绕角速度 (rad/s)

    # 回旋镖专用
    throw_range: float = 0.0               # 最大飞行距离（像素），飞出该距离后折返

    # 加特林 / 追踪弹专用
    bullet_spread: float = 0.0             # 子弹散布角（弧度）
    tracking_turn_rate: float = 0.0        # 追踪弹转向速率 (rad/s)

    # 连弩连射
    burst_count: int = 0                   # 每轮连射数量
    burst_interval: float = 0.0            # 连射间隔
    burst_cooldown: float = 0.0            # 连射完成后的额外冷却

    # 持有武器时玩家速度倍率
    speed_mult: float = 1.0


# ── SkillProxy: 让 Bullet 可以 duck-type 进 self.projectiles ──────────────────

class _SkillProxy:
    """最小命名空间，满足 check_collisions 对 proj.skill.damage / proj.skill.radius 的访问。"""
    __slots__ = ('damage', 'radius')

    def __init__(self, damage: float, radius: int):
        self.damage = damage
        self.radius = radius


# ── Bullet ─────────────────────────────────────────────────────────────────────

class Bullet:
    """手枪发射的瞬态子弹，可被 self.projectiles 的更新/过期/碰撞流程统一管理。"""

    def __init__(self, x: float, y: float, target_x: float, target_y: float,
                 owner_id: str, defn: WeaponDef, owner_team: int = 0):
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.defn = defn
        self.owner_team = owner_team
        self.age = 0.0
        self.radius = defn.bullet_radius
        self.color = defn.bullet_color if defn.bullet_color is not None else defn.color
        self.lifetime = defn.bullet_lifetime
        self.skill = _SkillProxy(defn.damage, defn.bullet_radius)
        self._hit = False  # 命中后立即消失

        dx = target_x - x
        dy = target_y - y
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            self.vx = dx / dist * defn.bullet_speed
            self.vy = dy / dist * defn.bullet_speed
        else:
            angle = random.uniform(0, 2 * math.pi)
            self.vx = math.cos(angle) * defn.bullet_speed
            self.vy = math.sin(angle) * defn.bullet_speed

    def update(self, dt: float):
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Expire if beyond arena boundary
        dx = self.x - ARENA_CENTER[0]
        dy = self.y - ARENA_CENTER[1]
        if math.hypot(dx, dy) > ARENA_RADIUS:
            self.age = self.lifetime  # force expire next frame

    def is_expired(self) -> bool:
        return self.age >= self.lifetime or self._hit

    def collides_with(self, player) -> bool:
        """圆-圆碰撞检测。"""
        dx = self.x - player.x
        dy = self.y - player.y
        return math.hypot(dx, dy) < player.radius + self.radius

    def draw(self, screen):
        angle = math.atan2(self.vy, self.vx)

        # 箭/弩箭：细长杆 + 箭头 + 尾羽
        if self.defn.weapon_type in (WeaponType.BOW, WeaponType.CROSSBOW):
            self._draw_arrow(screen, angle)
            return

        # 子弹形状
        bullet_len = 22
        bullet_w = 7

        surf = pygame.Surface((bullet_len + 8, bullet_w + 8), pygame.SRCALPHA)
        cx = (bullet_len + 8) // 2
        cy = (bullet_w + 8) // 2
        half_l = bullet_len / 2
        hw = bullet_w / 2

        # 弹头 (尖锥) — 前半段，深灰
        tip_pts = [
            (cx + half_l, cy),
            (cx + half_l * 0.15, cy - hw),
            (cx + half_l * 0.15, cy + hw),
        ]
        pygame.draw.polygon(surf, (80, 80, 85), tip_pts)

        # 弹壳 (圆柱) — 后半段，铜色
        case_rect = pygame.Rect(cx - half_l * 0.6, cy - hw, half_l * 0.75, bullet_w)
        pygame.draw.rect(surf, (180, 140, 60), case_rect)
        # 弹壳高光
        pygame.draw.rect(surf, (210, 170, 80), case_rect, 1)

        # 底缘 (略宽)
        rim_rect = pygame.Rect(cx - half_l * 0.65, cy - hw - 1, half_l * 0.08, bullet_w + 2)
        pygame.draw.rect(surf, (140, 110, 50), rim_rect)

        # 旋转并对齐到飞行方向
        rotated = pygame.transform.rotate(surf, -math.degrees(angle))
        screen.blit(rotated, (int(self.x) - rotated.get_width() // 2,
                              int(self.y) - rotated.get_height() // 2))

    def _draw_arrow(self, screen, angle):
        """绘制箭/弩箭：细长杆 + 箭头 + 尾羽。"""
        shaft_len = 28
        shaft_w = 2
        head_len = 8
        feather_len = 7

        surf_w = shaft_len + head_len + feather_len + 8
        surf_h = 14
        surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
        cx = surf_w // 2
        cy = surf_h // 2

        # 箭杆（细长木色）
        shaft_start = cx - shaft_len // 2
        shaft_rect = pygame.Rect(shaft_start, cy - shaft_w // 2, shaft_len, shaft_w)
        pygame.draw.rect(surf, (160, 130, 80), shaft_rect)

        # 箭头（金属三角）
        tip_pts = [
            (shaft_start + shaft_len, cy),
            (shaft_start + shaft_len - head_len, cy - 3),
            (shaft_start + shaft_len - head_len, cy + 3),
        ]
        pygame.draw.polygon(surf, (120, 120, 130), tip_pts)
        pygame.draw.polygon(surf, (80, 80, 90), tip_pts, 1)

        # 尾羽（fletching）
        for side in (-1, 1):
            feather_pts = [
                (shaft_start, cy + shaft_w * side),
                (shaft_start - feather_len, cy + 4 * side),
                (shaft_start - feather_len * 0.5, cy + shaft_w * side),
            ]
            color = (200, 50, 30)  # 红色尾羽
            pygame.draw.polygon(surf, color, feather_pts)

        # 旋转并对齐到飞行方向
        rotated = pygame.transform.rotate(surf, -math.degrees(angle))
        screen.blit(rotated, (int(self.x) - rotated.get_width() // 2,
                              int(self.y) - rotated.get_height() // 2))


# ── HomingMissile ─────────────────────────────────────────────────────────────

class HomingMissile:
    """追踪导弹 —— 发射后持续转向目标，带尾焰粒子。"""

    def __init__(self, x: float, y: float, owner, opponent, defn, owner_team: int = 0):
        self.x = x
        self.y = y
        self.owner = owner
        self.owner_id = owner.char.id
        self.owner_team = owner_team
        self._target = opponent
        self.defn = defn
        self.skill = _SkillProxy(defn.damage, defn.bullet_radius)
        self.radius = defn.bullet_radius
        self.lifetime = defn.bullet_lifetime
        self.age = 0.0
        self._hit = False
        self._trail: list[tuple[float, float]] = []
        self._flame_seeds = [random.uniform(0, 100) for _ in range(10)]
        self._smoke_seeds = [random.uniform(0, 100) for _ in range(5)]

        if opponent is not None and opponent.alive:
            angle = math.atan2(opponent.y - y, opponent.x - x)
        else:
            angle = random.uniform(0, 2 * math.pi)
        self.vx = math.cos(angle) * defn.bullet_speed
        self.vy = math.sin(angle) * defn.bullet_speed
        self._heading = angle

    def update(self, dt: float):
        self.age += dt

        # 转向目标（目标隐身时保持直飞）
        if (self._target is not None and self._target.alive
                and not getattr(self._target, 'invisible', False)):
            target_angle = math.atan2(self._target.y - self.y, self._target.x - self.x)
            angle_diff = (target_angle - self._heading + math.pi) % (2 * math.pi) - math.pi
            max_turn = self.defn.tracking_turn_rate * dt
            angle_diff = max(-max_turn, min(max_turn, angle_diff))
            self._heading += angle_diff

        self.vx = math.cos(self._heading) * self.defn.bullet_speed
        self.vy = math.sin(self._heading) * self.defn.bullet_speed

        self.x += self.vx * dt
        self.y += self.vy * dt

        # 尾迹
        self._trail.append((self.x, self.y))
        if len(self._trail) > 30:
            self._trail.pop(0)

        # 竞技场边界反弹
        dx = self.x - ARENA_CENTER[0]
        dy = self.y - ARENA_CENTER[1]
        dist = math.hypot(dx, dy)
        if dist > ARENA_RADIUS - self.radius:
            nx = dx / dist
            ny = dy / dist
            dot = self.vx * nx + self.vy * ny
            self.vx -= 2 * dot * nx
            self.vy -= 2 * dot * ny
            self._heading = math.atan2(self.vy, self.vx)
            self.x = ARENA_CENTER[0] + nx * (ARENA_RADIUS - self.radius)
            self.y = ARENA_CENTER[1] + ny * (ARENA_RADIUS - self.radius)

    def is_expired(self) -> bool:
        return self._hit or self.age >= self.lifetime

    def collides_with(self, player) -> bool:
        dx = self.x - player.x
        dy = self.y - player.y
        return math.hypot(dx, dy) < player.radius + self.radius

    def draw(self, screen):
        now = pygame.time.get_ticks() / 1000.0
        heading_deg = -math.degrees(self._heading)

        # ── 1. 烟雾尾迹（先绘制，在导弹后面） ──
        for i, seed in enumerate(self._smoke_seeds):
            t = (self.age * 3.5 + seed * 1.7) % 1.0
            offset = 8 + t * 28
            spread = (seed - 0.5) * 14 * (1.0 - t)
            sx = self.x - math.cos(self._heading) * offset + math.sin(self._heading) * spread
            sy = self.y - math.sin(self._heading) * offset - math.cos(self._heading) * spread
            alpha = int(60 * (1.0 - t) * (1.0 - t))
            size = int(2 + 6 * (1.0 - t))
            if alpha > 0 and size > 0:
                smoke_surf = pygame.Surface((size * 2 + 2, size * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(smoke_surf, (100, 100, 105, alpha), (size + 1, size + 1), size)
                screen.blit(smoke_surf, (int(sx) - size - 1, int(sy) - size - 1))

        # ── 2. 火焰尾迹 ──
        flame_len = 28
        for i, seed in enumerate(self._flame_seeds):
            t = (self.age * 10 + seed * 2.3) % 1.0
            offset = t * flame_len
            perp = (seed - 0.5) * 7 * (1.0 - t * 0.5)
            fx = self.x - math.cos(self._heading) * (offset + 2) + math.sin(self._heading) * perp
            fy = self.y - math.sin(self._heading) * (offset + 2) - math.cos(self._heading) * perp

            alpha = int(220 * (1.0 - t))
            size = max(1, int(3.5 * (1.0 - t * 0.5)))

            # 内焰（白/黄）→ 外焰（橙/红）
            if t < 0.25:
                color = (255, 255, 200, alpha)  # 白热核心
            elif t < 0.55:
                color = (255, 180 + int(t * 50), 20, alpha)  # 橙黄
            else:
                color = (220, 70 + int(t * 40), 10, alpha // 2)  # 暗红
            if isinstance(color, tuple) and len(color) == 4:
                flame_surf = pygame.Surface((size * 2 + 2, size * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(flame_surf, color, (size + 1, size + 1), size)
                screen.blit(flame_surf, (int(fx) - size - 1, int(fy) - size - 1))

        # ── 3. 导弹体（逼真外形） ──
        body_len = 32
        body_w = 12
        pad = 14
        surf = pygame.Surface((body_len + pad * 2, body_w + pad * 2), pygame.SRCALPHA)
        bcx = body_len // 2 + pad
        bcy = body_w // 2 + pad
        hl = body_len / 2
        hw = body_w / 2

        # 弹体圆柱（军绿色金属）
        body_color = (70, 90, 70)
        body_rect = pygame.Rect(bcx - hl * 0.35, bcy - hw + 1, hl * 0.85, body_w - 2)
        pygame.draw.rect(surf, body_color, body_rect, border_radius=3)
        # 弹体高光条
        highlight_rect = pygame.Rect(bcx - hl * 0.3, bcy - hw + 2, hl * 0.75, body_w // 3)
        pygame.draw.rect(surf, (100, 125, 100), highlight_rect, border_radius=2)

        # 弹头锥（深灰尖锥，更长更锐）
        nose_len = hl * 0.7
        nose_pts = [
            (bcx + hl, bcy),                                    # 尖端
            (bcx + hl - nose_len, bcy - hw + 1),                # 右上
            (bcx + hl - nose_len, bcy + hw - 1),                # 右下
        ]
        pygame.draw.polygon(surf, (55, 55, 60), nose_pts)
        # 弹头高光
        nose_hl = [
            (bcx + hl - 2, bcy),
            (bcx + hl - nose_len + 2, bcy - hw + 3),
            (bcx + hl - nose_len + 2, bcy + 1),
        ]
        pygame.draw.polygon(surf, (90, 90, 95), nose_hl)

        # 弹头红带（导弹头锥后部的红色条纹）
        band_x = bcx + hl - nose_len + 3
        band_w = 4
        pygame.draw.rect(surf, (180, 40, 30),
                        pygame.Rect(band_x, bcy - hw + 1, band_w, body_w - 2))

        # 尾喷口（深色）
        nozzle_w = body_w * 0.7
        nozzle_rect = pygame.Rect(bcx - hl * 0.4, bcy - nozzle_w / 2, hl * 0.08, nozzle_w)
        pygame.draw.rect(surf, (35, 35, 40), nozzle_rect)

        # 尾翼 (4片，上下左右)
        fin_color = (50, 55, 50)
        fin_hl_color = (80, 85, 80)
        fin_root = bcx - hl * 0.25
        fin_tip = bcx - hl * 0.55
        fin_width = 7
        for side_sign in (-1, 1):
            for axis in (0, 1):  # 0=上下, 1=左右
                if axis == 0:
                    px, py = 0, hw * side_sign
                    px_tip, py_tip = 0, (hw + fin_width) * side_sign
                else:
                    px, py = hw * side_sign, 0
                    px_tip, py_tip = (hw + fin_width) * side_sign, 0
                fin_pts = [
                    (fin_root + px, bcy + py),
                    (fin_tip + px_tip, bcy + py_tip),
                    (fin_root - 4 + px, bcy + py),
                ]
                pygame.draw.polygon(surf, fin_color, fin_pts)
                # 尾翼细边框
                pygame.draw.polygon(surf, fin_hl_color, fin_pts, 1)

        # 旋转并对齐到飞行方向
        rotated = pygame.transform.rotate(surf, heading_deg)
        screen.blit(rotated, (int(self.x) - rotated.get_width() // 2,
                              int(self.y) - rotated.get_height() // 2))


# ── ShurikenProjectile ─────────────────────────────────────────────────────

class ShurikenProjectile:
    """忍者飞镖：直线飞行 → 命中目标造成伤害消失 / 未命中卡在竞技场边界10秒成陷阱。"""

    def __init__(self, x: float, y: float, target_x: float, target_y: float,
                 owner_id: str, defn: WeaponDef, owner_team: int = 0):
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.defn = defn
        self.owner_team = owner_team
        self.skill = _SkillProxy(defn.damage, defn.bullet_radius)
        self.radius = defn.bullet_radius
        self.age = 0.0
        self._hit = False
        self._spin = random.uniform(0, 6.28318)

        dx = target_x - x
        dy = target_y - y
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            self.vx = dx / dist * defn.bullet_speed
            self.vy = dy / dist * defn.bullet_speed
        else:
            angle = random.uniform(0, 2 * math.pi)
            self.vx = math.cos(angle) * defn.bullet_speed
            self.vy = math.sin(angle) * defn.bullet_speed

        # 卡墙状态
        self._stuck = False
        self._stuck_x = 0.0
        self._stuck_y = 0.0
        self._stuck_timer = 10.0
        self._hit_targets: dict[int, float] = {}

    def update(self, dt: float):
        self.age += dt
        if not self._stuck:
            self._spin += 4.0 * dt  # 慢速旋转

        if self._stuck:
            self._stuck_timer -= dt
            return

        self.x += self.vx * dt
        self.y += self.vy * dt

        # 检查竞技场边界碰撞 → 卡墙
        dx = self.x - ARENA_CENTER[0]
        dy = self.y - ARENA_CENTER[1]
        dist = math.hypot(dx, dy)
        if dist > ARENA_RADIUS - self.radius:
            nx = dx / dist
            ny = dy / dist
            self._stuck = True
            self._stuck_x = ARENA_CENTER[0] + nx * (ARENA_RADIUS - self.radius)
            self._stuck_y = ARENA_CENTER[1] + ny * (ARENA_RADIUS - self.radius)
            self.x = self._stuck_x
            self.y = self._stuck_y

    def is_expired(self) -> bool:
        if self._hit:
            return True
        if self._stuck:
            return self._stuck_timer <= 0
        # 飞行中超出边界但未卡墙（安全网）
        dx = self.x - ARENA_CENTER[0]
        dy = self.y - ARENA_CENTER[1]
        return math.hypot(dx, dy) > ARENA_RADIUS + 20 or self.age > 8.0

    def collides_with(self, player) -> bool:
        px = self._stuck_x if self._stuck else self.x
        py = self._stuck_y if self._stuck else self.y
        dx = px - player.x
        dy = py - player.y
        return math.hypot(dx, dy) < player.radius + self.radius

    def try_stuck_damage(self, target, target_id: int, dt: float) -> float:
        """卡墙状态对目标造成伤害。返回实际造成的伤害值。"""
        if not self._stuck:
            return 0.0
        last = self._hit_targets.get(target_id, -999.0)
        if self.age - last < 0.3:
            return 0.0
        self._hit_targets[target_id] = self.age
        return 1.5

    def draw(self, screen):
        px = self._stuck_x if self._stuck else self.x
        py = self._stuck_y if self._stuck else self.y

        if self._stuck:
            # 卡墙警示脉冲圈
            now = pygame.time.get_ticks() / 1000.0
            pulse = (math.sin(now * 4.0) + 1.0) / 2.0
            glow_alpha = int(20 + pulse * 40)
            glow_r = int(self.radius + 6 + pulse * 4)
            glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 60, 40, glow_alpha),
                             (glow_r + 2, glow_r + 2), glow_r)
            screen.blit(glow_surf, (int(px) - glow_r - 2, int(py) - glow_r - 2))

        # 真实飞镖：4片弧形弯刃 + 中心环
        r = self.radius + 4
        inner_r = self.radius // 2
        surf_size = int(r * 2 + 12)
        surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        cx = cy = surf_size // 2

        blade_color = (130, 135, 145)
        blade_edge = (80, 85, 95)

        for i in range(4):
            base_angle = self._spin + i * math.pi / 2
            # 每片刀刃：从中心环向外延伸，一侧直、一侧弯
            tip_x = cx + math.cos(base_angle) * r
            tip_y = cy + math.sin(base_angle) * r

            # 刀刃的两个侧边（弧形）
            mid_angle = base_angle + 0.35
            mid_x = cx + math.cos(mid_angle) * r * 0.65
            mid_y = cy + math.sin(mid_angle) * r * 0.65

            mid_angle2 = base_angle - 0.35
            mid_x2 = cx + math.cos(mid_angle2) * r * 0.65
            mid_y2 = cy + math.sin(mid_angle2) * r * 0.65

            inner_base1 = cx + math.cos(base_angle + 0.45) * inner_r
            inner_base1_y = cy + math.sin(base_angle + 0.45) * inner_r
            inner_base2 = cx + math.cos(base_angle - 0.45) * inner_r
            inner_base2_y = cy + math.sin(base_angle - 0.45) * inner_r

            blade_pts = [
                (inner_base1, inner_base1_y),
                (mid_x, mid_y),
                (tip_x, tip_y),
                (mid_x2, mid_y2),
                (inner_base2, inner_base2_y),
            ]
            pygame.draw.polygon(surf, blade_color, blade_pts)
            pygame.draw.polygon(surf, blade_edge, blade_pts, 1)

        # 中心环（深色金属）
        pygame.draw.circle(surf, (70, 75, 85), (cx, cy), inner_r + 1)
        pygame.draw.circle(surf, (50, 55, 65), (cx, cy), inner_r + 1, 1)
        # 中心孔
        pygame.draw.circle(surf, (30, 30, 35), (cx, cy), max(2, inner_r // 2))

        screen.blit(surf, (int(px) - surf_size // 2, int(py) - surf_size // 2))


# ── BoomerangProjectile ──────────────────────────────────────────────────────────

class BoomerangProjectile:
    """回旋镖飞行实体：向外飞出，到达最大射程后折返飞回主人。"""

    def __init__(self, x: float, y: float, owner, opponent, defn, owner_team: int = 0):
        self.x = x
        self.y = y
        self.owner = owner
        self.owner_id = owner.char.id
        self.owner_team = owner_team
        self.defn = defn
        self.skill = _SkillProxy(defn.damage, defn.length // 2)
        self.radius = defn.length // 2
        self.age = 0.0
        self._hit = False

        # 飞行方向：指向对手
        if opponent is not None and opponent.alive:
            dx = opponent.x - x
            dy = opponent.y - y
        else:
            angle = random.uniform(0, 2 * math.pi)
            dx = math.cos(angle)
            dy = math.sin(angle)
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            self.vx = dx / dist * defn.bullet_speed
            self.vy = dy / dist * defn.bullet_speed
        else:
            angle = random.uniform(0, 2 * math.pi)
            self.vx = math.cos(angle) * defn.bullet_speed
            self.vy = math.sin(angle) * defn.bullet_speed

        self._origin = (x, y)
        self._returning = False
        self._spin_angle = 0.0

    def update(self, dt: float):
        self.age += dt
        self._spin_angle += 20.0 * dt  # 高速自转用于视觉效果

        if not self._returning:
            # 向外飞行
            self.x += self.vx * dt
            self.y += self.vy * dt
            # 轻微弧形：施加垂直加速度
            speed = math.hypot(self.vx, self.vy)
            if speed > 0.001:
                perp_x = -self.vy / speed
                perp_y = self.vx / speed
                curve = 80.0  # 弯曲力度
                self.vx += perp_x * curve * dt
                self.vy += perp_y * curve * dt
                # 保持速度恒定
                spd = math.hypot(self.vx, self.vy)
                if spd > 0.001:
                    self.vx = self.vx / spd * self.defn.bullet_speed
                    self.vy = self.vy / spd * self.defn.bullet_speed
            # 检查是否超过最大射程
            dx = self.x - self._origin[0]
            dy = self.y - self._origin[1]
            if math.hypot(dx, dy) >= self.defn.throw_range:
                self._returning = True
        else:
            # 飞回主人
            ox, oy = self.owner.x, self.owner.y
            dx = ox - self.x
            dy = oy - self.y
            dist = math.hypot(dx, dy)
            if dist < self.owner.radius + 15:
                self._hit = True  # 被抓取，消失
                return
            if dist > 0.001:
                target_vx = dx / dist * self.defn.bullet_speed
                target_vy = dy / dist * self.defn.bullet_speed
                lerp = 3.0 * dt
                self.vx += (target_vx - self.vx) * lerp
                self.vy += (target_vy - self.vy) * lerp
            self.x += self.vx * dt
            self.y += self.vy * dt

        # 竞技场边界反弹
        dx = self.x - ARENA_CENTER[0]
        dy = self.y - ARENA_CENTER[1]
        dist = math.hypot(dx, dy)
        if dist > ARENA_RADIUS - self.radius:
            nx = dx / dist
            ny = dy / dist
            dot = self.vx * nx + self.vy * ny
            self.vx -= 2 * dot * nx
            self.vy -= 2 * dot * ny
            self.x = ARENA_CENTER[0] + nx * (ARENA_RADIUS - self.radius)
            self.y = ARENA_CENTER[1] + ny * (ARENA_RADIUS - self.radius)

    def is_expired(self) -> bool:
        return self._hit

    def collides_with(self, player) -> bool:
        dx = self.x - player.x
        dy = self.y - player.y
        return math.hypot(dx, dy) < player.radius + self.radius

    def draw(self, screen):
        """绘制旋转的 V 形回旋镖。"""
        length = self.defn.length
        wing_half = length * 0.55
        arm_len = length * 0.7

        # 构建回旋镖形状表面
        surf_size = length * 2 + 4
        surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        cx = cy = surf_size // 2

        # V 形两个翼
        angle_a = self._spin_angle
        angle_b = self._spin_angle + math.radians(120)

        pts = [(cx, cy)]
        for wing_angle in (angle_a, angle_b):
            for frac in (0.2, 0.6, 1.0):
                u = math.cos(wing_angle) * arm_len * frac
                v = math.sin(wing_angle) * arm_len * frac
                # 翼宽偏移
                perp = wing_angle + math.pi / 2
                offset = (0.5 - abs(frac - 0.5)) * wing_half
                px = cx + u + math.cos(perp) * offset
                py = cy + v + math.sin(perp) * offset
                pts.append((px, py))
            for frac in (1.0, 0.6, 0.2):
                u = math.cos(wing_angle) * arm_len * frac
                v = math.sin(wing_angle) * arm_len * frac
                perp = wing_angle - math.pi / 2
                offset = (0.5 - abs(frac - 0.5)) * wing_half
                px = cx + u + math.cos(perp) * offset
                py = cy + v + math.sin(perp) * offset
                pts.append((px, py))

        if len(pts) > 2:
            pygame.draw.polygon(surf, self.defn.color, pts)
            pygame.draw.polygon(surf, (100, 60, 20), pts, 2)

        # 绘制
        ix, iy = int(self.x), int(self.y)
        screen.blit(surf, (ix - surf_size // 2, iy - surf_size // 2))


# ── Weapon ─────────────────────────────────────────────────────────────────────

class Weapon:
    """持久武器实体，附着于角色，根据 weapon_type 表现不同行为。"""

    def __init__(self, owner, opponent, defn: WeaponDef, owner_team: int = 0):
        self.owner = owner              # Player 引用
        self.opponent = opponent        # Player 引用（手枪瞄准目标）
        self.defn = defn
        self.owner_id = owner.char.id
        self.owner_team = owner_team
        self.age = 0.0
        self.x = owner.x
        self.y = owner.y

        # 手枪 / 回旋镖冷却
        self.fire_timer = 0.0

        # 轨道运动（镰刀 / 盾牌 / 回旋镖待机）
        self._orbit_angle = random.uniform(0, 2 * math.pi)

        # 命中冷却（镰刀 / 盾牌）
        self._last_hit_times: dict[str, float] = {}  # target_id → last hit age

        # 盾牌击退标记
        self._knockback_target = None

        # 回旋镖 / 追踪弹：当前飞行中的实体引用
        self._active_boomerang = None
        self._active_missile = None

        # 加特林过热机制
        self._gatling_shots = 0
        self._gatling_overheat = 0.0

        # 瞄准角度（对手隐身时冻结）
        self._last_aim_angle = 0.0
        # 连弩连射状态
        self._burst_remaining = 0
        self._burst_timer = 0.0
        self._burst_cooldown_remaining = 0.0
        # 法杖速度触发冷却
        self._staff_speed_cd = 0.0
        # 武士刀斩击状态
        self._slash_state = "idle"     # idle | slash1 | slash2
        self._slash_timer = 0.0
        self._slash_angle = 0.0
        self._slash_hit_done: set[int] = set()  # 本次斩击已命中目标id

        # 双战斧状态 —— 单一主相位驱动左右斧顺序挥砍
        self._axe_master_phase = 0.0
        self._axe_hit_targets: dict[str, float] = {}  # target_id → last hit age

        # 圣剑状态
        self._holy_charge_phase = "idle"   # idle | charging
        self._holy_charge_timer = 0.0      # idle时往上计数到18s
        self._holy_firing_charged = False  # True = 本次fire()释放三段竖剑气
        self._slash_beam_fired = False     # 当前斩击是否已释放剑气
        self._beam_ready = False           # 剑气就绪，should_fire返回True
        self._slash_duration = 1.0         # 当前斩击总时长（普通1.0s / 蓄力2.0s）
        self._saved_vx = 0.0              # 蓄力前保存的速度
        self._saved_vy = 0.0

    # ── Update ─────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        self.age += dt

        if self.defn.weapon_type in (WeaponType.PISTOL, WeaponType.SNIPER,
                                       WeaponType.GATLING, WeaponType.BOW,
                                       WeaponType.CROSSBOW, WeaponType.STAFF):
            self.fire_timer += dt
            if self.defn.weapon_type == WeaponType.GATLING and self._gatling_overheat > 0:
                self._gatling_overheat = max(0.0, self._gatling_overheat - dt)
            if self.defn.weapon_type == WeaponType.CROSSBOW:
                if self._burst_cooldown_remaining > 0:
                    self._burst_cooldown_remaining = max(0.0, self._burst_cooldown_remaining - dt)
                if self._burst_remaining > 0:
                    self._burst_timer += dt
            if self.defn.weapon_type == WeaponType.STAFF and self._staff_speed_cd > 0:
                self._staff_speed_cd = max(0.0, self._staff_speed_cd - dt)
            if self.owner.alive:
                self.x = self.owner.x
                self.y = self.owner.y

        elif self.defn.weapon_type == WeaponType.SCYTHE:
            self._orbit_angle += self.defn.orbit_speed * dt
            if self.owner.alive:
                self.x = (self.owner.x
                          + math.cos(self._orbit_angle) * self.defn.orbit_radius)
                self.y = (self.owner.y
                          + math.sin(self._orbit_angle) * self.defn.orbit_radius)

        elif self.defn.weapon_type == WeaponType.SHIELD:
            self._orbit_angle += self.defn.orbit_speed * dt
            if self.owner.alive:
                self.x = (self.owner.x
                          + math.cos(self._orbit_angle) * self.defn.orbit_radius)
                self.y = (self.owner.y
                          + math.sin(self._orbit_angle) * self.defn.orbit_radius)

        elif self.defn.weapon_type == WeaponType.BOOMERANG:
            self.fire_timer += dt
            if self._active_boomerang is not None and self._active_boomerang.is_expired():
                self._active_boomerang = None
            if self._active_boomerang is None:
                self._orbit_angle += self.defn.orbit_speed * dt
                if self.owner.alive:
                    self.x = (self.owner.x
                              + math.cos(self._orbit_angle) * self.defn.orbit_radius)
                    self.y = (self.owner.y
                              + math.sin(self._orbit_angle) * self.defn.orbit_radius)

        elif self.defn.weapon_type == WeaponType.HOMING:
            self.fire_timer += dt
            if self._active_missile is not None and self._active_missile.is_expired():
                self._active_missile = None
            self._orbit_angle += self.defn.orbit_speed * dt
            if self.owner.alive:
                self.x = (self.owner.x
                          + math.cos(self._orbit_angle) * self.defn.orbit_radius)
                self.y = (self.owner.y
                          + math.sin(self._orbit_angle) * self.defn.orbit_radius)

        elif self.defn.weapon_type == WeaponType.SHURIKEN:
            self.fire_timer += dt
            if self.owner.alive:
                self.x = self.owner.x
                self.y = self.owner.y

        elif self.defn.weapon_type == WeaponType.KATANA:
            self.fire_timer += dt
            # 始终朝向对手（对手隐身时保持原方向）
            if self.opponent is not None and self.opponent.alive and not getattr(self.opponent, 'invisible', False):
                self._slash_angle = math.atan2(
                    self.opponent.y - self.owner.y,
                    self.opponent.x - self.owner.x)
            # 静止持刀：刀在玩家前方边缘
            if self.owner.alive:
                dir_x = math.cos(self._slash_angle)
                dir_y = math.sin(self._slash_angle)
                self.x = self.owner.x + dir_x * (self.owner.radius + self.defn.length * 0.4)
                self.y = self.owner.y + dir_y * (self.owner.radius + self.defn.length * 0.4)
            # 斩击状态机：垂直扫动
            if self._slash_state != "idle":
                self._slash_timer -= dt
                if self._slash_timer <= 0:
                    if self._slash_state == "slash1":
                        self._slash_state = "slash2"
                        self._slash_timer = 0.2
                        self._slash_hit_done.clear()
                    elif self._slash_state == "slash2":
                        self._slash_state = "idle"
                        self._slash_timer = 0.0
                        self._slash_hit_done.clear()

        elif self.defn.weapon_type == WeaponType.DUAL_AXE:
            # 始终朝向对手（隐身时保持原方向继续挥动）
            if self.opponent is not None and self.opponent.alive and not getattr(self.opponent, 'invisible', False):
                self._slash_angle = math.atan2(
                    self.opponent.y - self.owner.y,
                    self.opponent.x - self.owner.x)
            # 单一主相位驱动：左斧→右斧→同归，周期 0.75s
            self._axe_master_phase = (self._axe_master_phase + dt / 0.75) % 1.0
            if self.owner.alive:
                self.x = self.owner.x
                self.y = self.owner.y

        elif self.defn.weapon_type == WeaponType.HOLY_SWORD:
            self.fire_timer += dt
            # 始终朝向敌人（隐身时冻结角度）
            if self.opponent and self.opponent.alive and not getattr(self.opponent, 'invisible', False):
                self._slash_angle = math.atan2(
                    self.opponent.y - self.owner.y,
                    self.opponent.x - self.owner.x)
            # 剑位于玩家前方
            if self.owner.alive:
                dir_x = math.cos(self._slash_angle)
                dir_y = math.sin(self._slash_angle)
                self.x = self.owner.x + dir_x * (self.owner.radius + self.defn.length * 0.35)
                self.y = self.owner.y + dir_y * (self.owner.radius + self.defn.length * 0.35)
            # 斩击状态机：计时倒数 → 中段释放剑气 → 终点清除
            if self._slash_state == "slashing":
                self._slash_timer -= dt
                if not self._slash_beam_fired:
                    mid = self._slash_duration / 2
                    if self._slash_timer <= mid:
                        self._slash_beam_fired = True
                        self._beam_ready = True
                # 蓄力期间持续减速
                if self._holy_charge_phase == "charging":
                    self.owner.vx *= 0.05
                    self.owner.vy *= 0.05
                if self._slash_timer <= 0:
                    self._slash_state = "idle"
                    self._slash_hit_done.clear()
                    self._slash_beam_fired = False
                    self._beam_ready = False
                    if self._holy_charge_phase == "charging":
                        self._holy_charge_phase = "idle"
                        self._holy_charge_timer = 0.0
                        self.owner.vx = self._saved_vx
                        self.owner.vy = self._saved_vy
            # 蓄力计时器（实时计数）
            if self._holy_charge_phase == "idle":
                self._holy_charge_timer += dt

        # 更新瞄准角度（对手隐身时冻结，用于枪械类武器）
        if self.defn.weapon_type in (WeaponType.PISTOL, WeaponType.SNIPER,
                                       WeaponType.GATLING, WeaponType.SHURIKEN,
                                       WeaponType.HOMING, WeaponType.STAFF):
            if self.opponent is not None and self.opponent.alive and not getattr(self.opponent, 'invisible', False):
                self._last_aim_angle = math.atan2(
                    self.opponent.y - self.owner.y,
                    self.opponent.x - self.owner.x)

    # ── Aim helper ──────────────────────────────────────────────────────────────

    def _get_aim_target(self) -> tuple[float, float]:
        """返回瞄准目标坐标，对手隐身时使用冻结的瞄准角度。"""
        if self.opponent is not None and self.opponent.alive and not getattr(self.opponent, 'invisible', False):
            return self.opponent.x, self.opponent.y
        return (self.owner.x + math.cos(self._last_aim_angle) * 500,
                self.owner.y + math.sin(self._last_aim_angle) * 500)

    # ── Pistol interface ───────────────────────────────────────────────────────

    def should_fire(self) -> bool:
        """返回 True 表示冷却就绪，并重置计时器。"""
        if self.defn.weapon_type in (WeaponType.PISTOL, WeaponType.SNIPER, WeaponType.GATLING):
            if self.defn.weapon_type == WeaponType.GATLING:
                if self._gatling_overheat > 0:
                    return False
            if self.fire_timer >= self.defn.cooldown:
                self.fire_timer = 0.0
                if self.defn.weapon_type == WeaponType.GATLING:
                    self._gatling_shots += 1
                    if self._gatling_shots >= 10:
                        self._gatling_overheat = 8.0
                        self._gatling_shots = 0
                return True
            return False
        elif self.defn.weapon_type in (WeaponType.BOOMERANG, WeaponType.HOMING):
            if self.defn.weapon_type == WeaponType.BOOMERANG and self._active_boomerang is not None:
                return False
            if self.defn.weapon_type == WeaponType.HOMING and self._active_missile is not None:
                return False
            if self.fire_timer >= self.defn.cooldown:
                self.fire_timer = 0.0
                return True
            return False
        elif self.defn.weapon_type == WeaponType.SHURIKEN:
            if self.fire_timer >= self.defn.cooldown:
                self.fire_timer = 0.0
                return True
            return False
        elif self.defn.weapon_type == WeaponType.BOW:
            if self.fire_timer >= self.defn.cooldown:
                self.fire_timer = 0.0
                return True
            return False
        elif self.defn.weapon_type == WeaponType.CROSSBOW:
            if self._burst_cooldown_remaining > 0:
                return False
            # 连射中
            if self._burst_remaining > 0:
                if self._burst_timer >= self.defn.burst_interval:
                    self._burst_timer = 0.0
                    self._burst_remaining -= 1
                    if self._burst_remaining == 0:
                        self._burst_cooldown_remaining = self.defn.burst_cooldown
                    return True
                return False
            # 开始新一轮连射
            if self.fire_timer >= self.defn.cooldown:
                self.fire_timer = 0.0
                self._burst_remaining = self.defn.burst_count - 1
                self._burst_timer = 0.0
                return True
            return False
        elif self.defn.weapon_type == WeaponType.STAFF:
            # 速度触发：敌人移速 >= 13 时无视冷却（3s 冷却防连发）
            if self.opponent and self.opponent.alive:
                speed = math.hypot(self.opponent.vx, self.opponent.vy)
            else:
                speed = 0
            if speed >= 13 and self._staff_speed_cd <= 0:
                self._staff_speed_cd = 3.0
                self.fire_timer = 0.0
                return True
            if self.fire_timer >= self.defn.cooldown:
                self.fire_timer = 0.0
                return True
            return False
        elif self.defn.weapon_type == WeaponType.KATANA:
            if self._slash_state != "idle":
                return False
            if self.fire_timer >= self.defn.cooldown:
                self.fire_timer = 0.0
                self._slash_state = "slash1"
                self._slash_timer = 0.2
                self._slash_hit_done.clear()
                return True
            return False
        elif self.defn.weapon_type == WeaponType.HOLY_SWORD:
            # 优先级1：斩击中段释放剑气（beam_ready 由 update() 置位）
            if self._beam_ready:
                self._beam_ready = False
                return True
            # 优先级2：触发蓄力斩击（18s到且空闲 → 2s蓄力斩）
            if self._slash_state == "idle" and self._holy_charge_phase == "idle" and self._holy_charge_timer >= 18.0:
                self._holy_charge_phase = "charging"
                self._holy_firing_charged = True
                self._slash_state = "slashing"
                self._slash_duration = 2.0
                self._slash_timer = 2.0
                self._slash_hit_done.clear()
                self._slash_beam_fired = False
                self._beam_ready = False
                self.fire_timer = 0.0
                # 保留速度 → 减速至 0.05×
                self._saved_vx = self.owner.vx
                self._saved_vy = self.owner.vy
                self.owner.vx *= 0.05
                self.owner.vy *= 0.05
                return False  # 剑气在1s后由 update() 触发
            # 优先级3：普通斩击（1s，中段0.5s释放剑气）
            if self._slash_state == "idle" and self._holy_charge_phase in ("idle",):
                if self.fire_timer >= self.defn.cooldown:
                    self.fire_timer = 0.0
                    self._holy_firing_charged = False
                    self._slash_state = "slashing"
                    self._slash_duration = 1.0
                    self._slash_timer = 1.0
                    self._slash_hit_done.clear()
                    self._slash_beam_fired = False
                    self._beam_ready = False
                    return False  # 剑气在0.5s后由 update() 触发
            return False
        return False

    def fire(self):
        if self.defn.weapon_type == WeaponType.STAFF:
            if self.opponent and self.opponent.alive:
                speed = math.hypot(self.opponent.vx, self.opponent.vy)
                self.opponent._staff_saved_speed = speed
                self.opponent.vx *= 0.1
                self.opponent.vy *= 0.1
                self.opponent._staff_hit_timer = 1.0
                marks = len(getattr(self.opponent, '_fear_mark_timers', []))
                dmg = speed * (1.2 ** marks)
                self.opponent.take_damage(dmg)
            return None
        if self.defn.weapon_type in (WeaponType.PISTOL, WeaponType.SNIPER):
            tx, ty = self._get_aim_target()
            return Bullet(self.x, self.y, tx, ty, self.owner_id, self.defn, owner_team=self.owner_team)
        elif self.defn.weapon_type == WeaponType.GATLING:
            tx, ty = self._get_aim_target()
            spread = self.defn.bullet_spread
            if spread > 0:
                angle = math.atan2(ty - self.y, tx - self.x)
                angle += random.uniform(-spread, spread)
                dist = math.hypot(ty - self.y, tx - self.x)
                tx = self.x + math.cos(angle) * dist
                ty = self.y + math.sin(angle) * dist
            return Bullet(self.x, self.y, tx, ty, self.owner_id, self.defn, owner_team=self.owner_team)
        elif self.defn.weapon_type == WeaponType.BOOMERANG:
            b = BoomerangProjectile(self.x, self.y, self.owner, self.opponent, self.defn, owner_team=self.owner_team)
            self._active_boomerang = b
            return b
        elif self.defn.weapon_type == WeaponType.HOMING:
            # 从发射筒口射出
            mx, my = self._get_launcher_muzzle()
            m = HomingMissile(mx, my, self.owner, self.opponent, self.defn, owner_team=self.owner_team)
            self._active_missile = m
            return m
        elif self.defn.weapon_type == WeaponType.SHURIKEN:
            tx, ty = self._get_aim_target()
            spread = self.defn.bullet_spread
            results = []
            for _ in range(2):
                sx, sy = tx, ty
                if spread > 0 and random.random() < 0.5:
                    offset = random.uniform(-spread, spread)
                    a = math.atan2(ty - self.y, tx - self.x) + offset
                    d = math.hypot(ty - self.y, tx - self.x)
                    sx = self.x + math.cos(a) * d
                    sy = self.y + math.sin(a) * d
                results.append(ShurikenProjectile(self.x, self.y, sx, sy, self.owner_id, self.defn, owner_team=self.owner_team))
            return results
        elif self.defn.weapon_type == WeaponType.BOW:
            tx, ty = self._get_aim_target()
            base_angle = math.atan2(ty - self.y, tx - self.x)
            dist = math.hypot(ty - self.y, tx - self.x)
            results = []
            for offset in (-0.12, 0.0, 0.12):
                a = base_angle + offset
                sx = self.x + math.cos(a) * dist
                sy = self.y + math.sin(a) * dist
                results.append(Bullet(self.x, self.y, sx, sy, self.owner_id, self.defn, owner_team=self.owner_team))
            return results
        elif self.defn.weapon_type == WeaponType.CROSSBOW:
            tx, ty = self._get_aim_target()
            return Bullet(self.x, self.y, tx, ty, self.owner_id, self.defn, owner_team=self.owner_team)
        elif self.defn.weapon_type == WeaponType.KATANA:
            return None
        elif self.defn.weapon_type == WeaponType.HOLY_SWORD:
            if self._holy_firing_charged:
                # 三段竖向剑气（中 + 左右各偏15°）
                results = []
                base_angle = self._slash_angle
                for offset in (-math.radians(15), 0, math.radians(15)):
                    a = base_angle + offset
                    bx = self.owner.x + math.cos(a) * (self.owner.radius + 20)
                    by = self.owner.y + math.sin(a) * (self.owner.radius + 20)
                    results.append(VerticalBeam(
                        bx, by, a, self.owner_id,
                        damage=self.defn.damage * 2.5,
                        color=(255, 215, 60),
                        lifetime=2.0,
                        speed=280,
                        length=25,
                        width=180,
                        owner_team=self.owner_team,
                    ))
                return results
            else:
                # 普通斩击 → 月牙剑气
                bx = self.owner.x + math.cos(self._slash_angle) * (self.owner.radius + 20)
                by = self.owner.y + math.sin(self._slash_angle) * (self.owner.radius + 20)
                return CrescentBeam(
                    bx, by, self._slash_angle, self.owner_id,
                    damage=self.defn.damage,
                    color=(255, 230, 100),
                    lifetime=3.5,
                    speed=230,
                    size=100,
                    owner_team=self.owner_team,
                )
        return None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def is_expired(self) -> bool:
        return not self.owner.alive

    # ── Melee collision (scythe + shield) ─────────────────────────────────────

    def collides_with(self, player) -> bool:
        """近战武器与玩家圆碰撞检测（含命中冷却）。"""
        wt = self.defn.weapon_type
        if wt == WeaponType.KATANA:
            return self._katana_slash_collides(player.x, player.y, player.radius,
                                               id(player))
        if wt == WeaponType.HOLY_SWORD:
            return self._katana_slash_collides(player.x, player.y, player.radius,
                                               id(player))
        if wt == WeaponType.DUAL_AXE:
            return self._dual_axe_collides_with(player.char.id,
                                                player.x, player.y, player.radius)
        if wt not in (WeaponType.SCYTHE, WeaponType.SHIELD):
            return False
        target_id = player.char.id
        last = self._last_hit_times.get(target_id, -999.0)
        if self.age - last < self.defn.cooldown:
            return False
        effective_radius = self.defn.length / 2
        dx = self.x - player.x
        dy = self.y - player.y
        if math.hypot(dx, dy) < player.radius + effective_radius:
            self._last_hit_times[target_id] = self.age
            if wt == WeaponType.SHIELD:
                self._knockback_target = player
            return True
        return False

    def collides_with_pet(self, pet) -> bool:
        """近战武器与宠物头碰撞（含命中冷却）。"""
        wt = self.defn.weapon_type
        if wt == WeaponType.KATANA:
            head_x, head_y = pet.segments[0] if hasattr(pet, 'segments') else (pet.x, pet.y)
            head_r = getattr(pet, '_head_radius', lambda: pet.defn.body_width // 2)()
            if hasattr(head_r, '__call__'):
                head_r = pet.defn.body_width // 2
            return self._katana_slash_collides(head_x, head_y, head_r, id(pet))
        if wt == WeaponType.HOLY_SWORD:
            head_x, head_y = pet.segments[0] if hasattr(pet, 'segments') else (pet.x, pet.y)
            head_r = getattr(pet, '_head_radius', lambda: pet.defn.body_width // 2)()
            if hasattr(head_r, '__call__'):
                head_r = pet.defn.body_width // 2
            return self._katana_slash_collides(head_x, head_y, head_r, id(pet))
        if wt == WeaponType.DUAL_AXE:
            target_id = str(id(pet))
            last = self._axe_hit_targets.get(target_id, -999.0)
            if self.age - last < self.defn.cooldown:
                return False
            head_x, head_y = pet.segments[0] if hasattr(pet, 'segments') else (pet.x, pet.y)
            head_r = pet.defn.body_width // 2
            if self._check_either_axe_hits(head_x, head_y, head_r):
                self._axe_hit_targets[target_id] = self.age
                return True
            return False
        if wt not in (WeaponType.SCYTHE, WeaponType.SHIELD):
            return False
        target_id = str(id(pet))
        last = self._last_hit_times.get(target_id, -999.0)
        if self.age - last < self.defn.cooldown:
            return False
        effective_radius = self.defn.length / 2
        if pet.head_collides_with_circle(self.x, self.y, effective_radius):
            self._last_hit_times[target_id] = self.age
            return True
        return False

    def collides_with_projectile(self, proj) -> bool:
        """武士刀斩击抵消投射物（炸弹除外）。"""
        if self.defn.weapon_type not in (WeaponType.KATANA, WeaponType.HOLY_SWORD):
            return False
        if self._slash_state == "idle":
            return False
        px = getattr(proj, 'x', 0.0)
        py = getattr(proj, 'y', 0.0)
        pr = getattr(proj, 'radius', 5)
        return self._katana_slash_collides(px, py, pr, None)

    def _katana_slash_collides(self, tx: float, ty: float, tr: float,
                                target_key) -> bool:
        """检测目标是否在斩击弧内。支持武士刀（两段）和圣剑（单段）。"""
        if self._slash_state == "idle":
            return False
        if target_key is not None and target_key in self._slash_hit_done:
            return False
        tdx = tx - self.owner.x
        tdy = ty - self.owner.y
        dist = math.hypot(tdx, tdy)
        max_dist = self.owner.radius + self.defn.length + tr
        if dist > max_dist:
            return False
        target_angle = math.atan2(tdy, tdx)
        if self._slash_timer <= 0:
            return False

        if self._slash_state == "slashing":
            # 圣剑单段：从 -60° 扫到 +60°
            progress = 1.0 - (self._slash_timer / self._slash_duration)
            blade_angle = self._slash_angle + math.radians(60 * (2.0 * progress - 1.0))
        elif self._slash_state == "slash1":
            progress = 1.0 - (self._slash_timer / 0.2)
            blade_angle = self._slash_angle + math.radians(60 * (1.0 - 2.0 * progress))
        else:
            progress = 1.0 - (self._slash_timer / 0.2)
            blade_angle = self._slash_angle + math.radians(60 * (2.0 * progress - 1.0))

        angle_diff = (target_angle - blade_angle + math.pi) % (2 * math.pi) - math.pi
        if abs(angle_diff) < math.radians(30):
            if target_key is not None:
                self._slash_hit_done.add(target_key)
            return True
        return False

    # ── Dual Axe helpers ─────────────────────────────────────────────────────

    # ── Dual Axe swing helpers ──────────────────────────────────────────────

    @staticmethod
    def _ease_out_cubic(t: float) -> float:
        return 1.0 - (1.0 - t) ** 3

    def _get_axe_swing_offset(self, side: str) -> float:
        """返回 swing_offset（弧度）。左斧正值=前挥，右斧负值=前挥。"""
        mp = self._axe_master_phase
        amp = math.radians(85)

        if side == "left":
            if mp < 0.03:
                return 0.0
            elif mp < 0.18:
                p = (mp - 0.03) / 0.15
                return amp * self._ease_out_cubic(p)
            elif mp < 0.24:
                return amp
            elif mp < 0.36:
                p = (mp - 0.24) / 0.12
                return amp * (1.0 - p)
            else:
                return 0.0
        else:  # right
            if mp < 0.36:
                return 0.0
            elif mp < 0.51:
                p = (mp - 0.36) / 0.15
                return -amp * self._ease_out_cubic(p)
            elif mp < 0.57:
                return -amp
            elif mp < 0.69:
                p = (mp - 0.57) / 0.12
                return -amp * (1.0 - p)
            else:
                return 0.0

    def _get_axe_blade_pos(self, side: str) -> tuple[float, float, float, float, float]:
        """返回斧头 (bx, by, handle_angle, px, py)。
           pygame: 0=右, π/2=下, -π/2=上。左=负角(上), 右=正角(下)。"""
        base_offset = math.radians(70)
        handle_len = 28.0

        if side == "left":
            pivot_angle = self._slash_angle - base_offset
            swing_offset = self._get_axe_swing_offset("left")
        else:
            pivot_angle = self._slash_angle + base_offset
            swing_offset = self._get_axe_swing_offset("right")

        handle_angle = pivot_angle + swing_offset

        px = self.owner.x + math.cos(pivot_angle) * self.owner.radius
        py = self.owner.y + math.sin(pivot_angle) * self.owner.radius
        bx = px + math.cos(handle_angle) * handle_len
        by = py + math.sin(handle_angle) * handle_len

        return bx, by, handle_angle, px, py

    def _is_axe_active(self, side: str) -> bool:
        """斧头是否处于可造成伤害的挥砍阶段。"""
        mp = self._axe_master_phase
        if side == "left":
            return 0.10 < mp < 0.30
        else:
            return 0.43 < mp < 0.63

    def _check_either_axe_hits(self, tx: float, ty: float, tr: float) -> bool:
        """检查任一斧头是否命中目标（目标坐标 + 半径）。"""
        for side in ("left", "right"):
            bx, by, _, _, _ = self._get_axe_blade_pos(side)
            if math.hypot(bx - tx, by - ty) < tr + 24:
                return True
        return False

    def _dual_axe_collides_with(self, target_id: str,
                                 tx: float, ty: float, tr: float) -> bool:
        """双战斧命中检测，含每目标冷却。"""
        last = self._axe_hit_targets.get(target_id, -999.0)
        if self.age - last < self.defn.cooldown:
            return False
        if self._check_either_axe_hits(tx, ty, tr):
            self._axe_hit_targets[target_id] = self.age
            return True
        return False

    # ── Render ─────────────────────────────────────────────────────────────────

    def draw(self, screen):
        if not self.owner.alive:
            return

        if self.defn.weapon_type == WeaponType.PISTOL:
            self._draw_pistol(screen)
        elif self.defn.weapon_type == WeaponType.SNIPER:
            self._draw_sniper(screen)
        elif self.defn.weapon_type == WeaponType.GATLING:
            self._draw_gatling(screen)
        elif self.defn.weapon_type == WeaponType.HOMING:
            self._draw_launcher(screen)
        elif self.defn.weapon_type == WeaponType.SCYTHE:
            self._draw_scythe(screen)
        elif self.defn.weapon_type == WeaponType.SHIELD:
            self._draw_shield(screen)
        elif self.defn.weapon_type == WeaponType.BOOMERANG:
            if self._active_boomerang is None:
                self._draw_boomerang(screen)
        elif self.defn.weapon_type == WeaponType.BOW:
            self._draw_bow(screen)
        elif self.defn.weapon_type == WeaponType.CROSSBOW:
            self._draw_crossbow(screen)
        elif self.defn.weapon_type == WeaponType.KATANA:
            self._draw_katana(screen)
        elif self.defn.weapon_type == WeaponType.DUAL_AXE:
            self._draw_dual_axe(screen)
        elif self.defn.weapon_type == WeaponType.STAFF:
            self._draw_staff(screen)
        elif self.defn.weapon_type == WeaponType.HOLY_SWORD:
            self._draw_holy_sword(screen)

    def _draw_staff(self, screen):
        """绘制逼真法杖：角色左侧竖立，分段金属杖身 + 骷髅法球。"""
        ox, oy = self.owner.x, self.owner.y
        tx, ty = self._get_aim_target()
        dx = tx - ox
        dy = ty - oy
        dist = math.hypot(dx, dy)
        if dist < 0.001:
            return
        angle = math.atan2(dy, dx)

        # 法杖在角色左侧（面朝方向的 -90°）
        left_angle = angle - math.pi / 2
        staff_offset = self.owner.radius + 14  # 离角色距离
        base_x = ox + math.cos(left_angle) * staff_offset
        base_y = oy + math.sin(left_angle) * staff_offset

        staff_len = 50
        # 杖顶端（斜向敌人方向）
        tip_lean = 0.3  # 轻微倾向敌人
        tip_x = base_x + math.cos(angle) * tip_lean * 8
        tip_y = base_y + math.sin(angle) * tip_lean * 8 - staff_len
        # 杖尾端
        tail_x = base_x - math.cos(angle) * 2
        tail_y = base_y + 12

        casting = self.fire_timer < 0.3

        # ── 杖身（分段金属，3 节） ──
        segments = 3
        for i in range(segments):
            t0 = i / segments
            t1 = (i + 1) / segments
            sx0 = tail_x + (tip_x - tail_x) * t0
            sy0 = tail_y + (tip_y - tail_y) * t0
            sx1 = tail_x + (tip_x - tail_x) * t1
            sy1 = tail_y + (tip_y - tail_y) * t1
            # 偶数节深紫，奇数节暗紫
            color = (75, 35, 105) if i % 2 == 0 else (55, 25, 80)
            w = 5 - i * 0.8
            pygame.draw.line(screen, color,
                             (int(sx0), int(sy0)), (int(sx1), int(sy1)), int(w))
        # 杖身高光
        pygame.draw.line(screen, (130, 80, 170),
                         (int(tail_x + 1), int(tail_y + 1)),
                         (int(tip_x + 1), int(tip_y + 1)), 1)

        # ── 分段金属环 ──
        for i in range(1, segments):
            t = i / segments
            rx = tail_x + (tip_x - tail_x) * t
            ry = tail_y + (tip_y - tail_y) * t
            pygame.draw.circle(screen, (140, 100, 180), (int(rx), int(ry)), 3)
            pygame.draw.circle(screen, (60, 30, 90), (int(rx), int(ry)), 3, 1)

        # ── 杖尾尖刺 ──
        tail_spike = (tail_x, tail_y + 6)
        pygame.draw.line(screen, (100, 60, 140),
                         (int(tail_x), int(tail_y)), (int(tail_spike[0]), int(tail_spike[1])), 3)

        # ── 杖头法球 ──
        orb_r = 8 + (4 if casting else 0)
        glow_r = orb_r + 10 + (12 if casting else 0)
        glow_alpha = 100 + (100 if casting else 0)
        glow = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (170, 90, 230, glow_alpha),
                           (glow_r + 2, glow_r + 2), glow_r)
        pygame.draw.circle(glow, (130, 50, 200, glow_alpha // 3),
                           (glow_r + 2, glow_r + 2), int(glow_r * 0.6))
        screen.blit(glow, (int(tip_x) - glow_r - 2, int(tip_y) - glow_r - 2))

        # 法球本体
        orb_color = (230, 190, 255) if casting else (180, 110, 240)
        pygame.draw.circle(screen, orb_color, (int(tip_x), int(tip_y)), orb_r)
        # 高光
        pygame.draw.circle(screen, (255, 240, 255),
                           (int(tip_x - orb_r * 0.3), int(tip_y - orb_r * 0.3)),
                           max(1, orb_r // 3))
        pygame.draw.circle(screen, (90, 30, 140),
                           (int(tip_x), int(tip_y)), orb_r, 1)

    def _draw_holy_sword(self, screen):
        """绘制圣剑：金色直刃双刃剑 + 十字护手 + 缠绕剑柄 + 斩击弧光 + 蓄力光效。"""
        ox, oy = self.owner.x, self.owner.y
        angle = self._slash_angle

        # 斩击动画：刀刃从 angle-60° 扫到 angle+60°
        if self._slash_state == "slashing" and self._slash_timer > 0:
            progress = 1.0 - (self._slash_timer / self._slash_duration)
            sweep = math.radians(60 * (2.0 * progress - 1.0))
            blade_angle = angle + sweep
        else:
            blade_angle = angle

        # 斩击弧光（以 base_angle 为中心，120° 范围）
        if self._slash_state == "slashing":
            self._draw_slash_arc(screen, ox, oy, angle, (255, 230, 100))

        dir_x = math.cos(blade_angle)
        dir_y = math.sin(blade_angle)
        perp_x = -dir_y
        perp_y = dir_x

        blade_len = self.defn.length
        blade_w = self.defn.width
        hw = blade_w / 2

        # 蓄力脉冲光效
        charge_glow = 0.0
        if self._holy_charge_phase == "charging":
            charge_glow = 0.3 + 0.3 * math.sin(pygame.time.get_ticks() * 0.015)

        # 剑格位置
        guard_dist = self.owner.radius + blade_len * 0.08
        guard_x = ox + dir_x * guard_dist
        guard_y = oy + dir_y * guard_dist

        # 剑尖
        tip_x = guard_x + dir_x * (blade_len * 0.88)
        tip_y = guard_y + dir_y * (blade_len * 0.88)

        # ── 剑身光晕（蓄力时扩大） ──
        if charge_glow > 0:
            glow_alpha = int(80 * charge_glow)
            glow_r = int(blade_w + 12 * charge_glow)
            glow_surf = pygame.Surface((int(blade_len + 30), glow_r * 2 + 8), pygame.SRCALPHA)
            gc = glow_surf.get_width() // 2
            gc2 = glow_surf.get_height() // 2
            glow_rect = pygame.Rect(gc - int(blade_len * 0.44), gc2 - glow_r,
                                    int(blade_len * 0.88), glow_r * 2)
            pygame.draw.rect(glow_surf, (255, 220, 80, glow_alpha), glow_rect)
            rot_glow = pygame.transform.rotate(glow_surf, -math.degrees(angle))
            screen.blit(rot_glow, (int(guard_x) - rot_glow.get_width() // 2,
                                   int(guard_y) - rot_glow.get_height() // 2))

        # ── 剑身 (直刃双刃) ──
        body_start = guard_dist + blade_len * 0.04
        body_end = guard_dist + blade_len * 0.88
        bsx = ox + dir_x * body_start
        bsy = oy + dir_y * body_start
        bex = ox + dir_x * body_end
        bey = oy + dir_y * body_end

        # 直刃剑身多边形（双刃对称收窄到尖端）
        tip_narrow = hw * 0.3
        body_pts = [
            (bsx + perp_x * hw, bsy + perp_y * hw),
            (bex + perp_x * tip_narrow, bey + perp_y * tip_narrow),
            (tip_x, tip_y),
            (bex - perp_x * tip_narrow, bey - perp_y * tip_narrow),
            (bsx - perp_x * hw, bsy - perp_y * hw),
        ]
        body_color = (220, 200, 60) if charge_glow == 0 else (
            min(255, 220 + int(35 * charge_glow)),
            min(255, 200 + int(55 * charge_glow)),
            min(255, 60 + int(100 * charge_glow)))
        pygame.draw.polygon(screen, body_color, body_pts)
        pygame.draw.polygon(screen, (180, 160, 40), body_pts, 1)

        # 剑身中线高光
        mid_x = (bsx + bex) / 2
        mid_y = (bsy + bey) / 2
        hl_start_x = bsx + perp_x * hw * 0.25
        hl_start_y = bsy + perp_y * hw * 0.25
        hl_end_x = bex + perp_x * tip_narrow * 0.25
        hl_end_y = bey + perp_y * tip_narrow * 0.25
        pygame.draw.line(screen, (255, 240, 180),
                         (int(hl_start_x), int(hl_start_y)),
                         (int(hl_end_x), int(hl_end_y)), max(1, int(hw * 0.3)))

        # ── 十字护手 ──
        guard_w = blade_w + 8
        guard_h = 3
        gx1 = guard_x + perp_x * guard_w
        gy1 = guard_y + perp_y * guard_w
        gx2 = guard_x - perp_x * guard_w
        gy2 = guard_y - perp_y * guard_w
        guard_pts = [
            (gx1 + dir_x * guard_h, gy1 + dir_y * guard_h),
            (gx1 - dir_x * guard_h, gy1 - dir_y * guard_h),
            (gx2 - dir_x * guard_h, gy2 - dir_y * guard_h),
            (gx2 + dir_x * guard_h, gy2 + dir_y * guard_h),
        ]
        pygame.draw.polygon(screen, (200, 170, 40), guard_pts)
        pygame.draw.polygon(screen, (150, 120, 20), guard_pts, 1)
        # 护手中心宝石
        pygame.draw.circle(screen, (255, 100, 50), (int(guard_x), int(guard_y)), 3)

        # ── 剑柄 ──
        handle_len = blade_len * 0.35
        handle_start_x = guard_x - dir_x * guard_h
        handle_start_y = guard_y - dir_y * guard_h
        handle_end_x = handle_start_x - dir_x * handle_len
        handle_end_y = handle_start_y - dir_y * handle_len
        hh = hw * 0.85
        handle_pts = [
            (handle_start_x + perp_x * hh, handle_start_y + perp_y * hh),
            (handle_end_x + perp_x * hh * 0.8, handle_end_y + perp_y * hh * 0.8),
            (handle_end_x - perp_x * hh * 0.8, handle_end_y - perp_y * hh * 0.8),
            (handle_start_x - perp_x * hh, handle_start_y - perp_y * hh),
        ]
        pygame.draw.polygon(screen, (80, 55, 30), handle_pts)
        pygame.draw.polygon(screen, (50, 35, 15), handle_pts, 1)
        # 缠绕纹
        for i in range(1, 7):
            t = i / 7
            hx = handle_start_x + (handle_end_x - handle_start_x) * t
            hy = handle_start_y + (handle_end_y - handle_start_y) * t
            w = hh * (0.6 + 0.3 * (i % 2))
            pygame.draw.line(screen, (160, 130, 70),
                             (int(hx + perp_x * w), int(hy + perp_y * w)),
                             (int(hx - perp_x * w), int(hy - perp_y * w)), 1)

        # 剑首
        pommel_r = hh * 0.9
        pygame.draw.circle(screen, (180, 150, 60),
                           (int(handle_end_x), int(handle_end_y)), int(pommel_r))
        pygame.draw.circle(screen, (120, 90, 30),
                           (int(handle_end_x), int(handle_end_y)), int(pommel_r), 1)

    @staticmethod
    def _draw_slash_arc(screen, ox, oy, base_angle, color):
        """绘制斩击弧光（SRCALPHA 表面，120° 身前弧）。

        pygame.draw.arc 使用数学坐标系（0=右, π/2=上, 逆时针）。
        atan2 返回屏幕坐标系（0=右, π/2=下）。取负对齐两者。
        """
        arc_r = 70
        surf_size = arc_r * 2 + 20
        surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        c = surf_size // 2
        rect = pygame.Rect(c - arc_r, c - arc_r, arc_r * 2, arc_r * 2)
        # 取负对齐 pygame arc 的数学坐标系
        a1 = -(base_angle - math.radians(60))
        a2 = -(base_angle + math.radians(60))
        arc_start = min(a1, a2)
        arc_end = max(a1, a2)
        pygame.draw.arc(surf, (*color, 100), rect, arc_start, arc_end, 5)
        pygame.draw.arc(surf, (255, 255, 255, 60), rect, arc_start, arc_end, 2)
        screen.blit(surf, (int(ox) - c, int(oy) - c))

    def _draw_pistol(self, screen):
        """绘制更精致的手枪。"""
        tx, ty = self._get_aim_target()

        dx = tx - self.owner.x
        dy = ty - self.owner.y
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            angle = math.atan2(dy, dx)
        else:
            angle = 0.0

        # 枪身参数
        barrel_len = self.defn.length
        handle_len = barrel_len * 0.4
        barrel_width = self.defn.width
        handle_width = barrel_width * 1.2
        
        # 计算枪口方向向量
        dir_x = math.cos(angle)
        dir_y = math.sin(angle)
        perp_x = -dir_y  # 垂直方向
        perp_y = dir_x
        
        # 枪身起点（玩家边缘）
        start_x = self.owner.x + dir_x * self.owner.radius
        start_y = self.owner.y + dir_y * self.owner.radius
        
        # 枪口位置
        muzzle_x = self.owner.x + dir_x * (self.owner.radius + barrel_len)
        muzzle_y = self.owner.y + dir_y * (self.owner.radius + barrel_len)
        
        # 枪身结束点（握把后方）
        rear_x = self.owner.x + dir_x * (self.owner.radius - handle_len * 0.5)
        rear_y = self.owner.y + dir_y * (self.owner.radius - handle_len * 0.5)
        
        # 1. 枪身主体（带渐变色的梯形）
        points = [
            (start_x + perp_x * barrel_width * 0.3, start_y + perp_y * barrel_width * 0.3),  # 枪身上缘
            (muzzle_x + perp_x * barrel_width * 0.4, muzzle_y + perp_y * barrel_width * 0.4),  # 枪口上缘
            (muzzle_x - perp_x * barrel_width * 0.4, muzzle_y - perp_y * barrel_width * 0.4),  # 枪口下缘
            (start_x - perp_x * barrel_width * 0.5, start_y - perp_y * barrel_width * 0.5),  # 枪身下缘
        ]
        pygame.draw.polygon(screen, self.defn.color, points)
        
        # 2. 枪管高光线（顶部）
        top_line = [
            (start_x + perp_x * barrel_width * 0.25, start_y + perp_y * barrel_width * 0.25),
            (muzzle_x + perp_x * barrel_width * 0.35, muzzle_y + perp_y * barrel_width * 0.35)
        ]
        pygame.draw.line(screen, (255, 255, 200), top_line[0], top_line[1], max(1, barrel_width // 3))
        
        # 3. 握把（倾斜的矩形）
        handle_angle = angle + math.radians(-30)  # 握把向后倾斜30度
        handle_dir_x = math.cos(handle_angle)
        handle_dir_y = math.sin(handle_angle)
        handle_perp_x = -handle_dir_y
        handle_perp_y = handle_dir_x
        
        # 握把位置（从枪身底部向后延伸）
        grip_base_x = start_x - perp_x * barrel_width * 0.6
        grip_base_y = start_y - perp_y * barrel_width * 0.6
        grip_end_x = grip_base_x + handle_dir_x * handle_len
        grip_end_y = grip_base_y + handle_dir_y * handle_len
        
        grip_points = [
            (grip_base_x + handle_perp_x * handle_width * 0.4, grip_base_y + handle_perp_y * handle_width * 0.4),
            (grip_end_x + handle_perp_x * handle_width * 0.35, grip_end_y + handle_perp_y * handle_width * 0.35),
            (grip_end_x - handle_perp_x * handle_width * 0.35, grip_end_y - handle_perp_y * handle_width * 0.35),
            (grip_base_x - handle_perp_x * handle_width * 0.5, grip_base_y - handle_perp_y * handle_width * 0.5),
        ]
        # 握把深色
        dark_color = tuple(max(0, c - 60) for c in self.defn.color)
        pygame.draw.polygon(screen, dark_color, grip_points)
        
        # 4. 扳机护环（小圆弧）
        trigger_x = grip_base_x + handle_dir_x * handle_len * 0.3
        trigger_y = grip_base_y + handle_dir_y * handle_len * 0.3
        trigger_radius = barrel_width * 0.5
        pygame.draw.arc(screen, (150, 150, 150),
                        (trigger_x - trigger_radius, trigger_y - trigger_radius,
                        trigger_radius * 2, trigger_radius * 2),
                        math.radians(0), math.radians(180), max(1, barrel_width // 4))
        
        # 5. 准星（枪口处的红点）
        sight_offset = barrel_width * 0.15
        sight_x = muzzle_x + dir_x * 3
        sight_y = muzzle_y + dir_y * 3
        pygame.draw.circle(screen, (255, 50, 50),
                        (int(sight_x), int(sight_y)),
                        max(2, barrel_width // 3))
        pygame.draw.circle(screen, (255, 150, 150),
                        (int(sight_x), int(sight_y)),
                        max(1, barrel_width // 4))
        
        # 6. 枪口闪光（如果正在射击）
        if hasattr(self, '_muzzle_flash_timer') and self._muzzle_flash_timer > 0:
            flash_alpha = min(255, int(self._muzzle_flash_timer * 500))
            flash_radius = barrel_width + int(self._muzzle_flash_timer * 10)
            pygame.draw.circle(screen, (255, 255, 100),
                            (int(muzzle_x), int(muzzle_y)),
                            flash_radius)
            self._muzzle_flash_timer -= 0.05  # 需要传入 dt，这里简化
        
        # 7. 枪身装饰（简单刻线）
        for i in range(3):
            line_offset = barrel_len * (0.2 + i * 0.15)
            line_x = start_x + dir_x * line_offset
            line_y = start_y + dir_y * line_offset
            pygame.draw.line(screen, (100, 100, 120),
                            (int(line_x - perp_x * barrel_width * 0.3),
                            int(line_y - perp_y * barrel_width * 0.3)),
                            (int(line_x + perp_x * barrel_width * 0.3),
                            int(line_y + perp_y * barrel_width * 0.3)),
                            1)
            
    def _draw_scythe(self, screen):
        """绘制死神镰刀：长柄末端安装垂直于柄的大型弯刃。"""
        ox, oy = self.owner.x, self.owner.y
        bx, by = self.x, self.y

        dx = bx - ox
        dy = by - oy
        dist = math.hypot(dx, dy)
        if dist < 0.001:
            return

        hx = dx / dist   # 柄方向（从玩家朝外）
        hy = dy / dist
        px = -hy         # 垂直方向（刀刃延伸方向）
        py = hx

        blade_span = 56  # 刀刃跨度（沿垂直方向）
        blade_width = 16 # 刀刃宽度（沿柄方向的最大厚度）

        # ── 1. 长柄（深棕色木杆，从玩家边缘到刀刃根部） ──
        handle_start_x = ox + hx * (self.owner.radius - 4)
        handle_start_y = oy + hy * (self.owner.radius - 4)
        handle_end_x = bx
        handle_end_y = by

        handle_w = max(2, self.defn.width + 1)
        pygame.draw.line(screen, (65, 45, 22),
                         (int(handle_start_x), int(handle_start_y)),
                         (int(handle_end_x), int(handle_end_y)), handle_w)
        pygame.draw.line(screen, (125, 85, 45),
                         (int(handle_start_x + px * 1), int(handle_start_y + py * 1)),
                         (int(handle_end_x + px * 1), int(handle_end_y + py * 1)),
                         max(1, handle_w // 2))

        # ── 2. 弯月刀刃（垂直于柄，朝一侧弯曲） ──
        # 刀背 (spine): 外弧 — 离柄远的一侧
        spine_pts = []
        for t in (0.0, 0.1, 0.22, 0.38, 0.55, 0.7, 0.84, 0.95, 1.0):
            v = t * blade_span                    # v 沿垂直方向 (px,py)
            u = blade_width * (1.0 - t) * 0.5 + 4 # u 沿柄方向 (hx,hy) — 刀背偏外
            spine_pts.append((u, v))

        # 刀刃 (cutting edge): 内弧 — 靠近柄的一侧，更锐利
        edge_pts = []
        for t in (1.0, 0.93, 0.78, 0.6, 0.42, 0.25, 0.12, 0.0):
            v = t * blade_span
            u = -(blade_width * t * 0.45 + 2)      # 负值 = 向玩家方向凹陷
            edge_pts.append((u, v))

        all_pts = spine_pts + edge_pts
        world_pts = []
        for u, v in all_pts:
            wx = bx + hx * u + px * v
            wy = by + hy * u + py * v
            world_pts.append((int(wx), int(wy)))

        # 刀身填充（银白冷钢）
        blade_color = (200, 210, 225)
        pygame.draw.polygon(screen, blade_color, world_pts)
        pygame.draw.polygon(screen, (90, 100, 120), world_pts, 2)

        # 刀刃高光线（内弧）
        hl_pts = []
        for t in (0.08, 0.18, 0.32, 0.48, 0.65, 0.8, 0.92):
            v = t * blade_span
            u = -(blade_width * t * 0.45) + 1
            hl_pts.append((int(bx + hx * u + px * v),
                           int(by + hy * u + py * v)))
        if len(hl_pts) >= 2:
            pygame.draw.lines(screen, (240, 245, 255), False, hl_pts, 1)

        # ── 3. 刀尖延伸（锐利尖端，超出弯刃主体） ──
        tip_u = blade_width * 0.5 * 0.5 + 4
        tip_v = blade_span
        tip_end_u = tip_u - 10
        tip_end_v = blade_span + 16
        tip_pts = [
            (int(bx + hx * tip_u + px * tip_v),
             int(by + hy * tip_u + py * tip_v)),
            (int(bx + hx * (tip_u - 8) + px * (tip_v + 8)),
             int(by + hy * (tip_u - 8) + py * (tip_v + 8))),
            (int(bx + hx * tip_end_u + px * tip_end_v),
             int(by + hy * tip_end_u + py * tip_end_v)),
        ]
        pygame.draw.polygon(screen, blade_color, tip_pts)
        pygame.draw.polygon(screen, (90, 100, 120), tip_pts, 1)

        # ── 4. 连接箍环 ──
        ring_r = 5
        pygame.draw.circle(screen, (130, 120, 110), (int(bx), int(by)), ring_r)
        pygame.draw.circle(screen, (80, 70, 60), (int(bx), int(by)), ring_r, 1)
        pygame.draw.circle(screen, (60, 55, 50), (int(bx), int(by)), 2)

    def _draw_shield(self, screen):
        """绘制风筝盾牌：金属边框 + 彩色填充 + 铆钉。"""
        ox, oy = self.owner.x, self.owner.y
        sx, sy = self.x, self.y

        dx = sx - ox
        dy = sy - oy
        dist = math.hypot(dx, dy)
        if dist < 0.001:
            return

        # 盾牌朝向：切线方向（垂直于半径方向）
        hx = dx / dist
        hy = dy / dist
        px = -hy
        py = hx

        # 盾牌局部坐标 (u 沿半径向外, v 沿切线)
        sh_w = self.defn.length  # 盾牌宽度
        sh_h = self.defn.width   # 盾牌高度

        # 风筝盾牌多边形点 (相对盾牌中心)
        # 上半部 (宽)
        kite_pts_local = [
            (0, -sh_h * 0.85),      # 顶部尖端
            (sh_w * 0.35, -sh_h * 0.55),   # 右上弧
            (sh_w * 0.65, -sh_h * 0.25),   # 右中上
            (sh_w * 0.5, sh_h * 0.15),     # 右中
            (sh_w * 0.15, sh_h * 0.5),     # 右下弧
            (0, sh_h * 0.85),               # 底部尖端
            (-sh_w * 0.15, sh_h * 0.5),    # 左下弧
            (-sh_w * 0.5, sh_h * 0.15),    # 左中
            (-sh_w * 0.65, -sh_h * 0.25),  # 左中上
            (-sh_w * 0.35, -sh_h * 0.55),  # 左上弧
        ]

        world_pts = []
        for u, v in kite_pts_local:
            wx = sx + hx * u + px * v
            wy = sy + hy * u + py * v
            world_pts.append((wx, wy))

        # 填充
        fill_color = self.defn.color
        pygame.draw.polygon(screen, fill_color, world_pts)

        # 金属边框
        border_color = (80, 85, 95)
        pygame.draw.polygon(screen, border_color, world_pts, 2)

        # 内层装饰线
        inner_pts = []
        for u, v in kite_pts_local:
            wx = sx + hx * u * 0.7 + px * v * 0.7
            wy = sy + hy * u * 0.7 + py * v * 0.7
            inner_pts.append((wx, wy))
        inner_border = (160, 170, 190)
        pygame.draw.polygon(screen, inner_border, inner_pts, 1)

        # 中央竖线（盾脊）
        top_y = sy + hy * (-sh_h * 0.75) + py * (-sh_h * 0.75) * 0
        bot_y = sy + hy * (sh_h * 0.75)
        # 使用局部坐标计算
        top_wx = sx + hx * 0 + px * 0
        top_wy = sy + hy * (-sh_h * 0.8) + py * 0
        bot_wx = sx + hx * 0 + px * 0
        bot_wy = sy + hy * (sh_h * 0.8) + py * 0
        # 简化：直接使用中心线
        ridge_top = (sx + hx * 0 - hy * (-sh_h * 0.75), sy + hy * 0 + hx * (-sh_h * 0.75))
        # Actually, let me just draw a simple center line parallel to orbit direction
        center_top = (sx + hy * (-sh_h * 0.7), sy + (-hx) * (-sh_h * 0.7))
        center_bot = (sx + hy * (sh_h * 0.7), sy + (-hx) * (sh_h * 0.7))
        pygame.draw.line(screen, (120, 140, 170),
                        (int(center_top[0]), int(center_top[1])),
                        (int(center_bot[0]), int(center_bot[1])), 1)

        # 四个铆钉
        rivet_color = (180, 185, 195)
        rivet_positions = [
            (0.35, -0.5),
            (-0.35, -0.5),
            (0.22, 0.35),
            (-0.22, 0.35),
        ]
        for ru, rv in rivet_positions:
            rx = sx + hx * (ru * sh_w) + px * (rv * sh_h)
            ry = sy + hy * (ru * sh_w) + py * (rv * sh_h)
            pygame.draw.circle(screen, rivet_color, (int(rx), int(ry)), 2)
            pygame.draw.circle(screen, (120, 125, 135), (int(rx), int(ry)), 2, 1)

    def _draw_bow(self, screen):
        """绘制弓箭：弧形弓身 + 弓弦。"""
        tx, ty = self._get_aim_target()
        dx = tx - self.owner.x
        dy = ty - self.owner.y
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            angle = math.atan2(dy, dx)
        else:
            angle = 0.0
        dir_x = math.cos(angle)
        dir_y = math.sin(angle)
        perp_x = -dir_y
        perp_y = dir_x
        ox, oy = self.owner.x, self.owner.y

        bow_len = self.defn.length  # ~50
        bow_curve = 10
        grip_x = ox + dir_x * self.owner.radius
        grip_y = oy + dir_y * self.owner.radius

        # 弓身（弧形）
        num_segs = 10
        bow_pts = []
        for i in range(num_segs + 1):
            t = i / num_segs
            u = (t - 0.5) * bow_len
            v = bow_curve * (1.0 - (2.0 * t - 1.0) ** 2)
            bx = grip_x + perp_x * u + dir_x * v
            by = grip_y + perp_y * u + dir_y * v
            bow_pts.append((int(bx), int(by)))
        if len(bow_pts) >= 2:
            pygame.draw.lines(screen, (140, 100, 60), False, bow_pts, 3)

        # 弓弦
        string_left = bow_pts[0]
        string_right = bow_pts[-1]
        pygame.draw.line(screen, (180, 170, 150), string_left, string_right, 1)

        # 搭箭点（握把位置）
        pygame.draw.circle(screen, (200, 50, 30), (int(grip_x), int(grip_y)), 2)

    def _draw_crossbow(self, screen):
        """绘制连弩：弩身在前 + 弓臂在前端 + 弦拉回扳机。"""
        tx, ty = self._get_aim_target()
        dx = tx - self.owner.x
        dy = ty - self.owner.y
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            angle = math.atan2(dy, dx)
        else:
            angle = 0.0
        dir_x = math.cos(angle)
        dir_y = math.sin(angle)
        perp_x = -dir_y
        perp_y = dir_x
        ox, oy = self.owner.x, self.owner.y

        stock_len = self.defn.length * 0.7
        prod_width = self.defn.length * 0.6

        # 弩身：从玩家前方延伸到更前方
        stock_back_x = ox + dir_x * self.owner.radius
        stock_back_y = oy + dir_y * self.owner.radius
        stock_front_x = ox + dir_x * (self.owner.radius + stock_len)
        stock_front_y = oy + dir_y * (self.owner.radius + stock_len)

        # 弩身（木质主体，后端宽前端窄）
        stock_pts = [
            (stock_back_x + perp_x * 4, stock_back_y + perp_y * 4),
            (stock_front_x + perp_x * 2, stock_front_y + perp_y * 2),
            (stock_front_x - perp_x * 2, stock_front_y - perp_y * 2),
            (stock_back_x - perp_x * 4, stock_back_y - perp_y * 4),
        ]
        pygame.draw.polygon(screen, (100, 75, 45), stock_pts)
        pygame.draw.polygon(screen, (70, 50, 30), stock_pts, 1)

        # 弓臂（横在弩身最前端）
        prod_x = stock_front_x
        prod_y = stock_front_y
        prod_left_x = prod_x + perp_x * prod_width
        prod_left_y = prod_y + perp_y * prod_width
        prod_right_x = prod_x - perp_x * prod_width
        prod_right_y = prod_y - perp_y * prod_width
        # 弓臂微微前弯
        prod_mid_x = prod_x + dir_x * 4
        prod_mid_y = prod_y + dir_y * 4
        pygame.draw.line(screen, (80, 80, 90),
                        (int(prod_left_x), int(prod_left_y)),
                        (int(prod_mid_x), int(prod_mid_y)), 3)
        pygame.draw.line(screen, (80, 80, 90),
                        (int(prod_mid_x), int(prod_mid_y)),
                        (int(prod_right_x), int(prod_right_y)), 3)

        # 弓弦（从弓臂两端拉回到扳机）
        trigger_x = stock_back_x + dir_x * stock_len * 0.3
        trigger_y = stock_back_y + dir_y * stock_len * 0.3
        pygame.draw.line(screen, (160, 150, 140),
                        (int(prod_left_x), int(prod_left_y)),
                        (int(trigger_x), int(trigger_y)), 1)
        pygame.draw.line(screen, (160, 150, 140),
                        (int(prod_right_x), int(prod_right_y)),
                        (int(trigger_x), int(trigger_y)), 1)

        # 扳机（垂直短杆）
        pygame.draw.line(screen, (60, 60, 70),
                        (int(trigger_x), int(trigger_y)),
                        (int(trigger_x + perp_x * 5), int(trigger_y + perp_y * 5)), 2)

    def _draw_katana(self, screen):
        """绘制武士刀：静止时刀尖指向敌人，斩击时垂直挥动。"""
        ox, oy = self.owner.x, self.owner.y

        blade_len = self.defn.length
        blade_w = max(2, self.defn.width)

        # 当前刀刃角度（静止时指向敌人，斩击时偏移）
        base_angle = self._slash_angle
        if self._slash_state == "idle":
            blade_angle = base_angle
        else:
            progress = 1.0 - (self._slash_timer / 0.2)
            if self._slash_state == "slash1":
                blade_angle = base_angle + math.radians(60 * (1.0 - 2.0 * progress))
            else:
                blade_angle = base_angle + math.radians(60 * (2.0 * progress - 1.0))

        dir_x = math.cos(blade_angle)
        dir_y = math.sin(blade_angle)
        perp_x = -dir_y
        perp_y = dir_x

        # 刀柄末端位置（主人后方）
        handle_rear_x = ox - dir_x * (self.owner.radius + 8)
        handle_rear_y = oy - dir_y * (self.owner.radius + 8)
        # 刀锷位置
        guard_x = ox + dir_x * (self.owner.radius + 6)
        guard_y = oy + dir_y * (self.owner.radius + 6)
        # 刀尖
        tip_x = guard_x + dir_x * blade_len
        tip_y = guard_y + dir_y * blade_len

        # ── 斩击刀光 ──
        if self._slash_state != "idle":
            progress = 1.0 - (self._slash_timer / 0.2)
            slash_alpha = int(120 * (1.0 - abs(progress - 0.5) * 2.0))
            sweep_r = self.owner.radius + blade_len + 15
            if slash_alpha > 0:
                arc_surf = pygame.Surface((sweep_r * 2 + 4, sweep_r * 2 + 4),
                                          pygame.SRCALPHA)
                # 均以 base_angle 为中心 ±60° 的 120° 身前弧
                # pygame.draw.arc 逆时针绘制 → 小角→大角走短弧
                a1 = -(base_angle + math.radians(60))
                a2 = -(base_angle - math.radians(60))
                arc_start = min(a1, a2)
                arc_end = max(a1, a2)
                arc_color = (255, 255, 255, slash_alpha)
                rect = pygame.Rect(2, 2, sweep_r * 2, sweep_r * 2)
                pygame.draw.arc(arc_surf, arc_color, rect,
                              arc_start, arc_end, 3)
                inner_color = (180, 210, 255, slash_alpha // 2)
                inner_r = sweep_r - 20
                inner_rect = pygame.Rect(sweep_r - inner_r + 2, sweep_r - inner_r + 2,
                                        inner_r * 2, inner_r * 2)
                pygame.draw.arc(arc_surf, inner_color, inner_rect,
                              arc_start, arc_end, 2)
                screen.blit(arc_surf,
                           (int(ox) - sweep_r - 2, int(oy) - sweep_r - 2))

        # ── 刀身（70%直身 + 30%刀尖弧线收窄） ──
        hw = blade_w * 0.5
        straight_ratio = 0.65
        straight_len = blade_len * straight_ratio
        tip_len = blade_len - straight_len

        # 刀背点（spine）和刀刃点（edge）
        num_segs = 10
        spine_pts = []
        edge_pts = []
        for i in range(num_segs + 1):
            t = i / num_segs
            if t <= straight_ratio:
                # 直身：等宽
                s = t / straight_ratio
                bx = guard_x + dir_x * straight_len * s
                by = guard_y + dir_y * straight_len * s
                spine_pts.append((int(bx + perp_x * hw), int(by + perp_y * hw)))
                edge_pts.append((int(bx - perp_x * hw), int(by - perp_y * hw)))
            else:
                # 刀尖：背弧内收，刃微收
                s = (t - straight_ratio) / (1.0 - straight_ratio)
                bx = guard_x + dir_x * (straight_len + tip_len * s)
                by = guard_y + dir_y * (straight_len + tip_len * s)
                # 刀背弧线内收至尖端
                spine_w = hw * (1.0 - s * s)
                spine_pts.append((int(bx + perp_x * spine_w), int(by + perp_y * spine_w)))
                # 刀刃微收至尖端
                edge_w = hw * (1.0 - s * 0.6)
                edge_pts.append((int(bx - perp_x * edge_w), int(by - perp_y * edge_w)))

        all_pts = spine_pts + list(reversed(edge_pts))
        blade_color = (200, 210, 220)
        pygame.draw.polygon(screen, blade_color, all_pts)
        pygame.draw.polygon(screen, (130, 140, 155), all_pts, 1)

        # 刃纹线（hamon）— 仅在直身部分
        hamon_pts = []
        for i in range(int(num_segs * straight_ratio) + 1):
            t = i / num_segs
            bx = guard_x + dir_x * blade_len * t
            by = guard_y + dir_y * blade_len * t
            hamon_pts.append((int(bx - perp_x * (hw * 0.1)),
                              int(by - perp_y * (hw * 0.1))))
        if len(hamon_pts) >= 2:
            pygame.draw.lines(screen, (230, 235, 245), False, hamon_pts, 1)

        # 刀尖高光线
        tip_mid_x = guard_x + dir_x * (straight_len + tip_len * 0.7)
        tip_mid_y = guard_y + dir_y * (straight_len + tip_len * 0.7)
        pygame.draw.line(screen, (240, 245, 255),
                        (int(tip_mid_x), int(tip_mid_y)),
                        (int(tip_x), int(tip_y)), 1)

        # ── 刀锷（tsuba 椭圆形护手） ──
        guard_w = blade_w + 8
        guard_h = 4
        guard_pts = [
            (guard_x + perp_x * guard_w, guard_y + perp_y * guard_w),
            (guard_x + dir_x * guard_h + perp_x * guard_w * 0.3,
             guard_y + dir_y * guard_h + perp_y * guard_w * 0.3),
            (guard_x + dir_x * guard_h - perp_x * guard_w * 0.3,
             guard_y + dir_y * guard_h - perp_y * guard_w * 0.3),
            (guard_x - perp_x * guard_w, guard_y - perp_y * guard_w),
            (guard_x - dir_x * guard_h - perp_x * guard_w * 0.3,
             guard_y - dir_y * guard_h - perp_y * guard_w * 0.3),
            (guard_x - dir_x * guard_h + perp_x * guard_w * 0.3,
             guard_y - dir_y * guard_h + perp_y * guard_w * 0.3),
        ]
        pygame.draw.polygon(screen, (55, 55, 65), guard_pts)
        pygame.draw.polygon(screen, (30, 30, 40), guard_pts, 1)

        # ── 刀柄（tsuka 缠绕柄） ──
        handle_len = blade_len * 0.38
        handle_end_x = guard_x - dir_x * handle_len
        handle_end_y = guard_y - dir_y * handle_len
        # 柄主体
        hw = blade_w + 1
        handle_pts = [
            (guard_x + perp_x * hw, guard_y + perp_y * hw),
            (handle_end_x + perp_x * hw * 0.9, handle_end_y + perp_y * hw * 0.9),
            (handle_end_x - perp_x * hw * 0.9, handle_end_y - perp_y * hw * 0.9),
            (guard_x - perp_x * hw, guard_y - perp_y * hw),
        ]
        pygame.draw.polygon(screen, (35, 35, 45), handle_pts)
        pygame.draw.polygon(screen, (50, 45, 35), handle_pts, 1)
        # 柄卷（ito 缠绕纹）
        for i in range(6):
            t = (i + 0.5) / 6
            hx = guard_x + (handle_end_x - guard_x) * t
            hy = guard_y + (handle_end_y - guard_y) * t
            w = hw * (0.7 + 0.3 * (i % 2))
            pygame.draw.line(screen, (70, 55, 30),
                           (int(hx + perp_x * w), int(hy + perp_y * w)),
                           (int(hx - perp_x * w), int(hy - perp_y * w)), 1)

        # 柄头（kashira）
        pygame.draw.circle(screen, (50, 45, 40),
                         (int(handle_end_x), int(handle_end_y)), blade_w // 2 + 2)
        pygame.draw.circle(screen, (30, 25, 20),
                         (int(handle_end_x), int(handle_end_y)), blade_w // 2 + 2, 1)

    def _draw_boomerang(self, screen):
        """绘制环绕待机的回旋镖（小V形）。"""
        ox, oy = self.owner.x, self.owner.y
        bx, by = self.x, self.y

        dx = bx - ox
        dy = by - oy
        dist = math.hypot(dx, dy)
        if dist < 0.001:
            return

        hx = dx / dist
        hy = dy / dist
        px = -hy
        py = hx

        arm = self.defn.length * 0.6
        wing = self.defn.width + 4

        # V 形两支
        pts = [(bx, by)]
        for sign in (1, -1):
            tip_x = bx + hx * arm + px * wing * sign
            tip_y = by + hy * arm + py * wing * sign
            mid_x = bx + hx * arm * 0.55 + px * wing * 0.3 * sign
            mid_y = by + hy * arm * 0.55 + py * wing * 0.3 * sign
            pts.append((mid_x, mid_y))
            pts.append((tip_x, tip_y))

        pygame.draw.polygon(screen, self.defn.color, pts)
        pygame.draw.polygon(screen, (100, 60, 20), pts, 2)

        # 连接点
        pygame.draw.circle(screen, (180, 140, 80), (int(bx), int(by)), 3)

    def _draw_dual_axe(self, screen):
        """
        绘制：恶魔双战斧
        风格：黑曜石/暗红金属 + 能量核心 + 锯齿刃
        """
        ox, oy = self.owner.x, self.owner.y
        if not self.owner.alive:
            return

        # 定义配色常量
        METAL_DARK = (30, 15, 15)      # 黑曜石黑
        METAL_MID = (65, 25, 25)       # 暗红铁锈
        METAL_BRIGHT = (120, 40, 40)   # 亮面金属
        GLOW_CORE = (255, 80, 40)      # 核心橙红光
        EDGE_COLOR = (200, 100, 100)   # 刃口高光

        for side in ("left", "right"):
            # 获取基础位置与角度
            bx, by, handle_angle, px, py = self._get_axe_blade_pos(side)
            swing_offset = self._get_axe_swing_offset(side)
            swing_ratio = abs(swing_offset) / math.radians(85)

            # 向量计算：手柄方向(h) 和 垂直方向(p)
            hx = math.cos(handle_angle)
            hy = math.sin(handle_angle)
            # 左侧刃口逆时针延展，右侧顺时针延展（镜像对称）
            if side == "left":
                perp_x = -hy
                perp_y = hx
            else:
                perp_x = hy
                perp_y = -hx

            # ==========================
            # 1. 斧柄 (带有金属纹理和尖刺)
            # ==========================
            grip_w = 5  # 柄宽
            # 柄的节点 (增加一点不规则感)
            handle_pts = [
                (px + perp_x * grip_w * 0.8, py + perp_y * grip_w * 0.8),
                (px - perp_x * grip_w * 0.8, py - perp_y * grip_w * 0.8),
                (bx - perp_x * 2, by - perp_y * 2),  # 连接处变细
                (bx + perp_x * 2, by + perp_y * 2),
            ]

            # 绘制柄主体 (深色)
            pygame.draw.polygon(screen, METAL_DARK, [(int(x), int(y)) for x, y in handle_pts])

            # 绘制柄上的"缠绕"或"脊刺"细节
            segments = 4
            for i in range(segments):
                t = i / (segments - 1)
                seg_x = px + (bx - px) * t
                seg_y = py + (by - py) * t
                # 简单的尖刺装饰
                spike_len = 3 if i % 2 == 0 else 2
                p1 = (seg_x + perp_x * (grip_w + spike_len), seg_y + perp_y * (grip_w + spike_len))
                p2 = (seg_x - perp_x * (grip_w + spike_len), seg_y - perp_y * (grip_w + spike_len))
                pygame.draw.line(screen, METAL_MID, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 1)

            # 柄的高光
            hl_start = (px + perp_x * grip_w * 0.4, py + perp_y * grip_w * 0.4)
            hl_end = (bx + perp_x * 1, by + perp_y * 1)
            pygame.draw.line(screen, (80, 40, 40), (int(hl_start[0]), int(hl_start[1])), (int(hl_end[0]), int(hl_end[1])), 1)

            # ==========================
            # 2. 斧刃 (不规则、锯齿状、黑红配色)
            # ==========================
            blade_span = 36.0   # 刃长
            blade_depth = 22.0  # 刃宽

            # 刃口张角方向：左逆时针、右顺时针（镜像）
            angle_dir = -1 if side == "right" else 1

            # 斧刃顶点列表
            blade_pts = []

            # 上钩/顶部尖刺
            top_spike = (bx + hx * 5 + perp_x * (blade_span * 0.4), by + hy * 5 + perp_y * (blade_span * 0.4))
            blade_pts.append(top_spike)

            # 主刃口
            num_pts = 12
            for i in range(num_pts):
                t = i / (num_pts - 1)
                angle_dist = (t - 0.1) * math.radians(110) * angle_dir
                dist = blade_depth + math.sin(t * math.pi) * 10
                serration = 2.0 if i % 2 == 0 else 0.0
                rx = bx + math.cos(handle_angle + angle_dist) * (dist + serration)
                ry = by + math.sin(handle_angle + angle_dist) * (dist + serration)
                blade_pts.append((rx, ry))

            # 底部连接点
            bottom_anchor = (bx + hx * 2 - perp_x * 5, by + hy * 2 - perp_y * 5)
            blade_pts.append(bottom_anchor)

            # 内部凹陷 (连接回核心)
            inner_core = (bx, by)
            blade_pts.append(inner_core)

            # --- 绘制斧刃主体 ---
            int_pts = [(int(x), int(y)) for x, y in blade_pts]
            
            # 填充：深色金属
            pygame.draw.polygon(screen, METAL_DARK, int_pts)
            
            # 边缘光：暗红色描边
            pygame.draw.polygon(screen, METAL_MID, int_pts, 2)

            # 刃口高光 (只画最外侧的弧线)
            edge_line = [int_pts[1]] + int_pts[2:-2] + [int_pts[-3]]
            if len(edge_line) > 2:
                # 挥砍时高光变色变亮
                current_edge_color = EDGE_COLOR if swing_ratio < 0.1 else (255, 150, 100)
                pygame.draw.lines(screen, current_edge_color, False, edge_line, 1)

            # ==========================
            # 3. 核心能量球 (斧头连接处的眼睛/红宝石)
            # ==========================
            core_r = 4 + int(2 * swing_ratio) # 挥砍时充能变大
            # 脉冲效果
            pulse = abs(math.sin(pygame.time.get_ticks() * 0.01)) * 30
            core_color = (
                min(255, GLOW_CORE[0] + pulse),
                min(255, GLOW_CORE[1]),
                min(255, GLOW_CORE[2])
            )
            pygame.draw.circle(screen, core_color, (int(bx), int(by)), core_r)
            # 核心外圈黑边
            pygame.draw.circle(screen, METAL_DARK, (int(bx), int(by)), core_r, 1)

            # ==========================
            # 4. 挥砍特效 (暗红残影/血光)
            # ==========================
            if self._is_axe_active(side) and swing_ratio > 0.2:
                # 计算挥砍弧度
                sweep_alpha = int(100 * swing_ratio)
                if sweep_alpha > 20:
                    # 创建一个用于绘制半透明特效的表面
                    radius = self.owner.radius + 20 + blade_span
                    arc_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
                    
                    # 颜色：暗红带一点橙
                    arc_color = (255, 50, 20, sweep_alpha)
                    
                    # 绘制多条弧线形成拖尾感
                    rect = pygame.Rect(2, 2, radius * 2 - 4, radius * 2 - 4)
                    center_angle = handle_angle
                    
                    # 根据挥砍方向调整起始角
                    start_a = -(center_angle + math.radians(40) * (1-swing_ratio))
                    end_a = -(center_angle - math.radians(40) * (1-swing_ratio))
                    
                    pygame.draw.arc(arc_surf, arc_color, rect, start_a, end_a, 6)
                    
                    screen.blit(arc_surf, (int(ox) - radius, int(oy) - radius))

            # ==========================
            # 5. 尾部装饰 (柄的末端)
            # ==========================
            # 简单的柄尾尖刺
            tail_len = 8
            tail_x = px - hx * tail_len
            tail_y = py - hy * tail_len
            pygame.draw.line(screen, METAL_MID, (int(px), int(py)), (int(tail_x), int(tail_y)), 4)

    def _draw_sniper(self, screen):
        """绘制狙击枪：长枪管 + 瞄准镜 + 两脚架。"""
        tx, ty = self._get_aim_target()

        dx = tx - self.owner.x
        dy = ty - self.owner.y
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            angle = math.atan2(dy, dx)
        else:
            angle = 0.0

        dir_x = math.cos(angle)
        dir_y = math.sin(angle)
        perp_x = -dir_y
        perp_y = dir_x

        barrel_len = self.defn.length  # ~50
        barrel_width = self.defn.width  # ~3
        ox, oy = self.owner.x, self.owner.y

        # 枪管起点（玩家边缘）
        start_x = ox + dir_x * self.owner.radius
        start_y = oy + dir_y * self.owner.radius
        muzzle_x = ox + dir_x * (self.owner.radius + barrel_len)
        muzzle_y = oy + dir_y * (self.owner.radius + barrel_len)

        # 1. 两脚架（枪管中段下方）
        bipod_x = start_x + dir_x * barrel_len * 0.5
        bipod_y = start_y + dir_y * barrel_len * 0.5
        for side in (-1, 1):
            leg_x = bipod_x + perp_x * side * 8
            leg_y = bipod_y + perp_y * side * 8
            pygame.draw.line(screen, (60, 65, 70),
                           (int(bipod_x), int(bipod_y)),
                           (int(leg_x), int(leg_y)), 2)

        # 2. 枪管（细长矩形）
        barrel_points = [
            (start_x + perp_x * barrel_width * 0.5, start_y + perp_y * barrel_width * 0.5),
            (muzzle_x + perp_x * barrel_width * 0.6, muzzle_y + perp_y * barrel_width * 0.6),
            (muzzle_x - perp_x * barrel_width * 0.6, muzzle_y - perp_y * barrel_width * 0.6),
            (start_x - perp_x * barrel_width * 0.5, start_y - perp_y * barrel_width * 0.5),
        ]
        pygame.draw.polygon(screen, self.defn.color, barrel_points)
        pygame.draw.polygon(screen, (40, 45, 50), barrel_points, 1)

        # 3. 瞄准镜（枪管上方）
        scope_x = start_x + dir_x * barrel_len * 0.35
        scope_y = start_y + dir_y * barrel_len * 0.35
        scope_len = 12
        scope_w = 4
        scope_pts = [
            (scope_x + dir_x * scope_len + perp_x * scope_w, scope_y + dir_y * scope_len + perp_y * scope_w),
            (scope_x + dir_x * scope_len - perp_x * scope_w, scope_y + dir_y * scope_len - perp_y * scope_w),
            (scope_x - perp_x * scope_w, scope_y - perp_y * scope_w),
            (scope_x + perp_x * scope_w, scope_y + perp_y * scope_w),
        ]
        pygame.draw.polygon(screen, (50, 55, 60), scope_pts)
        # 镜片反光
        lens_x = scope_x + dir_x * scope_len
        lens_y = scope_y + dir_y * scope_len
        pygame.draw.circle(screen, (120, 180, 255),
                         (int(lens_x), int(lens_y)), scope_w // 2)

        # 4. 枪托（玩家后方）
        stock_x = ox - dir_x * self.owner.radius * 0.6
        stock_y = oy - dir_y * self.owner.radius * 0.6
        stock_len = 10
        stock_w = 5
        stock_pts = [
            (stock_x - dir_x * stock_len + perp_x * stock_w, stock_y - dir_y * stock_len + perp_y * stock_w),
            (stock_x - dir_x * stock_len - perp_x * stock_w, stock_y - dir_y * stock_len - perp_y * stock_w),
            (stock_x + perp_x * stock_w * 0.6, stock_y + perp_y * stock_w * 0.6),
            (stock_x - perp_x * stock_w * 0.6, stock_y - perp_y * stock_w * 0.6),
        ]
        pygame.draw.polygon(screen, (80, 70, 60), stock_pts)

    def _draw_gatling(self, screen):
        """绘制加特林：6管旋转枪管 + 弹药箱。"""
        tx, ty = self._get_aim_target()

        dx = tx - self.owner.x
        dy = ty - self.owner.y
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            angle = math.atan2(dy, dx)
        else:
            angle = 0.0

        dir_x = math.cos(angle)
        dir_y = math.sin(angle)
        perp_x = -dir_y
        perp_y = dir_x

        barrel_len = self.defn.length  # ~30
        ox, oy = self.owner.x, self.owner.y

        # 枪身中心（玩家边缘前方）
        hub_x = ox + dir_x * (self.owner.radius + 5)
        hub_y = oy + dir_y * (self.owner.radius + 5)

        # 弹药箱（后方）
        ammo_x = ox - dir_x * self.owner.radius * 0.5
        ammo_y = oy - dir_y * self.owner.radius * 0.5
        ammo_w, ammo_h = 10, 8
        ammo_rect = pygame.Rect(ammo_x - ammo_w // 2, ammo_y - ammo_h // 2, ammo_w, ammo_h)
        pygame.draw.rect(screen, (60, 65, 55), ammo_rect)
        pygame.draw.rect(screen, (40, 45, 40), ammo_rect, 1)

        # 弹链（从弹药箱到枪身）
        pygame.draw.line(screen, (80, 70, 40),
                       (int(ammo_x), int(ammo_y)),
                       (int(hub_x), int(hub_y)), 2)

        # 6管旋转枪管
        spin = self.age * 15.0  # 旋转速度
        barrel_r = 4
        for i in range(6):
            ba = spin + i * math.pi / 3
            bx = hub_x + math.cos(ba) * barrel_r
            by = hub_y + math.sin(ba) * barrel_r
            ex = bx + dir_x * barrel_len
            ey = by + dir_y * barrel_len
            pygame.draw.line(screen, (80, 85, 90), (int(bx), int(by)), (int(ex), int(ey)), 2)
            # 管口
            pygame.draw.circle(screen, (50, 50, 55),
                             (int(bx), int(by)), 1)

        # 中央轮毂
        pygame.draw.circle(screen, (70, 75, 80), (int(hub_x), int(hub_y)), barrel_r + 1)
        pygame.draw.circle(screen, (50, 55, 60), (int(hub_x), int(hub_y)), barrel_r + 1, 1)

        # 握把（下方）
        grip_x = hub_x - dir_x * 3
        grip_y = hub_y - dir_y * 3
        pygame.draw.line(screen, (100, 90, 70),
                       (int(grip_x), int(grip_y)),
                       (int(grip_x + perp_x * 8), int(grip_y + perp_y * 8)), 3)

    def _get_launcher_muzzle(self) -> tuple[float, float]:
        """计算发射筒口位置。"""
        tx, ty = self._get_aim_target()
        dx = tx - self.owner.x
        dy = ty - self.owner.y
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            angle = math.atan2(dy, dx)
        else:
            angle = 0.0
        dir_x = math.cos(angle)
        dir_y = math.sin(angle)
        ox, oy = self.owner.x, self.owner.y
        start_x = ox - dir_x * self.owner.radius * 0.3
        start_y = oy - dir_y * self.owner.radius * 0.3
        muzzle_x = start_x + dir_x * self.defn.length
        muzzle_y = start_y + dir_y * self.defn.length
        return muzzle_x, muzzle_y

    def _draw_launcher(self, screen):
        """绘制肩扛导弹发射筒。"""
        tx, ty = self._get_aim_target()

        dx = tx - self.owner.x
        dy = ty - self.owner.y
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            angle = math.atan2(dy, dx)
        else:
            angle = 0.0

        dir_x = math.cos(angle)
        dir_y = math.sin(angle)
        perp_x = -dir_y
        perp_y = dir_x

        tube_len = self.defn.length  # ~64
        tube_w = self.defn.width    # ~10
        ox, oy = self.owner.x, self.owner.y

        # 发射筒起点（玩家后方）
        start_x = ox - dir_x * self.owner.radius * 0.3
        start_y = oy - dir_y * self.owner.radius * 0.3
        end_x = start_x + dir_x * tube_len
        end_y = start_y + dir_y * tube_len

        # 筒身（粗圆管）
        tube_points = [
            (start_x + perp_x * tube_w, start_y + perp_y * tube_w),
            (end_x + perp_x * tube_w, end_y + perp_y * tube_w),
            (end_x - perp_x * tube_w, end_y - perp_y * tube_w),
            (start_x - perp_x * tube_w, start_y - perp_y * tube_w),
        ]
        pygame.draw.polygon(screen, self.defn.color, tube_points)
        pygame.draw.polygon(screen, (40, 50, 40), tube_points, 2)

        # 筒口高光
        pygame.draw.line(screen, (100, 120, 100),
                       (int(end_x + perp_x * tube_w), int(end_y + perp_y * tube_w)),
                       (int(end_x - perp_x * tube_w), int(end_y - perp_y * tube_w)), 2)

        # 肩托
        stock_x = start_x - dir_x * 6
        stock_y = start_y - dir_y * 6
        pygame.draw.line(screen, (60, 65, 55),
                       (int(start_x + perp_x * tube_w * 0.3), int(start_y + perp_y * tube_w * 0.3)),
                       (int(stock_x), int(stock_y)), 3)
        pygame.draw.line(screen, (60, 65, 55),
                       (int(start_x - perp_x * tube_w * 0.3), int(start_y - perp_y * tube_w * 0.3)),
                       (int(stock_x), int(stock_y)), 3)

        # 瞄准具（筒身上方小突起）
        sight_x = start_x + dir_x * tube_len * 0.15
        sight_y = start_y + dir_y * tube_len * 0.15
        pygame.draw.circle(screen, (200, 50, 30),
                         (int(sight_x + perp_x * (tube_w + 2)),
                          int(sight_y + perp_y * (tube_w + 2))), 2)


# ── WeaponPickup ─────────────────────────────────────────────────────────────

class WeaponPickup:
    """掉落在地面上的武器图标，可被玩家拾取。"""

    def __init__(self, x: float, y: float, defn: WeaponDef):
        self.x = x
        self.y = y
        self.defn = defn
        self.radius = 18
        self.age = 0.0
        self.lifetime = 15.0
        self._pulse_seed = random.uniform(0, 100)

    def update(self, dt: float):
        self.age += dt

    def is_expired(self) -> bool:
        return self.age >= self.lifetime

    def collides_with(self, player) -> bool:
        dx = self.x - player.x
        dy = self.y - player.y
        return math.hypot(dx, dy) < player.radius + self.radius

    def draw(self, screen):
        now = pygame.time.get_ticks() / 1000.0
        pulse = (math.sin(now * 3.0 + self._pulse_seed) + 1.0) / 2.0

        # 外圈脉冲光环
        glow_radius = self.radius + 8 + pulse * 6
        glow_alpha = int(40 + pulse * 80)
        glow_surf = pygame.Surface((glow_radius * 2 + 4, glow_radius * 2 + 4), pygame.SRCALPHA)
        glow_color = (*self.defn.color, glow_alpha)
        pygame.draw.circle(glow_surf, glow_color,
                         (glow_radius + 2, glow_radius + 2), glow_radius)
        screen.blit(glow_surf, (int(self.x) - glow_radius - 2,
                                 int(self.y) - glow_radius - 2))

        # 实心图标
        pygame.draw.circle(screen, self.defn.color,
                         (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(screen, (60, 60, 60),
                         (int(self.x), int(self.y)), self.radius, 2)

        # 内圈高光
        inner_r = self.radius - 4
        inner_color = tuple(min(255, c + 60) for c in self.defn.color)
        pygame.draw.circle(screen, inner_color,
                         (int(self.x), int(self.y)), inner_r, 1)

        # 武器名称（小字）
        font = pygame.font.SysFont("WenQuanYi Micro Hei", 11)
        name_surf = font.render(self.defn.name, True, self.defn.color)
        screen.blit(name_surf, (int(self.x) - name_surf.get_width() // 2,
                                int(self.y) + self.radius + 4))
