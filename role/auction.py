"""拍卖系统：随机展示角斗士、管理叫价、归属判定。"""

import random
from dataclasses import dataclass, field

STARTING_PRICE = 50    # 起拍价（游戏币）
AUTO_FILL_PRICE = 85   # 系统补填价（一方满后，随机补角斗士给另一方）
MAX_BID_CAP = 150       # 一口价上限


@dataclass
class AuctionSession:
    """一次拍卖会话（每天一轮），管理 9 个角斗士的竞拍流程。

    流程：
      show() → 展示角斗士（仅 char_id + 名称）
      bid(player, amount) → 叫价（amount=0 弃权）
      另一方回应 → bid 或 pass
      确定归属 → next()
      直到双方各 3 个 或 展示完 9 个
      自动补分配（从剩余角斗士随机给，按 75 币扣除）
    """

    # 所有 20 个角斗士的 char_id 列表（用于随机抽取 9 个）
    all_gladiators: list[dict]  # [{"char_id": ..., "name": ...}, ...]
    player_a_name: str = "玩家A"
    player_b_name: str = "玩家B"

    # ── 运行时状态 ──
    pool: list[dict] = field(default_factory=list)    # 从 all 中随机抽的 9 个
    shown_index: int = 0                                # 当前展示到第几个
    current_char: dict | None = None                    # 当前拍卖的角斗士
    current_bid: int = 0                                # 当前最高出价
    highest_bidder: str = ""                            # 当前最高出价者 player_name
    state: str = "init"                                 # init|showing|filling|end
    owner_a: list[dict] = field(default_factory=list)   # Player A 已获得 [{"char_id":, "name":, "point":}]
    owner_b: list[dict] = field(default_factory=list)   # Player B 已获得

    def __post_init__(self):
        if len(self.all_gladiators) < 6:
            raise ValueError(f"至少需要 6 个角斗士进行拍卖，当前仅 {len(self.all_gladiators)}")
        available = self.all_gladiators.copy()
        random.shuffle(available)
        self.pool = available[:9]
        self.shown_index = 0
        self.bid_history: list[dict] = []  # 每轮暗标结果记录

    # ── 拍卖流程 ──────────────────────────────────────────────────────────

    def show(self) -> str | None:
        """展示当前角斗士。返回描述文本，如果拍卖结束返回 None。"""
        if len(self.owner_a) >= 3 and len(self.owner_b) >= 3:
            self.state = "end"
            return None

        if self.shown_index >= len(self.pool):
            self.state = "end"
            return None

        # 如果一方已满 3 个，系统随机补角斗士给另一方（point=75）
        if len(self.owner_a) >= 3:
            self._fill_to_three(self.owner_b, self.owner_a)
            self.shown_index = len(self.pool)
            self.state = "end"
            names = ", ".join(f"{c['name']} ({c['char_id']})" for c in self.owner_b)
            return (f"{self.player_a_name} 已满 3 个角斗士。\n"
                    f"系统随机分配 {len(self.owner_b)} 个给 {self.player_b_name}（各 {AUTO_FILL_PRICE} 币）: {names}")

        if len(self.owner_b) >= 3:
            self._fill_to_three(self.owner_a, self.owner_b)
            self.shown_index = len(self.pool)
            self.state = "end"
            names = ", ".join(f"{c['name']} ({c['char_id']})" for c in self.owner_a)
            return (f"{self.player_b_name} 已满 3 个角斗士。\n"
                    f"系统随机分配 {len(self.owner_a)} 个给 {self.player_a_name}（各 {AUTO_FILL_PRICE} 币）: {names}")

        self.current_char = self.pool[self.shown_index]
        self.current_bid = 0
        self.highest_bidder = ""
        self.state = "showing"

        return (
            f"【当前拍卖角斗士】\n"
            f"  名称: {self.current_char['name']}\n"
            f"  char_id: {self.current_char['char_id']}\n"
            f"  起拍价: {STARTING_PRICE} 游戏币\n\n"
            f"请给出你的出价（调用 auction_bid），输入 0 表示弃权。"
        )

    def _assign_to(self, player_name: str, point: int = 0):
        """将当前角斗士分配给指定玩家，设置 point。"""
        if self.current_char is None:
            return
        entry = {
            "char_id": self.current_char["char_id"],
            "name": self.current_char["name"],
            "point": point,
        }
        if player_name == self.player_a_name:
            self.owner_a.append(entry)
        else:
            self.owner_b.append(entry)

    def _fill_to_three(self, target: list[dict], filled: list[dict]):
        """将 target 补到 3 个角斗士。仅从拍卖池 9 人中随机选未认领的。"""
        needed = 3 - len(target)
        if needed <= 0:
            return
        owned_ids = {c['char_id'] for c in target + filled}
        candidates = [c for c in self.pool if c['char_id'] not in owned_ids]
        random.shuffle(candidates)
        for c in candidates[:needed]:
            c["point"] = AUTO_FILL_PRICE
            c["auto_filled"] = True
            target.append(c)

    def _auto_assign_remaining(self) -> str:
        """自动补分配：将双方补到各 3 个角斗士（按系统补填价）。"""
        a_before = len(self.owner_a)
        b_before = len(self.owner_b)
        self._fill_to_three(self.owner_a, self.owner_b)
        self._fill_to_three(self.owner_b, self.owner_a)
        a_added = len(self.owner_a) - a_before
        b_added = len(self.owner_b) - b_before
        if a_added or b_added:
            parts = []
            if a_added:
                parts.append(f"{self.player_a_name} +{a_added} 个")
            if b_added:
                parts.append(f"{self.player_b_name} +{b_added} 个")
            return f"自动补分配（按 {AUTO_FILL_PRICE} 游戏币/个）：{', '.join(parts)}"
        return ""

    # ── 暗标出价 ──────────────────────────────────────────────────────────

    def sealed_bid_round(self, bid_a: int, bid_b: int,
                          player_a_name: str, player_b_name: str,
                          round_num: int = 0) -> dict:
        """暗标一轮：接收两个玩家的出价，比较并判定归属。

        出价验证：>150 拒绝，非零且<50 拒绝。

        Returns:
            {"result": "win"|"tie"|"skip", "winner": ..., "amount": ..., "msg": ...}
        """
        if self.current_char is None:
            return {"result": "skip", "winner": None, "amount": 0,
                    "msg": "（当前没有正在拍卖的角斗士）"}

        char_name = self.current_char["name"]
        char_id = self.current_char["char_id"]

        # 出价验证
        for bid, name in [(bid_a, player_a_name), (bid_b, player_b_name)]:
            if bid > MAX_BID_CAP:
                self._record_bid(round_num, char_id, char_name, bid_a, bid_b,
                                 player_a_name, player_b_name, "skip", None, 0)
                return {"result": "skip", "winner": None, "amount": 0,
                        "msg": f"错误：{name} 出价 {bid} 超过一口价上限 {MAX_BID_CAP}。"}
            if bid != 0 and bid < STARTING_PRICE:
                self._record_bid(round_num, char_id, char_name, bid_a, bid_b,
                                 player_a_name, player_b_name, "skip", None, 0)
                return {"result": "skip", "winner": None, "amount": 0,
                        "msg": f"错误：{name} 出价 {bid} 低于起拍价 {STARTING_PRICE}。出价必须为 0（弃权）或 ≥{STARTING_PRICE}。"}

        # 双方都弃权 → 跳过该角斗士
        if bid_a == 0 and bid_b == 0:
            self._advance_to_next()
            msg = f"双方均弃权，{char_name} 回池，跳过。"
            self._record_bid(round_num, char_id, char_name, bid_a, bid_b,
                             player_a_name, player_b_name, "skip", None, 0)
            return {"result": "skip", "winner": None, "amount": 0, "msg": msg}

        # 一人弃权 → 另一人获得
        if bid_a == 0:
            self._assign_to(player_b_name, point=bid_b)
            self._advance_to_next()
            self._record_bid(round_num, char_id, char_name, bid_a, bid_b,
                             player_a_name, player_b_name, "win", player_b_name, bid_b)
            return {"result": "win", "winner": player_b_name, "amount": bid_b,
                    "msg": f"{player_a_name} 弃权，{char_name} 以 {bid_b} 游戏币归 {player_b_name} 所有。"}

        if bid_b == 0:
            self._assign_to(player_a_name, point=bid_a)
            self._advance_to_next()
            self._record_bid(round_num, char_id, char_name, bid_a, bid_b,
                             player_a_name, player_b_name, "win", player_a_name, bid_a)
            return {"result": "win", "winner": player_a_name, "amount": bid_a,
                    "msg": f"{player_b_name} 弃权，{char_name} 以 {bid_a} 游戏币归 {player_a_name} 所有。"}

        # 出价不同 → 高者得
        if bid_a > bid_b:
            self._assign_to(player_a_name, point=bid_a)
            self._advance_to_next()
            self._record_bid(round_num, char_id, char_name, bid_a, bid_b,
                             player_a_name, player_b_name, "win", player_a_name, bid_a)
            return {"result": "win", "winner": player_a_name, "amount": bid_a,
                    "msg": f"{char_name} 以 {bid_a} 游戏币归 {player_a_name} 所有（{player_b_name} 出价 {bid_b}）。"}
        elif bid_b > bid_a:
            self._assign_to(player_b_name, point=bid_b)
            self._advance_to_next()
            self._record_bid(round_num, char_id, char_name, bid_a, bid_b,
                             player_a_name, player_b_name, "win", player_b_name, bid_b)
            return {"result": "win", "winner": player_b_name, "amount": bid_b,
                    "msg": f"{char_name} 以 {bid_b} 游戏币归 {player_b_name} 所有（{player_a_name} 出价 {bid_a}）。"}

        # 出价相同 → 平局，触发重拍（不记录，等待最终结果）
        return {"result": "tie", "winner": None, "amount": bid_a,
                "msg": f"双方出价相同 ({bid_a} 游戏币)，需要重新出价。"}

    def _record_bid(self, round_num: int, char_id: str, char_name: str,
                    bid_a: int, bid_b: int, player_a_name: str, player_b_name: str,
                    result: str, winner: str | None, amount: int):
        """记录一轮暗标结果到 bid_history。"""
        self.bid_history.append({
            "round_num": round_num,
            "char_id": char_id,
            "char_name": char_name,
            "bids": {player_a_name: bid_a, player_b_name: bid_b},
            "winner": winner,
            "result": result,
            "amount": amount,
        })

    def _advance_to_next(self):
        """前进到下一个角斗士。"""
        self.shown_index += 1
        self.current_char = None
        self.current_bid = 0

    # ── 查询 ──────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self.state not in ("end",)

    def summary(self) -> str:
        """返回拍卖摘要。"""
        lines = [f"【拍卖状态】（{self.state}）"]
        lines.append(f"  拍卖池: {len(self.pool)} 个角斗士, 已展示 {self.shown_index} 个")
        if self.current_char:
            lines.append(f"  当前: {self.current_char['name']} ({self.current_char['char_id']})")
            if self.current_bid > 0:
                lines.append(f"  最高出价: {self.current_bid} 游戏币 ({self.highest_bidder})")
        lines.append(f"  {self.player_a_name}: {[(c['name'], c.get('point', 0)) for c in self.owner_a]}")
        lines.append(f"  {self.player_b_name}: {[(c['name'], c.get('point', 0)) for c in self.owner_b]}")
        return "\n".join(lines)
