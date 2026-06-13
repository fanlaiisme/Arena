"""公园 — 休闲社交场所，可免费休息恢复精力。"""

from dataclasses import dataclass

from .base import Place


@dataclass
class Park(Place):
    """公园场所。

    智能体可以在此免费休息（精力恢复比睡觉慢），
    也是社交偶遇的自然场所。
    """

    name: str = "公园"
    description: str = (
        "一片宁静的绿地，中央有一座小喷泉，长椅散落在树荫下。"
        "人们在这里散步、聊天、发呆。可以免费休息，恢复精力。"
    )
    rest_energy: float = 2.0        # 每次 rest 恢复的精力
    rest_health: float = 1.0        # 每次 rest 恢复的健康
