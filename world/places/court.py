"""法庭 — 审理案件、判处罚金或监禁。"""

from dataclasses import dataclass, field
import random

from .base import Place


@dataclass
class Court(Place):
    """法庭场所。

    审理智能体的案件。判决结果包括：
      - 无罪释放
      - 罚金（扣除金币）
      - 入狱（移送监狱关押）
    """

    name: str = "法庭"
    description: str = (
        "一栋庄严的司法建筑，门口悬挂着天平标志。"
        "法官端坐在高台之上，法警肃立两旁。"
        "这里是裁决罪与罚的地方。"
    )
    fine_min: int = 50
    fine_max: int = 200
    prison_ticks_min: int = 10
    prison_ticks_max: int = 30

    def trial(self, agent_name: str, cash: int) -> dict:
        """审理案件。返回判决结果 dict。

        result = {
            "verdict": "innocent" | "fine" | "prison",
            "fine_amount": int (if fine),
            "prison_ticks": int (if prison),
            "msg": str,
        }
        """
        roll = random.random()
        if roll < 0.25:
            return {
                "verdict": "innocent",
                "fine_amount": 0,
                "prison_ticks": 0,
                "msg": f"法庭判决: {agent_name} 无罪释放！",
            }
        elif roll < 0.65:
            fine = random.randint(self.fine_min, min(self.fine_max, cash))
            return {
                "verdict": "fine",
                "fine_amount": fine,
                "prison_ticks": 0,
                "msg": f"法庭判决: {agent_name} 有罪，处以 {fine} 金币罚金。",
            }
        else:
            ticks = random.randint(self.prison_ticks_min, self.prison_ticks_max)
            return {
                "verdict": "prison",
                "fine_amount": 0,
                "prison_ticks": ticks,
                "msg": f"法庭判决: {agent_name} 有罪，判处监禁 {ticks} ticks！",
            }
