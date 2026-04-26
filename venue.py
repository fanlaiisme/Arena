"""竞技场定义 —— 圆形竞技场，边界分为红/黄/蓝三段，各有不同碰撞效果。"""

import math
from enum import Enum

import pygame

# ── 竞技场常量 ──────────────────────────────────────────────────────────────────
ARENA_CENTER = (400, 400)
ARENA_RADIUS = 350
INITIAL_HP = 100

# ── 分段颜色 ────────────────────────────────────────────────────────────────────
class SegmentColor(Enum):
    RED = "红"
    YELLOW = "黄"
    BLUE = "蓝"

SEGMENT_RGB = {
    SegmentColor.RED: (220, 50, 40),
    SegmentColor.YELLOW: (240, 200, 30),
    SegmentColor.BLUE: (40, 130, 240),
}


class ArenaSegment:
    """竞技场边界的一段，覆盖一个角度区间。"""
    def __init__(self, color: SegmentColor, start_angle: float, end_angle: float):
        self.color = color
        self.start_angle = start_angle
        self.end_angle = end_angle


class Arena:
    """圆形竞技场，边界等分为红、黄、蓝三段。"""

    def __init__(self, center=ARENA_CENTER, radius=ARENA_RADIUS):
        self.center = center
        self.radius = radius
        self.segments = [
            ArenaSegment(SegmentColor.RED,  0,                  2 * math.pi / 3),
            ArenaSegment(SegmentColor.YELLOW, 2 * math.pi / 3,   4 * math.pi / 3),
            ArenaSegment(SegmentColor.BLUE,    4 * math.pi / 3,   2 * math.pi),
        ]

    # ── 分段查询 ──────────────────────────────────────────────────────────────

    def get_segment_at(self, x: float, y: float) -> ArenaSegment:
        dx = x - self.center[0]
        dy = y - self.center[1]
        angle = math.atan2(dy, dx) % (2 * math.pi)
        
        # 直接根据角度值判断，避免遍历和边界问题
        if angle < 2 * math.pi / 3:  # 0-120°
            return self.segments[0]  # 红色
        elif angle < 4 * math.pi / 3:  # 120-240°
            return self.segments[1]  # 黄色
        else:  # 240-360°
            return self.segments[2]  # 蓝色

    # ── 碰撞效果 ──────────────────────────────────────────────────────────────

    def apply_effect(self, player, segment: ArenaSegment):
        if segment.color == SegmentColor.RED:
            player.take_damage(5)
            # 速度提升 50%
            player.vx *= 1.5
            player.vy *= 1.5

        elif segment.color == SegmentColor.BLUE:
            heal = int(INITIAL_HP * 0.1)
            player.hp = min(player.hp + heal, INITIAL_HP)

        # 黄边：暂不生效

    # ── 边界碰撞物理 ──────────────────────────────────────────────────────────

    def resolve_boundary(self, player) -> ArenaSegment | None:
        dx = player.x - self.center[0]
        dy = player.y - self.center[1]
        dist = math.hypot(dx, dy)
        limit = self.radius - player.radius

        if dist > limit and dist > 0.001:
            nx = dx / dist
            ny = dy / dist
            dot = player.vx * nx + player.vy * ny
            player.vx -= 2 * dot * nx
            player.vy -= 2 * dot * ny
            player.x = self.center[0] + nx * limit
            player.y = self.center[1] + ny * limit
            return self.get_segment_at(player.x, player.y)
        return None

    def resolve_projectile_boundary(self, proj) -> ArenaSegment | None:
        dx = proj.x - self.center[0]
        dy = proj.y - self.center[1]
        dist = math.hypot(dx, dy)
        limit = self.radius - proj.skill.radius

        if dist > limit and dist > 0.001:
            nx = dx / dist
            ny = dy / dist
            dot = proj.vx * nx + proj.vy * ny
            proj.vx -= 2 * dot * nx
            proj.vy -= 2 * dot * ny
            proj.x = self.center[0] + nx * limit
            proj.y = self.center[1] + ny * limit
            return self.get_segment_at(proj.x, proj.y)
        return None

    # ── 渲染 ──────────────────────────────────────────────────────────────────

    def draw(self, screen):
        screen.fill((30, 30, 40))
        pygame.draw.circle(screen, (50, 50, 60), self.center, self.radius - 15, 1)

        line_width = 4
        for seg in self.segments:
            color = SEGMENT_RGB[seg.color]
            rect = pygame.Rect(
                self.center[0] - self.radius,
                self.center[1] - self.radius,
                self.radius * 2,
                self.radius * 2,
            )
            pygame.draw.arc(screen, color, rect,
                            seg.start_angle, seg.end_angle, line_width)
