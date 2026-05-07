"""投掷炸弹技能 —— 抛物线飞行 → 落地延时 → AoE 爆炸。"""

import math
import random
from dataclasses import dataclass

from enum import Enum

import pygame


class BombType(Enum):
    NORMAL = "normal"
    CLUSTER = "cluster"
    GAS = "gas"


class BombState(Enum):
    THROW = "throw"
    PRIMED = "primed"
    EXPLODED = "exploded"


@dataclass
class BombDef:
    """炸弹技能的定义数据。"""
    name: str
    cooldown: float
    damage: float                       # 爆炸中心最高伤害
    color: tuple[int, int, int]         # 炸弹本体颜色
    bomb_radius: float                  # 炸弹可视半径
    throw_speed: float                  # 投掷初速度 (px/s)
    throw_distance: float               # 最大投掷距离 (px)
    detonate_delay: float               # 落地后延时引爆 (秒)
    explosion_radius: float             # 爆炸伤害半径 (px)
    explosion_color: tuple[int, int, int]  # 预警圈颜色
    min_damage_ratio: float             # 边缘伤害比例 (0~1)
    bomb_type: BombType = BombType.NORMAL  # 炸弹类型
    # 集束炸弹
    cluster_count: int = 0
    cluster_spread_speed: float = 0.0
    cluster_spread_distance: float = 0.0
    cluster_child_radius: float = 0.0
    cluster_child_damage: float = 0.0
    # 毒气弹
    gas_duration: float = 0.0
    gas_dps: float = 0.0
    gas_slow_mult: float = 0.0
    gas_cloud_radius: float = 0.0
    gas_cloud_color: tuple[int, int, int] = (0, 0, 0)

    def damage_at_distance(self, dist: float) -> float:
        """根据爆炸中心距离计算伤害 (带最小伤害保底和线性衰减)。"""
        if dist >= self.explosion_radius:
            return self.damage * self.min_damage_ratio
        ratio = 1.0 - (1.0 - self.min_damage_ratio) * (dist / self.explosion_radius)
        ratio = max(self.min_damage_ratio, min(1.0, ratio))
        return self.damage * ratio


class Bomb:
    """投掷炸弹实体 —— THROW → PRIMED → EXPLODED 三阶段状态机。"""

    def __init__(self, x: float, y: float, target_x: float, target_y: float,
                 owner_id: str, defn: BombDef, is_child: bool = False, owner_team: int = 0):
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.is_child = is_child
        self.defn = defn
        self.start_x = float(x)
        self.start_y = float(y)
        self.target_x = target_x
        self.target_y = target_y
        self.x = float(x)
        self.y = float(y)
        self.state = BombState.THROW
        self.age = 0.0
        self._explosion_processed = False
        self._height_t = 0.0            # 抛物线高度模拟参数 (0~1, 峰值=1)
        self._fuse_seed = random.uniform(0, 100)
        self._flash_alpha = 0           # 爆炸闪光 alpha
        self._throw_duration = self.defn.throw_distance / max(self.defn.throw_speed, 0.001)

    @property
    def explosion_ready(self) -> bool:
        """Ready for explosion-damage processing: just exploded, not yet processed."""
        return self.state == BombState.EXPLODED and not self._explosion_processed

    def update(self, dt: float):
        self.age += dt

        if self.state == BombState.THROW:
            progress = min(self.age / self._throw_duration, 1.0)
            # ease-out quad 缓动，模拟减速落地
            t = 1.0 - (1.0 - progress) ** 2
            self.x = self.start_x + (self.target_x - self.start_x) * t
            self.y = self.start_y + (self.target_y - self.start_y) * t
            # 抛物线高度：sin 曲线，飞行中段最高
            self._height_t = math.sin(progress * math.pi)

            if progress >= 1.0:
                self.state = BombState.PRIMED
                self.age = 0.0

        elif self.state == BombState.PRIMED:
            if self.age >= self.defn.detonate_delay:
                self.state = BombState.EXPLODED
                self._flash_alpha = 255

        elif self.state == BombState.EXPLODED:
            self._flash_alpha = max(0, self._flash_alpha - 1200 * dt)

    def is_expired(self) -> bool:
        return self.state == BombState.EXPLODED and self._explosion_processed

    def draw(self, screen):
        if self.state == BombState.THROW:
            self._draw_thrown(screen)
        elif self.state == BombState.PRIMED:
            self._draw_primed(screen)
        elif self.state == BombState.EXPLODED and self._flash_alpha > 0:
            self._draw_flash(screen)

    # ── THROW 阶段绘制 ──────────────────────────────────────────────────────

    def _draw_thrown(self, screen):
        scale = 0.7 + 0.3 * self._height_t
        r = max(3, int(self.defn.bomb_radius * scale))
        cx, cy = int(self.x), int(self.y)

        self._draw_bomb_body(screen, cx, cy, r, scale)
        self._draw_fuse(screen, cx, cy, r, scale, intensity=0.5)

    # ── PRIMED 阶段绘制 ─────────────────────────────────────────────────────

    def _draw_primed(self, screen):
        cx, cy = int(self.x), int(self.y)
        r = int(self.defn.bomb_radius)

        # 脉冲红色预警圈
        pulse = (math.sin(self.age * 8.0) + 1.0) / 2.0  # 0~1
        alpha = int(20 + pulse * 40)
        warn_surf = pygame.Surface(
            (self.defn.explosion_radius * 2 + 4, self.defn.explosion_radius * 2 + 4),
            pygame.SRCALPHA)
        warn_color = (*self.defn.explosion_color, alpha)
        pygame.draw.circle(
            warn_surf, warn_color,
            (self.defn.explosion_radius + 2, self.defn.explosion_radius + 2),
            self.defn.explosion_radius)
        # 外圈细线
        edge_alpha = int(60 + pulse * 80)
        edge_color = (*self.defn.explosion_color, edge_alpha)
        pygame.draw.circle(
            warn_surf, edge_color,
            (self.defn.explosion_radius + 2, self.defn.explosion_radius + 2),
            self.defn.explosion_radius, 1)
        screen.blit(warn_surf,
                    (cx - self.defn.explosion_radius - 2,
                     cy - self.defn.explosion_radius - 2))

        # 炸弹本体微抖动
        jitter_x = int(math.sin(self.age * 30.0 + self._fuse_seed) * 1.5)
        jitter_y = int(math.cos(self.age * 27.0 + self._fuse_seed) * 1.5)
        self._draw_bomb_body(screen, cx + jitter_x, cy + jitter_y, r, scale=1.0)
        self._draw_fuse(screen, cx + jitter_x, cy + jitter_y, r, scale=1.0, intensity=0.9)

    # ── 炸弹本体绘制 ────────────────────────────────────────────────────────

    def _draw_bomb_body(self, screen, cx, cy, r, scale):
        if r < 2:
            return

        # 1. 底色圆
        body_color = (55, 55, 60)
        pygame.draw.circle(screen, body_color, (cx, cy), r)

        # 2. 金属高光（左上角偏移小圆）
        hl_radius = max(2, int(r * 0.7))
        hl_offset = int(r * 0.18)
        hl_color = (120, 120, 125)
        pygame.draw.circle(
            screen, hl_color,
            (cx - hl_offset, cy - hl_offset), hl_radius)

        # 3. 中间环带（深色横纹）
        band_height = max(2, int(r * 0.4))
        band_width = int(r * 1.6)
        band_color = (35, 35, 40)
        band_rect = pygame.Rect(
            cx - band_width // 2, cy - band_height // 2,
            band_width, band_height)
        pygame.draw.rect(screen, band_color, band_rect)

        # 4. 深色轮廓
        outline_color = (30, 30, 35)
        pygame.draw.circle(screen, outline_color, (cx, cy), r, max(1, int(1.5 * scale)))

    # ── 引信绘制 ────────────────────────────────────────────────────────────

    def _draw_fuse(self, screen, cx, cy, r, scale, intensity):
        # 引信从右上角向外延伸
        angle = math.radians(-45)
        fuse_start_x = cx + math.cos(angle) * r
        fuse_start_y = cy + math.sin(angle) * r
        fuse_len = max(2, int(6 * scale))
        fuse_end_x = fuse_start_x + math.cos(angle) * fuse_len
        fuse_end_y = fuse_start_y + math.sin(angle) * fuse_len

        # 引信线
        pygame.draw.line(
            screen, (80, 70, 50),
            (int(fuse_start_x), int(fuse_start_y)),
            (int(fuse_end_x), int(fuse_end_y)),
            max(1, int(1.5 * scale)))

        # 火花粒子
        spark_count = 3
        now = pygame.time.get_ticks() / 1000.0
        for i in range(spark_count):
            spark_angle = angle + random.uniform(-0.5, 0.5)
            spark_dist = fuse_len + random.uniform(1, 5 * scale)
            spark_x = fuse_start_x + math.cos(spark_angle) * spark_dist
            spark_y = fuse_start_y + math.sin(spark_angle) * spark_dist

            if intensity > 0.7:
                # PRIMED 阶段：红/白交替
                if random.random() < 0.5:
                    spark_color = (255, 80 + int(random.uniform(0, 80)), 20)
                else:
                    spark_color = (255, 255, 200)
            else:
                spark_color = (255, 140 + int(random.uniform(0, 60)), 10)

            spark_size = max(1, int(1.5 * scale * intensity))
            pygame.draw.circle(
                screen, spark_color,
                (int(spark_x), int(spark_y)), spark_size)

    # ── 爆炸闪光 ────────────────────────────────────────────────────────────

    def _draw_flash(self, screen):
        alpha = int(self._flash_alpha)
        if alpha <= 0:
            return
        flash_surf = pygame.Surface(
            (self.defn.explosion_radius * 2 + 4, self.defn.explosion_radius * 2 + 4),
            pygame.SRCALPHA)
        flash_color = (255, 255, 200, min(255, alpha))
        pygame.draw.circle(
            flash_surf, flash_color,
            (self.defn.explosion_radius + 2, self.defn.explosion_radius + 2),
            self.defn.explosion_radius)
        screen.blit(flash_surf,
                    (int(self.x) - self.defn.explosion_radius - 2,
                     int(self.y) - self.defn.explosion_radius - 2))


class GasCloud:
    """持续毒雾实体 —— 对范围内敌人施加 DoT + 减速。"""

    def __init__(self, x: float, y: float, owner_id: str, defn: BombDef, owner_team: int = 0):
        self.x = x
        self.owner_team = owner_team
        self.y = y
        self.owner_id = owner_id
        self.radius = defn.gas_cloud_radius
        self.dps = defn.gas_dps
        self.slow_mult = defn.gas_slow_mult
        self.duration = defn.gas_duration
        self.color = defn.gas_cloud_color
        self.age = 0.0
        self._opacity = 0.0
        self._seed = random.uniform(0, 100)

    def update(self, dt: float):
        self.age += dt
        self._opacity = min(1.0, self.age / 0.3)
        if self.age > self.duration - 1.0:
            self._opacity = max(0.0, (self.duration - self.age) / 1.0)

    def is_expired(self) -> bool:
        return self.age >= self.duration

    def contains(self, px: float, py: float, entity_radius: float = 0.0) -> bool:
        return math.hypot(self.x - px, self.y - py) < self.radius + entity_radius

    def draw(self, screen):
        alpha = int(60 * self._opacity)
        if alpha <= 0:
            return
        size = int(self.radius * 2)
        surf = pygame.Surface((size + 8, size + 8), pygame.SRCALPHA)
        cx = cy = size // 2 + 4

        now = pygame.time.get_ticks() / 1000.0

        # 动态绿色：在黄绿↔青绿之间缓慢摆动
        r = int(self.color[0] + math.sin(now * 1.7 + self._seed) * 30)
        g = int(self.color[1] + math.sin(now * 2.1 + self._seed + 1.3) * 25)
        b = int(self.color[2] + math.sin(now * 1.3 + self._seed + 2.7) * 20)
        dyn_color = (
            max(0, min(255, r)),
            max(0, min(255, g)),
            max(0, min(255, b)),
        )

        # 波浪边缘多边形
        wave_count = 12
        points = []
        for i in range(wave_count * 4):
            angle = 2 * math.pi * i / (wave_count * 4)
            wave_offset = math.sin(now * 2.5 + angle * wave_count + self._seed) * 5
            r_wave = self.radius + wave_offset
            px = cx + math.cos(angle) * r_wave
            py = cy + math.sin(angle) * r_wave
            points.append((px, py))

        fill_alpha = int(alpha * (0.7 + 0.3 * math.sin(now * 1.5 + self._seed)))
        fill_color = (*dyn_color, fill_alpha)
        if len(points) > 2:
            pygame.draw.polygon(surf, fill_color, points)
        edge_alpha = min(255, int(alpha * 1.5))
        edge_color = (*dyn_color, edge_alpha)
        if len(points) > 2:
            pygame.draw.polygon(surf, edge_color, points, 2)

        screen.blit(surf, (int(self.x) - cx, int(self.y) - cy))
