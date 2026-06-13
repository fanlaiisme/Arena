"""酒馆 — 智能体社交、交换情报、发起赌局的场所。"""

from dataclasses import dataclass, field

from .base import Place


@dataclass
class Tavern(Place):
    """酒馆场所。

    智能体在这里自由对话、交换信息、发起挑战。
    这是社交网络的核心节点，也是赌局最常见的发起地。
    """

    name: str = "酒馆"
    description: str = (
        "一间热闹的酒馆，木质吧台上摆满了各式酒瓶。"
        "昏暗的灯光下，形形色色的人围坐在桌旁，喝酒、聊天、密谋。"
        "这是交换情报和发起赌局的最佳场所。"
    )
    # 酒馆公告板 — 智能体可以留言
    _board: list[str] = field(default_factory=list, init=False)
    # 待处理的挑战: [(挑战者, 被挑战者, 赌注)]
    _pending_challenges: list[tuple[str, str, int]] = field(default_factory=list, init=False)

    def post_message(self, agent_name: str, message: str) -> str:
        """在公告板上张贴消息。"""
        entry = f"【{agent_name}】: {message}"
        self._board.append(entry)
        return f"{agent_name} 在公告板上留言: '{message}'"

    def read_board(self) -> str:
        """查看公告板。"""
        if not self._board:
            return "公告板空空如也。"
        return "=== 酒馆公告板 ===\n" + "\n".join(f"  {i+1}. {msg}" for i, msg in enumerate(self._board))

    def issue_challenge(self, challenger: str, target: str, stake: int) -> str:
        """发起挑战 — 向另一个智能体下战书。"""
        self._pending_challenges.append((challenger, target, stake))
        return f"{challenger} 向 {target} 发起了赌局挑战！赌注: {stake} 金币。等待 {target} 接受..."

    def accept_challenge(self, target: str, challenger: str) -> tuple[int, str] | None:
        """接受挑战 — 返回 (赌注, 信息)，如果没有匹配的挑战则返回 None。"""
        for i, (c, t, stake) in enumerate(self._pending_challenges):
            if c == challenger and t == target:
                del self._pending_challenges[i]
                return stake, f"{target} 接受了 {challenger} 的挑战！赌注 {stake} 金币。前往竞技场！"
        return None

    def get_pending_challenges(self, agent_name: str) -> list[tuple[str, int]]:
        """获取针对某智能体的待处理挑战。"""
        return [(c, stake) for c, t, stake in self._pending_challenges if t == agent_name]
