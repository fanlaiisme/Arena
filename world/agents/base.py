"""WorldAgent 基类 — 生活在虚拟世界中的智能体。

所有行动都消耗 tick，智能体在忙期间被阻塞：

    状态机制:
        空闲 ──行动──▶ 忙（busy）──N ticks后──▶ 空闲
        空闲 ◀──完成──── 忙

    忙的原因可以是: 路上移动、睡觉、吃饭、工作

    地图显示:
        在场所 → 显示在建筑旁
        在路上 → 显示在道路的插值位置（travel_progress 0~1）
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..places.base import Place

# ===== 行动耗时常量（tick 数） =====

EAT_TICKS = 5              # 吃饭


@dataclass
class WorldAgent:
    """虚拟世界中的智能体。"""

    # ===== 身份 =====
    name: str
    gender: str = "男"
    age: int = 25                # 年龄（按天增长）
    personality: str = ""
    goal: str = ""

    # ===== 经济 =====
    cash: int = 1000
    food: int = 50

    # ===== 生理状态 =====
    hunger: float = 100.0        # 饱腹度 0-100
    energy: float = 100.0        # 精力 0-100
    health: float = 100.0        # 健康值 0-100 (0=重病)
    suspicion: float = 0.0       # 嫌疑值 0-100 (>80 触发法庭)
    confined: bool = False       # 是否被关押（监狱）
    happiness: float = 70.0      # 幸福度 0-100
    hunger_decay: float = 1.0
    energy_decay: float = 1.0
    health_decay: float = 0.3    # 健康自然衰减（慢）
    energy_regen: float = 4.0

    # ===== 位置 =====
    home: "Place | None" = None
    location: "Place | None" = field(default=None, init=False)

    # ===== 忙状态（阻塞所有新行动） =====
    sleeping: bool = False
    eating: bool = False
    _eat_timer: int = 0
    _eat_amount: int = 0

    # 路上移动
    travelling: bool = False
    travel_from: str = ""          # 出发场所名
    travel_to: str = ""            # 目的场所名
    travel_total: int = 0          # 总需 tick
    travel_elapsed: int = 0        # 已过 tick

    # 通用工作忙
    work_ticks: int = 0            # 工作剩余 tick（>0 = 忙）
    work_reason: str = ""          # 忙的原因

    # ===== 社交 =====
    relationships: dict[str, float] = field(default_factory=dict)

    # ===== 记忆 =====
    memory: list[str] = field(default_factory=list)

    # ===== 属性计算 =====

    @property
    def is_busy(self) -> bool:
        """是否被阻塞 — 睡觉/吃饭/移动/工作/关押中。"""
        return (self.sleeping or self.eating or
                self.travelling or self.work_ticks > 0 or self.confined)

    @property
    def busy_reason(self) -> str:
        """当前忙的原因。"""
        if self.confined:
            return "服刑中"
        if self.sleeping:
            return "睡觉"
        if self.eating:
            return "吃饭"
        if self.travelling:
            return f"前往{self.travel_to}途中"
        if self.work_ticks > 0:
            return self.work_reason or "工作中"
        return "空闲"

    @property
    def travel_progress(self) -> float:
        """路上移动进度 0.0~1.0。"""
        if not self.travelling or self.travel_total == 0:
            return 0.0
        return min(1.0, self.travel_elapsed / self.travel_total)

    @property
    def hunger_status(self) -> str:
        if self.hunger >= 80: return "饱腹"
        elif self.hunger >= 50: return "正常"
        elif self.hunger >= 20: return "饥饿"
        else: return "极度饥饿"

    @property
    def energy_status(self) -> str:
        if self.energy >= 80: return "精力充沛"
        elif self.energy >= 50: return "正常"
        elif self.energy >= 20: return "疲惫"
        else: return "精疲力竭"

    @property
    def health_status(self) -> str:
        if self.health >= 80: return "健康"
        elif self.health >= 50: return "亚健康"
        elif self.health >= 20: return "生病"
        else: return "重病"

    @property
    def happiness_status(self) -> str:
        if self.happiness >= 80: return "幸福"
        elif self.happiness >= 50: return "满足"
        elif self.happiness >= 30: return "低落"
        else: return "抑郁"

    # ===== 每 tick 生理更新 =====

    def tick_physiology(self) -> str | None:
        """每 tick 更新状态。返回状态变化事件或 None。"""
        # 嫌疑值微量增长
        self.suspicion = min(100, self.suspicion + 0.05)

        if self.confined:
            # 关押中：衰减减半，倒计时刑期
            self.energy = max(0, self.energy - self.energy_decay * 0.3)
            self.hunger = max(0, self.hunger - self.hunger_decay * 0.3)
            self.health = max(0, self.health - self.health_decay * 0.3)
            self.happiness = max(0, self.happiness - 0.2)
            if self.work_ticks > 0:
                self.work_ticks -= 1
                if self.work_ticks <= 0:
                    return "__released__"  # World.step() 处理释放
            return None

        if self.sleeping:
            old = self.energy
            self.energy = min(100, self.energy + self.energy_regen)
            self.health = min(100, self.health + 0.5)  # 睡觉缓慢恢复健康
            self.happiness = min(100, self.happiness + 0.03)
            if self.energy >= 100 and old < 100:
                self.sleeping = False
                self.happiness = min(100, self.happiness + 5)  # 睡醒额外 +5
                return f"{self.name} 睡醒了，精力充沛。"

        elif self.eating:
            self._eat_timer -= 1
            self.health = max(0, self.health - self.health_decay * 0.3)
            self.happiness = min(100, self.happiness + 0.05)
            if self._eat_timer <= 0:
                return self._finish_eating()

        elif self.travelling:
            self.travel_elapsed += 1
            self.energy = max(0, self.energy - self.energy_decay * 0.5)
            self.hunger = max(0, self.hunger - self.hunger_decay * 0.5)
            self.health = max(0, self.health - self.health_decay * 0.5)
            # 路上幸福度不变
            if self.travel_elapsed >= self.travel_total:
                return "__arrived__"

        elif self.work_ticks > 0:
            self.work_ticks -= 1
            self.energy = max(0, self.energy - self.energy_decay)
            self.hunger = max(0, self.hunger - self.hunger_decay)
            self.health = max(0, self.health - self.health_decay)
            self.happiness = max(0, self.happiness - 0.05)
            if self.work_ticks <= 0:
                return f"{self.name} 完成了: {self.work_reason}"

        else:
            old_energy = self.energy
            self.energy = max(0, self.energy - self.energy_decay)
            self.hunger = max(0, self.hunger - self.hunger_decay)
            self.health = max(0, self.health - self.health_decay)
            self.happiness = max(0, self.happiness - 0.02)  # 基础衰减
            # 额外条件惩罚
            if self.hunger < 20:
                self.happiness = max(0, self.happiness - 0.1)
            if self.health < 30:
                self.happiness = max(0, self.happiness - 0.1)
            if self.energy <= 0 and old_energy > 0:
                self.happiness = max(0, self.happiness - 3)  # 精力归零一次性 -3
            if self.energy <= 0:
                return f"{self.name} 精疲力竭了..."

        return None

    # ===== 行动 =====

    def start_travel(self, from_name: str, to_name: str, ticks: int) -> str:
        """开始前往另一个场所。"""
        self.travelling = True
        self.travel_from = from_name
        self.travel_to = to_name
        self.travel_total = ticks
        self.travel_elapsed = 0
        self.location = None  # 离开当前场所（由 World 处理 leave）
        return f"{self.name} 离开了{from_name}，前往{to_name}（{ticks} ticks）"

    def start_work(self, ticks: int, reason: str) -> str:
        """开始一项工作，忙 ticks 个 tick。"""
        self.work_ticks = ticks
        self.work_reason = reason
        return f"{self.name} 开始: {reason}（{ticks} ticks）"

    def start_eating(self, amount: int = 10) -> str:
        """开始吃饭。"""
        if self.is_busy:
            return f"{self.name} 正忙（{self.busy_reason}），无法吃饭。"
        if self.food < amount:
            return f"{self.name} 食物不足（剩余 {self.food}，需要 {amount}）。"
        self.eating = True
        self._eat_timer = EAT_TICKS
        self._eat_amount = amount
        return f"{self.name} 开始吃饭，{EAT_TICKS} ticks 后完成..."

    def _finish_eating(self) -> str:
        self.food -= self._eat_amount
        self.hunger = min(100, self.hunger + self._eat_amount * 5)
        self.happiness = min(100, self.happiness + 3)  # 吃完额外 +3
        msg = f"{self.name} 吃完了 {self._eat_amount} 食物，饱腹度 {self.hunger:.0f}。"
        self.eating = False
        self._eat_amount = 0
        return msg

    def sleep(self) -> str:
        """开始睡觉。"""
        if self.is_busy and not self.sleeping:
            return f"{self.name} 正忙（{self.busy_reason}），无法睡觉。"
        if self.sleeping:
            return f"{self.name} 已经在睡觉了。"
        self.sleeping = True
        return f"{self.name} 开始睡觉。精力: {self.energy:.0f}。"

    # ===== 社交 =====

    def get_relationship(self, other_name: str) -> float:
        return self.relationships.get(other_name, 0.0)

    def adjust_relationship(self, other_name: str, delta: float) -> None:
        current = self.relationships.get(other_name, 0.0)
        self.relationships[other_name] = max(-100, min(100, current + delta))

    # ===== 观察 =====

    def observe(self) -> str:
        if self.travelling:
            return (f"{self.name} 正在路上: {self.travel_from} → {self.travel_to}"
                    f"（进度 {self.travel_progress:.0%}）")

        if not self.location:
            return f"{self.name} 当前不在任何场所。"

        loc_desc = self.location.describe()
        others_present = [a.name for a in self.location.agents if a is not self]

        lines = [
            loc_desc, "",
            f"=== {self.name} 的状态 ===",
            f"年龄: {self.age} | 性别: {self.gender}",
            f"现金: {self.cash} | 食物: {self.food}",
            f"饱腹: {self.hunger:.0f}% ({self.hunger_status})",
            f"精力: {self.energy:.0f}% ({self.energy_status})",
            f"健康: {self.health:.0f}% ({self.health_status})",
            f"幸福: {self.happiness:.0f}% ({self.happiness_status})",
            f"状态: {self.busy_reason}",
            f"目标: {self.goal}",
        ]
        if others_present:
            lines.append(f"周围有人: {', '.join(others_present)}")
        return "\n".join(lines)

    # ===== 内部 =====

    def __repr__(self) -> str:
        if self.travelling:
            return f"<WorldAgent: {self.name} {self.travel_from}→{self.travel_to}>"
        loc = self.location.name if self.location else "路上"
        return f"<WorldAgent: {self.name} @ {loc}>"

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WorldAgent):
            return NotImplemented
        return self.name == other.name
