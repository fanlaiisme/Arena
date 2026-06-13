"""竞技场 — Bob的竞技场，智能体在这里进行赌局对决。"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from .base import Place

if TYPE_CHECKING:
    from ..agents.base import WorldAgent


class MatchStatus(Enum):
    IDLE = "idle"
    PENDING = "pending"       # 等待双方确认
    RUNNING = "running"       # 比赛进行中
    FINISHED = "finished"     # 比赛结束


@dataclass
class Match:
    """一场竞技场比赛。"""
    challenger: str
    opponent: str
    stake: int
    status: MatchStatus = MatchStatus.PENDING
    winner: str | None = None
    log: list[str] = field(default_factory=list)

    def describe(self) -> str:
        status_text = {
            MatchStatus.PENDING: "等待开始",
            MatchStatus.RUNNING: "进行中",
            MatchStatus.FINISHED: f"已结束 — 胜者: {self.winner}",
        }
        return (
            f"比赛: {self.challenger} VS {self.opponent} | "
            f"赌注: {self.stake} | 状态: {status_text[self.status]}"
        )


@dataclass
class Arena(Place):
    """Bob竞技场场所。

    智能体进入竞技场可以进行赌局对决。
    这里是现有 role/ 实验的入口 — 当赌局成立后，
    会触发 role/main.py 的比赛流程。
    """

    name: str = "Bob竞技场"
    description: str = (
        "一座宏伟的圆形竞技场，高耸的石墙上装饰着历代冠军的雕像。"
        "观众席上坐满了狂热的赌徒，空气中弥漫着汗水与热血的气息。"
        "这里是角斗士们证明自己实力的地方，也是赌徒们一夜暴富或倾家荡产的场所。"
    )
    # 比赛记录
    _matches: list[Match] = field(default_factory=list, init=False)
    # 当前活跃比赛
    _active_match: Match | None = field(default=None, init=False)

    def register_match(self, challenger: str, opponent: str, stake: int) -> Match:
        """登记一场比赛。"""
        match = Match(challenger=challenger, opponent=opponent, stake=stake)
        self._matches.append(match)
        self._active_match = match
        return match

    def set_match_running(self) -> str:
        """标记比赛开始。"""
        if not self._active_match:
            return "当前没有待开始的比赛。"
        self._active_match.status = MatchStatus.RUNNING
        self._active_match.log.append("比赛开始！")
        return f"比赛开始: {self._active_match.challenger} VS {self._active_match.opponent}"

    def set_match_finished(self, winner: str) -> str:
        """标记比赛结束，返回胜者。"""
        if not self._active_match:
            return "当前没有进行中的比赛。"
        self._active_match.status = MatchStatus.FINISHED
        self._active_match.winner = winner
        self._active_match.log.append(f"胜者: {winner}")
        msg = f"比赛结束！胜者: {winner}。赌注 {self._active_match.stake} 金币归 {winner}。"
        self._active_match = None
        return msg

    def get_match_history(self) -> str:
        """查看比赛历史。"""
        if not self._matches:
            return "竞技场还没有任何比赛记录。"
        recent = self._matches[-10:]  # 最近10场
        return "=== 竞技场比赛记录 ===\n" + "\n".join(
            f"  {m.describe()}" for m in recent
        )
