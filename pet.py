"""宠物/召唤物技能系统 —— 可被攻击、有独立HP、可追踪目标的召唤物。"""

import math
import random
from dataclasses import dataclass
from enum import Enum

import pygame

from venue import ARENA_CENTER, ARENA_RADIUS


class PetMovement(Enum):
    CHASE = "chase"  # 追踪目标
    SPIDER = "spider"  # 蜘蛛织网


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
    slow_mult: float = 0.0        # 碰到敌人时的减速倍率（0=不减速）
    slow_duration: float = 0.0    # 减速持续时间（秒）


@dataclass
class SpiderWeb:
    """蜘蛛网的一条线段。"""
    x1: float
    y1: float
    x2: float
    y2: float
    owner_id: str
    age: float = 0.0
    alpha: float = 0.0  # 0→1 淡入


def point_to_segment_dist(px: float, py: float,
                          x1: float, y1: float,
                          x2: float, y2: float) -> float:
    """计算点到线段的最短距离。"""
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 0.001:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _draw_shock_sparks(screen, cx: float, cy: float, radius: float):
    """在被电击的实体周围绘制小电流火花。"""
    now = pygame.time.get_ticks() / 1000.0
    for i in range(5):
        seed = (i * 2.399 + cx * 0.001 + cy * 0.003) % 1.0
        angle = (seed * 6.28318 + now * 3.5 + i * 1.2566) % 6.28318
        spark_dist = radius + 4 + (seed % 1.0) * 10
        flicker = math.sin(now * 11 + seed * 17) * 3
        sx = cx + math.cos(angle) * (spark_dist + flicker)
        sy = cy + math.sin(angle) * (spark_dist + flicker)

        # Short zigzag from the spark point
        seg_angle = angle + math.pi / 2
        seg_len = 4 + (seed % 1.0) * 6
        ex = sx + math.cos(seg_angle) * seg_len
        ey = sy + math.sin(seg_angle) * seg_len
        mx = (sx + ex) / 2 + math.sin(now * 15 + seed * 23) * 3

        points = [(int(sx), int(sy)), (int(mx), int(ey + (sy - ey) * 0.3)), (int(ex), int(ey))]
        pygame.draw.lines(screen, (255, 255, 100), False, points, 1)


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
        self.slow_timer = 0.0
        self.shock_timer = 0.0
        self.shock_dps = 0.0

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
        if self.slow_timer > 0:
            self.slow_timer = max(0.0, self.slow_timer - dt)
            if self.slow_timer == 0.0:
                self.slow_mult = 1.0
        if self.shock_timer > 0:
            self.shock_timer = max(0.0, self.shock_timer - dt)
            self.take_damage(self.shock_dps * dt)

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

        if self.shock_timer > 0:
            _draw_shock_sparks(screen, self.segments[0][0], self.segments[0][1], self._head_radius())

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


# ── Spider Pet ──────────────────────────────────────────────────────────────────

class SpiderPet:
    """蜘蛛宠物 —— 移动到竞技场边界，织网减速并伤害触碰网的敌人。"""

    def __init__(self, x: float, y: float, owner_id: str,
                 target, defn: PetDef):
        self.owner_id = owner_id
        self.target = target
        self.defn = defn
        self.age = 0.0
        self.hp = float(defn.hp)
        self.x = float(x)
        self.y = float(y)
        self.slow_mult = 1.0
        self.slow_timer = 0.0
        self.shock_timer = 0.0
        self.shock_dps = 0.0

        # State machine: SEEK_BOUNDARY → BUILDING → IDLE
        self.state = "SEEK_BOUNDARY"
        self.web_segments: list[SpiderWeb] = []
        self._build_timer = 0.0
        self._build_interval = 0.3
        self._built_count = 0
        self._max_web_segments = 8
        self._web_hub: tuple[float, float] | None = None
        self._web_anchors: list[tuple[float, float]] = []
        self._web_age = 0.0          # 网已存在时间
        self._web_lifetime = 15.0    # 网最大存在时间

        # Leg animation
        self._leg_phase = random.uniform(0, 2 * math.pi)

        # Find nearest boundary point
        self._find_nearest_boundary()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _body_radius(self) -> float:
        return self.defn.body_width * 0.5

    def _find_nearest_boundary(self):
        dx = self.x - ARENA_CENTER[0]
        dy = self.y - ARENA_CENTER[1]
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            r = ARENA_RADIUS - self._body_radius() - 5
            self._target_x = ARENA_CENTER[0] + dx / dist * r
            self._target_y = ARENA_CENTER[1] + dy / dist * r
        else:
            angle = random.uniform(0, 2 * math.pi)
            r = ARENA_RADIUS - self._body_radius() - 5
            self._target_x = ARENA_CENTER[0] + math.cos(angle) * r
            self._target_y = ARENA_CENTER[1] + math.sin(angle) * r

    def _angle_at_point(self, x: float, y: float) -> float:
        return math.atan2(y - ARENA_CENTER[1], x - ARENA_CENTER[0]) % (2 * math.pi)

    def _generate_web_anchors(self):
        """围绕蜘蛛当前位置在竞技场边界上生成锚点（~100度弧线）。"""
        cx, cy = ARENA_CENTER
        r = ARENA_RADIUS - 2
        hub_angle = self._angle_at_point(self.x, self.y)
        # 6 anchors spanning ~100 degrees
        span = math.radians(100)
        count = 6
        start_angle = hub_angle - span / 2
        self._web_anchors = []
        for i in range(count):
            a = start_angle + span * i / (count - 1)
            self._web_anchors.append((cx + math.cos(a) * r, cy + math.sin(a) * r))

    # ── Update ───────────────────────────────────────────────────────────────

    def update(self, dt: float):
        self.age += dt
        self._leg_phase += dt * 3.0

        if self.slow_timer > 0:
            self.slow_timer = max(0.0, self.slow_timer - dt)
            if self.slow_timer == 0.0:
                self.slow_mult = 1.0
        if self.shock_timer > 0:
            self.shock_timer = max(0.0, self.shock_timer - dt)
            self.take_damage(self.shock_dps * dt)

        # Fade-in existing web segments
        for web in self.web_segments:
            web.age += dt
            web.alpha = min(1.0, web.age / 0.3)

        if self.state == "SEEK_BOUNDARY":
            dx = self._target_x - self.x
            dy = self._target_y - self.y
            dist = math.hypot(dx, dy)
            if dist < 10.0:
                self.x = self._target_x
                self.y = self._target_y
                self._web_hub = (self.x, self.y)
                self._generate_web_anchors()
                self.state = "BUILDING"
                self._build_timer = 0.0
                self._built_count = 0
            else:
                speed = self.defn.speed
                self.x += dx / dist * speed * dt
                self.y += dy / dist * speed * dt

        elif self.state == "BUILDING":
            self._build_timer += dt
            if self._build_timer >= self._build_interval and self._built_count < self._max_web_segments:
                self._build_timer -= self._build_interval
                self._add_next_web_segment()
                self._built_count += 1
                if self._built_count >= self._max_web_segments:
                    self.state = "IDLE"

        elif self.state == "IDLE":
            self._web_age += dt
            if self._web_age >= self._web_lifetime:
                self._rebuild_web()

    def _add_next_web_segment(self):
        """按顺序添加下一段网：先径向线，再横线。"""
        hub_x, hub_y = self._web_hub
        num_radials = len(self._web_anchors)

        if self._built_count < num_radials:
            # Radial strand: hub → anchor
            ax, ay = self._web_anchors[self._built_count]
            self.web_segments.append(SpiderWeb(
                x1=hub_x, y1=hub_y, x2=ax, y2=ay,
                owner_id=self.owner_id,
            ))
        else:
            # Cross strand: connect midpoints of adjacent radials
            idx = self._built_count - num_radials
            if idx + 1 < num_radials:
                a1 = self._web_anchors[idx]
                a2 = self._web_anchors[idx + 1]
                mx1 = (hub_x + a1[0]) / 2
                my1 = (hub_y + a1[1]) / 2
                mx2 = (hub_x + a2[0]) / 2
                my2 = (hub_y + a2[1]) / 2
                self.web_segments.append(SpiderWeb(
                    x1=mx1, y1=my1, x2=mx2, y2=my2,
                    owner_id=self.owner_id,
                ))
            else:
                # Final segment: connect hub to midpoint of last radial
                a = self._web_anchors[-1]
                mx = (hub_x + a[0]) / 2
                my = (hub_y + a[1]) / 2
                self.web_segments.append(SpiderWeb(
                    x1=hub_x, y1=hub_y, x2=mx, y2=my,
                    owner_id=self.owner_id,
                ))

    def _rebuild_web(self):
        """清除旧网并重新开始织网。"""
        self.web_segments.clear()
        self._web_age = 0.0
        self._web_hub = (self.x, self.y)
        self._generate_web_anchors()
        self.state = "BUILDING"
        self._build_timer = 0.0
        self._built_count = 0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def is_expired(self) -> bool:
        if self.hp <= 0:
            return True
        if self.defn.lifetime is not None and self.age >= self.defn.lifetime:
            return True
        return False

    def take_damage(self, amount: float):
        self.hp -= amount

    # ── Collision ────────────────────────────────────────────────────────────

    def collides_with(self, player) -> bool:
        """蜘蛛身体与玩家圆碰撞。"""
        dx = self.x - player.x
        dy = self.y - player.y
        return math.hypot(dx, dy) < player.radius + self._body_radius()

    def head_collides_with_circle(self, cx: float, cy: float, radius: float) -> bool:
        """蜘蛛身体与圆形碰撞。"""
        dx = self.x - cx
        dy = self.y - cy
        return math.hypot(dx, dy) < radius + self._body_radius()

    def _web_slow_mult(self) -> float:
        """根据网存在时间计算减速倍率，0→0.5 到 lifetime→0.8 线性变化。"""
        decay = min(1.0, self._web_age / self._web_lifetime)
        return 0.5 + 0.3 * decay  # 0.5 → 0.8，减速效果下降至原来的40%

    def check_web_player_collision(self, player) -> bool:
        """检查玩家是否碰到蜘蛛网。返回True表示发生了碰撞。"""
        if not player.alive:
            return False
        if player.char.id == self.owner_id:
            return False
        threshold = player.radius + 4
        for web in self.web_segments:
            dist = point_to_segment_dist(
                player.x, player.y,
                web.x1, web.y1, web.x2, web.y2,
            )
            if dist < threshold:
                dmg = self.defn.damage * 0.016  # ~5 DPS at 60fps
                player.take_damage(dmg)
                player.slow_mult = self._web_slow_mult()
                player.slow_timer = 0.15
                return True
        return False

    def check_web_pet_collision(self, pet) -> bool:
        """检查敌方宠物是否碰到蜘蛛网。"""
        if isinstance(pet, SpiderPet):
            return False  # 蜘蛛网不互相影响
        if pet.owner_id == self.owner_id:
            return False
        if isinstance(pet, Pet):
            head_x, head_y = pet.segments[0]
            threshold = pet._head_radius() + 4
        else:
            return False
        for web in self.web_segments:
            dist = point_to_segment_dist(
                head_x, head_y,
                web.x1, web.y1, web.x2, web.y2,
            )
            if dist < threshold:
                pet.take_damage(self.defn.damage * 0.016)
                pet.slow_mult = self._web_slow_mult()
                pet.slow_timer = 0.15
                return True
        return False

    # ── Render ───────────────────────────────────────────────────────────────

    def draw(self, screen):
        self._draw_web(screen)
        self._draw_spider(screen)
        if self.shock_timer > 0:
            _draw_shock_sparks(screen, self.x, self.y, self._body_radius())
        self._draw_hp_bar(screen)

    def _draw_web(self, screen):
        """绘制所有网段 —— 半透明白色线条。"""
        for web in self.web_segments:
            alpha = int(web.alpha * 160)
            if alpha <= 0:
                continue
            color = (200, 200, 210, alpha)
            # Use absolute offsets; surface size must span the whole line + padding
            min_x = min(web.x1, web.x2)
            min_y = min(web.y1, web.y2)
            surf_w = int(abs(web.x2 - web.x1)) + 8
            surf_h = int(abs(web.y2 - web.y1)) + 8
            surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
            # Surface-relative coordinates for both endpoints
            lx1 = int(web.x1 - min_x) + 4
            ly1 = int(web.y1 - min_y) + 4
            lx2 = int(web.x2 - min_x) + 4
            ly2 = int(web.y2 - min_y) + 4
            # Glow layer (thicker, more transparent)
            glow_color = (200, 200, 210, max(1, alpha // 3))
            pygame.draw.line(surf, glow_color, (lx1, ly1), (lx2, ly2), 3)
            # Core line (thin, more opaque)
            pygame.draw.line(surf, color, (lx1, ly1), (lx2, ly2), 1)
            # Position surface at min corner
            sx = int(min_x) - 4
            sy = int(min_y) - 4
            screen.blit(surf, (sx, sy))

        # Draw anchor points on the boundary
        for ax, ay in self._web_anchors:
            pygame.draw.circle(screen, (255, 255, 255), (int(ax), int(ay)), 4)
            pygame.draw.circle(screen, (200, 200, 220), (int(ax), int(ay)), 2)

    def _draw_spider(self, screen):
        """绘制蜘蛛身体：圆形身体 + 8条腿 + 8只眼。"""
        cx, cy = int(self.x), int(self.y)
        body_r = int(self._body_radius())
        body_color = self.defn.color  # (80, 30, 100)
        darker = (
            int(body_color[0] * 0.5),
            int(body_color[1] * 0.5),
            int(body_color[2] * 0.5),
        )

        # Legs (4 pairs, 8 legs total)
        for leg_idx in range(8):
            self._draw_leg(screen, cx, cy, leg_idx)

        # Body
        pygame.draw.circle(screen, body_color, (cx, cy), body_r)
        pygame.draw.circle(screen, darker, (cx, cy), body_r, 2)

        # Cephalothorax line (front portion slightly lighter)
        front_color = (
            min(255, int(body_color[0] * 1.3)),
            min(255, int(body_color[1] * 1.3)),
            min(255, int(body_color[2] * 1.3)),
        )
        pygame.draw.circle(screen, front_color, (cx, cy), body_r // 2)

        # Eyes (8 eyes in two rows of 4)
        eye_dir = 0.0  # facing forward — front of body
        for row in range(2):
            for col in range(4):
                row_offset = -3 + row * 6
                col_offset = -6 + col * 4
                ex = int(cx + math.cos(eye_dir) * (body_r * 0.5 + row * 3)
                         - math.sin(eye_dir) * col_offset * 0.5
                         + math.cos(eye_dir) * row_offset)
                ey = int(cy + math.sin(eye_dir) * (body_r * 0.5 + row * 3)
                         + math.cos(eye_dir) * col_offset * 0.5
                         + math.sin(eye_dir) * row_offset)
                # Larger central eyes
                if row == 0 and (col == 1 or col == 2):
                    er = max(2, body_r // 5)
                else:
                    er = max(1, body_r // 7)
                pygame.draw.circle(screen, (240, 240, 240), (ex, ey), er)
                pygame.draw.circle(screen, (10, 10, 10), (ex, ey), max(1, er // 2))

    def _draw_leg(self, screen, cx: int, cy: int, leg_idx: int):
        """绘制单条蜘蛛腿（3段关节）。"""
        body_r = int(self._body_radius())
        # Base angle for this leg
        base_angle = leg_idx * math.pi / 4  # 8 legs evenly spaced
        leg_len = body_r * 1.4

        # Idle animation: sinusoidal movement
        anim = math.sin(self._leg_phase + leg_idx * 0.8) * 0.3

        # Three segments: coxa→femur, femur→tibia, tibia→tip
        seg_angles = [
            base_angle + anim * 0.3,
            base_angle + anim * 0.6,
            base_angle + anim,
        ]
        seg_len = leg_len / 3

        leg_color = (
            int(self.defn.color[0] * 0.6),
            int(self.defn.color[1] * 0.6),
            int(self.defn.color[2] * 0.6),
        )

        sx, sy = float(cx), float(cy)
        for i, angle in enumerate(seg_angles):
            ex = sx + math.cos(angle) * seg_len
            ey = sy + math.sin(angle) * seg_len
            width = max(1, 3 - i)  # thicker at base, thinner at tip
            pygame.draw.line(screen, leg_color, (int(sx), int(sy)), (int(ex), int(ey)), width)
            sx, sy = ex, ey

    def _draw_hp_bar(self, screen):
        """蜘蛛身体上方的HP条。"""
        hp_ratio = self.hp / self.defn.hp
        bar_w = 30
        bar_h = 3
        bar_x = int(self.x - bar_w / 2)
        bar_y = int(self.y - self._body_radius() - 10)
        pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_w, bar_h))
        if hp_ratio > 0:
            if hp_ratio > 0.5:
                hp_color = (50, 220, 50)
            elif hp_ratio > 0.25:
                hp_color = (220, 200, 30)
            else:
                hp_color = (220, 50, 50)
            pygame.draw.rect(screen, hp_color, (bar_x, bar_y, int(bar_w * hp_ratio), bar_h))


# ── Snowman Pet ──────────────────────────────────────────────────────────────────

class SnowmanPet(Pet):
    """雪人宠物 —— 缓慢追踪敌人，碰到造成伤害。"""

    def __init__(self, x: float, y: float, owner_id: str,
                 target, defn: PetDef):
        self.owner_id = owner_id
        self.target = target
        self.defn = defn
        self.age = 0.0
        self.hp = float(defn.hp)
        self.slow_mult = 1.0
        self.slow_timer = 0.0
        self.shock_timer = 0.0
        self.shock_dps = 0.0

        # Single segment at spawn position (no snake body)
        self.segments: list[tuple[float, float]] = [(float(x), float(y))]
        self._seg_spacing = 0.0
        self._wiggle_phase = random.uniform(0, 2 * math.pi)

    # ── Convenience properties ─────────────────────────────────────────────────
    @property
    def x(self):
        return self.segments[0][0]

    @property
    def y(self):
        return self.segments[0][1]

    def _head_radius(self) -> float:
        """碰撞半径使用身体下半部分（最大的圆）。"""
        return self.defn.body_width * 0.5

    # ── Update ─────────────────────────────────────────────────────────────────
    def update(self, dt: float):
        self.age += dt
        if self.slow_timer > 0:
            self.slow_timer = max(0.0, self.slow_timer - dt)
            if self.slow_timer == 0.0:
                self.slow_mult = 1.0
        if self.shock_timer > 0:
            self.shock_timer = max(0.0, self.shock_timer - dt)
            self.take_damage(self.shock_dps * dt)

        head_x, head_y = self.segments[0]

        # Determine target position
        if self.target is not None and self.target.alive:
            tx, ty = self.target.x, self.target.y
        else:
            tx, ty = head_x, head_y

        # Move head toward target at fixed speed
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

        # Constrain to arena
        dx_c = new_head_x - ARENA_CENTER[0]
        dy_c = new_head_y - ARENA_CENTER[1]
        dist_c = math.hypot(dx_c, dy_c)
        limit = ARENA_RADIUS - self.defn.body_width * 0.5
        if dist_c > limit and dist_c > 0.001:
            new_head_x = ARENA_CENTER[0] + dx_c / dist_c * limit
            new_head_y = ARENA_CENTER[1] + dy_c / dist_c * limit

        self.segments = [(new_head_x, new_head_y)]

    # ── Collision ──────────────────────────────────────────────────────────────
    def collides_with(self, player) -> bool:
        """圆-圆碰撞。碰到敌人时应用减速效果。"""
        head_x, head_y = self.segments[0]
        dx = head_x - player.x
        dy = head_y - player.y
        if math.hypot(dx, dy) < player.radius + self._head_radius():
            if self.defn.slow_mult > 0:
                player.slow_mult = self.defn.slow_mult
                player.slow_timer = self.defn.slow_duration
            return True
        return False

    # ── Render ─────────────────────────────────────────────────────────────────
    def draw(self, screen):
        self._draw_snowman(screen)
        if self.shock_timer > 0:
            head_x, head_y = self.segments[0]
            _draw_shock_sparks(screen, head_x, head_y, self._head_radius())
        self._draw_hp_bar(screen)

    def _draw_snowman(self, screen):
        """绘制雪人：三叠圆 + 眼睛 + 胡萝卜鼻子 + 树枝手臂。"""
        head_x, head_y = self.segments[0]
        color = self.defn.color
        darker = (
            int(color[0] * 0.25),
            int(color[1] * 0.25),
            int(color[2] * 0.25),
        )

        # Compute facing direction (toward target or movement)
        if self.target is not None and self.target.alive:
            face_angle = math.atan2(
                self.target.y - head_y,
                self.target.x - head_x,
            )
        else:
            face_angle = 0.0

        # Body radii
        bottom_r = int(self.defn.body_width * 0.9)
        middle_r = int(bottom_r * 0.75)
        head_r = int(bottom_r * 0.55)

        # Vertical stacking offsets from head position
        stack_gap = int(bottom_r * 0.15)

        bottom_y = int(head_y) + bottom_r + stack_gap
        middle_y = int(head_y) + middle_r + stack_gap
        head_cy = int(head_y)

        # Draw bottom circle
        pygame.draw.circle(screen, color, (int(head_x), bottom_y), bottom_r)
        pygame.draw.circle(screen, darker, (int(head_x), bottom_y), bottom_r, 2)

        # Draw middle circle
        pygame.draw.circle(screen, color, (int(head_x), middle_y), middle_r)
        pygame.draw.circle(screen, darker, (int(head_x), middle_y), middle_r, 2)

        # Draw head circle (top)
        pygame.draw.circle(screen, color, (int(head_x), head_cy), head_r)
        pygame.draw.circle(screen, darker, (int(head_x), head_cy), head_r, 2)

        # Eyes (two coal dots on head)
        eye_offset_y = -head_r // 4
        eye_offset_x = head_r // 3
        eye_r = max(2, head_r // 4)
        for side in (-1, 1):
            ex = int(head_x + eye_offset_x * side)
            ey = int(head_cy + eye_offset_y)
            pygame.draw.circle(screen, (20, 20, 20), (ex, ey), eye_r)

        # Carrot nose (pointing in facing direction)
        nose_base_x = int(head_x + math.cos(face_angle) * head_r * 0.3)
        nose_base_y = int(head_cy + math.sin(face_angle) * head_r * 0.3)
        nose_tip_x = int(head_x + math.cos(face_angle) * head_r * 1.1)
        nose_tip_y = int(head_cy + math.sin(face_angle) * head_r * 1.1)
        # Triangle base perpendicular to facing direction
        perp_x = -math.sin(face_angle) * head_r * 0.15
        perp_y = math.cos(face_angle) * head_r * 0.15
        nose_points = [
            (nose_base_x + int(perp_x), nose_base_y + int(perp_y)),
            (nose_base_x - int(perp_x), nose_base_y - int(perp_y)),
            (nose_tip_x, nose_tip_y),
        ]
        pygame.draw.polygon(screen, (255, 140, 50), nose_points)

        # Stick arms (two brown lines from middle section)
        arm_start_y = middle_y
        for side in (-1, 1):
            arm_angle = face_angle + side * math.radians(50)
            arm_len = int(bottom_r * 1.2)
            ax1 = int(head_x + math.cos(face_angle + side * 0.3) * middle_r * 0.6)
            ay1 = int(arm_start_y)
            ax2 = int(ax1 + math.cos(arm_angle) * arm_len)
            ay2 = int(ay1 + math.sin(arm_angle) * arm_len)
            pygame.draw.line(screen, (100, 70, 40), (ax1, ay1), (ax2, ay2), 2)
            # Small branch fingers
            finger_angle1 = arm_angle + math.radians(20) * side
            finger_angle2 = arm_angle - math.radians(25) * side
            finger_len = int(arm_len * 0.3)
            fx1 = int(ax2 + math.cos(finger_angle1) * finger_len)
            fy1 = int(ay2 + math.sin(finger_angle1) * finger_len)
            fx2 = int(ax2 + math.cos(finger_angle2) * finger_len)
            fy2 = int(ay2 + math.sin(finger_angle2) * finger_len)
            pygame.draw.line(screen, (100, 70, 40), (ax2, ay2), (fx1, fy1), 1)
            pygame.draw.line(screen, (100, 70, 40), (ax2, ay2), (fx2, fy2), 1)

    def _draw_hp_bar(self, screen):
        """雪人上方的HP条。"""
        hp_ratio = self.hp / self.defn.hp
        bar_w = 30
        bar_h = 3
        head_x, head_y = self.segments[0]
        head_r = int(self.defn.body_width * 0.55)  # head radius
        bar_x = int(head_x - bar_w / 2)
        bar_y = int(head_y - head_r - 10)
        pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_w, bar_h))
        if hp_ratio > 0:
            if hp_ratio > 0.5:
                hp_color = (50, 220, 50)
            elif hp_ratio > 0.25:
                hp_color = (220, 200, 30)
            else:
                hp_color = (220, 50, 50)
            pygame.draw.rect(screen, hp_color, (bar_x, bar_y, int(bar_w * hp_ratio), bar_h))
