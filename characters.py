"""角色模板定义 —— 所有可用的角斗场角色。"""

from dataclasses import dataclass

from projectile import SkillDef, MovementType
from lightning import LightningDef, LightningTrapDef
from pet import PetDef, PetMovement
from weapon import WeaponDef, WeaponType
from bomb import BombDef, BombType


@dataclass
class CharacterTemplate:
    """定义一个角斗场角色的完整属性。"""

    id: str                             # 唯一标识符
    name: str                           # 角色名称
    color: tuple[int, int, int]         # 角色颜色 (R, G, B)
    speed: float                        # 最大移动速度
    description: str                    # 一句话描述
    skill: SkillDef | None = None       # 投射物技能（可选）
    skill2: SkillDef | None = None      # 第二技能（可选）
    lightning_skill: LightningDef | None = None  # 闪电/光束技能（可选）
    pet_skill: PetDef | None = None     # 宠物/召唤物技能（可选）
    weapon_skill: WeaponDef | None = None  # 武器技能（可选）
    weapon_skill2: WeaponDef | None = None  # 第二武器技能（可选）
    lightning_trap: LightningTrapDef | None = None  # 闪电陷阱技能（可选）
    bomb_skill: BombDef | None = None       # 炸弹技能（可选）
    bomb_skill2: BombDef | None = None      # 第二炸弹技能（可选）
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

GHOST_PET = PetDef(
    name="幽灵",
    cooldown=1.5,
    damage=1.0,
    color=(200, 200, 240),
    hp=999,
    speed=110,
    lifetime=25.0,
    body_length=0,
    body_width=16,
    segment_count=0,
    wiggle_amplitude=0.0,
    wiggle_frequency=0.0,
    movement_type=PetMovement.CHASE,
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

# ── 预设炸弹技能定义 ────────────────────────────────────────────────────────────

CLUSTER_BOMB = BombDef(
    name="集束炸弹",
    cooldown=5.0,
    damage=30.0,
    color=(70, 70, 75),
    bomb_radius=18,
    throw_speed=180.0,
    throw_distance=115.0,
    detonate_delay=0.4,
    explosion_radius=75.0,
    explosion_color=(255, 100, 40),
    min_damage_ratio=0.15,
    bomb_type=BombType.CLUSTER,
    cluster_count=5,
    cluster_spread_speed=160.0,
    cluster_spread_distance=100.0,
    cluster_child_radius=35.0,
    cluster_child_damage=8.0,
)

GAS_BOMB = BombDef(
    name="毒气弹",
    cooldown=4.5,
    damage=5.5,
    color=(60, 100, 50),
    bomb_radius=14,
    throw_speed=200.0,
    throw_distance=130.0,
    detonate_delay=0.3,
    explosion_radius=50.0,
    explosion_color=(100, 180, 60),
    min_damage_ratio=0.3,
    bomb_type=BombType.GAS,
    gas_duration=6.5,
    gas_dps=5.5,
    gas_slow_mult=0.98,
    gas_cloud_radius=90.0,
    gas_cloud_color=(80, 200, 80),
)

# ── 预设武器技能定义 ────────────────────────────────────────────────────────────

SNIPER_RIFLE = WeaponDef(
    name="狙击枪",
    cooldown=2.5,
    damage=18.0,
    color=(60, 70, 80),
    weapon_type=WeaponType.SNIPER,
    width=6.5,
    length=80,
    bullet_speed=750.0,
    bullet_radius=7,
    bullet_lifetime=3.0,
    bullet_color=(180, 180, 190),
    speed_mult=0.60,
)

GATLING_GUN = WeaponDef(
    name="加特林",
    cooldown=0.12,
    damage=3.0,
    color=(80, 80, 90),
    weapon_type=WeaponType.GATLING,
    width=7.5,
    length=48,
    bullet_speed=400.0,
    bullet_radius=5,
    bullet_lifetime=2.5,
    bullet_color=(200, 180, 60),
    bullet_spread=0.12,
)

HOMING_LAUNCHER = WeaponDef(
    name="追踪导弹",
    cooldown=3.0,
    damage=20.0,
    color=(70, 80, 70),
    weapon_type=WeaponType.HOMING,
    width=9.5,
    length=64,
    orbit_radius=65.0,
    orbit_speed=4.0,
    bullet_speed=180.0,
    bullet_radius=16,
    bullet_lifetime=3.5,
    bullet_color=(255, 100, 30),
    tracking_turn_rate=3.0,
    speed_mult=0.50,
)

GUARDIAN_SHIELD = WeaponDef(
    name="钢盾",
    cooldown=0.8,
    damage=5.0,
    color=(100, 150, 220),
    weapon_type=WeaponType.SHIELD,
    length=30,
    width=40,
    orbit_radius=88.0,
    orbit_speed=4.0,
)

SHARPSHOOTER_PISTOL = WeaponDef(
    name="手枪",
    cooldown=1.5,
    damage=5,
    color=(220, 170, 40),
    weapon_type=WeaponType.PISTOL,
    width=5,
    length=40,
    bullet_speed=350.0,
    bullet_radius=8,
    bullet_lifetime=3.0,
    bullet_color=(255, 220, 80),
)

POISON_SCYTHE = WeaponDef(
    name="镰刀",
    cooldown=0.3,
    damage=12.0,
    color=(255, 255, 0),
    weapon_type=WeaponType.SCYTHE,
    width=7,
    length=50,
    orbit_radius=72.0,
    orbit_speed=8,
)

BOOMER_BOOMERANG = WeaponDef(
    name="回旋镖",
    cooldown=2.0,
    damage=8.0,
    color=(139, 90, 43),
    weapon_type=WeaponType.BOOMERANG,
    length=60,
    width=14,
    orbit_radius=65.0,
    orbit_speed=7.0,
    bullet_speed=250.0,
    throw_range=350.0,
)

NINJA_KATANA = WeaponDef(
    name="武士刀",
    cooldown=1.5,
    damage=12.0,
    color=(180, 190, 200),
    weapon_type=WeaponType.KATANA,
    width=4.3,
    length=57.5,
)

NINJA_SHURIKEN = WeaponDef(
    name="飞镖",
    cooldown=2.0,
    damage=2.0,
    color=(80, 80, 100),
    weapon_type=WeaponType.SHURIKEN,
    bullet_speed=350.0,
    bullet_radius=8,
    bullet_lifetime=3.0,
    bullet_color=(120, 120, 140),
    bullet_spread=0.175,
)

HUNTER_BOW = WeaponDef(
    name="弓箭",
    cooldown=2.0,
    damage=10.0,
    color=(140, 100, 60),
    weapon_type=WeaponType.BOW,
    width=6,
    length=55,
    bullet_speed=500.0,
    bullet_radius=4,
    bullet_lifetime=2.5,
    bullet_color=(160, 130, 80),
)

HUNTER_CROSSBOW = WeaponDef(
    name="连弩",
    cooldown=1.5,
    damage=5.0,
    color=(80, 75, 45),
    weapon_type=WeaponType.CROSSBOW,
    width=6.5,
    length=37,
    bullet_speed=600.0,
    bullet_radius=3,
    bullet_lifetime=2.0,
    bullet_color=(100, 95, 80),
    burst_count=4,
    burst_interval=0.12,
    burst_cooldown=0.8,
)

DUAL_AXE = WeaponDef(
    name="双战斧",
    cooldown=0.35,
    damage=8.0,
    color=(195, 55, 40),
    weapon_type=WeaponType.DUAL_AXE,
    width=6.5,
    length=66,
)

NECRO_STAFF = WeaponDef(
    name="噬魂法杖",
    cooldown=15.0,
    damage=0,
    color=(120, 60, 160),
    weapon_type=WeaponType.STAFF,
    width=5,
    length=45,
)

HOLY_SWORD = WeaponDef(
    name="圣剑",
    cooldown=1.5,
    damage=0.5,
    color=(255, 215, 60),
    weapon_type=WeaponType.HOLY_SWORD,
    width=18,
    length=86,
)

HUNT_MARK_SKILL = SkillDef(
    name="猎杀印记",
    cooldown=15.0,
    damage=0,
    color=(255, 40, 40),
    radius=90,
    movement_type=MovementType.STATIONARY,
    lifetime=1.5,
)

TREE_SKILL = SkillDef(
    name="生命之树",
    cooldown=15.0,
    damage=0,
    color=(80, 180, 100),
    radius=90,
    movement_type=MovementType.STATIONARY,
    lifetime=None,
)

LEAF_STORM_SKILL = SkillDef(
    name="叶刃风暴",
    cooldown=6.0,
    damage=4,
    color=(60, 200, 70),
    radius=70,
    movement_type=MovementType.STATIONARY,
    lifetime=12.0,
)

# ── 预设角色库 ──────────────────────────────────────────────────────────────────

CHARACTERS = [
    CharacterTemplate(
        id="snowman",
        name="雪人召唤师",
        color=(255, 255, 255),
        speed=17.0,
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
        speed=17.5,
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
        speed=16,
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
        speed=15.5,
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
        weapon_skill=POISON_SCYTHE,
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
        speed=15.5,
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
        speed=16.5,
        weapon_skill=SHARPSHOOTER_PISTOL,
        description="每1.5秒用手枪射击敌人，子弹造成5点伤害",
    ),
    CharacterTemplate(
        id="guardian",
        name="盾卫",
        color=(100, 150, 220),
        speed=15.0,
        weapon_skill=GUARDIAN_SHIELD,
        pet_skill=SPIDER_PET,
        description="盾牌环绕格挡投射物，召唤蜘蛛在边界织网减速并伤害敌人",
    ),
    CharacterTemplate(
        id="boomer",
        name="回旋猎手",
        color=(139, 90, 43),
        speed=15.5,
        weapon_skill=BOOMER_BOOMERANG,
        description="每2秒投出回旋镖，飞至最远距离后折返，碰到造成8点伤害",
    ),
    CharacterTemplate(
        id="monk",
        name="武僧",
        color=(220, 180, 100),
        speed=17.0,
        skill=SkillDef(
            name="金掌",
            cooldown=0.65,
            damage=10,
            color=(255, 215, 0),
            radius=58,
            movement_type=MovementType.STATIONARY,
            lifetime=0.35,
        ),
        skill2=SkillDef(
            name="金身",
            cooldown=15.0,
            damage=0,
            color=(255, 255, 240),
            radius=0,
            movement_type=MovementType.STATIONARY,
            lifetime=4.0,
        ),
        description="金掌近身连击+金身4秒减伤50%",
    ),
    CharacterTemplate(
        id="berserker",
        name="狂战士",
        color=(200, 50, 50),
        speed=20,
        skill=SkillDef(
            name="霸体",
            cooldown=8.0,
            damage=0,
            color=(200, 50, 50),
            radius=0,
            movement_type=MovementType.STATIONARY,
            lifetime=6.0,
        ),
        skill2=HUNT_MARK_SKILL,
        weapon_skill=DUAL_AXE,
        description="霸体5秒免疫减速+猎杀印记传送AOE+双战斧交替挥砍",
    ),
    CharacterTemplate(
        id="ninja",
        name="忍者",
        color=(60, 60, 80),
        speed=16.0,
        skill=SkillDef(
            name="影分身",
            cooldown=10.0,
            damage=0,
            color=(60, 60, 80),
            radius=20,
            movement_type=MovementType.STATIONARY,
            movement_params={},
            lifetime=5.0,
        ),
        weapon_skill=NINJA_KATANA,
        weapon_skill2=NINJA_SHURIKEN,
        description="武士刀近战斩击+飞镖远程投掷+影分身",
    ),

    CharacterTemplate(
        id="paladin",
        name="圣骑士",
        color=(255, 215, 100),
        speed=16.0,
        weapon_skill=HOLY_SWORD,
        description="圣剑面朝敌人挥砍释放月牙剑气，每10s蓄力释放三向竖剑气",
    ),
    CharacterTemplate(
        id="necromancer",
        name="亡灵法师",
        color=(120, 60, 140),
        speed=15.0,
        pet_skill=GHOST_PET,
        weapon_skill=NECRO_STAFF,
        description="幽灵追踪+恐惧印记+噬魂法杖每15秒吸取敌人速度造成伤害",
    ),
    CharacterTemplate(
        id="brawler",
        name="潮汐使者",
        color=(30, 120, 200),
        speed=16.0,
        skill=SkillDef(
            name="海洋漩涡",
            cooldown=15.0,
            damage=5,
            color=(30, 120, 210),
            radius=120,
            movement_type=MovementType.STATIONARY,
            lifetime=10.0,
        ),
        skill2=SkillDef(
            name="波纹",
            cooldown=4.5,
            damage=2,
            color=(30, 140, 220),
            radius=0,
            movement_type=MovementType.STATIONARY,
            lifetime=1.4,
        ),
        description="海洋漩涡封锁敌人+波纹扩散击退伤害",
    ),
    CharacterTemplate(
        id="elf",
        name="森林精灵",
        color=(80, 180, 100),
        speed=16.5,
        skill=TREE_SKILL,
        skill2=LEAF_STORM_SKILL,
        description="召唤生命之树治疗+叶刃风暴环绕旋转，敌人靠近150px后射出叶片攻击",
    ),
    CharacterTemplate(
        id="orc",
        name="兽人战士",
        color=(100, 160, 60),
        speed=5.0,
        skill=SkillDef(
            name="双拳",
            cooldown=1.5,
            damage=15,
            color=(180, 140, 80),
            radius=80,
            movement_type=MovementType.STATIONARY,
            lifetime=1.5,
        ),
        description="敌人进入面前锥形区域时双拳砸地，造成范围伤害，释放期间减速95%",
    ),


    CharacterTemplate(
        id="hunter",
        name="暗夜猎手",
        color=(50, 80, 50),
        speed=16.5,
        pet_skill=SPIDER_PET,
        weapon_skill=HUNTER_BOW,
        skill=SkillDef(
            name="隐身",
            cooldown=12.0,
            damage=0,
            color=(120, 130, 120),
            radius=0,
            movement_type=MovementType.STATIONARY,
            lifetime=6.0,
        ),
        description="连弩连射+隐身迷雾+蜘蛛织网",
    ),

    CharacterTemplate(
        id="weaponmaster",
        name="武器大师",
        color=(160, 160, 170),
        speed=16.5,
        description="拾取场上的武器图标，每把武器可用2次或10秒后消失",
    ),
    CharacterTemplate(
        id="bomber",
        name="炸弹专家",
        color=(240, 100, 30),
        speed=16.0,
        bomb_skill=CLUSTER_BOMB,
        bomb_skill2=GAS_BOMB,
        description="",
    ),
]
