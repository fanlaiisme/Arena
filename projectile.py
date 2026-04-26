"""技能与投射物系统 —— 定义技能的投射物行为（移动模式、存留时间等）。"""

import random
import math
from dataclasses import dataclass, field
from enum import Enum


# ── 移动类型枚举 ────────────────────────────────────────────────────────────────
class MovementType(Enum):
    STATIONARY = "stationary"  # 原地不动
    ORBIT = "orbit"            # 围绕角色圆周运动
    ROAM = "roam"              # 在竞技场内随机游走
    BOUNCE = "bounce"          # 直线弹射


# ── 技能定义 ────────────────────────────────────────────────────────────────────
@dataclass
class SkillDef:
    """定义一个技能的全部属性，包括投射物行为。"""
    name: str                              # 技能名称
    cooldown: float                        # 冷却时间（秒）
    damage: int                            # 单次伤害
    color: tuple[int, int, int]            # 投射物颜色
    radius: int                            # 投射物半径
    movement_type: MovementType            # 移动模式
    movement_params: dict = field(default_factory=dict)  # 移动参数
    lifetime: float | None = None          # 存留时间（秒），None 表示永久


from venue import ARENA_CENTER, ARENA_RADIUS


# ── 投射物 ──────────────────────────────────────────────────────────────────────


class Projectile:
    """一个由技能生成的投射物实例，具有独立的移动行为和存留时间。"""

    def __init__(self, x: float, y: float, owner_id: str,
                 skill: SkillDef, owner=None):
        self.x = x
        self.y = y
        self.owner_id = owner_id        # 发射者的角色 id
        self.owner = owner              # 发射者引用（orbit 模式需要跟踪位置）
        self.skill = skill
        self.age = 0.0                  # 已存留时间

        # 移动状态
        self.vx = 0.0
        self.vy = 0.0

        # orbit 模式的初始角度
        self._orbit_angle = random.uniform(0, 2 * math.pi)

        # bounce / roam 模式初始化速度
        mt = skill.movement_type
        if mt == MovementType.BOUNCE:
            spd = skill.movement_params.get("speed", 2.0)
            angle = random.uniform(0, 2 * math.pi)
            self.vx = math.cos(angle) * spd
            self.vy = math.sin(angle) * spd
        elif mt == MovementType.ROAM:
            spd = skill.movement_params.get("speed", 2.0)
            self.vx = random.uniform(-spd, spd)
            self.vy = random.uniform(-spd, spd)

    # ── 各移动模式的更新逻辑 ──────────────────────────────────────────────────

    def _update_stationary(self, dt):
        pass  # 原地不动

    def _update_orbit(self, dt):
        if self.owner is None or not getattr(self.owner, 'alive', False):
            return
        params = self.skill.movement_params
        angular_speed = params.get("angular_speed", 2.0)
        orbit_radius = params.get("radius", 60)
        self._orbit_angle += angular_speed * dt
        self.x = self.owner.x + math.cos(self._orbit_angle) * orbit_radius
        self.y = self.owner.y + math.sin(self._orbit_angle) * orbit_radius

    def _update_roam(self, dt):
        params = self.skill.movement_params
        max_spd = params.get("speed", 2.0)

        # 随机加速度
        ax = random.uniform(-0.1, 0.1)
        ay = random.uniform(-0.1, 0.1)
        if random.random() < 0.03:
            ax += random.uniform(-0.4, 0.4)
            ay += random.uniform(-0.4, 0.4)

        self.vx += ax
        self.vy += ay
        self.vx *= 0.995
        self.vy *= 0.995

        speed = math.hypot(self.vx, self.vy)
        if speed > max_spd:
            self.vx = self.vx / speed * max_spd
            self.vy = self.vy / speed * max_spd

        self.x += self.vx
        self.y += self.vy

        # 竞技场边界反弹
        self._bounce_off_arena()

    def _update_bounce(self, dt):
        self.x += self.vx
        self.y += self.vy
        # 竞技场边界反弹
        self._bounce_off_arena()

    def _bounce_off_arena(self):
        """碰到圆形竞技场边界时反弹。"""
        dx = self.x - ARENA_CENTER[0]
        dy = self.y - ARENA_CENTER[1]
        dist = math.hypot(dx, dy)
        limit = ARENA_RADIUS - self.skill.radius
        if dist > limit:
            nx = dx / dist
            ny = dy / dist
            # 反射速度
            dot = self.vx * nx + self.vy * ny
            self.vx -= 2 * dot * nx
            self.vy -= 2 * dot * ny
            # 钳制位置到边界内
            self.x = ARENA_CENTER[0] + nx * limit
            self.y = ARENA_CENTER[1] + ny * limit

    # ── 公共接口 ──────────────────────────────────────────────────────────────

    def update(self, dt: float):
        """每帧调用，更新投射物位置和存留时间。"""
        self.age += dt
        mt = self.skill.movement_type
        if mt == MovementType.STATIONARY:
            self._update_stationary(dt)
        elif mt == MovementType.ORBIT:
            self._update_orbit(dt)
        elif mt == MovementType.ROAM:
            self._update_roam(dt)
        elif mt == MovementType.BOUNCE:
            self._update_bounce(dt)

    def is_expired(self) -> bool:
        """存留时间到期则返回 True（lifetime=None 永不超时）。"""
        if self.skill.lifetime is None:
            return False
        return self.age >= self.skill.lifetime

    def collides_with(self, player) -> bool:
        """判断是否与玩家碰撞。"""
        dx = self.x - player.x
        dy = self.y - player.y
        dist = math.hypot(dx, dy)
        return dist < player.radius + self.skill.radius

    # ── 渲染 ──────────────────────────────────────────────────────────────────

    def draw(self, screen):
        """在屏幕上绘制投射物。"""
        import pygame
        pygame.draw.circle(screen, self.skill.color,
                           (int(self.x), int(self.y)), self.skill.radius)
        pygame.draw.circle(screen, (100, 100, 100),
                           (int(self.x), int(self.y)), self.skill.radius, 1)
