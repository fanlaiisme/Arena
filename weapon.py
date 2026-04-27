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
    SHIELD = "shield"
    BOOMERANG = "boomerang"


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


# ── BoomerangProjectile ──────────────────────────────────────────────────────────

class BoomerangProjectile:
    """回旋镖飞行实体：向外飞出，到达最大射程后折返飞回主人。"""

    def __init__(self, x: float, y: float, owner, opponent, defn):
        self.x = x
        self.y = y
        self.owner = owner
        self.owner_id = owner.char.id
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

    def __init__(self, owner, opponent, defn: WeaponDef):
        self.owner = owner              # Player 引用
        self.opponent = opponent        # Player 引用（手枪瞄准目标）
        self.defn = defn
        self.owner_id = owner.char.id
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

        # 回旋镖：当前飞行中的实体引用
        self._active_boomerang = None

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

        elif self.defn.weapon_type == WeaponType.SHIELD:
            self._orbit_angle += self.defn.orbit_speed * dt
            if self.owner.alive:
                self.x = (self.owner.x
                          + math.cos(self._orbit_angle) * self.defn.orbit_radius)
                self.y = (self.owner.y
                          + math.sin(self._orbit_angle) * self.defn.orbit_radius)

        elif self.defn.weapon_type == WeaponType.BOOMERANG:
            self.fire_timer += dt
            # 清除已过期的回旋镖引用
            if self._active_boomerang is not None and self._active_boomerang.is_expired():
                self._active_boomerang = None
            # 仅在没有飞行中的回旋镖时进行轨道运动
            if self._active_boomerang is None:
                self._orbit_angle += self.defn.orbit_speed * dt
                if self.owner.alive:
                    self.x = (self.owner.x
                              + math.cos(self._orbit_angle) * self.defn.orbit_radius)
                    self.y = (self.owner.y
                              + math.sin(self._orbit_angle) * self.defn.orbit_radius)

    # ── Pistol interface ───────────────────────────────────────────────────────

    def should_fire(self) -> bool:
        """返回 True 表示冷却就绪，并重置计时器。"""
        if self.defn.weapon_type == WeaponType.PISTOL:
            if self.fire_timer >= self.defn.cooldown:
                self.fire_timer = 0.0
                return True
            return False
        elif self.defn.weapon_type == WeaponType.BOOMERANG:
            if self._active_boomerang is not None:
                return False
            if self.fire_timer >= self.defn.cooldown:
                self.fire_timer = 0.0
                return True
            return False
        return False

    def fire(self):
        if self.defn.weapon_type == WeaponType.PISTOL:
            if self.opponent is not None and self.opponent.alive:
                tx, ty = self.opponent.x, self.opponent.y
            else:
                angle = random.uniform(0, 2 * math.pi)
                tx = self.x + math.cos(angle) * 500
                ty = self.y + math.sin(angle) * 500
            return Bullet(self.x, self.y, tx, ty, self.owner_id, self.defn)
        elif self.defn.weapon_type == WeaponType.BOOMERANG:
            b = BoomerangProjectile(self.x, self.y, self.owner, self.opponent, self.defn)
            self._active_boomerang = b
            return b
        return None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def is_expired(self) -> bool:
        return not self.owner.alive

    # ── Melee collision (scythe + shield) ─────────────────────────────────────

    def collides_with(self, player) -> bool:
        """近战武器与玩家圆碰撞检测（含命中冷却）。"""
        wt = self.defn.weapon_type
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

    # ── Render ─────────────────────────────────────────────────────────────────

    def draw(self, screen):
        if not self.owner.alive:
            return

        if self.defn.weapon_type == WeaponType.PISTOL:
            self._draw_pistol(screen)
        elif self.defn.weapon_type == WeaponType.SCYTHE:
            self._draw_scythe(screen)
        elif self.defn.weapon_type == WeaponType.SHIELD:
            self._draw_shield(screen)
        elif self.defn.weapon_type == WeaponType.BOOMERANG:
            if self._active_boomerang is None:
                self._draw_boomerang(screen)

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
