"""办公大楼 — 智能体上班赚钱。"""

from dataclasses import dataclass, field
import random

from .base import Place


@dataclass
class Office(Place):
    """办公大楼场所。

    智能体可以在这里上班工作，消耗时间换取金币。
    """

    name: str = "办公大楼"
    description: str = (
        "一栋现代化的玻璃幕墙写字楼，电梯快速穿梭于各层之间。"
        "白领们抱着文件匆匆走过，键盘声此起彼伏。"
        "在这里上班可以赚取金币，是稳定的收入来源。"
    )
    base_salary: int = 35             # 基础工资
    salary_variance: int = 15         # 工资浮动 ±15

    def work(self, agent_name: str) -> tuple[int, str]:
        """上班工作。返回 (赚取金币, 信息)。"""
        earned = self.base_salary + random.randint(-self.salary_variance, self.salary_variance)
        return max(5, earned), f"{agent_name} 在办公大楼工作了 10 ticks，赚了 {earned} 金币。"
