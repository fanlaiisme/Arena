"""武器系统 —— 角色可装备的持久性武器（手枪发射子弹、镰刀绕身旋转）。"""

import math
import random
from dataclasses import dataclass, field
from enum import Enum

import pygame

from venue import ARENA_CENTER, ARENA_RADIUS


class WeaponType(Enum):
    PISTOL = "pistol"
    SCYTHE = "scythe"


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

    # 镰刀专用
    orbit_radius: float = 0.0              # 环绕半径
    orbit_speed: float = 0.0               # 环绕角速度 (rad/s)


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
                 owner_id: str, defn: WeaponDef):
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.defn = defn
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
        """绘制子弹：填充圆 + 轮廓。"""
        ix, iy = int(self.x), int(self.y)
        pygame.draw.circle(screen, self.color, (ix, iy), self.radius)
        pygame.draw.circle(screen, (100, 100, 100), (ix, iy), self.radius, 1)


# ── Weapon ─────────────────────────────────────────────────────────────────────

class Weapon:
    """持久武器实体，附着于角色，根据 weapon_type 表现不同行为。"""

    def __init__(self, owner, opponent, defn: WeaponDef):
        self.owner = owner              # Player 引用
        self.opponent = opponent        # Player 引用（手枪瞄准目标）
        self.defn = defn
        self.owner_id = owner.char.id
        self.age = 0.0
        self.x = owner.x
        self.y = owner.y

        # 手枪状态
        self.fire_timer = 0.0

        # 镰刀状态
        self._orbit_angle = random.uniform(0, 2 * math.pi)
        self._last_hit_times: dict[str, float] = {}  # target_id → last hit age

    # ── Update ─────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        self.age += dt

        if self.defn.weapon_type == WeaponType.PISTOL:
            self.fire_timer += dt
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

    # ── Pistol interface ───────────────────────────────────────────────────────

    def should_fire(self) -> bool:
        """返回 True 表示冷却就绪，并重置计时器。"""
        if self.defn.weapon_type != WeaponType.PISTOL:
            return False
        if self.fire_timer >= self.defn.cooldown:
            self.fire_timer = 0.0
            return True
        return False

    def fire(self) -> Bullet:
        """在手枪位置生成一颗瞄准对手的子弹。"""
        if self.opponent is not None and self.opponent.alive:
            tx, ty = self.opponent.x, self.opponent.y
        else:
            angle = random.uniform(0, 2 * math.pi)
            tx = self.x + math.cos(angle) * 500
            ty = self.y + math.sin(angle) * 500
        return Bullet(self.x, self.y, tx, ty, self.owner_id, self.defn)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def is_expired(self) -> bool:
        return not self.owner.alive

    # ── Scythe collision ───────────────────────────────────────────────────────

    def collides_with(self, player) -> bool:
        """镰刀刀刃与玩家圆碰撞检测（含命中冷却）。"""
        if self.defn.weapon_type != WeaponType.SCYTHE:
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
            return True
        return False

    def collides_with_pet(self, pet) -> bool:
        """镰刀刀刃与宠物头碰撞（含命中冷却）。"""
        if self.defn.weapon_type != WeaponType.SCYTHE:
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

    # ── Render ─────────────────────────────────────────────────────────────────

    def draw(self, screen):
        if not self.owner.alive:
            return

        if self.defn.weapon_type == WeaponType.PISTOL:
            self._draw_pistol(screen)
        elif self.defn.weapon_type == WeaponType.SCYTHE:
            self._draw_scythe(screen)

    def _draw_pistol(self, screen):
        """绘制更精致的手枪。"""
        if self.opponent is not None and self.opponent.alive:
            tx, ty = self.opponent.x, self.opponent.y
        else:
            tx = self.owner.x + 100
            ty = self.owner.y

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
        """绘制死神镰刀：木柄 + 弧形刀刃。"""
        ox, oy = self.owner.x, self.owner.y
        bx, by = self.x, self.y

        dx = bx - ox
        dy = by - oy
        dist = math.hypot(dx, dy)
        if dist < 0.001:
            return

        # 方向向量
        hx = dx / dist   # 柄方向（朝外）
        hy = dy / dist
        px = -hy         # 垂直方向
        py = hx

        # ── 1. 木柄 ──
        handle_start_x = ox + hx * (self.owner.radius - 4)
        handle_start_y = oy + hy * (self.owner.radius - 4)
        # 柄延伸到刀刃位置之外一点
        handle_end_x = bx - hx * 6
        handle_end_y = by - hy * 6

        handle_color = (101, 67, 33)
        handle_width = max(2, self.defn.width // 2)
        pygame.draw.line(screen, handle_color,
                         (int(handle_start_x), int(handle_start_y)),
                         (int(handle_end_x), int(handle_end_y)), handle_width)
        # 柄的高光
        hl_color = (140, 100, 50)
        pygame.draw.line(screen, hl_color,
                         (int(handle_start_x + px * 1), int(handle_start_y + py * 1)),
                         (int(handle_end_x + px * 1), int(handle_end_y + py * 1)),
                         max(1, handle_width // 2))

        # ── 2. 弧形刀刃 ──
        blade_len = 34
        blade_w = 10

        # 刀刃多边形点 (局部坐标: u沿柄方向, v垂直方向)
        # 刀背 (spine) — 厚实弯曲的背部
        spine = [
            (0, -4),
            (4, -blade_w),
            (14, -blade_w - 1),
            (24, -blade_w * 0.7),
            (30, -blade_w * 0.3),
            (blade_len, 1),
        ]
        # 刀刃 (cutting edge) — 锐利的内弧
        edge = [
            (blade_len, 1),
            (28, 3),
            (18, blade_w * 0.4),
            (8, blade_w * 0.3),
            (0, 4),
        ]

        all_pts = spine + edge
        world_pts = []
        for u, v in all_pts:
            wx = bx + hx * u + px * v
            wy = by + hy * u + py * v
            world_pts.append((int(wx), int(wy)))

        blade_color = (200, 210, 220)
        blade_outline = (120, 130, 145)
        pygame.draw.polygon(screen, blade_color, world_pts)
        pygame.draw.polygon(screen, blade_outline, world_pts, 1)

        # 刀面高光线
        highlight_pts = []
        for u, v in [(10, -blade_w * 0.6), (22, -blade_w * 0.4), (30, -blade_w * 0.15)]:
            wx = bx + hx * u + px * v
            wy = by + hy * u + py * v
            highlight_pts.append((int(wx), int(wy)))
        if len(highlight_pts) >= 2:
            pygame.draw.lines(screen, (230, 235, 245), False, highlight_pts, 1)

        # ── 3. 连接环 ──
        ring_r = 3
        pygame.draw.circle(screen, (80, 80, 90), (int(bx), int(by)), ring_r)
        pygame.draw.circle(screen, (50, 50, 60), (int(bx), int(by)), ring_r, 1)
