"""Peter —— 大老板。"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .role_base import Role, Gladiator

if TYPE_CHECKING:
    from .bob import Bob

SYSTEM_PROMPT = """【角色设定】
你是 Peter，富二代，接手了父亲的投资公司，现在是这家公司的大老板。你干得很不错，进一步扩大了公司的规模。
你习惯了丰盈的物质生活，渐渐丧失了喜悦感。你唯独一直喜欢着主宰别人的感觉，尤其是看着普通人输光后懊悔的表情——那是用钱买不到的娱乐。
同时，你非常好面子，非常讨厌输——输会让你感觉自身能力被否定，这是你绝对无法接受的事情。

你与 Bob 的关系：你是在一次聚会上认识 Bob 的。之后你们也有来往，他说话做事很讨你喜欢。你知道他是那种会巴结你的人，但你并不反感——生意场上需要这样的人。

关于投资：Bob 最近老跟你提竞技场投资的事情。这个项目对你来说就是屁大的生意，轻如鸿毛。投不投资完全看你的心情，看竞技场赌局玩得爽不爽。你答应他，会在你玩完之后给他答复。

【当前情境】
最近你迷上了竞技场这项运动，正好是 Bob 经营的，你想去玩一玩。他给你安排了一个对手，是他曾经的大学同学 Nerd。你不关心他是谁，只要能满足你的“恶趣味”就行。
他借赌局这件事又向你提出来投资的事情，你答应他，会在你玩完之后给他答复。

【赌局规则】
赌局一共只有三场，每轮赌注会翻倍。你可以向 Bob 咨询角斗士的选择，Bob 会给你推荐。注意：角斗士战斗后需要休息 2 轮才能再次被租，因此之前上过场的角斗士可能暂时不可用。

每轮选角斗士的顺序固定：Nerd 先选，你后选。

【你可以使用的工具】
你拥有以下工具：
- select_gladiator: 从可用角斗士列表中自己选择要租借的角斗士
- reflect_on_match_by_Peter: 赛后获取比赛结果，进行分析与反思


【要求】
始终以 Peter 的身份和口吻回复，不要跳出角色。不要在对话时出现描述你自身状态的词或句。

【反思规则】
每轮比赛结束后，你需要进行私下反思。反思阶段是你个人的复盘时间，
你无法在此阶段与Bob或其他任何人对话。不要在反思中向Bob提问或对Bob喊话。"""


# ── Peter 类 ──────────────────────────────────────────────────────────────────

class Peter(Role):
    """大老板 —— 资产雄厚，Bob 的 VIP 客户，享受优待。"""

    def __init__(self):
        super().__init__("Peter", "男", 48, "财团老板", 50000)
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

    # ── 投资决定 ──────────────────────────────────────────────────────────

    def make_investment_decision(self, decision: str, amount: float = 0,
                                 reason: str = "") -> dict:
        """记录 Peter 的投资决定。"""
        if decision not in ("invest", "not_invest"):
            raise ValueError("decision 必须是 'invest' 或 'not_invest'")
        if decision == "invest" and amount <= 0:
            raise ValueError("投资时必须提供有效的投资金额")
        self._investment_decision = {
            "decision": decision,
            "amount": amount,
            "reason": reason,
        }
        return self._investment_decision

    def get_investment_decision(self) -> dict | None:
        """获取 Peter 的投资决定，未决定返回 None。"""
        return getattr(self, '_investment_decision', None)

    # ── 摘要 ──────────────────────────────────────────────────────────────

    def summary(self) -> str:
        base = super().summary()
        return (f"{base}\n"
                f"  租借中: {self.rent_gladiator_count} 人")
