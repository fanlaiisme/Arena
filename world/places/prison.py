"""监狱 — 关押被法庭判刑的智能体。"""

from dataclasses import dataclass, field

from .base import Place


@dataclass
class Prison(Place):
    """监狱场所。

    被法庭判刑的智能体在此关押。
    关押期间不能移动、不能执行行动。
    刑满自动释放。
    """

    name: str = "监狱"
    description: str = (
        "一座灰色混凝土堡垒，高墙上拉着铁丝网，四角有瞭望塔。"
        "铁门厚重，只有服刑期满才能离开。"
    )
    # {agent_name: (release_global_tick, original_work_ticks)}
    _inmates: dict[str, int] = field(default_factory=dict, init=False)

    def imprison(self, agent_name: str, ticks: int, current_global_tick: int) -> str:
        """关押智能体。"""
        release_tick = current_global_tick + ticks
        self._inmates[agent_name] = release_tick
        return f"{agent_name} 被关入监狱，刑期 {ticks} ticks（于 tick {release_tick} 释放）。"

    def is_released(self, agent_name: str, current_global_tick: int) -> bool:
        """检查智能体是否已刑满。"""
        release = self._inmates.get(agent_name)
        if release is None:
            return True  # 不在监狱
        return current_global_tick >= release

    def release(self, agent_name: str) -> str:
        """释放智能体。"""
        if agent_name in self._inmates:
            del self._inmates[agent_name]
            return f"{agent_name} 刑满释放，重获自由！"
        return f"{agent_name} 不在监狱中。"

    def get_inmates(self) -> list[str]:
        """当前在押名单。"""
        return list(self._inmates.keys())
