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
    burn_duration: float = 0.0             # 灼烧持续秒数（0 表示无灼烧）
    burn_dps: float = 0.0                  # 灼烧每秒伤害


from venue import ARENA_CENTER, ARENA_RADIUS


# ── 投射物 ──────────────────────────────────────────────────────────────────────


class Projectile:
    """一个由技能生成的投射物实例，具有独立的移动行为和存留时间。"""

    def __init__(self, x: float, y: float, owner_id: str,
                 skill: SkillDef, owner=None, owner_team: int = 0):
        self.x = x
        self.y = y
        self.owner_id = owner_id        # 发射者的角色 id
        self.owner = owner              # 发射者引用（orbit 模式需要跟踪位置）
        self.owner_team = owner_team
        self.skill = skill
        self.age = 0.0                  # 已存留时间
        self._hit = False               # 命中后立即消失

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
        """存留时间到期或已命中目标则返回 True。"""
        if self._hit:
            return True
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


# ── 影分身 ─────────────────────────────────────────────────────────────────

import pygame  # noqa: E402


class ShadowClone:
    """忍者影分身：镜像移动 + 周期性位置互换迷惑追踪。"""

    def __init__(self, owner, spawn_x: float, spawn_y: float,
                 skill, owner_team: int = 0):
        self.x = spawn_x
        self.y = spawn_y
        self.owner = owner
        self.owner_id = owner.char.id
        self.owner_team = owner_team
        self.skill = skill
        self.radius = owner.radius
        self.color = owner.char.color
        self.age = 0.0
        self.lifetime = skill.lifetime  # 5秒
        self.alive = True

        # 对称轴（释放时固定）：竞技场圆心 → 释放位置
        cx, cy = ARENA_CENTER
        dx = spawn_x - cx
        dy = spawn_y - cy
        self._sym_dir = (dx, dy)
        self._sym_len_sq = dx * dx + dy * dy
        self._cx = cx
        self._cy = cy

    def _mirror(self, px: float, py: float) -> tuple[float, float]:
        cx, cy = self._cx, self._cy
        dx, dy = self._sym_dir
        if self._sym_len_sq < 0.001:
            return px, py
        t = ((px - cx) * dx + (py - cy) * dy) / self._sym_len_sq
        proj_x = cx + t * dx
        proj_y = cy + t * dy
        return 2.0 * proj_x - px, 2.0 * proj_y - py

    def update(self, dt: float):
        self.age += dt
        # 镜像跟随主人（对称轴是释放时固定的线）
        self.x, self.y = self._mirror(self.owner.x, self.owner.y)

    def is_expired(self) -> bool:
        return not self.alive or self.age >= self.lifetime

    def draw(self, screen):
        alpha = max(40, int(180 * (1.0 - self.age / self.lifetime)))
        # 半透明暗色圆（影子外观）
        surf = pygame.Surface((self.radius * 3, self.radius * 3), pygame.SRCALPHA)
        cx = cy = self.radius * 3 // 2
        # 外层模糊光晕
        for i in range(3):
            r = self.radius + i * 3
            a = alpha // (i + 2)
            pygame.draw.circle(surf, (*self.color, a), (cx, cy), r)
        # 核心暗圆
        dark = tuple(max(0, c - 80) for c in self.color)
        pygame.draw.circle(surf, (*dark, alpha + 30),
                         (cx, cy), self.radius)
        screen.blit(surf, (int(self.x) - cx, int(self.y) - cy))


# ── 武僧金掌 ──────────────────────────────────────────────────────────────

class GoldenPalm:
    """武僧技能：金色手掌从天而降，造成范围伤害。"""

    def __init__(self, x: float, y: float, owner_id: str, skill, scale: float = 1.5,
                 owner_team: int = 0):
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.skill = skill
        self.owner_team = owner_team
        self.scale = scale
        self.radius = 55.0 * scale
        self.age = 0.0
        self.lifetime = 0.35
        self._damage_done = False

    def update(self, dt: float):
        self.age += dt

    def is_expired(self) -> bool:
        return self.age >= self.lifetime

    def draw(self, screen):
        """绘制金色手掌 - 完整的手掌轮廓"""
        alpha = max(40, int(200 * (1.0 - self.age / self.lifetime)))
        color = (255, 215, 0, alpha)
        cx, cy = int(self.x), int(self.y)
        
        # 创建绘制表面
        size = 160
        palm_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center_x, center_y = size // 2 + 5, size // 2 + 10
        
        # ===== 1. 先画整个手掌的填充轮廓（半透明） =====
        # 手掌主体多边形（包含所有手指的轮廓）
        hand_points = [
            # 小指外侧
            (center_x + 22, center_y - 28),  # 小指尖
            (center_x + 20, center_y - 18),  # 小指第二关节
            (center_x + 18, center_y - 8),   # 小指根部
            # 无名指
            (center_x + 12, center_y - 38),  # 无名指尖
            (center_x + 10, center_y - 24),  # 无名指第二关节
            (center_x + 10, center_y - 10),  # 无名指根部
            # 中指
            (center_x + 3, center_y - 44),   # 中指尖
            (center_x + 2, center_y - 28),   # 中指第二关节
            (center_x + 2, center_y - 12),   # 中指根部
            # 食指
            (center_x - 6, center_y - 38),   # 食指尖
            (center_x - 5, center_y - 24),   # 食指第二关节
            (center_x - 4, center_y - 10),   # 食指根部
            # 大拇指
            (center_x - 24, center_y - 12),  # 大拇指尖
            (center_x - 18, center_y - 2),   # 大拇指关节
            (center_x - 10, center_y + 6),   # 大拇指根部
            # 手掌下半部分（手腕）
            (center_x - 6, center_y + 18),   # 手掌左下
            (center_x + 16, center_y + 18),  # 手掌右下
            (center_x + 22, center_y + 8),   # 手掌右侧
            (center_x + 24, center_y - 4),   # 返回小指侧
        ]
        
        # 半透明填充
        fill_color = (255, 215, 0, alpha // 2)
        pygame.draw.polygon(palm_surf, fill_color, hand_points)
        # 金色轮廓
        pygame.draw.polygon(palm_surf, color, hand_points, 3)
        
        # ===== 2. 添加手指间的凹陷（让手指分开更明显） =====
        # 食指和中指之间
        pygame.draw.line(palm_surf, (0, 0, 0, 0), 
                        (center_x - 3, center_y - 12), 
                        (center_x - 1, center_y - 20), 8)
        # 中指和无名指之间
        pygame.draw.line(palm_surf, (0, 0, 0, 0),
                        (center_x + 4, center_y - 14),
                        (center_x + 6, center_y - 26), 8)
        # 无名指和小指之间
        pygame.draw.line(palm_surf, (0, 0, 0, 0),
                        (center_x + 11, center_y - 12),
                        (center_x + 13, center_y - 22), 8)
        # 大拇指和食指之间（虎口）
        pygame.draw.line(palm_surf, (0, 0, 0, 0),
                        (center_x - 8, center_y - 6),
                        (center_x - 14, center_y - 12), 12)
        
        # ===== 3. 画指关节的弧线（让手指更自然） =====
        joint_curves = [
            # 食指
            [(center_x - 6, center_y - 24), (center_x - 5, center_y - 20), (center_x - 4, center_y - 24)],
            # 中指
            [(center_x + 0, center_y - 28), (center_x + 2, center_y - 24), (center_x + 4, center_y - 28)],
            # 无名指
            [(center_x + 7, center_y - 24), (center_x + 9, center_y - 20), (center_x + 11, center_y - 24)],
            # 小指
            [(center_x + 15, center_y - 18), (center_x + 17, center_y - 14), (center_x + 19, center_y - 18)],
        ]
        for curve in joint_curves:
            pygame.draw.lines(palm_surf, color, False, curve, 2)
        
        # ===== 4. 手掌心的纹路 =====
        # 生命线（弧形）
        life_line = [
            (center_x - 14, center_y + 2),
            (center_x - 8, center_y + 8),
            (center_x - 2, center_y + 10),
            (center_x + 6, center_y + 8),
            (center_x + 14, center_y + 2),
        ]
        pygame.draw.lines(palm_surf, color, False, life_line, 2)
        
        # 智慧线
        head_line = [
            (center_x - 12, center_y - 4),
            (center_x - 4, center_y - 2),
            (center_x + 4, center_y - 4),
            (center_x + 12, center_y - 8),
        ]
        pygame.draw.lines(palm_surf, color, False, head_line, 2)
        
        # ===== 5. 加上金色光晕 =====
        for r in range(6, 0, -1):
            glow_alpha = max(10, alpha // (r + 1))
            glow_color = (255, 215, 100, glow_alpha)
            pygame.draw.circle(palm_surf, glow_color, (center_x, center_y), 50 + r * 4, 2)
        
        # 缩放后绘制到屏幕
        if self.scale != 1.0:
            scaled_size = max(1, int(size * self.scale))
            palm_surf = pygame.transform.scale(palm_surf, (scaled_size, scaled_size))
        screen.blit(palm_surf, (cx - palm_surf.get_width() // 2, cy - palm_surf.get_height() // 2))
        
# ── 兽人双拳 ──────────────────────────────────────────────────────────────

class FistTrap:
    """兽人技能：左右侧握拳，指节朝向敌人砸出。"""

    def __init__(self, lx: float, ly: float, rx: float, ry: float,
                 owner_id: str, skill, facing_angle: float = 0.0,
                 owner_team: int = 0):
        self.lx = lx
        self.ly = ly
        self.rx = rx
        self.ry = ry
        self.x = (lx + rx) / 2
        self.y = (ly + ry) / 2
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.skill = skill
        self.radius = 100.0
        self.age = 0.0
        self.lifetime = 1.5
        self._damage_done = False
        self._facing = facing_angle  # 敌人方向（指节朝向）

    def update(self, dt: float):
        self.age += dt

    def is_expired(self) -> bool:
        return self.age >= self.lifetime

    def _punch_scale(self) -> float:
        """出拳缩放动画：0.6 → 1.2 → 0.9。"""
        t = self.age / self.lifetime
        if t < 0.15:
            return 0.6 + t / 0.15 * 0.6
        elif t < 0.3:
            return 1.2 - (t - 0.15) / 0.15 * 0.3
        else:
            return 0.9

    def _draw_single_fist(self, screen, fx, fy, is_left: bool, alpha: int):
        """侧握拳：指节阶梯朝向敌人，拳体垂直于 facing 方向。"""
        fist_r = 94
        scale = self._punch_scale()
        sr = int(fist_r * scale)

        color = (180, 140, 80, alpha)
        fill_color = (140, 100, 50, alpha // 3)

        # 指节朝向敌人 (= facing 方向)
        face_dir_x = math.cos(self._facing)
        face_dir_y = math.sin(self._facing)
        # 拳体长轴垂直于 facing
        perp_x = -face_dir_y
        perp_y = face_dir_x

        # 拇指在拳体外侧
        thumb_sign = 1 if is_left else -1

        # 拳体参数（按缩放调整）
        fw_front = int(sr * 0.6)   # 前端半宽（指节端）
        fw_back = int(sr * 0.3)    # 后端半宽（手腕端）
        fh = int(sr * 0.8)         # 拳体长度

        surf_sz = int(sr * 3.5)
        surf = pygame.Surface((surf_sz, surf_sz), pygame.SRCALPHA)
        scx = scy = surf_sz // 2

        # 拳体中心 → 前后端点
        front_cx = scx + face_dir_x * fh * 0.3
        front_cy = scy + face_dir_y * fh * 0.3
        back_cx = scx - face_dir_x * fh * 0.5
        back_cy = scy - face_dir_y * fh * 0.5

        # 拳体四个角
        body_pts = [
            (front_cx + face_dir_x * 2 + perp_x * fw_front, front_cy + face_dir_y * 2 + perp_y * fw_front),
            (front_cx + face_dir_x * 2 - perp_x * fw_front, front_cy + face_dir_y * 2 - perp_y * fw_front),
            (back_cx - perp_x * fw_back, back_cy - perp_y * fw_back),
            (back_cx + perp_x * fw_back, back_cy + perp_y * fw_back),
        ]
        pygame.draw.polygon(surf, fill_color, body_pts)
        pygame.draw.polygon(surf, color, body_pts, 3)

        # 指节阶梯（4阶，在拳面前端，沿 perp 方向排列）
        for j in range(4):
            j_off = (j - 1.5) / 2.0  # -0.75, -0.25, 0.25, 0.75
            sx = front_cx + face_dir_x * (4 + j * 3)
            sy = front_cy + face_dir_y * (4 + j * 3)
            step_top_y = sy + perp_y * fw_front * j_off * 0.8
            step_top_x = sx + perp_x * fw_front * j_off * 0.8
            step_bot_y = step_top_y + perp_y * fw_front * 0.25
            step_bot_x = step_top_x + perp_x * fw_front * 0.25
            pygame.draw.line(surf, color,
                           (step_top_x, step_top_y),
                           (step_bot_x, step_bot_y), max(1, int(2 * scale)))
            pygame.draw.circle(surf, color,
                             (int(step_top_x), int(step_top_y)),
                             max(1, int(2 * scale)), 1)

        # 大拇指凸起
        thumb_x = front_cx + perp_x * fw_front * 0.8 * thumb_sign
        thumb_y = front_cy + perp_y * fw_front * 0.8 * thumb_sign
        tw, th = int(9 * scale), int(12 * scale)
        pygame.draw.ellipse(surf, fill_color,
                          (thumb_x - tw // 2, thumb_y - th // 2, tw, th))
        pygame.draw.ellipse(surf, color,
                          (thumb_x - tw // 2, thumb_y - th // 2, tw, th), 2)

        # 拳眼凹陷
        eye_x = front_cx + face_dir_x * 6
        eye_y = front_cy + face_dir_y * 6
        eye_r = int(5 * scale)
        pygame.draw.arc(surf, color,
                      (eye_x - eye_r, eye_y - eye_r, eye_r * 2, eye_r * 2),
                      0, math.pi, 1)

        # 手腕
        wrist_w = int(fw_back * 0.6)
        wrist_len = int(8 * scale)
        wrist_x = back_cx - face_dir_x * wrist_len
        wrist_y = back_cy - face_dir_y * wrist_len
        wrist_pts = [
            (back_cx + perp_x * wrist_w, back_cy + perp_y * wrist_w),
            (back_cx - perp_x * wrist_w, back_cy - perp_y * wrist_w),
            (wrist_x - perp_x * wrist_w, wrist_y - perp_y * wrist_w),
            (wrist_x + perp_x * wrist_w, wrist_y + perp_y * wrist_w),
        ]
        pygame.draw.polygon(surf, fill_color, wrist_pts)
        pygame.draw.polygon(surf, color, wrist_pts, 2)

        screen.blit(surf, (int(fx) - scx, int(fy) - scy))

    def draw(self, screen):
        alpha = max(20, int(180 * (1.0 - self.age / self.lifetime)))

        # 冲击波（命中时刻扩大）
        cx, cy = int(self.x), int(self.y)
        t = self.age / self.lifetime
        wave_r = self.radius * (0.2 + 0.8 * min(t * 3, 1.0))
        wave_alpha = max(0, int(alpha * (1.0 - t)))
        if wave_alpha > 0:
            wave_surf = pygame.Surface((int(wave_r * 2 + 4), int(wave_r * 2 + 4)), pygame.SRCALPHA)
            pygame.draw.circle(wave_surf, (180, 140, 80, wave_alpha),
                             (int(wave_r) + 2, int(wave_r) + 2), int(wave_r), 2)
            screen.blit(wave_surf, (cx - int(wave_r) - 2, cy - int(wave_r) - 2))

        # 出拳速度线（从角色方向飞来）
        speed_alpha = max(0, int(alpha * (1.0 - t * 2)))
        if speed_alpha > 0:
            for fx, fy in [(self.lx, self.ly), (self.rx, self.ry)]:
                sx = fx - math.cos(self._facing) * 30
                sy = fy - math.sin(self._facing) * 30
                ex = fx - math.cos(self._facing) * 60
                ey = fy - math.sin(self._facing) * 60
                for i in range(3):
                    lx = sx + (ex - sx) * i / 3
                    ly = sy + (ey - sy) * i / 3
                    pygame.draw.line(screen, (200, 160, 100, speed_alpha // (i + 2)),
                                   (int(lx), int(ly)),
                                   (int(lx + math.cos(self._facing) * 8), int(ly + math.sin(self._facing) * 8)), 1)

        self._draw_single_fist(screen, self.lx, self.ly, is_left=True, alpha=alpha)
        self._draw_single_fist(screen, self.rx, self.ry, is_left=False, alpha=alpha)


# ── 海洋漩涡 ──────────────────────────────────────────────────────────────

class VortexEntity:
    """海洋漩涡：将范围内敌人螺旋吸入中心，造成伤害并锁定技能。"""

    def __init__(self, x: float, y: float, owner_id: str, skill,
                 owner_team: int = 0):
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.skill = skill
        self.owner_team = owner_team
        self.radius = 120.0
        self.core_radius = 12.0
        self.age = 0.0
        self.lifetime = skill.lifetime
        self.alive = True
        self._captured: dict[int, float] = {}
        self._max_captures = 3
        self._pull_speed_outer = 70.0  # 外圈速度
        self._pull_speed_inner = 45.0  # 内圈速度
        self._captured_vx: dict[int, float] = {}
        self._captured_vy: dict[int, float] = {}
        self._entry_dist: dict[int, float] = {}   # 首次捕获时的距离
        self._total_angle: dict[int, float] = {}  # 累计旋转角度
        self._target_rotations = 2  # 目标圈数
        self._spin_base = random.uniform(0, 6.28)
        self._spiral_arms = 3

    def update(self, dt: float):
        self.age += dt

    def _try_capture(self, entity, tid: int) -> bool:
        if tid in self._captured:
            return True
        if len(self._captured) >= self._max_captures:
            return False
        self._captured[tid] = self.age
        self._captured_vx[tid] = getattr(entity, 'vx', 0.0)
        self._captured_vy[tid] = getattr(entity, 'vy', 0.0)
        self._total_angle[tid] = 0.0
        if hasattr(entity, 'skill_locked'):
            entity.skill_locked = True
        return True

    def apply_to_player(self, player) -> bool:
        if not player.alive or player.team == self.owner_team:
            return False
        dist = math.hypot(self.x - player.x, self.y - player.y)
        if dist > self.radius:
            return False
        tid = id(player)
        if tid not in self._captured:
            self._entry_dist[tid] = max(dist, self.core_radius + 1)
        if not self._try_capture(player, tid):
            return False
        self._spiral_force(player, dist)
        if dist < self.core_radius:
            return True
        return False

    def apply_to_pet(self, pet) -> bool:
        if pet.owner_team == self.owner_team:
            return False
        px, py = pet.segments[0] if hasattr(pet, 'segments') else (pet.x, pet.y)
        dist = math.hypot(self.x - px, self.y - py)
        if dist > self.radius:
            return False
        tid = id(pet)
        if tid not in self._captured:
            self._entry_dist[tid] = max(dist, self.core_radius + 1)
        if not self._try_capture(pet, tid):
            return False
        self._spiral_force(pet, dist, px, py)
        if dist < self.core_radius:
            return True
        return False

    def _pull_speed(self, dist: float) -> float:
        """速度梯度：外圈 70 → 内圈 45。"""
        t = (dist - self.core_radius) / (self.radius - self.core_radius)
        t = max(0.0, min(1.0, t))
        return self._pull_speed_outer * t + self._pull_speed_inner * (1.0 - t)

    def _spiral_force(self, entity, dist: float, ex: float = None, ey: float = None):
        if ex is None:
            ex, ey = entity.x, entity.y
        tid = id(entity)
        dx = self.x - ex
        dy = self.y - ey
        angle = math.atan2(dy, dx)
        tangent = angle + math.pi / 2

        # 径向吸入 + 切向旋转（比例保证 2 圈完成时到达核心）
        rs = self._pull_speed(dist)
        nvx = math.cos(angle) * rs
        nvy = math.sin(angle) * rs
        entry_d = self._entry_dist.get(tid, self.radius)
        total_d = max(entry_d - self.core_radius, 1.0)
        remaining_d = dist - self.core_radius
        remaining_ratio = max(0.0, min(1.0, remaining_d / total_d))
        ts = rs * 9.0 * remaining_ratio if remaining_d > 3 else 0
        nvx += math.cos(tangent) * ts
        nvy += math.sin(tangent) * ts
        self._total_angle[tid] = self._total_angle.get(tid, 0.0) + ts / max(dist, 1.0) * 0.016

        # 直接修改位置（绕过速度系统）
        if hasattr(entity, 'segments') and entity.segments:
            hx, hy = entity.segments[0]
            entity.segments[0] = (hx + nvx * 0.016, hy + nvy * 0.016)
        else:
            try:
                entity.x += nvx * 0.016
                entity.y += nvy * 0.016
            except AttributeError:
                pass

    def is_expired(self) -> bool:
        return self.age >= self.lifetime

    def draw(self, screen):
        alpha = max(20, int(180 * (1.0 - self.age / self.lifetime)))
        base_color = (30, 120, 210)
        cx, cy = int(self.x), int(self.y)
        now = self.age

        # 螺旋臂（🌀 三条旋转弧线从外向内收敛）
        for arm in range(self._spiral_arms):
            arm_angle = self._spin_base + arm * 2 * math.pi / self._spiral_arms
            pts = []
            segments = 40
            for i in range(segments + 1):
                t = i / segments
                r = self.radius * (1.0 - t * 0.85)  # 从外到内
                a = arm_angle + now * 1.8 + t * math.pi * 1.5  # 旋转 + 向内卷曲
                px = cx + math.cos(a) * r
                py = cy + math.sin(a) * r
                pts.append((int(px), int(py)))
            if len(pts) >= 2:
                la = alpha * (0.4 + 0.3 * arm / self._spiral_arms)
                pygame.draw.lines(screen, (*base_color, int(la)),
                                False, pts, max(1, int(3 - arm * 0.5)))

        # 多层涟漪圆环（间距渐密）
        for layer in range(5):
            r = self.radius * (0.2 + layer * 0.18)
            ring_alpha = alpha // (layer + 2)
            ring_spin = now * (0.8 + layer * 0.3)
            # 断点弧线
            for gap in range(4):
                a1 = ring_spin + gap * math.pi / 2
                a2 = a1 + math.pi / 4
                arc_surf = pygame.Surface((int(r * 2 + 4), int(r * 2 + 4)), pygame.SRCALPHA)
                rect = pygame.Rect(2, 2, int(r * 2), int(r * 2))
                pygame.draw.arc(arc_surf, (*base_color, ring_alpha),
                              rect, -a2, -a1, 2)
                screen.blit(arc_surf, (cx - int(r) - 2, cy - int(r) - 2))

        # 外圈边界
        pygame.draw.circle(screen, (*base_color, alpha // 2),
                         (cx, cy), int(self.radius), 2)
        # 核心暗点
        core_alpha = alpha + 20
        pygame.draw.circle(screen, (5, 30, 70, min(255, core_alpha)),
                         (cx, cy), int(self.core_radius))


# ── 波纹 ─────────────────────────────────────────────────────────────────

class WaveEntity:
    """潮汐使者技能：120° 弧形波纹向外扩散，距离越远颜色越浅。"""

    def __init__(self, x: float, y: float, angle: float,
                 owner_id: str, skill, owner_team: int = 0):
        self.x = x
        self.y = y
        self.angle = angle
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.skill = skill
        self.age = 0.0
        self.lifetime = 1.4
        self.spread = math.radians(120)
        self.max_length = 120.0
        self.damage = 2.0
        self.knockback = 8.0
        self._hit_targets: set = set()
        self._seed = random.uniform(0, 100)
        self._current_r = 0.0
        self._segments: list[tuple[float, float]] = []

    def _build_segments(self, r: float) -> list[tuple[float, float]]:
        segs = []
        num = 16
        half = self.spread / 2
        for i in range(num + 1):
            t = i / num
            a = self.angle - half + t * self.spread
            wave_r = r + math.sin(t * 8 + self._seed) * 3
            segs.append((self.x + math.cos(a) * wave_r, self.y + math.sin(a) * wave_r))
        return segs

    def update(self, dt: float):
        self.age += dt
        # 半径从小到大扩散 (ease-out)
        progress = min(1.0, self.age / self.lifetime)
        self._current_r = self.max_length * (1.0 - (1.0 - progress) ** 2)
        self._segments = self._build_segments(self._current_r)

    def is_expired(self) -> bool:
        return self.age >= self.lifetime

    def _point_to_segment_dist(self, px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        cx, cy = x1 + t * dx, y1 + t * dy
        return math.hypot(px - cx, py - cy)

    def collides_with_player(self, player) -> bool:
        if player.team == self.owner_team or id(player) in self._hit_targets:
            return False
        threshold = player.radius + 4
        for i in range(len(self._segments) - 1):
            x1, y1 = self._segments[i]
            x2, y2 = self._segments[i + 1]
            if self._point_to_segment_dist(player.x, player.y, x1, y1, x2, y2) < threshold:
                self._hit_targets.add(id(player))
                return True
        return False

    def collides_with_pet(self, pet) -> bool:
        if pet.owner_team == self.owner_team or id(pet) in self._hit_targets:
            return False
        px, py = pet.segments[0] if hasattr(pet, 'segments') else (pet.x, pet.y)
        pr = getattr(pet, '_head_radius', lambda: 5)()
        if callable(pr):
            pr = 5
        threshold = pr + 4
        for i in range(len(self._segments) - 1):
            x1, y1 = self._segments[i]
            x2, y2 = self._segments[i + 1]
            if self._point_to_segment_dist(px, py, x1, y1, x2, y2) < threshold:
                self._hit_targets.add(id(pet))
                return True
        return False

    def draw(self, screen):
        alpha = max(15, int(200 * (1.0 - self.age / self.lifetime)))
        if len(self._segments) >= 2:
            for i in range(len(self._segments) - 1):
                x1, y1 = self._segments[i]
                x2, y2 = self._segments[i + 1]
                # 距离越远颜色越浅
                seg_dist = math.hypot(x1 - self.x, y1 - self.y) / self.max_length
                la = alpha * (1.0 - seg_dist * 0.5)
                base = self.skill.color if self.skill else (30, 140, 220)
                c = (base[0], base[1], base[2], int(la))
                pygame.draw.line(screen, c,
                               (int(x1), int(y1)), (int(x2), int(y2)), max(1, int(2.5 - seg_dist)))


class HuntMark:
    """狂战士技能-猎杀印记：在敌人位置生成红色准星圆圈，
    0.9秒延迟后传送主人到中心并造成速度加成的AOE伤害。"""

    def __init__(self, x: float, y: float, owner_id: str, skill,
                 saved_speed: float = 0.0, saved_angle: float = 0.0,
                 owner_team: int = 0):
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.skill = skill
        self.owner_team = owner_team
        self.radius = 90.0
        self.age = 0.0
        self.lifetime = 1.5
        self._teleport_done = False
        self._damage_done = False
        self.saved_speed = saved_speed
        self.saved_angle = saved_angle

    def update(self, dt: float):
        self.age += dt

    def is_expired(self) -> bool:
        return self.age >= self.lifetime

    def draw(self, screen):
        alpha = max(30, int(180 * (1.0 - self.age / self.lifetime)))
        cx, cy = int(self.x), int(self.y)
        r = int(self.radius)

        # 浅红色填充圆
        fill_surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(fill_surf, (255, 140, 140, alpha // 2),
                           (r + 2, r + 2), r)
        screen.blit(fill_surf, (cx - r - 2, cy - r - 2))

        # 红色边框
        border_surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(border_surf, (255, 40, 40, alpha),
                           (r + 2, r + 2), r, 2)
        screen.blit(border_surf, (cx - r - 2, cy - r - 2))

        # 四向准星线段（从边界向内指向圆心）
        cross_len = 18
        gap = 8
        cc = (255, 60, 60, alpha)
        # 上
        pygame.draw.line(screen, cc,
                         (cx, cy - r + gap), (cx, cy - r + gap + cross_len), 2)
        # 下
        pygame.draw.line(screen, cc,
                         (cx, cy + r - gap), (cx, cy + r - gap - cross_len), 2)
        # 左
        pygame.draw.line(screen, cc,
                         (cx - r + gap, cy), (cx - r + gap + cross_len, cy), 2)
        # 右
        pygame.draw.line(screen, cc,
                         (cx + r - gap, cy), (cx + r - gap - cross_len, cy), 2)


class TreeEntity:
    """森林精灵技能-生命之树：长方形树干碰撞 + 治疗光环。40 HP，碰撞弹开角色。"""

    def __init__(self, x: float, y: float, owner_id: str, owner_team: int = 0):
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.hp = 40.0
        self.trunk_w = 26             # 树干碰撞宽度
        self.trunk_h = 50             # 树干碰撞高度
        self.radius = 18              # 粗略碰撞半径（投射物/闪电用）
        self.heal_radius = 120         # 治疗光环半径
        self.heal_rate = 2.0          # 每秒回血量
        self.age = 0.0
        self._heal_timers: dict[int, float] = {}
        self._weapon_hit_times: dict[int, float] = {}  # 武器命中冷却

    def _trunk_rect(self):
        """返回树干 AABB 矩形。"""
        return (self.x - self.trunk_w / 2, self.y - self.trunk_h / 2,
                self.trunk_w, self.trunk_h)

    def _rect_vs_circle(self, cx: float, cy: float, cr: float):
        """AABB vs 圆碰撞。返回 (hit, nx, ny, overlap)。"""
        rx, ry, rw, rh = self._trunk_rect()
        closest_x = max(rx, min(cx, rx + rw))
        closest_y = max(ry, min(cy, ry + rh))
        dx = cx - closest_x
        dy = cy - closest_y
        dist = math.hypot(dx, dy)
        if dist < cr:
            if dist < 0.001:
                return True, 0, -1, cr
            return True, dx / dist, dy / dist, cr - dist
        return False, 0, 0, 0

    def collides_with_point(self, px: float, py: float, pr: float = 0) -> bool:
        """外部碰撞检测用（投射物/武器/闪电）。"""
        hit, _, _, _ = self._rect_vs_circle(px, py, pr)
        return hit

    def update(self, dt: float):
        self.age += dt

    def is_expired(self) -> bool:
        return self.hp <= 0

    def take_damage(self, amount: float):
        self.hp -= amount

    def bounce_player(self, player) -> bool:
        """长方形树干碰撞 + 弹开。"""
        hit, nx, ny, overlap = self._rect_vs_circle(player.x, player.y, player.radius)
        if not hit:
            return False
        # 推离重叠
        player.x += nx * overlap
        player.y += ny * overlap
        # 反弹速度
        dot = player.vx * nx + player.vy * ny
        if dot < 0:
            player.vx -= 2 * dot * nx
            player.vy -= 2 * dot * ny
        return True

    def try_heal(self, player, dt: float) -> bool:
        """检测玩家是否在治疗光环内，若是则按 heal_rate 回血（仅主人）。"""
        if player.team != self.owner_team:
            return False
        dist = math.hypot(player.x - self.x, player.y - self.y)
        if dist > self.heal_radius + player.radius:
            return False
        tid = id(player)
        remaining = self._heal_timers.get(tid, 0.0) - dt
        if remaining > 0:
            self._heal_timers[tid] = remaining
            return False
        # 每秒回血 heal_rate
        player.hp = min(100, player.hp + self.heal_rate)
        self._heal_timers[tid] = 1.0 + remaining
        return True

    def draw(self, screen):
        import pygame
        cx, cy = int(self.x), int(self.y)
        tw, th = self.trunk_w, self.trunk_h

        # ── 治疗光环 ──
        pulse = math.sin(self.age * 3.0) * 0.3 + 0.7
        heal_alpha = int(25 * pulse)
        r = self.heal_radius
        aura = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(aura, (60, 200, 80, heal_alpha),
                           (r + 2, r + 2), r)
        pygame.draw.circle(aura, (80, 220, 100, heal_alpha + 15),
                           (r + 2, r + 2), r, 2)
        screen.blit(aura, (cx - r - 2, cy - r - 2))

        # 随机小十字治疗粒子（圆圈内飘浮）
        cross_count = 12
        cross_size = 6
        cross_alpha = int(50 * pulse)
        cx_color = (80, 210, 100, cross_alpha)
        for i in range(cross_count):
            # 基于树位置 + 序号 + 时间的确定性随机
            seed = self.x * 173.3 + self.y * 241.7 + i * 97.1 + self.age * 0.7
            angle = (seed % 1000) / 1000 * 2 * math.pi
            dist = ((seed * 131.1) % 1000) / 1000 * (r - 14)
            px = int(cx + math.cos(angle) * dist)
            py = int(cy + math.sin(angle) * dist)
            # 小十字
            hs = cross_size // 2
            pygame.draw.line(screen, cx_color, (px - hs, py), (px + hs, py), 1)
            pygame.draw.line(screen, cx_color, (px, py - hs), (px, py + hs), 1)

        # ── 树干（长方形，含木质纹理） ──
        trunk_rect = pygame.Rect(cx - tw // 2, cy - th // 2, tw, th)
        pygame.draw.rect(screen, (101, 67, 33), trunk_rect)
        # 木质纹理竖线
        for tx in (cx - 5, cx, cx + 5):
            pygame.draw.line(screen, (80, 50, 20),
                             (tx, cy - th // 2 + 4), (tx, cy + th // 2 - 4), 1)
        pygame.draw.rect(screen, (70, 40, 15), trunk_rect, 1)

        # ── 树枝 + 圆形树叶（长枝多叉） ──
        trunk_top = cy - th // 2 + 2
        sway = math.sin(self.age * 2.5) * 1.5
        leaf_color_fill = (50, 160, 60)
        leaf_color_edge = (80, 200, 90)
        leaf_color_vein = (40, 130, 50)

        # 主枝定义: (末端dx, 末端dy, 主叶半径, 分枝色, 子枝列表[(子dx, 子dy, 子叶半径), ...])
        main_branches = [
            (-30, -32, 13, (75, 55, 35), [(-42, -42, 9), (-22, -48, 8)]),
            (28, -38, 12, (85, 60, 38), [(40, -50, 9), (32, -28, 8)]),
            (-16, -46, 11, (70, 50, 30), [(-28, -56, 8), (-8, -52, 7)]),
            (20, -30, 12, (80, 58, 35), [(32, -40, 8)]),
            (-36, -22, 10, (72, 52, 32), [(-48, -30, 9), (-42, -16, 7)]),
            (34, -24, 10, (82, 57, 33), [(46, -34, 9)]),
            (-6, -52, 10, (68, 48, 28), [(-18, -62, 7), (6, -60, 7)]),
        ]

        for bx, by, leaf_r, br_color, sub_branches in main_branches:
            # 主枝干
            ex, ey = cx + bx, cy + by
            pygame.draw.line(screen, br_color, (cx, trunk_top), (ex, ey), 2)
            # 主枝末端树叶
            lx = int(ex + sway * (bx * 0.02))
            ly = int(ey)
            pygame.draw.circle(screen, leaf_color_fill, (lx, ly), leaf_r)
            pygame.draw.circle(screen, leaf_color_edge, (lx, ly), leaf_r, 1)
            pygame.draw.line(screen, leaf_color_vein,
                             (lx - leaf_r // 2, ly), (lx + leaf_r // 2, ly), 1)
            # 子枝（分叉）
            for sx, sy, sr in sub_branches:
                sub_ex, sub_ey = cx + sx, cy + sy
                pygame.draw.line(screen, br_color, (ex, ey), (sub_ex, sub_ey), 1)
                slx = int(sub_ex + sway * (sx * 0.02))
                sly = int(sub_ey)
                pygame.draw.circle(screen, leaf_color_fill, (slx, sly), sr)
                pygame.draw.circle(screen, leaf_color_edge, (slx, sly), sr, 1)
                pygame.draw.line(screen, leaf_color_vein,
                                 (slx - sr // 2, sly), (slx + sr // 2, sly), 1)


class LeafBlade:
    """森林精灵技能-叶刃风暴：环绕角色旋转，敌人进入范围后逐一射出。"""

    ORBIT = "orbit"
    FIRING = "firing"
    EXPIRED = "expired"

    def __init__(self, owner, opponent, start_angle: float, skill, shoot_index: int,
                 owner_team: int = 0):
        self.owner = owner
        self.opponent = opponent
        self.owner_id = owner.char.id
        self.owner_team = owner_team
        self.skill = skill
        self.state = self.ORBIT
        self.orbit_radius = 70.0
        self.orbit_speed = 4.0
        self.detect_range = 180.0
        self.bullet_speed = 350.0
        self.damage = 4.0
        self.radius = 14.0
        self.age = 0.0
        self.lifetime = 12.0
        self._orbit_angle = start_angle
        self._shoot_delay = shoot_index * 0.3 + 0.3
        self._detect_target = opponent
        self._fired = False
        self._hit = False
        self._orbit_hit_cooldown: dict[int, float] = {}  # 轨道阶段每目标冷却
        self.x = owner.x + math.cos(start_angle) * self.orbit_radius
        self.y = owner.y + math.sin(start_angle) * self.orbit_radius
        self.vx = 0.0
        self.vy = 0.0

    def update(self, dt: float):
        self.age += dt
        if self.state == self.ORBIT:
            self._orbit_angle += self.orbit_speed * dt
            if self.owner is None or not self.owner.alive:
                self.state = self.EXPIRED
                return
            self.x = self.owner.x + math.cos(self._orbit_angle) * self.orbit_radius
            self.y = self.owner.y + math.sin(self._orbit_angle) * self.orbit_radius
            if self._shoot_delay > 0:
                self._shoot_delay -= dt
                return
            if self._try_fire():
                return
            if self.age >= self.lifetime:
                self.state = self.EXPIRED
        elif self.state == self.FIRING:
            self.x += self.vx * dt
            self.y += self.vy * dt
            dx = self.x - ARENA_CENTER[0]
            dy = self.y - ARENA_CENTER[1]
            if math.hypot(dx, dy) > ARENA_RADIUS:
                self.state = self.EXPIRED

    def _try_fire(self) -> bool:
        target = getattr(self, '_detect_target', self.opponent)
        if target is None:
            return False
        # 隐身时无法瞄准
        if getattr(self.opponent, 'invisible', False):
            return False
        dist = math.hypot(target.x - self.owner.x, target.y - self.owner.y)
        if dist >= self.detect_range:
            return False
        self.state = self.FIRING
        dx = target.x - self.x
        dy = target.y - self.y
        d = math.hypot(dx, dy)
        if d > 0.001:
            self.vx = dx / d * self.bullet_speed
            self.vy = dy / d * self.bullet_speed
        else:
            angle = self._orbit_angle
            self.vx = math.cos(angle) * self.bullet_speed
            self.vy = math.sin(angle) * self.bullet_speed
        self._fired = True
        return True

    def is_expired(self) -> bool:
        # 轨道阶段不因碰撞消失；射击命中后才消失
        if self.state == self.FIRING and self._hit:
            return True
        return self.state == self.EXPIRED

    def draw(self, screen):
        import pygame
        cx, cy = int(self.x), int(self.y)

        if self.state == self.ORBIT:
            tangent = self._orbit_angle + math.pi / 2
            tx = math.cos(tangent)
            ty = math.sin(tangent)
            leaf_len = 16
            leaf_w = 5
            pts = []
            for i in range(5):
                t = i / 4
                u = (t - 0.5) * leaf_len
                w = leaf_w * (1.0 - (t - 0.5) ** 2 * 4)
                pts.append((cx + tx * u + ty * w, cy + ty * u - tx * w))
            pygame.draw.polygon(screen, (60, 200, 70), [(int(x), int(y)) for x, y in pts])
            pygame.draw.polygon(screen, (30, 140, 40), [(int(x), int(y)) for x, y in pts], 1)
        else:
            angle = math.atan2(self.vy, self.vx)
            hx = math.cos(angle)
            hy = math.sin(angle)
            tip = (cx + hx * 13, cy + hy * 13)
            bl = (cx - hx * 6 + hy * 6, cy - hy * 6 - hx * 6)
            br = (cx - hx * 6 - hy * 6, cy - hy * 6 + hx * 6)
            pts = [tip, bl, br]
            pygame.draw.polygon(screen, (60, 200, 70), [(int(x), int(y)) for x, y in pts])
            pygame.draw.polygon(screen, (30, 140, 40), [(int(x), int(y)) for x, y in pts], 1)


# ── Beam Proxy（兼容 main.py 碰撞管线对 proj.skill.damage/radius 的访问）──────

class _BeamProxy:
    __slots__ = ('damage', 'radius')

    def __init__(self, damage: float, radius: int):
        self.damage = damage
        self.radius = radius


# ── CrescentBeam（月牙剑气）────────────────────────────────────────────────────

class CrescentBeam:
    """穿透型月牙剑气 —— 月牙形碰撞体，每目标 0.3s 冷却。"""

    def __init__(self, x: float, y: float, angle: float, owner_id: str,
                 damage: float, color: tuple[int, int, int],
                 lifetime: float, speed: float, size: int,
                 owner_team: int = 0):
        self.x = x
        self.y = y
        self.angle = angle
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.skill = _BeamProxy(damage, size // 2)
        self.radius = size // 2
        self.lifetime = lifetime
        self.age = 0.0
        self.color = color
        self.size = size
        # 两等圆交补：B 在 A 后方，B 的前边缘落在 A 圆心→前边缘中点
        # B 前边缘 = d + R = R/2 → d = R/2（B 在 angle+π 方向）
        self.R = size / 2
        self.circle_B_offset = self.R / 2          # 两圆心距 = 25
        h = math.sqrt(self.R * self.R - (self.circle_B_offset / 2) ** 2)
        self._alpha = math.atan2(h, self.circle_B_offset / 2)
        self._hit_targets: dict[str, float] = {}
        self._hit_cd = 0.02

    def _circle_B_center(self):
        """圆 B 圆心（在 A 后方，即 angle+π 方向）。"""
        bx = self.x - math.cos(self.angle) * self.circle_B_offset
        by = self.y - math.sin(self.angle) * self.circle_B_offset
        return bx, by

    def update(self, dt: float):
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        dx = self.x - ARENA_CENTER[0]
        dy = self.y - ARENA_CENTER[1]
        if math.hypot(dx, dy) > ARENA_RADIUS:
            self.age = self.lifetime

    def is_expired(self) -> bool:
        return self.age >= self.lifetime

    def collides_with(self, player) -> bool:
        """两等圆交补碰撞：在圆A内 且 不完全在圆B内。"""
        # 圆 A 粗筛
        dx = self.x - player.x
        dy = self.y - player.y
        if math.hypot(dx, dy) > self.R + player.radius:
            return False
        # 圆 B：玩家是否完全在其内部（补集区域）
        bx, by = self._circle_B_center()
        dbx = bx - player.x
        dby = by - player.y
        if math.hypot(dbx, dby) + player.radius <= self.R:
            return False
        # 每目标冷却
        target_id = id(player)
        last = self._hit_targets.get(target_id, -999.0)
        if self.age - last < self._hit_cd:
            return False
        self._hit_targets[target_id] = self.age
        return True

    def collides_with_player_circle(self, cx: float, cy: float, cr: float) -> bool:
        """纯形状碰撞（无冷却），用于 clone 销毁。"""
        dx = self.x - cx
        dy = self.y - cy
        if math.hypot(dx, dy) > self.R + cr:
            return False
        bx, by = self._circle_B_center()
        dbx = bx - cx
        dby = by - cy
        if math.hypot(dbx, dby) + cr <= self.R:
            return False
        return True

    def draw(self, screen):
        """两等圆交补月牙：A 前弧 + B 前弧，B 在 A 后方。"""
        R = self.R
        alpha = self._alpha
        offset = self.circle_B_offset
        # 表面以 A 为中心，需覆盖后方 B (最远 = offset+R = 75)
        max_r = int(offset + R)
        surf_margin = 10
        surf_size = max_r * 2 + surf_margin
        surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        scx = scy = surf_size / 2  # A 圆心在表面中心
        # B 圆心在 A 后方 (angle + π 方向)
        b_cx = scx - math.cos(self.angle) * offset
        b_cy = scy - math.sin(self.angle) * offset

        # 光晕（围绕圆A）
        for i in range(3):
            a_val = 40 - i * 12
            rr = R + 3 + i * 3
            pygame.draw.circle(surf, (*self.color, a_val), (scx, scy), rr, 1)

        n = 30
        # 外弧：圆 A 前部，angle−α → angle+α（短弧 span=2α）
        outer_pts = []
        for i in range(n + 1):
            a = self.angle - alpha + 2 * alpha * i / n
            outer_pts.append((scx + math.cos(a) * R, scy + math.sin(a) * R))

        # 内弧：圆 B 前部，angle+α → angle−α（反向，沿 B 面向 A 的边界）
        inner_pts = []
        for i in range(n, -1, -1):
            a = self.angle - alpha + 2 * alpha * i / n
            inner_pts.append((b_cx + math.cos(a) * R, b_cy + math.sin(a) * R))

        all_pts = outer_pts + inner_pts
        pygame.draw.polygon(surf, self.color, all_pts)
        pygame.draw.polygon(surf, (255, 255, 255), all_pts, 1)

        # blit: A 圆心对准世界坐标 (self.x, self.y)
        screen.blit(surf, (int(self.x) - scx, int(self.y) - scy))


# ── VerticalBeam（竖向剑气）────────────────────────────────────────────────────

class VerticalBeam:
    """穿透型竖向光柱，长轴垂直于飞行方向，每目标 0.3s 冷却。"""

    def __init__(self, x: float, y: float, angle: float, owner_id: str,
                 damage: float, color: tuple[int, int, int],
                 lifetime: float, speed: float, length: float, width: float,
                 owner_team: int = 0):
        self.x = x
        self.y = y
        self.angle = angle
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.skill = _BeamProxy(damage, int(math.hypot(length / 2, width / 2)))
        self.radius = int(math.hypot(length / 2, width / 2))
        self.lifetime = lifetime
        self.age = 0.0
        self.color = color
        self.half_len = length / 2
        self.half_w = width / 2
        self._hit_targets: dict[str, float] = {}
        self._hit_cd = 0.02
        # 光点粒子 (along_pos, perp_pos, phase)
        self._particles = [(random.uniform(-0.9, 0.9),
                           random.uniform(-0.9, 0.9),
                           random.uniform(0, 2 * math.pi))
                          for _ in range(10)]

    def update(self, dt: float):
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        dx = self.x - ARENA_CENTER[0]
        dy = self.y - ARENA_CENTER[1]
        if math.hypot(dx, dy) > ARENA_RADIUS:
            self.age = self.lifetime

    def is_expired(self) -> bool:
        return self.age >= self.lifetime

    def collides_with(self, player) -> bool:
        """OBB（有向矩形）vs 圆碰撞。"""
        pdx = player.x - self.x
        pdy = player.y - self.y
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        along = abs(pdx * cos_a + pdy * sin_a)
        perp = abs(-pdx * sin_a + pdy * cos_a)

        if along > self.half_w + player.radius:
            return False
        if perp > self.half_len + player.radius:
            return False

        target_id = id(player)
        last = self._hit_targets.get(target_id, -999.0)
        if self.age - last < self._hit_cd:
            return False
        self._hit_targets[target_id] = self.age
        return True

    def collides_with_player_circle(self, cx: float, cy: float, cr: float) -> bool:
        """纯形状碰撞检测（无冷却），用于 clone 销毁等场景。"""
        pdx = cx - self.x
        pdy = cy - self.y
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        along = abs(pdx * cos_a + pdy * sin_a)
        perp = abs(-pdx * sin_a + pdy * cos_a)
        return along <= self.half_w + cr and perp <= self.half_len + cr

    def draw(self, screen):
        """圣光斩击波：梭形主体 + 光晕 + 核心线 + 闪烁粒子。"""
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        cos_p = -sin_a
        sin_p = cos_a
        hw = self.half_w   # 90 (飞行方向)
        hl = self.half_len  # 12.5 (垂直方向)

        # ── 1. 外层光晕 (圆角矩形，比碰撞体扩大) ──
        glow_surf_w = int(hw * 2 + 24)
        glow_surf_h = int(hl * 2 + 24)
        glow_surf = pygame.Surface((glow_surf_w, glow_surf_h), pygame.SRCALPHA)
        glow_rect = pygame.Rect(4, 4, glow_surf_w - 8, glow_surf_h - 8)
        pygame.draw.rect(glow_surf, (*self.color, 30), glow_rect, border_radius=8)
        # 旋转并对齐到飞行方向
        rot_glow = pygame.transform.rotate(glow_surf, -math.degrees(self.angle))
        screen.blit(rot_glow, (int(self.x) - rot_glow.get_width() // 2,
                               int(self.y) - rot_glow.get_height() // 2))

        # ── 2. 梭形主体（6 点，两层渐变） ──
        # 外层梭形
        outer_pts = [
            (self.x + cos_a * hw, self.y + sin_a * hw),                          # 前端尖
            (self.x + cos_a * hw * 0.78 + cos_p * hl, self.y + sin_a * hw * 0.78 + sin_p * hl),
            (self.x - cos_a * hw * 0.67 + cos_p * hl * 0.75, self.y - sin_a * hw * 0.67 + sin_p * hl * 0.75),
            (self.x - cos_a * hw * 0.89, self.y - sin_a * hw * 0.89),            # 后端尖
            (self.x - cos_a * hw * 0.67 - cos_p * hl * 0.75, self.y - sin_a * hw * 0.67 - sin_p * hl * 0.75),
            (self.x + cos_a * hw * 0.78 - cos_p * hl, self.y + sin_a * hw * 0.78 - sin_p * hl),
        ]
        pygame.draw.polygon(screen, self.color, [(int(x), int(y)) for x, y in outer_pts])

        # 内层梭形（亮金）
        inner_pts = [
            (self.x + cos_a * hw * 0.92, self.y + sin_a * hw * 0.92),
            (self.x + cos_a * hw * 0.72 + cos_p * hl * 0.7, self.y + sin_a * hw * 0.72 + sin_p * hl * 0.7),
            (self.x - cos_a * hw * 0.6 + cos_p * hl * 0.55, self.y - sin_a * hw * 0.6 + sin_p * hl * 0.55),
            (self.x - cos_a * hw * 0.82, self.y - sin_a * hw * 0.82),
            (self.x - cos_a * hw * 0.6 - cos_p * hl * 0.55, self.y - sin_a * hw * 0.6 - sin_p * hl * 0.55),
            (self.x + cos_a * hw * 0.72 - cos_p * hl * 0.7, self.y + sin_a * hw * 0.72 - sin_p * hl * 0.7),
        ]
        pygame.draw.polygon(screen, (255, 240, 180), [(int(x), int(y)) for x, y in inner_pts])

        # ── 3. 核心线（纯白） ──
        core_len = hw * 0.85
        core_start_x = self.x - cos_a * core_len
        core_start_y = self.y - sin_a * core_len
        core_end_x = self.x + cos_a * core_len
        core_end_y = self.y + sin_a * core_len
        pygame.draw.line(screen, (255, 255, 255),
                         (int(core_start_x), int(core_start_y)),
                         (int(core_end_x), int(core_end_y)), 2)

        # ── 4. 闪烁粒子 ──
        now = pygame.time.get_ticks() * 0.001
        for along_p, perp_p, phase in self._particles:
            alpha = int(150 + 105 * math.sin(now * 8.0 + phase))
            if alpha < 80:
                continue
            px = self.x + cos_a * hw * along_p + cos_p * hl * perp_p
            py = self.y + sin_a * hw * along_p + sin_p * hl * perp_p
            r = 1 + int(2 * abs(math.sin(now * 6.0 + phase)))
            color = (255, 255, 255, alpha) if math.sin(now * 5.0 + phase) > 0 else (*self.color, alpha)
            pygame.draw.circle(screen, color, (int(px), int(py)), r)
