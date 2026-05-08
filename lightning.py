"""闪电/光束类技能系统 —— 折线状闪电技能。"""

import math
import random
from dataclasses import dataclass

import pygame

from venue import ARENA_CENTER, ARENA_RADIUS


@dataclass
class LightningDef:
    """定义闪电技能的属性。"""
    name: str
    cooldown: float
    damage: int
    color: tuple[int, int, int]
    bolt_count: int                # 闪电条数
    bolt_length: float             # 每条闪电总长度
    segment_count: int             # 折线段数
    jitter: float                  # 折线最大偏移量
    duration: float                # 闪电存留时间（秒）
    width: int                     # 线宽
    self_speed_mult: float         # 释放期间自身速度倍率
    self_dmg_reduction: float      # 释放期间自身伤害减免 (0-1)
    target_slow_mult: float        # 目标减速倍率
    target_slow_duration: float    # 目标减速持续（秒）


class LightningBolt:
    """一条折线闪电实例，从释放点向外延伸，由多个随机偏移的线段组成。"""

    def __init__(self, x: float, y: float, angle: float,
                 owner_id: str, defn: LightningDef, owner_team: int = 0):
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.defn = defn
        self.age = 0.0

        # Generate zigzag points
        self.points = [(x, y)]
        seg_len = defn.bolt_length / defn.segment_count
        perp_angle = angle + math.pi / 2

        for i in range(1, defn.segment_count + 1):
            bx = x + math.cos(angle) * seg_len * i
            by = y + math.sin(angle) * seg_len * i
            if i < defn.segment_count:
                offset = random.uniform(-defn.jitter, defn.jitter)
                bx += math.cos(perp_angle) * offset
                by += math.sin(perp_angle) * offset
            self.points.append((bx, by))

    def update(self, dt: float):
        self.age += dt

    def is_expired(self) -> bool:
        return self.age >= self.defn.duration

    def collides_with(self, player) -> bool:
        """检测玩家圆与折线各段的碰撞。"""
        return self.collides_with_point(player.x, player.y, player.radius)

    def collides_with_point(self, px: float, py: float, radius: float) -> bool:
        """检测一个圆与折线各段的碰撞。"""
        threshold = radius + self.defn.width / 2
        for i in range(len(self.points) - 1):
            x1, y1 = self.points[i]
            x2, y2 = self.points[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0 and dy == 0:
                dist = math.hypot(px - x1, py - y1)
            else:
                t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
                t = max(0.0, min(1.0, t))
                cx = x1 + t * dx
                cy = y1 + t * dy
                dist = math.hypot(px - cx, py - cy)
            if dist < threshold:
                return True
        return False

    def draw(self, screen):
        """绘制折线闪电。"""
        if len(self.points) >= 2:
            pygame.draw.lines(screen, self.defn.color, False,
                              [(int(x), int(y)) for x, y in self.points],
                              self.defn.width)


# ── Lightning Trap ────────────────────────────────────────────────────────────────


@dataclass
class LightningTrapDef:
    """定义闪电陷阱技能的属性。"""
    name: str
    cooldown: float
    damage: float                    # shock DPS
    color: tuple[int, int, int]      # bolt line color during travel
    bolt_count: int                  # 散射条数
    bolt_length: float               # 移动时闪电尾迹长度
    bolt_speed: float                # 移动速度 (px/s)
    travel_duration: float           # 移动阶段时长 (秒)
    trap_radius: float               # 陷阱圆点半径
    trap_color: tuple[int, int, int] # 陷阱圆点颜色
    shock_duration: float            # 电击持续 (秒)
    shock_slow_mult: float           # 电击减速倍率


class LightningTrapBolt:
    """一条闪电陷阱 —— TRAVEL阶段快速移动并反弹，TRAP阶段静止为黄色圆点。"""

    def __init__(self, x: float, y: float, angle: float,
                 owner_id: str, defn: LightningTrapDef, owner_team: int = 0):
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.defn = defn
        self.age = 0.0
        self.state = "TRAVEL"
        self._triggered = False

        self.head_x = float(x)
        self.head_y = float(y)

        self.vx = math.cos(angle) * defn.bolt_speed
        self.vy = math.sin(angle) * defn.bolt_speed

        # Short trail for bolt body visual during travel
        self.trail: list[tuple[float, float]] = [(x, y)]

    def update(self, dt: float):
        self.age += dt
        if self.state == "TRAVEL":
            self.head_x += self.vx * dt
            self.head_y += self.vy * dt

            self.trail.append((self.head_x, self.head_y))
            max_trail = 8
            if len(self.trail) > max_trail:
                self.trail = self.trail[-max_trail:]

            # Bounce off arena boundary
            dx = self.head_x - ARENA_CENTER[0]
            dy = self.head_y - ARENA_CENTER[1]
            dist = math.hypot(dx, dy)
            limit = ARENA_RADIUS - self.defn.trap_radius - 2
            if dist >= limit and dist > 0.001:
                nx = dx / dist
                ny = dy / dist
                dot = self.vx * nx + self.vy * ny
                self.vx -= 2 * dot * nx
                self.vy -= 2 * dot * ny
                self.head_x = ARENA_CENTER[0] + nx * limit
                self.head_y = ARENA_CENTER[1] + ny * limit

            if self.age >= self.defn.travel_duration:
                self.state = "TRAP"

    def is_expired(self) -> bool:
        if self._triggered:
            return True
        # Safety timeout for traps: 20s
        if self.state == "TRAP" and self.age > self.defn.travel_duration + 20.0:
            return True
        return False

    def trigger(self):
        self._triggered = True

    def collides_with_player(self, player) -> bool:
        """TRAP阶段检测玩家圆是否碰到陷阱圆点。"""
        if self.state != "TRAP":
            return False
        dx = self.head_x - player.x
        dy = self.head_y - player.y
        return math.hypot(dx, dy) < player.radius + self.defn.trap_radius

    def collides_with_pet(self, pet) -> bool:
        """TRAP阶段检测宠物是否碰到陷阱圆点。"""
        if self.state != "TRAP":
            return False
        if isinstance(pet, SpiderPet):
            px, py = pet.x, pet.y
            pr = pet._body_radius()
        else:
            px, py = pet.segments[0]
            pr = pet._head_radius()
        dx = self.head_x - px
        dy = self.head_y - py
        return math.hypot(dx, dy) < pr + self.defn.trap_radius

    def apply_shock(self, target):
        """对目标（player或pet）施加电击效果。"""
        target.slow_mult = self.defn.shock_slow_mult
        target.slow_timer = self.defn.shock_duration
        target.shock_timer = self.defn.shock_duration
        target.shock_dps = self.defn.damage
        self.trigger()

    def draw(self, screen):
        if self.state == "TRAVEL":
            # Draw short zigzag bolt body trailing behind head
            if len(self.trail) >= 2:
                pts = []
                for i, (tx, ty) in enumerate(self.trail):
                    jitter_x = random.uniform(-2, 2) if i % 2 == 0 else random.uniform(-2, 2)
                    jitter_y = random.uniform(-2, 2) if i % 2 == 1 else random.uniform(-2, 2)
                    pts.append((int(tx + jitter_x), int(ty + jitter_y)))
                if len(pts) >= 2:
                    r, g, b = self.defn.color
                    glow = (r, g, b, 80)
                    line_surf = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA)
                    pygame.draw.lines(line_surf, glow, False, pts, 3)
                    screen.blit(line_surf, (0, 0))
                    pygame.draw.lines(screen, self.defn.color, False, pts, 1)
        elif self.state == "TRAP":
            # Yellow dot with glow
            cx, cy = int(self.head_x), int(self.head_y)
            # Outer glow
            glow_r = int(self.defn.trap_radius * 2.5)
            glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            for r in range(glow_r, 0, -1):
                alpha = max(1, int(50 * (1 - r / glow_r)))
                pygame.draw.circle(glow_surf, (255, 255, 50, alpha), (glow_r, glow_r), r)
            screen.blit(glow_surf, (cx - glow_r, cy - glow_r))
            # Core dot
            pygame.draw.circle(screen, self.defn.trap_color, (cx, cy), self.defn.trap_radius)
            pygame.draw.circle(screen, (255, 255, 255), (cx, cy), max(1, self.defn.trap_radius // 2))


# Forward import for type check in LightningTrapBolt.collides_with_pet
from pet import SpiderPet
