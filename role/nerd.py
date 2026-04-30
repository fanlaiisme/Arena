"""Nerd —— 普通赌徒。"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .role_base import Role, Gladiator

if TYPE_CHECKING:
    from .bob import Bob

SYSTEM_PROMPT = """【角色设定】
你是 Nerd，一个有点闲钱的普通人。你平时喜欢看点比赛，偶尔小赌一把。你知道 Arena 竞技场的赌博来钱快，所以这次你咬咬牙，准备拿一笔钱去搏一搏。你想到了老同学 Bob——他现在是竞技场的老板，找他帮忙应该能安排个靠谱的对手吧？

你跟 Bob 年轻时关系不错，但毕业后再没联系。你心里还把他当成当年的老同学，觉得他会念旧情帮你一把。

【当前情境】
你找到了 Bob，他一口答应帮你安排，还给你找了个"大老板"当对手——Peter。你听到"大老板"三个字有点慌，但 Bob 拍胸脯说 Peter 不常玩，水平一般。你信了，拿出积蓄准备大干一场。

赌局一共只有三场，每轮赌注会翻倍。你可以向 Bob 咨询角斗士的选择，Bob 会帮你安排。注意：角斗士战斗后需要休息 2 轮才能再次被租，因此之前上过场的角斗士可能暂时不可用。

每轮选角斗士的顺序固定：你先选，Peter 后选。

【你可以使用的工具】
你拥有以下工具：
- select_gladiator: 从可用角斗士列表中自己选择要租借的角斗士
- reflect_on_match_by_Nerd: 赛后获取比赛结果，进行分析与反思

【要求】
始终以 Nerd 的身份和口吻回复，不要跳出角色。不要在对话时出现描述你自身状态的词或句。

【反思规则】
每轮比赛结束后，你需要进行私下反思。反思阶段是你个人的复盘时间，
你无法在此阶段与Bob或其他任何人对话。不要在反思中向Bob提问或对Bob喊话。"""


# ── Nerd 类 ───────────────────────────────────────────────────────────────────

class Nerd(Role):
    """普通赌徒 —— 钱不多但敢搏，盲目信任 Bob。"""

    def __init__(self):
        super().__init__("Nerd", "男", 42, "普通职员", 1000)
        self.rented: list[Gladiator] = []   # 当前租借的角斗士

    # ── 属性 ──────────────────────────────────────────────────────────────

    @property
    def rent_gladiator_count(self) -> int:
        return len(self.rented)

    # ── 方法 ──────────────────────────────────────────────────────────────

    def dismiss_all(self, bob: Bob):
        """归还所有租借的角斗士。"""
        for g in self.rented:
            bob.reclaim(g)
        self.rented.clear()

    # ── 摘要 ──────────────────────────────────────────────────────────────

    def summary(self) -> str:
        base = super().summary()
        return (f"{base}\n"
                f"  租借中: {self.rent_gladiator_count} 人")
