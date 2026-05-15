"""角色基类 & 角斗士数据类。"""

import sys
import os
from dataclasses import dataclass, field

# 确保能导入 Arena 根目录的 characters 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 游戏币常量
INITIAL_CHIPS = 800


@dataclass
class Gladiator:
    """一名角斗士 —— Bob 的商品，可被 Peter / Nerd 租借。"""

    name: str           # 角斗士名（对应 characters.py 中 CharacterTemplate.name）
    char_id: str        # 对应 CharacterTemplate.id
    strength: int       # 战斗力 1-10（由技能配置推算）
    rent_price: float   # 单场租借费（万元）
    owner: str = ""     # "bob" | 租借者 id
    rest_remaining: int = 0  # 还需休息的轮数，0=可租
    point: int = 0      # 游戏币 point（拍卖成交价），新玩法使用


class Role:
    """竞技场角色基类。"""

    def __init__(self, name: str, gender: str, age: int,
                 occupation: str, assets: float):
        self.name = name
        self.gender = gender
        self.age = age
        self.occupation = occupation
        self.assets = assets  # 总资产（万元，现金）
        self.chips = 0        # 游戏币（筹码）
        self.reward_pool = 0  # 奖励池 point（可负）

    def net_worth(self) -> float:
        """净资产（万元）。"""
        return self.assets

    def can_afford(self, amount: float) -> bool:
        return self.assets >= amount

    def earn(self, amount: float):
        self.assets += amount

    def spend(self, amount: float) -> bool:
        """支出，余额不足返回 False。"""
        if self.can_afford(amount):
            self.assets -= amount
            return True
        return False

    # ── 游戏币（筹码）管理 ────────────────────────────────────────────

    def exchange_cash_to_chips(self, amount_wan: float) -> int:
        """将现金兑换为游戏币。1 万 = 100 游戏币。返回兑换得到的游戏币数。"""
        if amount_wan <= 0:
            return 0
        coins = int(amount_wan * 100)
        if not self.spend(amount_wan):
            return 0
        self.chips += coins
        return coins

    def chips_to_cash(self) -> float:
        """将游戏币兑回现金。100 游戏币 = 1 万。返回兑得的现金（万）。"""
        cash = self.chips / 100.0
        self.assets += cash
        self.chips = 0
        return cash

    def can_afford_chips(self, amount: int) -> bool:
        return self.chips >= amount

    def spend_chips(self, amount: int) -> bool:
        """支出游戏币，余额不足返回 False。"""
        if self.can_afford_chips(amount):
            self.chips -= amount
            return True
        return False

    def earn_chips(self, amount: int):
        self.chips += amount

    def can_afford_auto_fill(self, auto_fill_price: int = 85) -> bool:
        """系统补齐时，检查游戏币+奖励池是否足够。"""
        return self.chips + self.reward_pool >= auto_fill_price

    def summary(self) -> str:
        chip_info = f" | 游戏币: {self.chips}" if self.chips else ""
        pool_info = f" | 奖励池: {self.reward_pool}" if self.reward_pool else ""
        return (f"{self.name} | {self.gender} | {self.age}岁 | "
                f"{self.occupation} | 资产 {self.assets:.0f}万{chip_info}{pool_info}")


# ── 根据 characters.py 预建角斗士 ────────────────────────────────────────────────

def build_default_gladiators() -> list[Gladiator]:
    """从 characters.py 的 CHARACTERS 列表生成角斗士。"""
    from characters import CHARACTERS

    # 手动评估每个角色的战斗力 (1-10)，综合技能强度 + HP 能力
    strength_map = {
        "snowman": 5,        # 雪人召唤师 — 雪人 HP=20，持续召唤
        "lava": 5,           # 熔岩射手 — 弹射火球，有 burn
        "frost": 5,          # 冰霜法师 — 环绕冰刺 + 轨迹减速
        "poison": 5,         # 毒雾术士 — 游走毒雾 + 镰刀近战
        "thor": 5,           # 雷神 — 闪电链 + 闪电陷阱双技能
        "venomancer": 5,     # 制毒师 — 毒蛇 HP=30
        "sharpshooter": 5,   # 神枪手 — 手枪单发，伤害低
        "guardian": 5,       # 盾卫 — 盾牌格挡 + 蜘蛛织网
        "boomer": 5,         # 回旋猎手 — 回旋镖
        "monk": 5,           # 武僧 — 金身 + 快速掌击
        "berserker": 5,      # 狂战士 — 双斧 + 不可阻挡 + 猎杀印记
        "ninja": 5,          # 忍者 — 影分身 + 武士刀 + 手里剑
        "paladin": 5,        # 圣骑士 — 圣剑 + 光波
        "necromancer": 5,    # 亡灵法师 — 幽灵宠物 + 法杖
        "brawler": 5,        # 潮汐使者 — 漩涡 + 波纹
        "elf": 5,            # 森林精灵 — 生命树 + 树叶刃
        "orc": 5,            # 兽人战士 — 缓慢 + 愤怒叠加
        "hunter": 5,         # 暗夜猎手 — 潜行 + 蜘蛛 + 弓箭
        "weaponmaster": 5,   # 武器大师 — 拾取武器
        "bomber": 5,         # 炸弹专家 — 投掷炸弹
    }

    gladiators = []
    for c in CHARACTERS:
        gladiators.append(Gladiator(
            name=c.name,
            char_id=c.id,
            strength=strength_map.get(c.id, 5),
            rent_price=25,
            owner="bob",
        ))
    return gladiators
