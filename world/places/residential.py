"""居民区 — 智能体的家，用于休息和存放私人物品。"""

from dataclasses import dataclass, field

from .base import Place


@dataclass
class Residential(Place):
    """居民区场所。

    每个智能体都有一个家。在家中可以休息恢复精力，
    存放私人物品。这是智能体最安全的避风港。
    """

    name: str = "居民区"
    description: str = (
        "一片安静的居民区，错落有致的小屋排列在街道两旁。"
        "每家每户都有自己独特的装饰风格，烟囱里偶尔飘出炊烟。"
        "智能体可以在这里休息，恢复体力。"
    )
    # 每个智能体的私人存储: {agent_name: {item: count}}
    _storage: dict[str, dict[str, int]] = field(default_factory=dict, init=False)

    def store(self, agent_name: str, item: str, count: int = 1) -> str:
        """存放物品到家中。"""
        if agent_name not in self._storage:
            self._storage[agent_name] = {}
        self._storage[agent_name][item] = self._storage[agent_name].get(item, 0) + count
        return f"{agent_name} 在家中存放了 {count} 个 {item}。"

    def retrieve(self, agent_name: str, item: str, count: int = 1) -> tuple[int, str]:
        """从家中取物品。返回 (实际取出数量, 信息)。"""
        stored = self._storage.get(agent_name, {}).get(item, 0)
        actual = min(count, stored)
        if actual == 0:
            return 0, f"{agent_name} 家中没有 {item}。"
        self._storage[agent_name][item] -= actual
        if self._storage[agent_name][item] == 0:
            del self._storage[agent_name][item]
        return actual, f"{agent_name} 从家中取出了 {actual} 个 {item}。"

    def list_storage(self, agent_name: str) -> str:
        """查看家中存储的物品。"""
        items = self._storage.get(agent_name, {})
        if not items:
            return f"{agent_name} 的家中空空如也。"
        return f"{agent_name} 的家: " + ", ".join(f"{item}×{count}" for item, count in items.items())
