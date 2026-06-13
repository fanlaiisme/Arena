"""时间系统 — 虚拟世界的时间层级和日程管理。

时间层次：
    tick → phase → day → week → month

    1 tick   = 1 个决策/行动周期（所有智能体各做一次决策）
    100 ticks = 1 day
    7 days   = 1 week
    28 days  = 4 weeks = 1 month

每天分为 4 个时段，用于控制场所开放时间：
    深夜 (Night):    0-24    — 银行关门，酒馆关门，居民区可休息
    上午 (Morning):  25-49   — 银行开门，农场劳作
    下午 (Afternoon): 50-74  — 银行开门，酒馆开门，竞技场活跃
    傍晚 (Evening):   75-99  — 酒馆开门，适合社交
"""

from dataclasses import dataclass
from enum import IntEnum

# ===== 时间常量 =====

TICKS_PER_PHASE = 25     # 每个时段 = 25 ticks
PHASES_PER_DAY = 4       # 每天 4 个时段
TICKS_PER_DAY = TICKS_PER_PHASE * PHASES_PER_DAY  # 100
DAYS_PER_WEEK = 7
WEEKS_PER_MONTH = 4
DAYS_PER_MONTH = DAYS_PER_WEEK * WEEKS_PER_MONTH   # 28


class Phase(IntEnum):
    """一天中的时段。"""
    NIGHT = 0       # 0-24
    MORNING = 1     # 25-49
    AFTERNOON = 2   # 50-74
    EVENING = 3     # 75-99

    @property
    def label(self) -> str:
        labels = {0: "深夜", 1: "上午", 2: "下午", 3: "傍晚"}
        return labels[self.value]

    @property
    def tick_range(self) -> tuple[int, int]:
        """该时段对应的 tick 范围（当天内）。"""
        start = self.value * TICKS_PER_PHASE
        end = start + TICKS_PER_PHASE - 1
        return start, end


# ===== 场所时间约束 =====

# 银行：上午 + 下午开放
BANK_OPEN_PHASES = frozenset({Phase.MORNING, Phase.AFTERNOON})

# 酒馆：下午 + 傍晚开放
TAVERN_OPEN_PHASES = frozenset({Phase.AFTERNOON, Phase.EVENING})

# 竞技场：上午 + 下午可进行比赛（深夜和傍晚不安排）
ARENA_ACTIVE_PHASES = frozenset({Phase.MORNING, Phase.AFTERNOON})

# 农场：上午 + 下午可劳作
FARM_ACTIVE_PHASES = frozenset({Phase.MORNING, Phase.AFTERNOON})

# 居民区：全天可进入

# ===== 经济时间常量 =====

# 银行利率结算：每天一次（在 day 结束时）
INTEREST_PERIOD_TICKS = TICKS_PER_DAY   # 100

# 农作物生长：播种后需要 CROP_TOTAL_STAGES 天成熟
CROP_TOTAL_STAGES = 2

# 竞技场比赛预计耗时：每次比赛约 15 ticks
MATCH_DURATION_TICKS = 15

# 竞技场每天比赛消耗（拍卖+部署+3场+分析 ≈ 50 ticks）
ARENA_DAY_TICKS = 50


@dataclass
class GameTime:
    """世界时钟。

    维护 tick / day / week / month 的递增关系。
    """

    tick: int = 0

    @property
    def day(self) -> int:
        """当前是第几天（从 1 开始）。"""
        return self.tick // TICKS_PER_DAY + 1

    @property
    def day_of_week(self) -> int:
        """本周第几天（1-7）。"""
        return (self.day - 1) % DAYS_PER_WEEK + 1

    @property
    def week(self) -> int:
        """当前是第几周（从 1 开始）。"""
        return (self.day - 1) // DAYS_PER_WEEK + 1

    @property
    def month(self) -> int:
        """当前是第几月（从 1 开始）。"""
        return (self.day - 1) // DAYS_PER_MONTH + 1

    @property
    def phase(self) -> Phase:
        """当前时段。"""
        return Phase((self.tick % TICKS_PER_DAY) // TICKS_PER_PHASE)

    @property
    def tick_in_day(self) -> int:
        """当天的第几个 tick（0-99）。"""
        return self.tick % TICKS_PER_DAY

    @property
    def is_new_day(self) -> bool:
        """是否刚好是一天的起始（tick % 100 == 0）。"""
        return self.tick % TICKS_PER_DAY == 0

    @property
    def is_day_end(self) -> bool:
        """是否是一天的末尾（tick % 100 == 99）。"""
        return self.tick % TICKS_PER_DAY == TICKS_PER_DAY - 1

    def advance(self, n: int = 1) -> "GameTime":
        """推进 n 个 tick，返回新的 GameTime。"""
        return GameTime(tick=self.tick + n)

    def advance_inplace(self, n: int = 1) -> None:
        """原地推进 n 个 tick。"""
        self.tick += n

    def describe(self) -> str:
        """时间的文本描述。"""
        day_names = ["一", "二", "三", "四", "五", "六", "日"]
        dow = day_names[self.day_of_week - 1]
        return (
            f"第 {self.month} 月 第 {self.week} 周 "
            f"星期{dow} (第 {self.day} 天) "
            f"{self.phase.label} (tick {self.tick_in_day}/99)"
        )

    def is_bank_open(self) -> bool:
        return self.phase in BANK_OPEN_PHASES

    def is_tavern_open(self) -> bool:
        return self.phase in TAVERN_OPEN_PHASES

    def is_arena_active(self) -> bool:
        return self.phase in ARENA_ACTIVE_PHASES

    def is_farm_active(self) -> bool:
        return self.phase in FARM_ACTIVE_PHASES

    def __repr__(self) -> str:
        return f"<GameTime: day={self.day} {self.phase.label}>"
