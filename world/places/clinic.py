"""诊所 — 付费快速恢复精力。"""

from dataclasses import dataclass

from .base import Place


@dataclass
class Clinic(Place):
    """诊所场所。

    智能体可以花金币快速恢复精力，比睡觉快得多。
    """

    name: str = "诊所"
    description: str = (
        "一栋白色小楼，门口挂着红十字标志。"
        "里面的医生可以快速帮你恢复精力——当然，不是免费的。"
        "花金币可以恢复精力，比回家睡觉快得多。"
    )
    heal_price: int = 50            # 每次治疗基础价格
    heal_energy: float = 50.0       # 每次恢复精力值
    heal_health: float = 40.0       # 每次恢复健康值

    def heal(self, agent_name: str, cash: int) -> tuple[int, float, float, str]:
        """治疗。返回 (花费金币, 恢复精力, 恢复健康, 信息)。"""
        if cash < self.heal_price:
            return 0, 0, 0, f"{agent_name} 金币不足（有 {cash}，需要 {self.heal_price}）。"
        return self.heal_price, self.heal_energy, self.heal_health, (
            f"{agent_name} 在诊所接受了治疗，花费 {self.heal_price} 金币，"
            f"恢复了 {self.heal_energy:.0f} 精力和 {self.heal_health:.0f} 健康。"
        )
