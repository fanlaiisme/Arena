"""角色模板定义 —— 所有可用的角斗场角色。"""

from dataclasses import dataclass

from projectile import SkillDef, MovementType
from lightning import LightningDef, LightningTrapDef
from pet import PetDef, PetMovement
from weapon import WeaponDef, WeaponType


@dataclass
class CharacterTemplate:
    """定义一个角斗场角色的完整属性。"""

    id: str                             # 唯一标识符
    name: str                           # 角色名称
    color: tuple[int, int, int]         # 角色颜色 (R, G, B)
    speed: float                        # 最大移动速度
    description: str                    # 一句话描述
    skill: SkillDef | None = None       # 投射物技能（可选）
    lightning_skill: LightningDef | None = None  # 闪电/光束技能（可选）
    pet_skill: PetDef | None = None     # 宠物/召唤物技能（可选）
    weapon_skill: WeaponDef | None = None  # 武器技能（可选）
    lightning_trap: LightningTrapDef | None = None  # 闪电陷阱技能（可选）
    trail_enabled: bool = False         # 是否显示运动轨迹


# ── 预设宠物定义 ──────────────────────────────────────────────────────────────────

SPIDER_PET = PetDef(
    name="蛛网蜘蛛",
    cooldown=8,
    damage=3,
    color=(80, 30, 100),
    hp=5,
    speed=120,
    lifetime=20,
    body_length=0,
    body_width=32,
    segment_count=0,
    wiggle_amplitude=0.0,
    wiggle_frequency=0.0,
    movement_type=PetMovement.SPIDER,
)

SNOWMAN_PET = PetDef(
    name="雪人",
    cooldown=3.0,
    damage=8,
    color=(220, 230, 240),
    hp=20,
    speed=40,
    lifetime=None,
    body_length=0,
    body_width=18,
    segment_count=0,
    wiggle_amplitude=0.0,
    wiggle_frequency=0.0,
    movement_type=PetMovement.CHASE,
    slow_mult=0.0,
    slow_duration=0.0,
)

# ── 预设电系技能定义 ──────────────────────────────────────────────────────────────────

THOR_TRAP = LightningTrapDef(
    name="闪电陷阱",
    cooldown=6.0,
    damage=3.0,
    color=(180, 180, 220),
    bolt_count=6,
    bolt_length=80,
    bolt_speed=350,
    travel_duration=1.0,
    trap_radius=6,
    trap_color=(255, 255, 0),
    shock_duration=2.0,
    shock_slow_mult=0.5,
)

# ── 预设角色库 ──────────────────────────────────────────────────────────────────

CHARACTERS = [
    CharacterTemplate(
        id="snowman",
        name="雪人召唤师",
        color=(255, 255, 255),
        speed=15.0,
        skill=SkillDef(
            name="雪人召唤",
            cooldown=3.0,
            damage=8,
            color=(220, 230, 240),
            radius=12,
            movement_type=MovementType.STATIONARY,
            movement_params={},
            lifetime=None,  # 永不消失
        ),
        pet_skill=SNOWMAN_PET,
        description="每3秒召唤雪人追踪敌人，碰到造成8点伤害，雪人HP=20可被摧毁",
    ),
    CharacterTemplate(
        id="lava",
        name="熔岩射手",
        color=(255, 140, 0),
        speed=16.0,
        skill=SkillDef(
            name="熔岩弹",
            cooldown=5.0,
            damage=8,
            color=(255, 80, 20),
            radius=24,
            movement_type=MovementType.BOUNCE,
            movement_params={"speed": 2.5},
            lifetime=25.0,
            burn_duration=10.0,
            burn_dps=0.75,
        ),
        description="每5秒发射熔岩球，直线弹射，碰到造成2点伤害",
    ),
    CharacterTemplate(
        id="frost",
        name="冰霜法师",
        color=(0, 200, 255),
        speed=17.0,
        skill=SkillDef(
            name="冰霜之刺",
            cooldown=2.5,
            damage=7,
            color=(180, 220, 255),
            radius=10,
            movement_type=MovementType.ORBIT,
            movement_params={"radius": 65, "angular_speed": 3.0},
            lifetime=12.0,  # 12秒后消失
        ),
        description="每2.5秒释放冰刺环绕自身旋转，碰到造成1点伤害，运动轨迹使敌人减速减血",
        trail_enabled=True,
    ),
    CharacterTemplate(
        id="poison",
        name="毒雾术士",
        color=(100, 220, 80),
        speed=14.5,
        skill=SkillDef(
            name="毒雾蔓延",
            cooldown=4.0,
            damage=7,
            color=(60, 180, 40),
            radius=14,
            movement_type=MovementType.ROAM,
            movement_params={"speed": 30.8},
            lifetime=10.0,  # 10秒后消失
        ),
        weapon_skill=WeaponDef(
            name="镰刀",
            cooldown=0.3,
            damage=12.0,
            color=(255, 255, 0),
            weapon_type=WeaponType.SCYTHE,
            orbit_radius=45.0,
            orbit_speed=8,
        ),
        description="每4秒释放毒雾在竞技场中随机游走，碰到造成3点伤害",
    ),
    CharacterTemplate(
        id="thor",
        name="雷神",
        color=(255, 215, 0),
        speed=15.0,
        lightning_skill=LightningDef(
            name="雷霆之怒",
            cooldown=8.0,
            damage=0.95,
            color=(255, 255, 0),
            bolt_count=8,
            bolt_length=450,
            segment_count=10,
            jitter=35,
            duration=0.5,
            width=3,
            self_speed_mult=0.0,
            self_dmg_reduction=0.9,
            target_slow_mult=0.2,
            target_slow_duration=2.0,
        ),
        description="每8秒释放8条闪电，麻痹敌人2秒（速度-80%），释放期间静止且减伤90%",
        lightning_trap=THOR_TRAP,
    ),
    CharacterTemplate(
        id="venomancer",
        name="制毒师",
        color=(140, 200, 50),
        speed=14.5,
        pet_skill=PetDef(
            name="毒蛇",
            cooldown=3.5,
            damage=8,
            color=(60, 210, 40),
            hp=30,
            speed=100,
            lifetime=8.0,
            body_length=100,
            body_width=10,
        ),
        description="每3.5秒释放一条毒蛇追踪敌人，碰到造成8点伤害后消失，毒蛇HP=30可被攻击",
    ),
    CharacterTemplate(
        id="sharpshooter",
        name="神枪手",
        color=(255, 200, 50),
        speed=14.0,
        weapon_skill=WeaponDef(
            name="手枪",
            cooldown=1.5,
            damage=5,
            color=(220, 170, 40),
            weapon_type=WeaponType.PISTOL,
            width=3,
            length=24,
            bullet_speed=350.0,
            bullet_radius=5,
            bullet_lifetime=2.0,
            bullet_color=(255, 220, 80),
        ),
        description="每1.5秒用手枪射击敌人，子弹造成5点伤害",
    ),
    CharacterTemplate(
        id="guardian",
        name="盾卫",
        color=(100, 150, 220),
        speed=13.5,
        weapon_skill=WeaponDef(
            name="钢盾",
            cooldown=0.8,
            damage=5.0,
            color=(100, 150, 220),
            weapon_type=WeaponType.SHIELD,
            length=22,
            width=30,
            orbit_radius=55.0,
            orbit_speed=4.0,
        ),
        pet_skill=SPIDER_PET,
        description="盾牌环绕格挡投射物，召唤蜘蛛在边界织网减速并伤害敌人",
    ),
    CharacterTemplate(
        id="boomer",
        name="回旋猎手",
        color=(139, 90, 43),
        speed=15.5,
        weapon_skill=WeaponDef(
            name="回旋镖",
            cooldown=2.0,
            damage=8.0,
            color=(139, 90, 43),
            weapon_type=WeaponType.BOOMERANG,
            length=38,
            width=9,
            orbit_radius=40.0,
            orbit_speed=7.0,
            bullet_speed=250.0,
            throw_range=220.0,
        ),
        description="每2秒投出回旋镖，飞至最远距离后折返，碰到造成8点伤害",
    ),
]
