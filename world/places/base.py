"""Place 基类 — 世界中的一个场所。"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.base import WorldAgent


@dataclass
class Place:
    """世界中的场所基类。

    每个场所有一组智能体停留于此，定义了该场所可执行的动作。
    """

    name: str
    description: str
    agents: set["WorldAgent"] = field(default_factory=set, init=False)

    def enter(self, agent: "WorldAgent") -> None:
        """智能体进入该场所。"""
        self.agents.add(agent)
        agent.location = self

    def leave(self, agent: "WorldAgent") -> None:
        """智能体离开该场所。"""
        self.agents.discard(agent)

    @property
    def occupant_names(self) -> list[str]:
        """当前在此场所的智能体名字列表。"""
        return sorted(a.name for a in self.agents)

    def describe(self) -> str:
        """场所的文本描述，包含当前在场的人。"""
        parts = [f"【{self.name}】", self.description]
        if self.agents:
            parts.append(f"当前在场: {', '.join(self.occupant_names)}")
        else:
            parts.append("当前没有人在此。")
        return "\n".join(parts)

    def __repr__(self) -> str:
        return f"<Place: {self.name}>"
