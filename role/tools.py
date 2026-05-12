"""LangChain 工具定义 —— 角色智能体可调用的函数。

新赌局玩法的工具集：
  - Bob 工具: get_overall_ranking, get_gladiator_record, get_head_to_head,
              get_gladiator_list, get_gladiator_form, view_player_squad_info
  - 玩家工具: talk_to_bob, bribe_bob, view_auction_item, auction_bid,
              view_my_squad, select_deployment
  - 反思工具: reflect_on_match (通用)
"""

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import tool

# 线程局部存储：每个线程独立记录当前玩家名
_thread_local = threading.local()


def set_thread_player(name: str):
    """设置当前线程的玩家名（线程安全）。"""
    _thread_local.player_name = name


def _get_thread_player() -> str:
    """获取当前线程的玩家名。"""
    return getattr(_thread_local, 'player_name', '')


# ── GameState ──────────────────────────────────────────────────────────────────

@dataclass
class GameState:
    """共享游戏状态，所有工具通过此对象读写。

    新玩法字段：
    - bob: Bob 实例
    - player_a: Gambler 实例（玩家A）
    - player_b: Gambler 实例（玩家B）
    - day_number: 当前天数 (1-3)
    - match_slot: 当前局次 (1-3)
    - current_bets: dict[int, float]  如 {1: 100, 2: 300, 3: 600}
    - auction: AuctionSession | None  当前拍卖会话
    - match_history: list[dict]  比赛历史
    - pending_bob_reply: dict[str, str] | None  Bob 待回复 {player_name: question}
    - pending_bob_bribe: dict | None  Bob 待回复的贿赂
    - current_player: str  当前执行工具调用的玩家名（用于无 player_name 参数的工具）
    """
    bob: Any = None
    player_a: Any = None       # Gambler 实例
    player_b: Any = None       # Gambler 实例
    day_number: int = 1
    match_slot: int = 1
    current_bets: dict = field(default_factory=lambda: {1: 100, 2: 300, 3: 600})
    auction: Any = None        # AuctionSession | None
    match_history: list[dict] = field(default_factory=list)
    pending_bob_reply: dict | None = None  # {"player_name": ..., "question": ...}
    pending_bob_bribe: dict | None = None  # {"player_name": ..., "amount": ..., "question": ...}
    current_player: str = ""   # 当前正在调用工具的玩家名


_state: GameState | None = None


def set_game_state(state: GameState):
    global _state
    _state = state


def get_game_state() -> GameState:
    if _state is None:
        raise RuntimeError("GameState 尚未初始化，请先调用 set_game_state()")
    return _state


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

_stats_cache: dict | None = None


def _load_stats_json() -> dict:
    """加载角斗士战绩 JSON 数据（带缓存）。"""
    global _stats_cache
    if _stats_cache is not None:
        return _stats_cache
    stats_file = os.path.join(
        os.path.dirname(__file__),
        "data", "Bob", "tournament_stats.json"
    )
    if not os.path.exists(stats_file):
        raise FileNotFoundError(f"战绩数据文件不存在: {stats_file}")
    with open(stats_file, "r", encoding="utf-8") as f:
        _stats_cache = json.load(f)
    return _stats_cache


def _find_gladiator(char_id: str) -> dict | None:
    """在 rankings 中查找角斗士。"""
    stats = _load_stats_json()
    for g in stats["rankings"]:
        if g["char_id"] == char_id:
            return g
    return None


def _format_auction_owner(player_name: str, owner: list[dict]) -> str:
    """临时展示拍卖中已拍到的角斗士（squad 尚未构建时使用）。"""
    if not owner:
        return f"{player_name} 尚未获得角斗士阵容。请先完成拍卖。"
    lines = [f"【{player_name} 的角斗士阵容（拍卖进行中）】"]
    for i, entry in enumerate(owner):
        lines.append(
            f"  {i+1}. {entry['name']} (char_id: {entry['char_id']}) "
            f"point: {entry.get('point', 0)}"
        )
    lines.append(f"  已获得: {len(owner)}/3 个角斗士")
    return "\n".join(lines)


def _get_player(player_name: str) -> Any:
    """根据玩家名获取玩家对象。"""
    state = get_game_state()
    name = player_name.strip()
    if state.player_a and state.player_a.player_name == name:
        return state.player_a
    if state.player_b and state.player_b.player_name == name:
        return state.player_b
    raise ValueError(f"未知玩家: {name}")


# ══════════════════════════════════════════════════════════════════════════════════
# Bob 工具
# ══════════════════════════════════════════════════════════════════════════════════

@tool
def get_overall_ranking() -> str:
    """查看全部角斗士的胜率排名总表。返回所有角斗士按胜率从高到低的排名。
    当需要了解整体实力格局、谁强谁弱时调用此工具。"""
    try:
        stats = _load_stats_json()
    except FileNotFoundError as e:
        return f"（{e}）"
    lines = ["【角斗士总排名（按胜率从高到低）】"]
    for g in stats["rankings"]:
        pct = f"{g['win_rate']*100:.1f}%"
        lines.append(
            f"  {g['rank']}. {g['name']} ({g['char_id']}): "
            f"{g['wins']}胜/{g['total']}场, 胜率{pct}"
        )
    return "\n".join(lines)


@tool
def get_gladiator_record(char_id: str = "") -> str:
    """查看某个角斗士对所有对手的详细对战记录。返回该角斗士作为攻击方时，
    对阵每个对手的胜场数和胜率。
    当需要深入了解某个角斗士的具体对局表现时调用此工具。

    Args:
        char_id: 角斗士的英文ID，如 snowman、thor、poison 等
    """
    if not char_id:
        return "错误：请提供角斗士的 char_id（英文ID）。"
    try:
        stats = _load_stats_json()
    except FileNotFoundError as e:
        return f"（{e}）"

    gladiator = _find_gladiator(char_id)
    if gladiator is None:
        ids = [g["char_id"] for g in stats["rankings"]]
        return f"错误：找不到角斗士 '{char_id}'。可选: {', '.join(ids)}"

    matchups = stats["matchups"].get(char_id, {})
    pct = f"{gladiator['win_rate']*100:.1f}%"
    lines = [
        f"【{gladiator['name']} ({char_id}) 对战记录】",
        f"排名: 第{gladiator['rank']}名 | 总胜率: {pct} ({gladiator['wins']}/{gladiator['total']})",
    ]
    sorted_matchups = sorted(matchups.items(), key=lambda x: -x[1]["win_rate"])
    for opp_id, m in sorted_matchups:
        opp = _find_gladiator(opp_id)
        opp_name = opp["name"] if opp else opp_id
        rate_pct = f"{m['win_rate']*100:.0f}%"
        lines.append(f"  对{opp_name}: {m['wins']}胜 {rate_pct}")
    return "\n".join(lines)


@tool
def get_head_to_head(char_id_a: str = "", char_id_b: str = "") -> str:
    """查看两个特定角斗士之间的历史对战数据。返回 A打B 和 B打A 的双向胜率。
    当需要比较两个角斗士的对战优劣势时调用此工具。

    Args:
        char_id_a: 第一个角斗士的英文ID
        char_id_b: 第二个角斗士的英文ID
    """
    if not char_id_a or not char_id_b:
        return "错误：请同时提供两个角斗士的 char_id。"
    if char_id_a == char_id_b:
        return "错误：两个角斗士 ID 相同，请提供不同的角斗士。"
    try:
        stats = _load_stats_json()
    except FileNotFoundError as e:
        return f"（{e}）"

    glad_a = _find_gladiator(char_id_a)
    glad_b = _find_gladiator(char_id_b)
    if glad_a is None:
        ids = [g["char_id"] for g in stats["rankings"]]
        return f"错误：找不到角斗士 '{char_id_a}'。可选: {', '.join(ids)}"
    if glad_b is None:
        ids = [g["char_id"] for g in stats["rankings"]]
        return f"错误：找不到角斗士 '{char_id_b}'。可选: {', '.join(ids)}"

    a_vs_b = stats["matchups"].get(char_id_a, {}).get(char_id_b)
    b_vs_a = stats["matchups"].get(char_id_b, {}).get(char_id_a)

    lines = [f"【{glad_a['name']} vs {glad_b['name']}】"]
    if a_vs_b:
        lines.append(
            f"  {glad_a['name']}(攻击方) 对 {glad_b['name']}: "
            f"{a_vs_b['wins']}胜 {a_vs_b['win_rate']*100:.0f}%"
        )
    else:
        lines.append(f"  {glad_a['name']} 对 {glad_b['name']}: 无数据")
    if b_vs_a:
        lines.append(
            f"  {glad_b['name']}(攻击方) 对 {glad_a['name']}: "
            f"{b_vs_a['wins']}胜 {b_vs_a['win_rate']*100:.0f}%"
        )
    else:
        lines.append(f"  {glad_b['name']} 对 {glad_a['name']}: 无数据")
    return "\n".join(lines)


@tool
def get_gladiator_list() -> str:
    """查看竞技场内所有角斗士的名称和战斗描述。
    当需要了解有哪些角斗士可供选择时调用此工具。"""
    name_list_file = os.path.join(
        os.path.dirname(__file__),
        "data", "Public", "gladiators_stats", "name_list.md"
    )
    if not os.path.exists(name_list_file):
        return "（暂无角斗士名录）"
    with open(name_list_file, "r", encoding="utf-8") as f:
        return f.read()


# ── Bob 新工具 ─────────────────────────────────────────────────────────────────

@tool
def get_gladiator_form(char_id: str = "") -> str:
    """查看某个角斗士当前的疲劳状态（是否被玩家拥有、疲劳天数、HP 缩放）。
    只对已分配给玩家的角斗士有效——未分配的角斗士没有疲劳信息。

    Args:
        char_id: 角斗士的英文ID
    """
    if not char_id:
        return "错误：请提供角斗士的 char_id。"

    state = get_game_state()
    # 遍历两个玩家的阵容
    found = []
    for player in [state.player_a, state.player_b]:
        if player is None or player.squad is None:
            continue
        for m in player.squad.members:
            if m.char_id == char_id:
                hp = player.squad.get_hp_multiplier(char_id)
                can_use = player.squad.can_use_today(char_id)
                found.append(
                    f"  {player.player_name} 拥有 | "
                    f"疲劳天数: {m.fatigue_days} | "
                    f"HP 缩放: {hp*100:.0f}% | "
                    f"今日{'可用' if can_use else '已出战'}"
                )
    if found:
        return "\n".join(["【角斗士疲劳状态】"] + found)
    return f"角斗士 '{char_id}' 未被任何玩家拥有，或不在任何阵容中。"


@tool
def view_player_squad_info(player_name: str = "") -> str:
    """查看某玩家已公开拥有的角斗士名单（不含疲劳细节，不含 HP 信息）。
    这是公开信息——所有人理论上都可以知道谁拥有哪些角斗士。

    Args:
        player_name: 玩家名（如"玩家A"、"玩家B"）
    """
    if not player_name:
        return "错误：请提供玩家名。"

    try:
        player = _get_player(player_name)
    except ValueError:
        return f"错误：找不到玩家 '{player_name}'。"

    if player.squad is None:
        return f"{player_name} 尚未获得角斗士阵容。"

    members = player.squad.members
    lines = [f"【{player_name} 的角斗士阵容】"]
    for i, m in enumerate(members):
        used = " (今日已出战)" if m.char_id in player.squad.used_today else ""
        lines.append(f"  {i+1}. {m.name} (char_id: {m.char_id}){used}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════════
# 玩家工具
# ══════════════════════════════════════════════════════════════════════════════════

@tool
def talk_to_bob(player_name: str = "", question: str = "") -> str:
    """当你想了解角斗士的更多信息时，比如某个角斗士的总体胜率，
    对上其他角斗士的胜率等等，调用此工具向 Bob 提问。

    Args:
        player_name: 你的玩家名（如"玩家A"）
        question: 你想问 Bob 的问题
    """
    if not player_name or not question:
        return "错误：请同时提供 player_name 和 question。"
    state = get_game_state()
    state.pending_bob_reply = {
        "player_name": player_name,
        "question": question,
        "paid": False,
    }
    return (
        f"（你的问题已发送给 Bob: \"{question}\"）\n"
        f"（等待 Bob 回复...）"
    )


@tool
def bribe_bob(player_name: str = "", amount: int = 0, question: str = "") -> str:
    """当你想付费向 Bob 提问角斗士的信息时。调用此工具，
    花销会从你的资产中扣除 amount 万，转入 Bob 的收入。

    Args:
        player_name: 你的玩家名（如"玩家A"）
        amount: 支付金额（万），必须 > 0
        question: 你想问 Bob 的问题
    """
    if not player_name or not question:
        return "错误：请同时提供 player_name、amount 和 question。"
    if amount <= 0:
        return "错误：贿赂金额必须大于 0 万。"
    state = get_game_state()
    try:
        player = _get_player(player_name)
    except ValueError as e:
        return f"错误：{e}"

    if not player.spend(amount):
        return f"错误：你的资产不足。当前资产: {player.assets:.0f} 万，需要 {amount} 万。"

    state.bob.earn(amount)
    state.bob.arena_revenue += amount

    state.pending_bob_reply = {
        "player_name": player_name,
        "question": question,
        "paid": True,
        "amount": amount,
    }
    return (
        f"（已支付 {amount} 万给 Bob，你的问题: \"{question}\"）\n"
        f"（等待 Bob 回复...）"
    )


@tool
def view_auction_item() -> str:
    """查看当前正在拍卖的角斗士。仅展示名字和 char_id，不展示胜率或强弱信息。
    在拍卖阶段，每次有新的角斗士展示时使用此工具了解拍品。"""
    state = get_game_state()
    if state.auction is None:
        return "（当前没有正在进行的拍卖）"
    if state.auction.current_char is None:
        return "（当前没有正在展示的角斗士，拍卖可能已结束或尚未开始）"
    c = state.auction.current_char
    lines = [
        "【当前拍卖角斗士】",
        f"  名称: {c['name']}",
        f"  char_id: {c['char_id']}",
    ]
    if state.auction.current_bid > 0:
        lines.append(f"  当前最高出价: {state.auction.current_bid} 万 ({state.auction.highest_bidder})")
    else:
        lines.append("  当前出价: 暂无")
    lines.append(f"  拍卖状态: {state.auction.state}")
    return "\n".join(lines)


@tool
def auction_bid(amount: int = -1) -> str:
    """对当前拍卖的角斗士叫价（使用游戏币）。amount=0 表示弃权/跳过。

    Args:
        amount: 出价金额（游戏币），必须 >= 0。0 = 弃权
    """
    if amount < 0:
        return "错误：出价不能为负数（0 表示弃权）。"

    state = get_game_state()
    if state.auction is None:
        return "（当前没有正在进行的拍卖）"

    player_name = _get_thread_player()
    if not player_name:
        return "错误：无法确定当前玩家身份。"

    try:
        player = _get_player(player_name)
    except ValueError as e:
        return f"错误：{e}"

    # 用游戏币检查余额
    if amount > 0 and not player.can_afford_chips(amount):
        return f"错误：你的游戏币不足。当前游戏币: {player.chips}，出价 {amount} 游戏币。"

    # 检查该玩家是否已经拥有 3 个角斗士
    owner_list = state.auction.owner_a if player_name == state.auction.player_a_name else state.auction.owner_b
    if len(owner_list) >= 3:
        return "错误：你已经拥有 3 个角斗士，不能继续竞拍。"

    # 暗标模式：只记录 pending_bid，不立即扣钱。外部比较后统一处理。
    player.pending_bid = amount
    return (
        f"你的暗标出价: {amount} 游戏币"
        + (" (弃权)" if amount == 0 else "")
        + f"\n当前角斗士: {state.auction.current_char['name'] if state.auction.current_char else '?'}"
        + "\n等待双方出价完成..."
    )


def _finalize_auction(state: GameState):
    """拍卖结束后，为双方构建阵容。对系统补填的角斗士扣游戏币。"""
    if state.player_a and state.auction.owner_a:
        _charge_auto_assign(state.player_a, state.auction.owner_a, state.bob)
        state.player_a.build_squad(state.auction.owner_a)
    if state.player_b and state.auction.owner_b:
        _charge_auto_assign(state.player_b, state.auction.owner_b, state.bob)
        state.player_b.build_squad(state.auction.owner_b)


def _charge_auto_assign(player, owner_list: list[dict], bob):
    """对自动分配的角斗士（auto_filled 标记）按 point 扣游戏币。"""
    for entry in owner_list:
        if entry.get("auto_filled"):
            amount = entry.get("point", 0)
            if amount > 0 and player.spend_chips(amount):
                if bob is not None:
                    bob.arena_chips += amount


@tool
def view_my_squad(player_name: str = "") -> str:
    """查看你的角斗士阵容和疲劳状态。包括每个角斗士当前的 HP 缩放比例、
    今天是否已出战、连续出战天数等详细信息。

    Args:
        player_name: 你的名字
    """
    if not player_name:
        return "错误：请提供 player_name。"
    try:
        player = _get_player(player_name)
    except ValueError as e:
        return f"错误：{e}"

    if player.squad is None:
        state = get_game_state()
        # 拍卖进行中：从 auction 数据中临时展示已拍到的角斗士
        if state.auction and state.auction.is_running:
            if player_name == state.auction.player_a_name:
                owner = state.auction.owner_a
            elif player_name == state.auction.player_b_name:
                owner = state.auction.owner_b
            else:
                owner = None
            if owner:
                return _format_auction_owner(player_name, owner)
        return "你尚未获得角斗士阵容。请先完成拍卖。"

    return player.squad.summary()


@tool
def deploy_first_match(player_name: str = "", char_id: str = "") -> str:
    """选择第1局出战的角斗士。每天首局胜方可获对方point×50%的游戏币奖励。

    Args:
        player_name: 你的名字
        char_id: 要出战的角斗士 char_id
    """
    return _do_deploy(player_name, char_id, 1)


@tool
def deploy_remaining_matches(player_name: str = "",
                               first_char_id: str = "",
                               second_char_id: str = "") -> str:
    """选择第2局和第3局出战的角斗士。first_char_id 为第2局出战，second_char_id 为第3局出战。
    两个角斗士必须是阵容中不同的角斗士（同一天不能重复）。

    Args:
        player_name: 你的名字
        first_char_id: 第2局出战的角斗士 char_id
        second_char_id: 第3局出战的角斗士 char_id
    """
    if not player_name or not first_char_id or not second_char_id:
        return "错误：请同时提供 player_name、first_char_id 和 second_char_id。"
    if first_char_id == second_char_id:
        return "错误：第2局和第3局不能使用同一个角斗士。"

    result1 = _do_deploy(player_name, first_char_id, 2)
    result2 = _do_deploy(player_name, second_char_id, 3)
    return f"第2局: {result1}\n第3局: {result2}"


def _do_deploy(player_name: str, char_id: str, match_slot: int) -> str:
    """内部部署逻辑，检查合法性并写入 deployments。"""
    state = get_game_state()
    try:
        player = _get_player(player_name)
    except ValueError as e:
        return f"错误：{e}"

    if player.squad is None:
        return "错误：你尚未获得角斗士阵容。"

    # 检查角斗士是否在阵容中（支持 char_id 或 名字匹配）
    member = player.squad._find(char_id)
    if member is None:
        # 尝试按名字模糊匹配
        for m in player.squad.members:
            if m.name == char_id or char_id in m.name:
                member = m
                char_id = m.char_id
                break
    if member is None:
        ids = [f"{m.char_id}({m.name})" for m in player.squad.members]
        return f"错误：角斗士 '{char_id}' 不在你的阵容中。你的角斗士: {', '.join(ids)}"

    # 检查该 slot 是否已经部署
    if match_slot in player.deployments:
        old = player.deployments[match_slot]
        return f"错误：第 {match_slot} 局已经部署了 {old}。如需修改，请联系系统。"

    # 检查同一天是否已用该角斗士（通过 used_today）
    if char_id in player.squad.used_today:
        return f"错误：角斗士 '{char_id}' 今天已经出战过了。"

    # 检查是否在其他 slot 部署了同一角斗士
    for slot, cid in player.deployments.items():
        if cid == char_id:
            return f"错误：角斗士 '{char_id}' 已部署在第 {slot} 局。同一天不能重复使用同一角斗士。"

    player.deployments[match_slot] = char_id
    hp_mult = player.squad.get_hp_multiplier(char_id)
    point = member.point if member else 0

    first_bonus_hint = ""
    if match_slot == 1:
        first_bonus_hint = " | 首局胜方可获对方point×50%游戏币"

    return (
        f"已部署 {member.name} ({char_id}) 到第 {match_slot} 局。\n"
        f"角斗士 HP: {hp_mult*100:.0f}% | point: {point}{first_bonus_hint}"
    )


# 保留旧工具兼容，但不再暴露给玩家
@tool
def select_deployment(player_name: str = "", char_id: str = "", match_slot: int = 0) -> str:
    """[已废弃] 选择第 match_slot 局（1/2/3）出战的角斗士。请改用 deploy_first_match 或 deploy_remaining_matches。

    Args:
        player_name: 你的名字
        char_id: 要出战的角斗士 char_id
        match_slot: 局次（1/2/3）
    """
    if not player_name or not char_id:
        return "错误：请同时提供 player_name 和 char_id。"
    if match_slot not in (1, 2, 3):
        return "错误：match_slot 必须是 1、2 或 3。"
    return _do_deploy(player_name, char_id, match_slot)

