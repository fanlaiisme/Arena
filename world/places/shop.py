"""商店 — 买卖食物和物品，价格可浮动。"""

from dataclasses import dataclass

from .base import Place


@dataclass
class Shop(Place):
    """商店场所。

    智能体可以在这里买卖食物。价格根据供需浮动。
    """

    name: str = "商店"
    description: str = (
        "一个热闹的集市摊位，货架上摆满了各种食物和日用品。"
        "店主热情地招呼着来往的顾客。可以买卖食物，价格随行就市。"
    )
    food_price: int = 3             # 当前食物单价（购买价）
    food_sell_price: int = 2        # 卖出食物单价（回收价）
    transaction_count: int = 0      # 当日交易次数（影响价格）

    def buy(self, agent_name: str, cash: int, amount: int) -> tuple[int, int, str]:
        """购买食物。返回 (实际购买量, 花费金币, 信息)。"""
        cost = amount * self.food_price
        actual = min(amount, cash // self.food_price)
        if actual <= 0:
            return 0, 0, f"{agent_name} 金币不足，无法购买。需要 {self.food_price} 金币/食物。"
        spent = actual * self.food_price
        self.transaction_count += 1
        if self.transaction_count > 5:
            self.food_price = min(8, self.food_price + 1)  # 买的人多涨价
        return actual, spent, f"{agent_name} 购买了 {actual} 食物，花费 {spent} 金币。"

    def sell_food(self, agent_name: str, amount: int) -> tuple[int, str]:
        """卖出食物。返回 (获得金币, 信息)。"""
        earned = amount * self.food_sell_price
        self.transaction_count += 1
        if self.transaction_count > 5:
            self.food_sell_price = max(1, self.food_sell_price - 1)  # 卖的人多降价
        return earned, f"{agent_name} 卖出了 {amount} 食物，获得 {earned} 金币。"

    def reset_prices(self):
        """每天重置价格到基准。"""
        self.food_price = 3
        self.food_sell_price = 2
        self.transaction_count = 0
