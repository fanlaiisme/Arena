"""餐厅 — 花金币吃一顿好的，快速恢复饱腹度。"""

from dataclasses import dataclass

from .base import Place


@dataclass
class Restaurant(Place):
    """餐厅场所。

    花金币享用烹饪好的食物，比吃随身干粮恢复更多饱腹度。
    也是社交和谈生意的场所。
    """

    name: str = "餐厅"
    description: str = (
        "一家温馨的小餐馆，厨房里飘出诱人的香气。"
        "花金币可以享用一顿热饭，快速恢复饱腹度。"
        "也是人们边吃边聊、谈生意的好地方。"
    )
    meal_price: int = 15            # 一餐价格
    meal_hunger: float = 40.0       # 一顿饭恢复的饱腹度

    def dine(self, agent_name: str, cash: int) -> tuple[int, float, str]:
        """用餐。返回 (花费金币, 恢复饱腹度, 信息)。"""
        if cash < self.meal_price:
            return 0, 0, f"{agent_name} 金币不足（有 {cash}，需要 {self.meal_price}）。"
        return self.meal_price, self.meal_hunger, (
            f"{agent_name} 在餐厅吃了一顿热饭，花费 {self.meal_price} 金币，"
            f"饱腹度恢复了 {self.meal_hunger:.0f}。"
        )
