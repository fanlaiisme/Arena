"""人类玩家赌局主持工具。

提供角斗士管理、暗标拍卖、比赛运行、游戏币管理等功能。
所有函数直接打印终端输出供主持者和玩家阅读。
"""

import json
import random
import sys
from pathlib import Path

# 确保能导入 Arena 根目录和 role 模块
_ARENA_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ARENA_ROOT) not in sys.path:
    sys.path.insert(0, str(_ARENA_ROOT))

from characters import CHARACTERS

_DATA_DIR = Path(__file__).resolve().parent
_GLADIATORS_PATH = _DATA_DIR / "gladiators.json"
_GAME_STATE_PATH = _DATA_DIR / "game_state.json"

AUTO_FILL_PRICE = 85

_PREVIEW_COUNTS = {1: 5, 2: 4, 3: 3}

# ── 模块级拍卖状态 ────────────────────────────────────────────────────────

_auction_state = {
    "pool": [],
    "pool_index": 0,
    "current": None,
    "owner_a": [],
    "owner_b": [],
    "tie_count": 0,
    "player_a_name": "玩家A",
    "player_b_name": "玩家B",
    "active": False,
    "game_over": False,
    "daily_wins": {"player_a": 0, "player_b": 0},
}


def reset_auction():
    """重置拍卖状态。"""
    _auction_state["pool"] = []
    _auction_state["pool_index"] = 0
    _auction_state["current"] = None
    _auction_state["owner_a"] = []
    _auction_state["owner_b"] = []
    _auction_state["tie_count"] = 0
    _auction_state["active"] = False
    _auction_state["game_over"] = False
    _auction_state["daily_wins"] = {"player_a": 0, "player_b": 0}


def get_auction_state():
    """返回当前拍卖状态的副本。"""
    return {
        "pool": _auction_state["pool"][:],
        "pool_index": _auction_state["pool_index"],
        "current": dict(_auction_state["current"]) if _auction_state["current"] else None,
        "owner_a": [dict(o) for o in _auction_state["owner_a"]],
        "owner_b": [dict(o) for o in _auction_state["owner_b"]],
        "tie_count": _auction_state["tie_count"],
        "player_a_name": _auction_state["player_a_name"],
        "player_b_name": _auction_state["player_b_name"],
        "active": _auction_state["active"],
    }


# ── 角斗士数据管理 ────────────────────────────────────────────────────────

def load_gladiators():
    """读取 gladiators.json，返回列表。"""
    with open(_GLADIATORS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_gladiators(data):
    """写回 gladiators.json。

    Args:
        data: 角斗士列表
    """
    with open(_GLADIATORS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def query_gladiator(index):
    """按 index (1-20) 查询角斗士信息并打印。

    Args:
        index: 角斗士编号 (1-20)

    Returns:
        角斗士 dict，未找到返回 None
    """
    gladiators = load_gladiators()
    g = next((g for g in gladiators if g["index"] == index), None)
    if g is None:
        print(f"未找到 index={index} 的角斗士")
        return None
    print(f"【角斗士 #{g['index']}】")
    print(f"  名称: {g['name']}")
    print(f"  char_id: {g['char_id']}")
    print(f"  胜率: {g['win_rate']:.1%}  ({g['total_matches']} 场, 平 {g['ties']} 场)")
    print(f"  疲劳: {g['fatigue']:.0%}  HP")
    return g


def update_gladiator(index, **fields):
    """更新指定角斗士的字段（如 fatigue），写回 JSON 并打印。

    Args:
        index: 角斗士编号 (1-20)
        **fields: 要更新的字段键值对（如 fatigue=0.8）

    Returns:
        更新后的角斗士 dict，未找到返回 None
    """
    gladiators = load_gladiators()
    g = next((g for g in gladiators if g["index"] == index), None)
    if g is None:
        print(f"未找到 index={index} 的角斗士")
        return None
    for key, value in fields.items():
        if key in g:
            g[key] = value
        else:
            print(f"警告: 未知字段 '{key}'，已忽略")
    save_gladiators(gladiators)
    print(f"已更新 #{index} {g['name']}: {fields}")
    return g


# ── 角斗士胜率总览 ────────────────────────────────────────────────────────

def show_all_gladiators():
    """展示全部 20 名角斗士的名称和胜率排名（从高到低），提示排序不反映拍卖顺序。"""
    gladiators = load_gladiators()
    by_rate = sorted(gladiators, key=lambda g: g["win_rate"], reverse=True)

    print(f"\n{'='*60}")
    print(f"【角斗士胜率总览（共 20 名）】")
    print(f"  注意：以下胜率排名仅供策略参考，角斗士实际拍卖顺序随机排列，与胜率无关。")
    print(f"  暗标拍卖时角斗士亦不显示胜率，需凭经验判断。")
    print(f"{'排名':<6}{'名称':<12}{'char_id':<18}{'胜场':<8}{'总场':<8}{'平局':<8}{'胜率':<10}")
    print("-" * 60)
    for rank, g in enumerate(by_rate, 1):
        wins = int(g["win_rate"] * g["total_matches"])
        print(f"  {rank:<4}  {g['name']:<10}  {g['char_id']:<16}  "
              f"{wins:<6}  {g['total_matches']:<6}  {g['ties']:<6}  {g['win_rate']:.1%}")
    print(f"{'='*60}\n")


# ── 每日情报预览 ──────────────────────────────────────────────────────────

def generate_daily_preview(player_name, shown_set, count=5):
    """从 20 名角斗士中随机抽 count 个未展示过的，打印胜率情报。

    Args:
        player_name: 玩家名称（用于打印标题）
        shown_set: 已展示过的角斗士 index 集合
        count: 本次展示数量

    Returns:
        更新后的 shown_set（包含本次展示的 index）
    """
    gladiators = load_gladiators()
    candidates = [g for g in gladiators if g["index"] not in shown_set]

    if len(candidates) < count:
        count = len(candidates)
    if count == 0:
        print(f"【{player_name} 情报】所有角斗士已展示完毕。")
        return shown_set

    picked = random.sample(candidates, count)
    picked.sort(key=lambda g: g["win_rate"], reverse=True)

    print(f"\n{'='*60}")
    print(f"【{player_name} 角斗士情报】")
    print(f"{'序号':<6}{'名称':<12}{'char_id':<18}{'胜场':<8}{'总场':<8}{'平局':<8}{'胜率':<10}")
    print("-" * 60)
    for g in picked:
        wins = int(g['win_rate'] * g['total_matches'])
        print(f"  {g['index']:<4}  {g['name']:<10}  {g['char_id']:<16}  "
              f"{wins:<6}  {g['total_matches']:<6}  {g['ties']:<6}  {g['win_rate']:.1%}")
    print(f"{'='*60}\n")

    new_shown = shown_set | {g["index"] for g in picked}
    return new_shown


# ── 拍卖 ──────────────────────────────────────────────────────────────────

def generate_auction_pool(count=9):
    """从 20 名角斗士中随机抽 count 个进入拍卖池，打印列表并初始化拍卖状态。

    Args:
        count: 拍卖池角斗士数量，默认 9

    Returns:
        pool 列表
    """
    reset_auction()
    gladiators = load_gladiators()
    available = gladiators.copy()
    random.shuffle(available)
    pool = available[:count]

    _auction_state["pool"] = pool
    _auction_state["pool_index"] = 0
    _auction_state["owner_a"] = []
    _auction_state["owner_b"] = []
    _auction_state["active"] = True

    print(f"\n{'='*60}")
    print(f"【拍卖池（共 {count} 名角斗士）】")
    print(f"{'序号':<6}{'名称':<12}{'char_id':<18}{'疲劳':<10}")
    print("-" * 60)
    for i, g in enumerate(pool, 1):
        print(f"  {i:<4}  {g['name']:<10}  {g['char_id']:<16}  {g['fatigue']:.0%}")
    print(f"{'='*60}")
    print("主持者请收集双方暗标出价，然后调用 run_auction_round(bid_a, bid_b)")
    print("出价 0 = 弃权，双方均 0 = 跳过该角斗士\n")

    # 展示第一个角斗士
    _advance_pool()
    return pool


def _advance_pool():
    """推进到拍卖池下一个角斗士。"""
    state = _auction_state
    if state["game_over"]:
        return
    if state["pool_index"] >= len(state["pool"]):
        state["current"] = None
        state["active"] = False
        print("拍卖池已空。")
        return

    state["current"] = state["pool"][state["pool_index"]]
    state["tie_count"] = 0
    g = state["current"]
    print(f"【当前拍卖 #{state['pool_index'] + 1}/{len(state['pool'])}】")
    print(f"  角斗士: {g['name']} ({g['char_id']})  疲劳: {g['fatigue']:.0%}")
    print(f"  请双方出价（输入 0 弃权）")


def run_auction_round(bid_a, bid_b):
    """暗标一轮：比较双方出价，判定归属，扣游戏币。

    Args:
        bid_a: 玩家A 出价（整数，0=弃权）
        bid_b: 玩家B 出价（整数，0=弃权）

    Returns:
        {"result": "win"|"tie"|"skip", "winner": str|None, "amount": int, "msg": str}
    """
    state = _auction_state
    if state["game_over"]:
        msg = "游戏已结束。"
        print(msg)
        return {"result": "skip", "winner": None, "amount": 0, "msg": msg}
    if not state["active"] or state["current"] is None:
        msg = "拍卖未在进行中，请先调用 generate_auction_pool()"
        print(msg)
        return {"result": "skip", "winner": None, "amount": 0, "msg": msg}

    current = state["current"]
    char_name = current["name"]
    pa = state["player_a_name"]
    pb = state["player_b_name"]

    # 检查双方游戏币是否足够
    gs = load_game_state()
    chips_a = gs["player_a"]["chips"]
    chips_b = gs["player_b"]["chips"]

    if bid_a > chips_a:
        print(f"⚠ {pa} 出价 {bid_a} 超过游戏币 {chips_a}，无效。")
        return {"result": "tie", "winner": None, "amount": bid_a,
                "msg": f"{pa} 出价 {bid_a} 超过游戏币余额 {chips_a}，请重新出价。"}
    if bid_b > chips_b:
        print(f"⚠ {pb} 出价 {bid_b} 超过游戏币 {chips_b}，无效。")
        return {"result": "tie", "winner": None, "amount": bid_b,
                "msg": f"{pb} 出价 {bid_b} 超过游戏币余额 {chips_b}，请重新出价。"}

    # 游戏币不足 50 的玩家只能弃权（对方按起拍价任意选择）
    if chips_a < 50:
        if bid_a != 0:
            print(f"⚠ {pa} 游戏币不足 50（当前 {chips_a}），出价 {bid_a} 强制改为弃权。")
        bid_a = 0
    if chips_b < 50:
        if bid_b != 0:
            print(f"⚠ {pb} 游戏币不足 50（当前 {chips_b}），出价 {bid_b} 强制改为弃权。")
        bid_b = 0

    # 验证出价范围（非零出价必须 >= 50, <= 150）
    for bid_val, pname in [(bid_a, pa), (bid_b, pb)]:
        if bid_val != 0 and bid_val < 50:
            msg = f"⚠ {pname} 出价 {bid_val} 低于起拍价 50，请重新出价。"
            print(msg)
            return {"result": "tie", "winner": None, "amount": bid_val, "msg": msg}
        if bid_val > 150:
            msg = f"⚠ {pname} 出价 {bid_val} 超过一口价 150，请重新出价。"
            print(msg)
            return {"result": "tie", "winner": None, "amount": bid_val, "msg": msg}

    # 双方都弃权
    if bid_a == 0 and bid_b == 0:
        msg = f"双方均弃权，{char_name} ({current['char_id']}) 回池，跳过。"
        print(msg)
        _next_gladiator()
        return {"result": "skip", "winner": None, "amount": 0, "msg": msg}

    # 一人弃权
    if bid_a == 0:
        return _assign_winner(pb, bid_b, char_name, pa, pb, bid_a, bid_b)
    if bid_b == 0:
        return _assign_winner(pa, bid_a, char_name, pa, pb, bid_a, bid_b)

    # 出价不同
    if bid_a > bid_b:
        return _assign_winner(pa, bid_a, char_name, pa, pb, bid_a, bid_b)
    elif bid_b > bid_a:
        return _assign_winner(pb, bid_b, char_name, pa, pb, bid_a, bid_b)

    # 出价相同 → 平局重拍
    state["tie_count"] += 1
    if state["tie_count"] >= 2:
        msg = f"双方连续 2 次出价相同，{char_name} ({current['char_id']}) 跳过。"
        print(msg)
        _next_gladiator()
        return {"result": "skip", "winner": None, "amount": bid_a, "msg": msg}

    msg = f"双方出价相同 ({bid_a} 游戏币)，需要重新出价（第 {state['tie_count']} 次平局）。"
    print(msg)
    return {"result": "tie", "winner": None, "amount": bid_a, "msg": msg}


def _assign_winner(winner_name, amount, char_name, pa, pb, bid_a, bid_b):
    """将当前角斗士分配给胜者，扣币，推进。

    Args:
        winner_name: 胜者名称（"玩家A" 或 "玩家B"）
        amount: 胜者出价金额
        char_name: 角斗士中文名
        pa: 玩家A 名称
        pb: 玩家B 名称
        bid_a: 玩家A 出价
        bid_b: 玩家B 出价

    Returns:
        {"result": "win", "winner": str, "amount": int, "msg": str}
    """
    state = _auction_state
    current = state["current"]
    entry = {
        "char_id": current["char_id"],
        "name": current["name"],
        "fatigue": current["fatigue"],
        "point": amount,
    }

    if winner_name == pa:
        state["owner_a"].append(entry)
        player_key = "player_a"
    else:
        state["owner_b"].append(entry)
        player_key = "player_b"

    # 扣游戏币（双方都扣）
    update_player_chips(player_key, -amount)
    loser_key = "player_b" if winner_name == pa else "player_a"
    loser_bid = bid_b if winner_name == pa else bid_a
    if loser_bid > 0:
        update_player_chips(loser_key, -loser_bid)
        # 输方出价转入输方自己的奖励池（安慰金）
        update_reward_pool(loser_key, loser_bid)
    gs = load_game_state()

    other_bid = bid_b if winner_name == pa else bid_a
    msg = (f"{char_name} ({current['char_id']}) 以 {amount} 游戏币归 {winner_name} 所有"
           f"（对方出价 {other_bid}）。")

    print(f"\n{'='*60}")
    print(f"【拍卖结果】{msg}")
    print(f"  {pa}: {len(state['owner_a'])} 人 | {pb}: {len(state['owner_b'])} 人")
    print(f"  {pa} 剩余游戏币: {gs['player_a']['chips']}")
    print(f"  {pb} 剩余游戏币: {gs['player_b']['chips']}")
    print(f"{'='*60}\n")

    _next_gladiator()
    return {"result": "win", "winner": winner_name, "amount": amount, "msg": msg}


def _next_gladiator():
    """推进到下一个角斗士，检查是否需要自动补齐。"""
    state = _auction_state
    state["pool_index"] += 1
    state["current"] = None

    # 检查双方是否都已满 3 人
    if len(state["owner_a"]) >= 3 and len(state["owner_b"]) >= 3:
        state["active"] = False
        print("双方均已满 3 名角斗士，拍卖结束。")
        _print_auction_summary()
        return

    # 自动补齐
    if len(state["owner_a"]) >= 3:
        auto_fill_remaining()
        return
    if len(state["owner_b"]) >= 3:
        auto_fill_remaining()
        return

    # 检查池是否已空
    if state["pool_index"] >= len(state["pool"]):
        # 池空但双方未满 → 自动补齐双方
        if len(state["owner_a"]) < 3:
            auto_fill_remaining()
        if len(state["owner_b"]) < 3:
            auto_fill_remaining()
        state["active"] = False
        print("拍卖池已空。")
        _print_auction_summary()
        return

    _advance_pool()


def _deduct_with_pool_fallback(player_key, amount):
    """扣款：优先 chips，不够从 reward_pool 补。

    Args:
        player_key: "player_a" 或 "player_b"
        amount: 扣除金额
    """
    gs = load_game_state()
    name = gs[player_key]["name"]
    old_chips = gs[player_key]["chips"]
    old_pool = gs[player_key]["reward_pool"]

    if old_chips >= amount:
        gs[player_key]["chips"] -= amount
        save_game_state(gs)
        print(f"{name} 游戏币: {old_chips} → {gs[player_key]['chips']} (-{amount})")
    else:
        from_chips = old_chips
        shortfall = amount - from_chips
        gs[player_key]["chips"] = 0
        gs[player_key]["reward_pool"] = old_pool - shortfall
        save_game_state(gs)
        print(f"{name} 游戏币不足 ({old_chips})，从奖励池补扣 {shortfall} → "
              f"chips=0, reward_pool {old_pool}→{gs[player_key]['reward_pool']}")


def _trigger_bankruptcy(bankrupt_key, bankrupt_name):
    """玩家破产：游戏币清零，对方获得所有游戏币，游戏结束。

    Args:
        bankrupt_key: 破产玩家 key（"player_a" 或 "player_b"）
        bankrupt_name: 破产玩家名称
    """
    gs = load_game_state()
    other_key = "player_b" if bankrupt_key == "player_a" else "player_a"
    other_name = gs[other_key]["name"]

    bankrupt_chips = gs[bankrupt_key]["chips"]
    gs[other_key]["chips"] += bankrupt_chips
    gs[bankrupt_key]["chips"] = 0
    save_game_state(gs)

    print(f"\n{'='*60}")
    print(f"【{bankrupt_name} 破产！】")
    print(f"  奖励池不足以支付系统补齐费用（{AUTO_FILL_PRICE} 游戏币/人）")
    print(f"  {bankrupt_name} 游戏币 {bankrupt_chips} → 0")
    print(f"  {other_name} 获得 {bankrupt_name} 的全部游戏币，当前 {gs[other_key]['chips']}")
    print(f"  游戏结束。")
    print(f"{'='*60}\n")

    _auction_state["active"] = False
    _auction_state["game_over"] = True


def auto_fill_remaining():
    """当一方满 3 人时，自动以 85 币补齐另一方角斗士（从池中剩余未展示的随机选）。"""
    state = _auction_state
    if not state["active"]:
        return

    def _fill(target, other, player_key, player_name):
        needed = 3 - len(target)
        if needed <= 0:
            return
        owned_ids = {e["char_id"] for e in target + other}
        # 从拍卖池中收集所有未被认领的角斗士（不区分已展示/未展示）
        candidates = [g for g in state["pool"]
                      if g["char_id"] not in owned_ids]
        random.shuffle(candidates)
        # 不够从全部 20 人中补（池外角斗士）
        if len(candidates) < needed:
            all_gladiators = load_gladiators()
            fallback = [g for g in all_gladiators
                        if g["char_id"] not in owned_ids
                        and g not in candidates]
            random.shuffle(fallback)
            candidates += fallback[:needed - len(candidates)]
        random.shuffle(candidates)
        for g in candidates[:needed]:
            # 检查是否破产（chips + reward_pool 不够支付自动补齐费用）
            gs = load_game_state()
            total = gs[player_key]["chips"] + gs[player_key]["reward_pool"]
            if total < AUTO_FILL_PRICE:
                _trigger_bankruptcy(player_key, player_name)
                return
            entry = {
                "char_id": g["char_id"],
                "name": g["name"],
                "fatigue": g["fatigue"],
                "point": AUTO_FILL_PRICE,
                "auto_filled": True,
            }
            target.append(entry)
            _deduct_with_pool_fallback(player_key, AUTO_FILL_PRICE)
        if candidates[:needed]:
            names = ", ".join(f"{e['name']} ({e['char_id']})" for e in target[-needed:])
            print(f"\n系统自动补齐 {player_name}: {names}（各 {AUTO_FILL_PRICE} 游戏币）")
        else:
            print(f"\n⚠ 无法为 {player_name} 补齐角斗士（无可用角斗士）")

    _fill(state["owner_a"], state["owner_b"], "player_a", state["player_a_name"])
    _fill(state["owner_b"], state["owner_a"], "player_b", state["player_b_name"])

    # 检查是否拍卖可结束（双方满3人或池空无法继续）
    a_full = len(state["owner_a"]) >= 3
    b_full = len(state["owner_b"]) >= 3
    pool_exhausted = state["pool_index"] >= len(state["pool"])
    if (a_full and b_full) or pool_exhausted:
        state["active"] = False
        print("拍卖结束。" if (a_full and b_full) else "拍卖池已空，拍卖结束。")
        _print_auction_summary()


def _print_auction_summary():
    """打印拍卖摘要。"""
    state = _auction_state
    pa = state["player_a_name"]
    pb = state["player_b_name"]
    print(f"\n{'='*60}")
    print(f"【拍卖结束 — 双方阵容】")
    print(f"  {pa}:")
    for e in state["owner_a"]:
        tag = " (系统补)" if e.get("auto_filled") else ""
        print(f"    - {e['name']} ({e['char_id']})  疲劳: {e['fatigue']:.0%}  花费: {e['point']}{tag}")
    print(f"  {pb}:")
    for e in state["owner_b"]:
        tag = " (系统补)" if e.get("auto_filled") else ""
        print(f"    - {e['name']} ({e['char_id']})  疲劳: {e['fatigue']:.0%}  花费: {e['point']}{tag}")
    gs = load_game_state()
    print(f"  游戏币 — {pa}: {gs['player_a']['chips']} | {pb}: {gs['player_b']['chips']}")
    print(f"{'='*60}\n")


# ── 比赛 ──────────────────────────────────────────────────────────────────

def run_match(char_id_a, char_id_b, hp_a=1.0, hp_b=1.0):
    """运行一场 1v1 比赛并打印结果。

    Args:
        char_id_a: 玩家A 角斗士 char_id
        char_id_b: 玩家B 角斗士 char_id
        hp_a: 玩家A 角斗士 HP 倍率
        hp_b: 玩家B 角斗士 HP 倍率

    Returns:
        比赛结果 dict
    """
    from role.match_runner import run_headless_match

    # 找到角斗士名称
    name_a = next((c.name for c in CHARACTERS if c.id == char_id_a), char_id_a)
    name_b = next((c.name for c in CHARACTERS if c.id == char_id_b), char_id_b)

    print(f"\n{'='*60}")
    print(f"【比赛】{name_a} ({char_id_a}) vs {name_b} ({char_id_b})")
    print(f"  HP 倍率: {name_a}={hp_a:.0%}, {name_b}={hp_b:.0%}")
    print("  比赛中...")

    hp_multipliers = {char_id_a: hp_a, char_id_b: hp_b}
    try:
        result = run_headless_match([char_id_a, char_id_b], hp_multipliers)
    except Exception as e:
        print(f"  比赛运行失败: {e}")
        return {"winner": None, "error": str(e)}

    print(f"\n【比赛结果】{name_a} vs {name_b}")
    if result.get("winner") is None:
        print(f"  结果: 超时/平局")
        print(f"  耗时: {result['duration_frames']} 帧 ({result['duration_frames'] / 60:.1f}秒)")
    else:
        winner_name = result["winner"]  # already a Chinese name from game.winner
        loser_name = name_b if winner_name == name_a else name_a
        print(f"  胜者: {winner_name} (剩余HP: {result.get('winner_final_hp', '?')})")
        print(f"  败者: {loser_name} (剩余HP: {result.get('loser_final_hp', '?')})")
        print(f"  耗时: {result['duration_frames']} 帧 ({result['duration_frames'] / 60:.1f}秒)")
    print(f"{'='*60}\n")

    return result


def settle_match(char_id_a, char_id_b, is_second_of_day=False):
    """比赛 + 结算：运行比赛、point 转移、归池、疲劳更新。

    每天每名角斗士只能出战一次。比赛后胜方从败方 point 中夺取等于自身 point
    数量的部分（不超过败方 point），第二轮夺取量 ×1.5。所有 point 立即归入奖励池。

    Args:
        char_id_a: 玩家A 出战的角斗士 char_id
        char_id_b: 玩家B 出战的角斗士 char_id
        is_second_of_day: 是否当天第二轮（夺取量 ×1.5）
    """
    state = _auction_state
    if state["game_over"]:
        print("游戏已结束。")
        return

    # 在 owner 列表中查找角斗士
    entry_a = next((e for e in state["owner_a"] if e["char_id"] == char_id_a), None)
    entry_b = next((e for e in state["owner_b"] if e["char_id"] == char_id_b), None)
    if not entry_a or not entry_b:
        print("错误: 未在拍卖阵容中找到角斗士，请确认 char_id 和拍卖状态。")
        return

    # 确认角斗士今天还没出过战
    if entry_a.get("used_today"):
        print(f"错误: {entry_a['name']} ({char_id_a}) 今天已经出战过了。")
        return
    if entry_b.get("used_today"):
        print(f"错误: {entry_b['name']} ({char_id_b}) 今天已经出战过了。")
        return

    name_a = entry_a["name"]
    name_b = entry_b["name"]
    hp_a = entry_a["fatigue"]
    hp_b = entry_b["fatigue"]

    # 运行比赛
    result = run_match(char_id_a, char_id_b, hp_a, hp_b)

    if result.get("error"):
        print(f"比赛出错，跳过结算: {result['error']}")
        return

    # ── Point 转移 ──
    point_a = entry_a.get("point", 0)
    point_b = entry_b.get("point", 0)
    winner_name = result.get("winner")  # game.winner returns Chinese name

    print(f"【结算】{name_a} (point={point_a}) vs {name_b} (point={point_b})")

    multiplier = 1.5 if is_second_of_day else 1.0
    bonus_tag = "（第二轮 ×1.5）" if is_second_of_day else ""

    if winner_name is None:
        # 平局/超时：各自 point 归各自奖励池
        print(f"  结果: 平局/超时")
        if point_a:
            update_reward_pool("player_a", point_a)
            entry_a["point"] = 0
        if point_b:
            update_reward_pool("player_b", point_b)
            entry_b["point"] = 0
    elif winner_name == name_a:
        # A 胜：夺取 min(自己 point, 败方 point) × multiplier
        transfer = int(min(point_a, point_b) * multiplier)
        print(f"  胜方: {name_a} {bonus_tag}")
        print(f"  transfer = min({point_a}, {point_b}) × {multiplier} = {transfer}")
        print(f"  {name_a} 奖励池 += {point_a} + {transfer} = {point_a + transfer}")
        print(f"  {name_b} 奖励池 += {point_b} - {transfer} = {point_b - transfer}")
        update_reward_pool("player_a", point_a + transfer)
        update_reward_pool("player_b", point_b - transfer)
        entry_a["point"] = 0
        entry_b["point"] = 0
    else:
        # B 胜：夺取 min(自己 point, 败方 point) × multiplier
        transfer = int(min(point_b, point_a) * multiplier)
        print(f"  胜方: {name_b} {bonus_tag}")
        print(f"  transfer = min({point_b}, {point_a}) × {multiplier} = {transfer}")
        print(f"  {name_b} 奖励池 += {point_b} + {transfer} = {point_b + transfer}")
        print(f"  {name_a} 奖励池 += {point_a} - {transfer} = {point_a - transfer}")
        update_reward_pool("player_b", point_b + transfer)
        update_reward_pool("player_a", point_a - transfer)
        entry_a["point"] = 0
        entry_b["point"] = 0

    # ── 每日胜场记录 ──
    if winner_name == name_a:
        _auction_state["daily_wins"]["player_a"] += 1
    elif winner_name == name_b:
        _auction_state["daily_wins"]["player_b"] += 1

    # ── 疲劳更新 ──
    entry_a["used_today"] = True
    entry_b["used_today"] = True
    update_fatigue_after_match(char_id_a, was_used=True)
    update_fatigue_after_match(char_id_b, was_used=True)

    print()
    return result


def end_day():
    """每日结算：全局所有 20 名角斗士疲劳恢复一级，清除 used_today 标记。

    每天结束后调用。恢复规则：0.6→0.8, 0.8→0.9, 0.9→1.0, 1.0→1.0。
    注意 settle_match 已经更新了出战者的疲劳（恶化），此函数恢复其余所有人。
    """
    state = _auction_state
    today_fighters = set()
    for entry in state["owner_a"] + state["owner_b"]:
        if entry.get("used_today"):
            today_fighters.add(entry["char_id"])
        entry["used_today"] = False

    gladiators = load_gladiators()
    recovered = []
    for g in gladiators:
        if g["char_id"] not in today_fighters:
            old = g["fatigue"]
            fatigue_map = {1.0: 1.0, 0.9: 1.0, 0.8: 0.9, 0.6: 0.8}
            g["fatigue"] = fatigue_map.get(old, 1.0)
            if g["fatigue"] != old:
                recovered.append(f"{g['name']}({old:.0%}→{g['fatigue']:.0%})")
    save_gladiators(gladiators)

    if recovered:
        print(f"每日疲劳恢复: {', '.join(recovered)}")
    else:
        print("每日结算: 所有角斗士今日均已出战，无恢复。")
    print(f"今日出战 {len(today_fighters)} 人，休息恢复 {len(recovered)} 人。")

    # ── 每日胜者奖励（奖励池 point → 游戏币） ──
    dw = _auction_state["daily_wins"]
    wa = dw["player_a"]
    wb = dw["player_b"]
    print(f"\n今日胜场 — {state['player_a_name']}: {wa} | {state['player_b_name']}: {wb}")

    if wa == wb:
        print("双方胜场数相同，无每日胜者奖励。")
    else:
        winner_key = "player_a" if wa > wb else "player_b"
        gs = load_game_state()
        pool = gs[winner_key]["reward_pool"]
        if pool <= 0:
            print(f"{gs[winner_key]['name']} 为今日胜者，但奖励池 point={pool}（≤0），无转换。")
        elif pool < 50:
            # 0 < point < 50: 全部转换为游戏币
            gs[winner_key]["reward_pool"] = 0
            gs[winner_key]["chips"] += pool
            save_game_state(gs)
            print(f"{gs[winner_key]['name']} 为今日胜者！奖励池 {pool} point 全部转换为游戏币。")
            print(f"  奖励池: {pool} → 0 | 游戏币: +{pool}")
        else:
            # point >= 50: 转换 50 point 为游戏币
            convert = 50
            gs[winner_key]["reward_pool"] -= convert
            gs[winner_key]["chips"] += convert
            save_game_state(gs)
            print(f"{gs[winner_key]['name']} 为今日胜者！奖励池 {pool} point 转换为 50 游戏币。")
            print(f"  奖励池: {pool} → {gs[winner_key]['reward_pool']} | 游戏币: +{convert}")


# ── 游戏状态管理 ──────────────────────────────────────────────────────────

def load_game_state():
    """读取 game_state.json。"""
    with open(_GAME_STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_game_state(data):
    """写回 game_state.json。

    Args:
        data: 游戏状态 dict
    """
    with open(_GAME_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_player_chips(player_key, amount):
    """加减玩家游戏币。

    Args:
        player_key: "player_a" 或 "player_b"
        amount: 变化量（正数加，负数减）
    """
    gs = load_game_state()
    old = gs[player_key]["chips"]
    gs[player_key]["chips"] += amount
    if gs[player_key]["chips"] < 0:
        print(f"⚠ {gs[player_key]['name']} 游戏币不足！当前 {old}，变动 {amount}")
        gs[player_key]["chips"] = old
        return
    save_game_state(gs)
    print(f"{gs[player_key]['name']} 游戏币: {old} → {gs[player_key]['chips']} ({amount:+d})")


def update_reward_pool(player_key, amount):
    """加减玩家奖励池。

    Args:
        player_key: "player_a" 或 "player_b"
        amount: 变化量
    """
    gs = load_game_state()
    old = gs[player_key]["reward_pool"]
    gs[player_key]["reward_pool"] += amount
    save_game_state(gs)
    print(f"{gs[player_key]['name']} 奖励池: {old} → {gs[player_key]['reward_pool']} ({amount:+d})")


def print_game_state():
    """打印当前双方游戏币和奖励池状态。"""
    gs = load_game_state()
    pa = gs["player_a"]
    pb = gs["player_b"]
    print(f"\n{'='*40}")
    print(f"【当前状态】")
    if _auction_state["game_over"]:
        print(f"  ⚠ 游戏已结束（破产）")
    print(f"  {pa['name']}: 游戏币 {pa['chips']} | 奖励池 {pa['reward_pool']}")
    print(f"  {pb['name']}: 游戏币 {pb['chips']} | 奖励池 {pb['reward_pool']}")
    print(f"{'='*40}\n")


def finalize_game():
    """最终结算：奖励池 point 1:1 兑换为游戏币，打印胜负。"""
    gs = load_game_state()
    pa = gs["player_a"]
    pb = gs["player_b"]
    reward_a = pa["reward_pool"]
    reward_b = pb["reward_pool"]
    pa["chips"] += reward_a
    pb["chips"] += reward_b
    pa_total = pa["chips"]
    pb_total = pb["chips"]
    pa["reward_pool"] = 0
    pb["reward_pool"] = 0
    save_game_state(gs)

    print(f"\n{'='*60}")
    print(f"【最终结算 — 奖励池 1:1 兑换为游戏币】")
    print(f"  {pa['name']}: 游戏币 {pa_total}（奖励池 +{reward_a} 已兑换）")
    print(f"  {pb['name']}: 游戏币 {pb_total}（奖励池 +{reward_b} 已兑换）")
    if pa_total > pb_total:
        print(f"  🏆 {pa['name']} 获胜！")
    elif pb_total > pa_total:
        print(f"  🏆 {pb['name']} 获胜！")
    else:
        print(f"  平局！")
    print(f"  最终可兑换现金: {pa['name']} {pa_total}元, {pb['name']} {pb_total}元")
    print(f"{'='*60}\n")
    _auction_state["game_over"] = True


def print_players():
    """打印两位玩家的完整信息（所有字段）。"""
    gs = load_game_state()
    print(f"\n{'='*50}")
    for key in ("player_a", "player_b"):
        p = gs[key]
        print(f"【{p['name']}】 (key={key})")
        for k, v in p.items():
            print(f"  {k}: {v}")
    print(f"{'='*50}\n")


def reset_all():
    """重置所有数据：疲劳全部恢复为 1.0，游戏币恢复 800，奖励池清零，重置拍卖和情报。"""
    # 角斗士疲劳全部恢复
    gladiators = load_gladiators()
    for g in gladiators:
        g["fatigue"] = 1.0
    save_gladiators(gladiators)
    print("已重置 20 名角斗士疲劳 → 1.0 (100%)")

    # 游戏状态恢复初始
    save_game_state({
        "player_a": {"name": "玩家A", "chips": 800, "reward_pool": 0},
        "player_b": {"name": "玩家B", "chips": 800, "reward_pool": 0},
    })
    print("已重置游戏币 → 800, 奖励池 → 0")

    # 拍卖状态重置
    reset_auction()
    print("已重置拍卖状态")
    print("\n所有数据已恢复初始状态。")


# ── 每日完整流程 ──────────────────────────────────────────────────────────

def run_full_day(day, shown_a, shown_b):
    """一键执行当天完整流程：情报预览 + 生成拍卖池 + 打印操作指南。

    Args:
        day: 第几天 (1-based)
        shown_a: 玩家A 已展示过的角斗士 index 集合
        shown_b: 玩家B 已展示过的角斗士 index 集合

    Returns:
        (shown_a, shown_b) 更新后的已展示集合
    """
    print(f"\n{'#'*60}")
    print(f"#  第 {day} 天")
    print(f"{'#'*60}")

    # 0. 第 1 天展示胜率总览
    if day == 1:
        show_all_gladiators()

    # 重置每日胜场计数
    _auction_state["daily_wins"] = {"player_a": 0, "player_b": 0}

    # 1. 情报阶段
    print(f"\n── 情报阶段 ──")
    count = _PREVIEW_COUNTS.get(day, 3)
    shown_a = generate_daily_preview("玩家A", shown_a, count)
    shown_b = generate_daily_preview("玩家B", shown_b, count)

    # 2. 拍卖阶段
    print(f"\n── 拍卖阶段 ──")
    generate_auction_pool(count=9)

    # 3. 操作指南
    print(f"\n── 操作指南 ──")
    print("主持者请按以下步骤操作：")
    print("  1. 向双方玩家展示上方拍卖池和情报")
    print("  2. 逐个角斗士收集暗标出价，调用 run_auction_round(bid_a, bid_b)")
    print("  （出价范围: 0=弃权, 50-150，一口价 150 直接获胜）")
    print("  3. 拍卖结束后，双方各从自己的 3 人中选 1 人出战")
    print("  4. 调用 settle <char_id_a> <char_id_b> 运行比赛并结算（第二轮自动 ×1.5）")
    print("  5. 调用 state 查看当前状态")
    print()

    return shown_a, shown_b


# ── 疲劳更新 ──────────────────────────────────────────────────────────────

def update_fatigue_after_match(char_id, was_used):
    """比赛后更新角斗士疲劳。

    规则（参考 squad.py get_hp_multiplier）：
    - 出战: fatigue 降一级（1.0→0.8, 0.9→0.8, 0.8→0.6, 0.6→0.6）
    - 未出战（休息）: fatigue 升一级（0.6→0.8, 0.8→0.9, 0.9→1.0, 1.0→1.0）

    Args:
        char_id: 角斗士 char_id
        was_used: 是否今天出战
    """
    gladiators = load_gladiators()
    g = next((g for g in gladiators if g["char_id"] == char_id), None)
    if g is None:
        print(f"未找到 char_id={char_id} 的角斗士")
        return

    old = g["fatigue"]
    if was_used:
        # 出战：疲劳恶化
        fatigue_map = {1.0: 0.8, 0.9: 0.8, 0.8: 0.6, 0.6: 0.6}
        g["fatigue"] = fatigue_map.get(old, 0.6)
    else:
        # 休息：疲劳恢复
        fatigue_map = {0.6: 0.8, 0.8: 0.9, 0.9: 1.0, 1.0: 1.0}
        g["fatigue"] = fatigue_map.get(old, 1.0)

    save_gladiators(gladiators)
    action = "出战" if was_used else "休息"
    print(f"{g['name']} ({char_id}) {action}: 疲劳 {old:.0%} → {g['fatigue']:.0%}")


def update_squad_fatigue(owner_gladiators, used_char_id):
    """更新整个小队疲劳：出战的一个降级，其余两个恢复。

    Args:
        owner_gladiators: [{"char_id": ..., "name": ..., ...}, ...] 该玩家 3 人
        used_char_id: 今天出战的 char_id
    """
    for g in owner_gladiators:
        was_used = g["char_id"] == used_char_id
        update_fatigue_after_match(g["char_id"], was_used)


# ── 交互式 REPL ─────────────────────────────────────────────────────────

def _print_help():
    print("""
【命令列表】
  day <n>               开始第 n 天（情报预览 + 拍卖池）
  bid <a> <b>           暗标出价（A金额 B金额，0=弃权）
  autofill              系统补齐角斗士（一方满3后自动补另一方）
  settle <ca> <cb>        比赛+结算（ca=A角斗士, cb=B角斗士）
  endday                每日结算（恢复未出战角斗士疲劳）
  state                 查看游戏币和奖励池
  auction               查看当前拍卖状态
  query <index>         查看角斗士详情（1-20）
  update <idx> <k>=<v>  更新角斗士字段（如 update 1 fatigue=0.8）
  fatigue <cid> <u|r>   手动更新疲劳（u=出战 r=休息）
  chips <A|B> <amount>   调整游戏币
  reward <A|B> <amount>  调整奖励池
  preview <A|B> [n]     情报预览（n=数量，默认5）
  players               查看两名玩家完整信息
  resetall              重置全部（疲劳→1.0, 游戏币→800, 奖励池→0）
  reset                 重置拍卖状态
  finalize              最终结算（奖励池 1:1 兑换游戏币，判定胜负）
  ranks                 查看 20 名角斗士胜率总览
  help                  显示此帮助
  quit/exit/q           退出
""")


def _is_player_a(arg):
    """判断参数是否指向玩家A，支持 A / PLAYER_A / 玩家A 等写法。

    Args:
        arg: 玩家标识字符串

    Returns:
        True 表示玩家A，False 表示玩家B
    """
    return arg.upper() in ("A", "PLAYER_A", "玩家A")


def _repl():
    """交互式 REPL 主循环。"""
    print("=" * 50)
    print("人类玩家赌局主持工具 — 交互模式")
    print("输入 help 查看命令，quit 退出")
    print("=" * 50)

    shown_a: set[int] = set()
    shown_b: set[int] = set()
    _match_count = 0  # 每天比赛计数器，第2场触发 ×1.5 效果

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        try:
            if cmd in ("quit", "exit", "q"):
                break

            elif cmd == "help":
                _print_help()

            elif cmd == "day":
                n = int(parts[1])
                shown_a, shown_b = run_full_day(n, shown_a, shown_b)
                _match_count = 0

            elif cmd == "bid":
                bid_a = int(parts[1])
                bid_b = int(parts[2])
                run_auction_round(bid_a, bid_b)

            elif cmd == "autofill":
                auto_fill_remaining()

            elif cmd == "settle":
                char_a = parts[1]
                char_b = parts[2]
                _match_count += 1
                settle_match(char_a, char_b, is_second_of_day=(_match_count == 2))

            elif cmd == "endday":
                end_day()
                _match_count = 0
                print("每日结算完成，已恢复未出战角斗士疲劳。")

            elif cmd == "state":
                print_game_state()

            elif cmd == "auction":
                st = get_auction_state()
                print(f"拍卖状态: {'进行中' if st['active'] else '已结束'}")
                print(f"  池: {len(st['pool'])} 人, 已展示 {st['pool_index']} 个")
                if st["current"]:
                    print(f"  当前: {st['current']['name']} ({st['current']['char_id']})")
                print(f"  玩家A ({len(st['owner_a'])}人):",
                      ", ".join(f"{e['name']}({e['char_id']},pt={e.get('point',0)})"
                                for e in st["owner_a"]))
                print(f"  玩家B ({len(st['owner_b'])}人):",
                      ", ".join(f"{e['name']}({e['char_id']},pt={e.get('point',0)})"
                                for e in st["owner_b"]))

            elif cmd == "query":
                index = int(parts[1])
                query_gladiator(index)

            elif cmd == "update":
                idx = int(parts[1])
                kv = parts[2].split("=", 1)
                key = kv[0]
                val = float(kv[1]) if "." in kv[1] else int(kv[1])
                update_gladiator(idx, **{key: val})

            elif cmd == "fatigue":
                char_id = parts[1]
                used = parts[2].lower() in ("u", "used", "true", "1")
                update_fatigue_after_match(char_id, was_used=used)

            elif cmd == "chips":
                player_key = "player_a" if _is_player_a(parts[1]) else "player_b"
                amount = int(parts[2])
                update_player_chips(player_key, amount)

            elif cmd == "reward":
                player_key = "player_a" if _is_player_a(parts[1]) else "player_b"
                amount = int(parts[2])
                update_reward_pool(player_key, amount)

            elif cmd == "preview":
                target = "玩家A" if _is_player_a(parts[1]) else "玩家B"
                count = int(parts[2]) if len(parts) > 2 else 5
                if target == "玩家A":
                    shown_a = generate_daily_preview(target, shown_a, count)
                else:
                    shown_b = generate_daily_preview(target, shown_b, count)

            elif cmd == "reset":
                reset_auction()
                _match_count = 0
                print("拍卖状态已重置。")

            elif cmd == "players":
                print_players()

            elif cmd == "resetall":
                reset_all()
                _match_count = 0
                shown_a.clear()
                shown_b.clear()

            elif cmd == "finalize":
                finalize_game()

            elif cmd == "ranks":
                show_all_gladiators()

            else:
                print(f"未知命令: {cmd}，输入 help 查看所有命令。")

        except (IndexError, ValueError) as e:
            print(f"参数错误: {e}")
            print("输入 help 查看命令用法。")
        except Exception as e:
            print(f"执行出错: {e}")


if __name__ == "__main__":
    _repl()
