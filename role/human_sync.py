"""线程同步机制 —— 在实验线程和 Web API 端点之间传递人类输入。"""

import threading
from dataclasses import dataclass, field


@dataclass
class HumanInputState:
    """人类输入同步状态，通过 threading.Event 阻塞/唤醒实验线程。"""

    waiting_for: str = "none"  # "none" | "bid" | "deploy" | "confirm" | "summary"

    # ── 拍卖出价 ──
    bid_event: threading.Event = field(default_factory=threading.Event)
    human_bid: int = 0

    # ── 部署 ──
    deploy_event: threading.Event = field(default_factory=threading.Event)
    human_deployments: dict[int, str] = field(default_factory=dict)  # {slot: char_id}

    # ── 确认（预览/规则/分析/反思）──
    confirm_event: threading.Event = field(default_factory=threading.Event)

    # ── 每日复盘 ──
    summary_event: threading.Event = field(default_factory=threading.Event)
    ranking_table: str = ""       # 人类填写的匿名排名表文本
    chip_estimate: str = ""       # 人类估算的对手币量文本

    def reset(self):
        """重置所有事件和输入值。"""
        self.waiting_for = "none"
        self.bid_event.clear()
        self.human_bid = 0
        self.deploy_event.clear()
        self.human_deployments.clear()
        self.confirm_event.clear()
        self.summary_event.clear()
        self.ranking_table = ""
        self.chip_estimate = ""
