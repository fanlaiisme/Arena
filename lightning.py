"""闪电/光束类技能系统 —— 折线状闪电技能。"""

import math
import random
from dataclasses import dataclass

import pygame


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
                 owner_id: str, defn: LightningDef):
        self.owner_id = owner_id
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
