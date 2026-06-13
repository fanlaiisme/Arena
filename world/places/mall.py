"""商场 — 大型零售中心，买卖食物，价格浮动。"""

from dataclasses import dataclass

from .base import Place


@dataclass
class Mall(Place):
    """商场场所 — 沃尔玛式大型零售建筑。

    智能体可以买卖食物。价格随供需浮动。
    """

    name: str = "商场"
    description: str = (
        "一栋巨大的零售商场，货架上琳琅满目，从食品到日用品应有尽有。"
        "宽敞的通道和明亮的灯光让人逛起来很舒适。"
        "可以大量买卖食物，价格随行就市。"
    )
    food_price: int = 3
    food_sell_price: int = 2
    transaction_count: int = 0

    def buy(self, agent_name: str, cash: int, amount: int) -> tuple[int, int, str]:
        """购买食物。返回 (实际购买量, 花费金币, 信息)。"""
        cost = amount * self.food_price
        actual = min(amount, cash // self.food_price)
        if actual <= 0:
            return 0, 0, f"{agent_name} 金币不足，无法购买。需要 {self.food_price} 金币/食物。"
        spent = actual * self.food_price
        self.transaction_count += 1
        if self.transaction_count > 8:
            self.food_price = min(8, self.food_price + 1)
        return actual, spent, f"{agent_name} 在商场购买了 {actual} 食物，花费 {spent} 金币。"

    def sell_food(self, agent_name: str, amount: int) -> tuple[int, str]:
        """卖出食物。返回 (获得金币, 信息)。"""
        earned = amount * self.food_sell_price
        self.transaction_count += 1
        if self.transaction_count > 8:
            self.food_sell_price = max(1, self.food_sell_price - 1)
        return earned, f"{agent_name} 在商场卖出了 {amount} 食物，获得 {earned} 金币。"

    def reset_prices(self):
        self.food_price = 3
        self.food_sell_price = 2
        self.transaction_count = 0
