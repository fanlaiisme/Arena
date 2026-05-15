"""阵容管理：每个玩家持有 3 个角斗士、疲劳追踪、HP 缩放。"""

from dataclasses import dataclass, field


@dataclass
class SquadMember:
    """阵容中的一名角斗士。"""
    char_id: str
    name: str
    fatigue_days: int = 0          # 连续出战天数（0=新鲜, 1=昨天出战, 2=连续两天）
    rested_yesterday: bool = False  # 昨天是否休息了（用于隔天恢复判断）
    point: int = 0                 # 累积的游戏币 point（拍卖成交价 + 比赛夺取）


class Squad:
    """玩家阵容，管理 3 个角斗士的疲劳和出战限制。"""

    def __init__(self, members: list[SquadMember]):
        if len(members) != 3:
            raise ValueError(f"Squad must have exactly 3 members, got {len(members)}")
        self.members: list[SquadMember] = members
        self.used_today: set[str] = set()  # 当天已出战的角斗士 char_id
        self.point_pool: int = 0            # 奖励池：每天比赛结束后归入的 point（与角斗士脱钩）

    # ── HP 缩放 ──────────────────────────────────────────────────────────

    def get_hp_multiplier(self, char_id: str) -> float:
        """根据疲劳状态返回 HP 缩放倍数。

        规则：
        - fatigue_days=0, 没有休息过: 100% (完全新鲜)
        - fatigue_days=0, rested_yesterday: 90% (曾出战，昨天休息恢复中)
        - fatigue_days=1: 80% (昨天出战)
        - fatigue_days>=2: 60% (连续两天以上出战)
        """
        member = self._find(char_id)
        if member is None:
            return 1.0

        if member.fatigue_days == 0:
            if member.rested_yesterday:
                return 0.9  # 曾出战，昨天休息恢复中
            return 1.0
        elif member.fatigue_days == 1:
            return 0.8
        elif member.fatigue_days >= 2:
            return 0.6

        return 1.0

    # ── 出战管理 ──────────────────────────────────────────────────────────

    def can_use_today(self, char_id: str) -> bool:
        """同一天同一角斗士最多出战 1 次。"""
        return char_id not in self.used_today

    def mark_used(self, char_id: str):
        """标记当天已出战。"""
        if char_id in self.used_today:
            raise ValueError(f"角斗士 {char_id} 今天已经出战过了")
        member = self._find(char_id)
        if member is None:
            raise ValueError(f"角斗士 {char_id} 不在阵容中")
        member.fatigue_days += 1
        member.rested_yesterday = False
        self.used_today.add(char_id)

    def next_day(self):
        """推进一天，更新所有角斗士的疲劳状态。"""
        for member in self.members:
            if member.char_id not in self.used_today:
                # 今天休息 → 标记 rested_yesterday，疲劳递减
                if member.fatigue_days > 0:
                    member.rested_yesterday = True
                    member.fatigue_days -= 1  # 休息一天，疲劳减 1
            else:
                # 今天出战了 → 不标记 rested_yesterday
                pass
        self.used_today.clear()

    # ── Point 管理 ────────────────────────────────────────────────────────

    def collect_points_to_pool(self):
        """每天比赛结束后，将所有角斗士的 point 归入奖励池，member point 归零。"""
        for m in self.members:
            self.point_pool += m.point
            m.point = 0

    def set_point(self, char_id: str, point: int):
        """设置角斗士的 point（拍卖成交时）。"""
        member = self._find(char_id)
        if member:
            member.point = point

    def settle_points_to_pool(self, char_id: str, amount: int):
        """比赛后结算：清零角斗士 point，amount 归入 point_pool（可为负）。"""
        member = self._find(char_id)
        if member:
            self.point_pool += amount
            member.point = 0

    def get_total_points(self) -> int:
        """奖励池 + 成员 point 总和。"""
        return self.point_pool + sum(m.point for m in self.members)

    # ── 查询 ──────────────────────────────────────────────────────────────

    def _find(self, char_id: str) -> SquadMember | None:
        for m in self.members:
            if m.char_id == char_id:
                return m
        return None

    @property
    def unused_today(self) -> list[SquadMember]:
        """今天还没出战的角斗士。"""
        return [m for m in self.members if m.char_id not in self.used_today]

    def summary(self) -> str:
        """返回阵容摘要文本。"""
        lines = ["【我的角斗士阵容】"]
        for i, m in enumerate(self.members):
            hp = self.get_hp_multiplier(m.char_id)
            used_mark = " (今日已出战)" if m.char_id in self.used_today else ""
            fatigue_info = ""
            if m.fatigue_days > 0:
                fatigue_info = f" | 连续出战{m.fatigue_days}天 | HP={hp*100:.0f}%"
            point_info = f" | point: {m.point}" if m.point else ""
            lines.append(
                f"  {i+1}. {m.name} (char_id: {m.char_id}){used_mark}{fatigue_info}{point_info}"
            )
        lines.append(f"\n  【奖励池】: {self.point_pool} point（已归池，与角斗士无关）")
        return "\n".join(lines)
