"""银行 — 智能体可以存款、取款、贷款。"""

from dataclasses import dataclass, field

from .base import Place


@dataclass
class Bank(Place):
    """银行场所。

    智能体可以存款（获得利息）、取款、申请贷款。
    银行提供金融服务，是经济系统的核心组成部分。
    """

    name: str = "银行"
    description: str = (
        "一栋气派的石砌建筑，门口挂着金色的天平标志。"
        "柜台后的银行职员面无表情地处理着各种金融业务。"
        "可以存款、取款、申请贷款。"
    )
    interest_rate: float = 0.005         # 存款日利率（0.5%）
    loan_interest_rate: float = 0.02     # 贷款日利率（2%）
    max_loan: int = 5000                # 最大贷款额
    # 存款记录: {agent_name: balance}
    _deposits: dict[str, int] = field(default_factory=dict, init=False)
    # 贷款记录: {agent_name: amount}
    _loans: dict[str, int] = field(default_factory=dict, init=False)

    def deposit(self, agent_name: str, amount: int) -> str:
        """存款。"""
        self._deposits[agent_name] = self._deposits.get(agent_name, 0) + amount
        return f"{agent_name} 存入 {amount} 金币。当前存款余额: {self._deposits[agent_name]}。"

    def withdraw(self, agent_name: str, amount: int) -> tuple[int, str]:
        """取款。返回 (实际取出金额, 信息)。"""
        balance = self._deposits.get(agent_name, 0)
        actual = min(amount, balance)
        if actual == 0:
            return 0, f"{agent_name} 存款余额不足。当前余额: {balance}。"
        self._deposits[agent_name] = balance - actual
        return actual, f"{agent_name} 取出 {actual} 金币。当前存款余额: {self._deposits[agent_name]}。"

    def borrow(self, agent_name: str, amount: int) -> tuple[int, str]:
        """贷款。返回 (实际贷出金额, 信息)。"""
        current_loan = self._loans.get(agent_name, 0)
        available = self.max_loan - current_loan
        actual = min(amount, available)
        if actual <= 0:
            return 0, f"{agent_name} 贷款额度已满。当前贷款: {current_loan}/{self.max_loan}。"
        self._loans[agent_name] = current_loan + actual
        return actual, f"{agent_name} 贷出 {actual} 金币。当前贷款总额: {self._loans[agent_name]}，利率 {self.loan_interest_rate:.0%}/tick。"

    def repay(self, agent_name: str, amount: int) -> str:
        """还款。"""
        current = self._loans.get(agent_name, 0)
        actual = min(amount, current)
        if actual == 0:
            return f"{agent_name} 没有未还贷款。"
        self._loans[agent_name] = current - actual
        return f"{agent_name} 还款 {actual} 金币。剩余贷款: {self._loans[agent_name]}。"

    def get_balance(self, agent_name: str) -> int:
        """查询存款余额。"""
        return self._deposits.get(agent_name, 0)

    def get_loan(self, agent_name: str) -> int:
        """查询贷款余额。"""
        return self._loans.get(agent_name, 0)
