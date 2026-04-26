"""角色模板定义 —— 所有可用的角斗场角色。"""

from dataclasses import dataclass

from projectile import SkillDef, MovementType


@dataclass
class CharacterTemplate:
    """定义一个角斗场角色的完整属性。"""

    id: str                        # 唯一标识符
    name: str                      # 角色名称
    color: tuple[int, int, int]    # 角色颜色 (R, G, B)
    speed: float                   # 最大移动速度
    skill: SkillDef                # 技能定义（包含投射物全部行为）
    description: str               # 一句话描述


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
            damage=1,
            color=(220, 230, 240),
            radius=12,
            movement_type=MovementType.STATIONARY,
            movement_params={},
            lifetime=None,  # 永不消失
        ),
        description="每3秒召唤小雪人，碰到造成1点伤害（雪人不消失）",
    ),
    CharacterTemplate(
        id="lava",
        name="熔岩射手",
        color=(255, 140, 0),
        speed=16.0,
        skill=SkillDef(
            name="熔岩弹",
            cooldown=5.0,
            damage=2,
            color=(255, 80, 20),
            radius=12,
            movement_type=MovementType.BOUNCE,
            movement_params={"speed": 2.5},
            lifetime=15.0,  # 15秒后消失
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
            damage=1,
            color=(180, 220, 255),
            radius=10,
            movement_type=MovementType.ORBIT,
            movement_params={"radius": 65, "angular_speed": 3.0},
            lifetime=12.0,  # 12秒后消失
        ),
        description="每2.5秒释放冰刺环绕自身旋转，碰到造成1点伤害",
    ),
    CharacterTemplate(
        id="poison",
        name="毒雾术士",
        color=(100, 220, 80),
        speed=14.5,
        skill=SkillDef(
            name="毒雾蔓延",
            cooldown=4.0,
            damage=3,
            color=(60, 180, 40),
            radius=14,
            movement_type=MovementType.ROAM,
            movement_params={"speed": 30.8},
            lifetime=10.0,  # 10秒后消失
        ),
        description="每4秒释放毒雾在竞技场中随机游走，碰到造成3点伤害",
    ),
]
