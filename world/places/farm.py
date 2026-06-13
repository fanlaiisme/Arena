"""农场 — 智能体可以进行农业生产，获取食物。

作物生长周期：
    播种 → 生长中 (day 1) → 成熟 (day 2 起)
    即：播种后经过 2 个日夜（200 ticks）可收割。
"""

from dataclasses import dataclass, field

from .base import Place
from ..time import CROP_TOTAL_STAGES


@dataclass
class Farm(Place):
    """农场场所。

    智能体可以播种、收割。作物需要 2 天（200 ticks）成熟。
    食物是虚拟世界的基础资源。
    """

    name: str = "农场"
    description: str = (
        "一片肥沃的农田，种植着各种作物。空气中弥漫着泥土和麦穗的气息。"
        "智能体可以在这里种植作物获取食物。"
        f"作物需要 {CROP_TOTAL_STAGES} 天的生长期才能成熟收割。"
    )
    crop_yield: int = 50               # 每次收割的基准食物产出
    seed_price: int = 10               # 购买种子的价格
    # 记录每个智能体的作物生长天数（每天的 tick 结束时 +1）
    _crop_stage: dict[str, int] = field(default_factory=dict, init=False)

    def plant(self, agent_name: str) -> str:
        """播种 — 消耗种子价格，开始种植周期。"""
        if agent_name in self._crop_stage:
            return f"{agent_name} 已经播种过了，当前生长阶段: {self._crop_stage[agent_name]}/{CROP_TOTAL_STAGES}。"
        self._crop_stage[agent_name] = 0
        return f"{agent_name} 在农场播下了种子。生长周期: {CROP_TOTAL_STAGES} 天。"

    def harvest(self, agent_name: str) -> tuple[int, str]:
        """收割 — 如果作物成熟（≥CROP_TOTAL_STAGES），返回食物；否则返回进度信息。"""
        stage = self._crop_stage.get(agent_name)
        if stage is None:
            return 0, f"{agent_name} 还没有播种，无法收割。请先 plant。"
        if stage < CROP_TOTAL_STAGES:
            return 0, f"{agent_name} 的作物尚未成熟（生长 {stage}/{CROP_TOTAL_STAGES} 天），需要继续等待。"
        del self._crop_stage[agent_name]
        return self.crop_yield, f"{agent_name} 收割了作物，获得 {self.crop_yield} 食物！"

    def get_crop_status(self, agent_name: str) -> str:
        """查看作物生长状态。"""
        stage = self._crop_stage.get(agent_name)
        if stage is None:
            return f"{agent_name} 没有正在生长的作物。"
        if stage < CROP_TOTAL_STAGES:
            return f"{agent_name} 的作物: 生长 {stage}/{CROP_TOTAL_STAGES} 天（还需 {CROP_TOTAL_STAGES - stage} 天成熟）"
        return f"{agent_name} 的作物: 已成熟，可以收割！"

    def tick_crops(self) -> None:
        """每天结束时调用，推进所有作物的生长阶段。"""
        for name in list(self._crop_stage):
            self._crop_stage[name] += 1
