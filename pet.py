"""宠物/召唤物技能系统 —— 可被攻击、有独立HP、可追踪目标的召唤物。"""

import math
import random
from dataclasses import dataclass
from enum import Enum

import pygame

from venue import ARENA_CENTER, ARENA_RADIUS


class PetMovement(Enum):
    CHASE = "chase"  # 追踪目标


@dataclass
class PetDef:
    """定义宠物技能的属性。"""
    name: str
    cooldown: float
    damage: float
    color: tuple[int, int, int]
    hp: int                       # 宠物自身血量
    speed: float                  # 移动速度 (px/s)
    lifetime: float | None        # 存留时间（秒），None 表示永久
    body_length: float            # 身体总长度（像素）
    body_width: int               # 身体粗细（像素）
    segment_count: int = 12       # 身体段数
    wiggle_amplitude: float = 5.0 # 蛇形摆动幅度
    wiggle_frequency: float = 3.0 # 蛇形摆动频率
    movement_type: PetMovement = PetMovement.CHASE


class Pet:
    """一个宠物/召唤物实例，有独立HP、可被攻击。蛇形身体由多个跟随段组成。"""

    def __init__(self, x: float, y: float, owner_id: str,
                 target, defn: PetDef):
        self.owner_id = owner_id
        self.target = target
        self.defn = defn
        self.age = 0.0
        self.hp = float(defn.hp)

        seg_spacing = defn.body_length / defn.segment_count

        # Spread body segments behind the spawn point (away from target)
        if target is not None:
            tdx = target.x - x
            tdy = target.y - y
        else:
            tdx, tdy = 0.0, -1.0
        tdist = math.hypot(tdx, tdy)
        if tdist < 0.001:
            tdx, tdy = 0.0, -1.0
            tdist = 1.0
        back_dir_x = -tdx / tdist
        back_dir_y = -tdy / tdist

        self.segments: list[tuple[float, float]] = []
        for i in range(defn.segment_count):
            self.segments.append((
                x + back_dir_x * i * seg_spacing,
                y + back_dir_y * i * seg_spacing,
            ))

        self._seg_spacing = seg_spacing
        self._wiggle_phase = random.uniform(0, 2 * math.pi)
        self.slow_mult = 1.0

    # ── Convenience properties ─────────────────────────────────────────────────
    @property
    def x(self):
        return self.segments[0][0]

    @property
    def y(self):
        return self.segments[0][1]

    def _head_radius(self) -> float:
        return self.defn.body_width * 0.5 + 4

    # ── Update ─────────────────────────────────────────────────────────────────
    def update(self, dt: float):
        self.age += dt
        self._wiggle_phase += dt * self.defn.wiggle_frequency
        self.slow_mult = 1.0  # reset each frame; trail collision may reduce it

        # Determine target position
        if self.target is not None and self.target.alive:
            tx, ty = self.target.x, self.target.y
        else:
            # Keep moving in current heading direction
            if len(self.segments) >= 2:
                hx, hy = self.segments[0]
                px, py = self.segments[1]
                dx_dir = hx - px
                dy_dir = hy - py
                d = math.hypot(dx_dir, dy_dir)
                if d > 0.001:
                    tx = hx + dx_dir / d * 500
                    ty = hy + dy_dir / d * 500
                else:
                    tx, ty = hx, hy
            else:
                tx, ty = self.segments[0]

        # Move head toward target at fixed speed
        head_x, head_y = self.segments[0]
        dx = tx - head_x
        dy = ty - head_y
        dist = math.hypot(dx, dy)

        if dist > 0.001:
            speed = self.defn.speed * self.slow_mult
            move_x = dx / dist * speed * dt
            move_y = dy / dist * speed * dt
        else:
            move_x = move_y = 0.0

        new_head_x = head_x + move_x
        new_head_y = head_y + move_y

        # Constrain head to arena
        new_head_x, new_head_y = self._clamp_to_arena(new_head_x, new_head_y)

        # Build new segments: head moves, each segment follows the one ahead
        new_segments = [(new_head_x, new_head_y)]
        for i in range(1, len(self.segments)):
            prev_x, prev_y = new_segments[i - 1]
            seg_x, seg_y = self.segments[i]
            sdx = prev_x - seg_x
            sdy = prev_y - seg_y
            sdist = math.hypot(sdx, sdy)
            if sdist > self._seg_spacing:
                seg_x += sdx / sdist * (sdist - self._seg_spacing)
                seg_y += sdy / sdist * (sdist - self._seg_spacing)
            # Soft-clamp each segment to arena
            seg_x, seg_y = self._clamp_to_arena(seg_x, seg_y)
            new_segments.append((seg_x, seg_y))

        self.segments = new_segments

    def _clamp_to_arena(self, x: float, y: float):
        """软钳制到竞技场内。"""
        dx = x - ARENA_CENTER[0]
        dy = y - ARENA_CENTER[1]
        dist = math.hypot(dx, dy)
        limit = ARENA_RADIUS - self.defn.body_width * 0.5
        if dist > limit and dist > 0.001:
            x = ARENA_CENTER[0] + dx / dist * limit
            y = ARENA_CENTER[1] + dy / dist * limit
        return x, y

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def is_expired(self) -> bool:
        if self.hp <= 0:
            return True
        if self.defn.lifetime is not None and self.age >= self.defn.lifetime:
            return True
        return False

    def take_damage(self, amount: float):
        self.hp -= amount

    # ── Collision ──────────────────────────────────────────────────────────────
    def collides_with(self, player) -> bool:
        """检测玩家圆是否碰到蛇头。"""
        head_x, head_y = self.segments[0]
        dx = head_x - player.x
        dy = head_y - player.y
        return math.hypot(dx, dy) < player.radius + self._head_radius()

    def head_collides_with_circle(self, cx: float, cy: float, radius: float) -> bool:
        """检测一个圆形是否与蛇头碰撞。"""
        head_x, head_y = self.segments[0]
        dx = head_x - cx
        dy = head_y - cy
        return math.hypot(dx, dy) < radius + self._head_radius()

    # ── Render ─────────────────────────────────────────────────────────────────
    def draw(self, screen):
        """绘制蛇形宠物——头大尾小、有眼睛、身体有摆动。"""
        if len(self.segments) < 2:
            return

        n = len(self.segments)

        # Draw body from tail to head so head renders on top
        for i in range(n - 1, 0, -1):
            x, y = self.segments[i]
            # t: 0 at tail, 1 at head
            t = 1.0 - i / (n - 1)

            # Perpendicular wiggle offset
            wig_x = wig_y = 0.0
            if i < n - 1:
                px, py = self.segments[i + 1]
                nx, ny = self.segments[i - 1]
                pdx = px - nx
                pdy = py - ny
                plen = math.hypot(pdx, pdy)
                if plen > 0.001:
                    perp_x = -pdy / plen
                    perp_y = pdx / plen
                    amp = math.sin(self._wiggle_phase + t * math.pi * 3) * self.defn.wiggle_amplitude * (1.0 - t)
                    wig_x = perp_x * amp
                    wig_y = perp_y * amp

            # Radius: smaller at tail, larger near head
            r = self.defn.body_width * 0.3 + self.defn.body_width * 0.7 * t
            # Color: darker at tail
            shade = 0.3 + 0.7 * t
            color = (
                int(self.defn.color[0] * shade),
                int(self.defn.color[1] * shade),
                int(self.defn.color[2] * shade),
            )
            pygame.draw.circle(screen, color,
                             (int(x + wig_x), int(y + wig_y)), max(2, int(r)))

        # Draw head
        head_x, head_y = self.segments[0]
        head_r = int(self._head_radius())

        # Head wiggle
        if n >= 2:
            nx, ny = self.segments[1]
            hdx = head_x - nx
            hdy = head_y - ny
            hlen = math.hypot(hdx, hdy)
            if hlen > 0.001:
                perp_x = -hdy / hlen
                perp_y = hdx / hlen
                wig_amt = math.sin(self._wiggle_phase) * self.defn.wiggle_amplitude * 0.25
                head_x += perp_x * wig_amt
                head_y += perp_y * wig_amt

        pygame.draw.circle(screen, self.defn.color, (int(head_x), int(head_y)), head_r)
        pygame.draw.circle(screen,
                          (int(self.defn.color[0] * 0.25),
                           int(self.defn.color[1] * 0.25),
                           int(self.defn.color[2] * 0.25)),
                          (int(head_x), int(head_y)), head_r, 1)

        # Direction for eyes
        if n >= 2:
            nx, ny = self.segments[1]
            angle = math.atan2(head_y - ny, head_x - nx)
        else:
            angle = 0.0

        # Eyes
        eye_dist = head_r * 0.45
        eye_r = max(2, int(head_r * 0.3))
        perp_angle = angle + math.pi / 2

        for side in (-1, 1):
            ex = int(head_x + math.cos(angle) * eye_dist * 0.6
                     + math.cos(perp_angle) * eye_dist * side)
            ey = int(head_y + math.sin(angle) * eye_dist * 0.6
                     + math.sin(perp_angle) * eye_dist * side)
            pygame.draw.circle(screen, (240, 240, 240), (ex, ey), eye_r)
            pupil_r = max(1, eye_r // 2)
            px = int(ex + math.cos(angle) * pupil_r * 0.7)
            py = int(ey + math.sin(angle) * pupil_r * 0.7)
            pygame.draw.circle(screen, (10, 10, 10), (px, py), pupil_r)

        # HP bar above head
        hp_ratio = self.hp / self.defn.hp
        bar_w = 30
        bar_h = 3
        bar_x = int(self.segments[0][0] - bar_w / 2)
        bar_y = int(self.segments[0][1] - head_r - 10)
        pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_w, bar_h))
        if hp_ratio > 0:
            if hp_ratio > 0.5:
                hp_color = (50, 220, 50)
            elif hp_ratio > 0.25:
                hp_color = (220, 200, 30)
            else:
                hp_color = (220, 50, 50)
            pygame.draw.rect(screen, hp_color, (bar_x, bar_y, int(bar_w * hp_ratio), bar_h))
