"""World 类 — 管理整个虚拟世界的模拟引擎。"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .time import GameTime, Phase
from .places.base import Place
from .places.arena import Arena
from .places.farm import Farm
from .places.bank import Bank
from .places.tavern import Tavern
from .places.residential import Residential
from .places.mall import Mall
from .places.park import Park
from .places.clinic import Clinic
from .places.restaurant import Restaurant
from .places.cityhall import CityHall
from .places.office import Office
from .places.court import Court
from .places.prison import Prison

if TYPE_CHECKING:
    from .agents.base import WorldAgent

# ===== 8 条连续道路（4 横 + 4 纵） =====
# 每条道路是沿路方向排序的建筑列表
_ROADS: list[list[str]] = [
    # 横向（按 X 排序）
    ["农场", "公园", "居民A区", "居民B区", "商场"],                          # H0: Z=-30
    ["农场", "诊所", "公园", "居民A区", "酒馆", "居民B区", "银行", "餐厅", "商场"],  # H1: Z=-10
    ["监狱", "诊所", "法庭", "酒馆", "市政厅", "银行", "办公大楼", "餐厅", "Bob竞技场"], # H2: Z=10
    ["监狱", "法庭", "市政厅", "办公大楼", "Bob竞技场"],                       # H3: Z=30
    ["集市"],                                                              # H4: Z=50
    # 纵向（按 Z 排序）
    ["农场", "诊所", "监狱"],                                               # V0: X=-30
    ["公园", "居民A区", "诊所", "酒馆", "法庭", "监狱", "集市"],              # V1: X=-10
    ["商场", "居民B区", "餐厅", "银行", "办公大楼", "市政厅", "Bob竞技场", "集市"], # V2: X=10
    ["商场", "餐厅", "办公大楼", "Bob竞技场"],                                # V3: X=30
]


def _gen_road_graph() -> list[tuple[str, str, int]]:
    """从 8 条道路推导建筑间连通边。"""
    edges: set[tuple[str, str]] = set()
    for buildings in _ROADS:
        for i in range(len(buildings) - 1):
            a, b = buildings[i], buildings[i + 1]
            if a != b:
                edges.add((min(a, b), max(a, b)))
    return sorted((a, b, 3) for a, b in edges)


# 同单元格内的紧密连接（短距离 walk）
_SAME_CELL: list[tuple[str, str, int]] = [
    ("农场", "公园", 1),
    ("居民A区", "居民B区", 1),
    ("酒馆", "银行", 1),
    ("监狱", "法庭", 1),
    ("Bob竞技场", "办公大楼", 1),
]

# 跨单元格的直达路线（保留旧图中的重要连接）
_CROSS_CELL: list[tuple[str, str, int]] = [
    ("酒馆", "Bob竞技场", 5),
    ("银行", "Bob竞技场", 5),
    ("法庭", "Bob竞技场", 4),
    ("诊所", "市政厅", 4),
    ("居民B区", "办公大楼", 4),
    ("办公大楼", "商场", 4),
    ("集市", "市政厅", 4),
    ("集市", "餐厅", 5),
]

# 道路自动推导的所有边（排除与手动边重复的）
_MANUAL_NAMES: set[tuple[str, str]] = {
    (min(a, b), max(a, b)) for a, b, _ in (_SAME_CELL + _CROSS_CELL)
}
_ROAD_EDGES: list[tuple[str, str, int]] = [
    (a, b, t) for a, b, t in _gen_road_graph() if (a, b) not in _MANUAL_NAMES
]

ROAD_GRAPH: list[tuple[str, str, int]] = _SAME_CELL + _CROSS_CELL + _ROAD_EDGES


# ===== 场所 3D 坐标（建筑在网格单元格内） =====
# 4 横 4 纵道路在 X/Z = -30, -10, 10, 30
# 形成 9 个 20×20 单元格，建筑在单元格内
PLACE_POSITIONS: dict[str, tuple[int, int]] = {
    # 单元格 (-20,-20): 农场, 公园
    "农场":       (-25, -20),
    "公园":       (-15, -20),
    # 单元格 (0,-20): 居民A区, 居民B区
    "居民A区":    (-5, -20),
    "居民B区":    (5, -20),
    # 单元格 (20,-20): 商场
    "商场":       (20, -22),
    # 单元格 (-20,0): 诊所
    "诊所":       (-20, 0),
    # 单元格 (0,0): 酒馆, 银行
    "酒馆":       (-5, 0),
    "银行":       (5, 0),
    # 单元格 (20,0): 餐厅
    "餐厅":       (20, -2),
    # 单元格 (-20,20): 监狱, 法庭
    "监狱":       (-25, 20),
    "法庭":       (-15, 20),
    # 单元格 (0,20): 市政厅
    "市政厅":     (0, 22),
    # 单元格 (0,40): 集市（Z=30~50 新行，独享单元格）
    "集市":       (0, 42),
    # 单元格 (20,20): Bob竞技场, 办公大楼
    "Bob竞技场":  (25, 25),
    "办公大楼":   (15, 15),
}


def travel_ticks(place_a: str, place_b: str) -> int | None:
    """查询两个场所间的旅行 tick 数。"""
    for a, b, t in ROAD_GRAPH:
        if (a == place_a and b == place_b) or (a == place_b and b == place_a):
            return t
    return None


def build_map_data() -> dict:
    """构建地图初始化数据（传给前端）。"""
    return {
        "buildings": [
            {"id": name, "x": pos[0], "z": pos[1]}
            for name, pos in PLACE_POSITIONS.items()
        ],
        "roads": [
            {"from": a, "to": b, "ticks": t}
            for a, b, t in ROAD_GRAPH
        ],
        "grid": {
            "x_lines": [-30, -10, 10, 30],
            "z_lines": [-30, -10, 10, 30, 50],
        },
    }


@dataclass
class World:
    """虚拟世界 — 管理所有场所、智能体和时间推进。"""

    places: dict[str, Place] = field(default_factory=dict)
    agents: dict[str, "WorldAgent"] = field(default_factory=dict)
    time: GameTime = field(default_factory=GameTime)
    log: list[str] = field(default_factory=list)

    # ===== 构造 =====

    def add_place(self, place: Place) -> None:
        self.places[place.name] = place

    def add_agent(self, agent: "WorldAgent") -> None:
        self.agents[agent.name] = agent
        home = self.places.get("居民A区")
        if home:
            agent.home = home
            home.enter(agent)

    def get_place(self, name: str) -> Place | None:
        return self.places.get(name)

    def get_agent(self, name: str) -> "WorldAgent | None":
        return self.agents.get(name)

    # ===== 移动（Travel） =====

    def agent_move(self, agent_name: str, place_name: str) -> str:
        """智能体移动到指定场所 — 在路上消耗 tick。"""
        agent = self.agents.get(agent_name)
        place = self.places.get(place_name)
        if not agent:
            return f"错误: 智能体 {agent_name} 不存在。"
        if not place:
            return f"错误: 场所 {place_name} 不存在。"

        if agent.is_busy:
            return f"{agent_name} 正忙（{agent.busy_reason}），无法移动。"

        current = agent.location.name if agent.location else None
        if current == place_name:
            return f"{agent_name} 已经在 {place_name}。"

        # 检查场所开放时间
        if place_name == "银行" and not self.time.is_bank_open():
            return f"{agent_name} 无法进入银行: 银行只在{Phase.MORNING.label}和{Phase.AFTERNOON.label}开放。现在是{self.time.phase.label}。"
        if place_name == "酒馆" and not self.time.is_tavern_open():
            return f"{agent_name} 无法进入酒馆: 酒馆只在{Phase.AFTERNOON.label}和{Phase.EVENING.label}开放。现在是{self.time.phase.label}。"

        if current is None:
            # 已在路上 — 不允许
            return f"{agent_name} 正在路上，无法改变方向。"

        ticks = travel_ticks(current, place_name)
        if ticks is None:
            return f"错误: {current} 和 {place_name} 之间没有道路。"

        # 离开当前场所，开始上路
        agent.location.leave(agent)
        agent.start_travel(current, place_name, ticks)
        agent.memory.append(f"出发: {current} → {place_name} ({ticks} ticks)")
        return f"{agent_name} 离开了{current}，前往{place_name}（{ticks} ticks）"

    def _handle_arrival(self, agent: "WorldAgent") -> str:
        """智能体到达目的地。"""
        place = self.places.get(agent.travel_to)
        assert place, f"场所 {agent.travel_to} 不存在"
        agent.travelling = False
        agent.travel_from = ""
        agent.travel_to = ""
        agent.travel_total = 0
        agent.travel_elapsed = 0
        place.enter(agent)
        msg = f"{agent.name} 到达了{place.name}。"
        agent.memory.append(msg)
        return msg

    # ===== 工作 =====

    # 各场所工作的 tick 消耗
    WORK_TICKS = {
        "plant": 10,
        "harvest": 10,
        "bank": 5,
        "tavern_chat": 8,
    }

    def agent_start_work(self, agent_name: str, reason: str, ticks: int | None = None) -> str:
        """让智能体开始一项工作，忙指定 tick 数。"""
        agent = self.agents.get(agent_name)
        if not agent:
            return f"错误: 智能体 {agent_name} 不存在。"
        if agent.is_busy:
            return f"{agent_name} 正忙（{agent.busy_reason}），无法开始新工作。"
        t = ticks or self.WORK_TICKS.get(reason, 5)
        return agent.start_work(t, reason)

    # ===== 时间推进 =====

    def step(self) -> list[str]:
        """推进世界一个 tick。"""
        self.time.advance_inplace()
        events: list[str] = []

        if self.time.is_new_day:
            events.append(f"=== 第 {self.time.day} 天开始 ===")

        # 每个智能体生理更新
        for agent in self.agents.values():
            phys = agent.tick_physiology()
            if phys == "__arrived__":
                events.append(self._handle_arrival(agent))
            elif phys == "__released__":
                agent.confined = False
                events.append(f"{agent.name} 刑满释放了！")
            elif phys:
                events.append(phys)

        if self.time.is_day_end:
            events.extend(self._daily_tick())

        return events

    def _daily_tick(self) -> list[str]:
        events: list[str] = []
        farm: Farm = self.places.get("农场")  # type: ignore[assignment]
        if farm:
            farm.tick_crops()
        mall: Mall = self.places.get("商场")  # type: ignore[assignment]
        if mall:
            mall.reset_prices()
        cityhall: CityHall = self.places.get("市政厅")  # type: ignore[assignment]
        if cityhall:
            cityhall.daily_reset()
        events.extend(self._settle_interest())
        for agent in self.agents.values():
            agent.age += 1
            # 每日幸福度结算
            if agent.cash < 10:
                agent.happiness = max(0, agent.happiness - 5)
            elif agent.cash < 50:
                agent.happiness = max(0, agent.happiness - 2)
            if agent.hunger < 15:
                agent.happiness = max(0, agent.happiness - 3)
        return events

    def advance_to_phase(self, target_phase: Phase) -> list[str]:
        events: list[str] = []
        while self.time.phase != target_phase:
            events.extend(self.step())
        return events

    def advance_to_next_day(self) -> list[str]:
        events: list[str] = []
        target_day = self.time.day + 1
        while self.time.day < target_day:
            events.extend(self.step())
        return events

    # ===== 银行 =====

    def _settle_interest(self) -> list[str]:
        events: list[str] = []
        bank: Bank = self.places.get("银行")  # type: ignore[assignment]
        if not bank:
            return events
        for name, balance in list(bank._deposits.items()):
            interest = int(balance * bank.interest_rate)
            if interest > 0:
                bank._deposits[name] += interest
                events.append(f"[利息] {name} 存款利息 +{interest}。余额: {bank._deposits[name]}。")
        for name, loan in list(bank._loans.items()):
            interest = int(loan * bank.loan_interest_rate)
            if interest > 0:
                bank._loans[name] += interest
                events.append(f"[利息] {name} 贷款利息 +{interest}。贷款总额: {bank._loans[name]}。")
        return events

    # ===== 食物交易 =====

    FOOD_PRICE = 3

    def buy_food(self, agent_name: str, amount: int) -> str:
        agent = self.agents.get(agent_name)
        if not agent:
            return f"错误: 智能体 {agent_name} 不存在。"
        if agent.is_busy:
            return f"{agent_name} 正忙（{agent.busy_reason}），无法购买。"
        if amount <= 0:
            return f"无效的食物数量: {amount}。"
        cost = amount * self.FOOD_PRICE
        if agent.cash < cost:
            return f"{agent_name} 现金不足（有 {agent.cash}，需要 {cost}）。"
        agent.cash -= cost
        agent.food += amount
        return f"{agent_name} 购买了 {amount} 食物，花费 {cost} 金币。"

    # ===== 智能体经济 =====

    def agent_assets(self, agent_name: str) -> int:
        agent = self.agents.get(agent_name)
        if not agent:
            return 0
        bank: Bank = self.places.get("银行")  # type: ignore[assignment]
        deposit = bank.get_balance(agent_name) if bank else 0
        return agent.cash + deposit

    def agent_transfer(self, from_name: str, to_name: str, amount: int) -> str:
        sender = self.agents.get(from_name)
        receiver = self.agents.get(to_name)
        if not sender or not receiver:
            return f"错误: 智能体不存在。"
        if sender.is_busy:
            return f"{from_name} 正忙（{sender.busy_reason}），无法转账。"
        if sender.cash < amount:
            return f"{from_name} 现金不足（有 {sender.cash}，需要 {amount}）。"
        sender.cash -= amount
        receiver.cash += amount
        return f"{from_name} 转账 {amount} 金币给 {to_name}。"

    # ===== 描述 =====

    def describe(self) -> str:
        lines = [
            f"=== 虚拟世界 ({self.time.describe()}) ===",
            "",
            f"场所: {', '.join(self.places)}",
            f"智能体: {', '.join(self.agents)}",
            "",
        ]
        for place in self.places.values():
            lines.append(place.describe())
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def create_default() -> "World":
        world = World()
        world.add_place(Arena())
        world.add_place(Farm())
        world.add_place(Bank())
        world.add_place(Tavern())
        world.add_place(Residential(name="居民A区"))
        world.add_place(Mall())
        world.add_place(Park())
        world.add_place(Clinic())
        world.add_place(Restaurant())
        world.add_place(CityHall())
        world.add_place(Office())
        world.add_place(Court())
        world.add_place(Prison())
        world.add_place(Residential(name="居民B区", description=(
            "另一片安静的居民区，房屋风格与A区略有不同，透着灰蓝色的调子。"
            "智能体可以在这里休息，恢复体力。"
        )))
        world.add_place(Place(name="集市", description=(
            "热闹的露天集市。摊贩们在这里出售蔬菜水果、手工制品和各式杂货。"
            "智能体可以在这里买卖物品，用金币交换商品。"
        )))
        return world
