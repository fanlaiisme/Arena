"""市政厅 — 政府公告、税收、任务发布。"""

from dataclasses import dataclass, field

from .base import Place


@dataclass
class CityHall(Place):
    """市政厅场所。

    发布公共公告，收取税金，偶尔发布任务。
    """

    name: str = "市政厅"
    description: str = (
        "一栋庄严的政府大楼，门前的公告栏上贴着最新的通知。"
        "官员们面无表情地处理着各种政务。"
        "可以查看公告、缴纳税金、接取任务。"
    )
    tax_rate: float = 0.02          # 每日税率（现金的 2%）
    _announcements: list[str] = field(default_factory=lambda: [
        "欢迎来到本镇！遵守法律，按时纳税。",
        "竞技场比赛期间禁止斗殴。",
    ], init=False)
    _daily_tax_collected: int = 0   # 当日已收税

    def post_announcement(self, text: str) -> str:
        """发布公告。"""
        self._announcements.append(text)
        return f"[市政厅公告] {text}"

    def read_announcements(self) -> str:
        """查看公告。"""
        if not self._announcements:
            return "公告栏空空如也。"
        return "=== 市政厅公告栏 ===\n" + "\n".join(
            f"  {i+1}. {a}" for i, a in enumerate(self._announcements[-5:])
        )

    def collect_tax(self, agent_name: str, cash: int) -> tuple[int, str]:
        """收税。返回 (税额, 信息)。"""
        tax = max(1, int(cash * self.tax_rate))
        self._daily_tax_collected += tax
        return tax, f"{agent_name} 缴纳了 {tax} 金币的税金。"

    def daily_reset(self):
        """每日重置。"""
        self._daily_tax_collected = 0
