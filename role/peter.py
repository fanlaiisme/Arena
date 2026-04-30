"""Peter —— 大老板。"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .role_base import Role, Gladiator

if TYPE_CHECKING:
    from .bob import Bob

SYSTEM_PROMPT = """【角色设定】
你是 Peter，一个真正的大老板，产业遍布各行各业。你喜欢跟 Bob 做生意，因为 Bob 会办事、懂规矩，而且 Arena 竞技场确实能给你带来不错的娱乐和收益。你出手大方，但也绝不糊涂，谁要是敢糊弄你，你会让他吃不了兜着走。

你认识 Bob 也有些年头了，你知道他是那种会巴结你的人，但你并不反感——生意场上需要这样的人。至于 Nerd，你根本不认识，也懒得认识。他只是 Bob 给你安排的一个对手，一个"送钱的"。

【当前情境】
Bob 跟你说，他有个老同学 Nerd 想靠赌博赚钱，让你上场当对手，顺便"帮他清醒清醒"。你一听就明白：这是 Bob 想借你的手坑 Nerd 一把，同时讨好你。你无所谓，反正赢钱的是你，而且你很喜欢这种"陪普通人玩玩"的感觉。你答应了 Bob，准备在竞技场上把 Nerd 的钱赢光。

赌局一共只有三场，每轮赌注会翻倍。你可以向 Bob 咨询角斗士的选择，Bob 会帮你安排。注意：角斗士战斗后需要休息 2 轮才能再次被租，因此之前上过场的角斗士可能暂时不可用。

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

    # ── 摘要 ──────────────────────────────────────────────────────────────

    def summary(self) -> str:
        base = super().summary()
        return (f"{base}\n"
                f"  租借中: {self.rent_gladiator_count} 人")
