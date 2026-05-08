"""LangChain 工具定义 —— 角色智能体可调用的函数。

所有工具通过模块级 _state 共享访问游戏状态。
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import tool


# ── GameState ──────────────────────────────────────────────────────────────────

@dataclass
class GameState:
    """共享游戏状态，所有工具通过此对象读写。"""
    bob: Any          # Bob 实例
    peter: Any        # Peter 实例
    nerd: Any         # Nerd 实例
    round_number: int = 0
    current_bet: float = 100.0
    match_history: list[dict] = field(default_factory=list)
    pending_selection: dict | None = None  # 客户的选择意向



_state: GameState | None = None


def set_game_state(state: GameState):
    global _state
    _state = state


def get_game_state() -> GameState:
    if _state is None:
        raise RuntimeError("GameState 尚未初始化，请先调用 set_game_state()")
    return _state


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def _get_customer(name: str):
    """根据名字获取客户对象。"""
    state = get_game_state()
    name_lower = name.lower()
    if name_lower == "peter":
        return state.peter
    elif name_lower == "nerd":
        return state.nerd
    else:
        raise ValueError(f"未知客户: {name}，可选 'Peter' 或 'Nerd'")


# ── 工具1: 查看角斗士战绩（拆分为三个精准查询工具）──────────────────────────

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


@tool
def get_overall_ranking() -> str:
    """查看全部角斗士的胜率排名总表。返回9个角斗士按胜率从高到低的排名。
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
    # 按胜率从高到低排列
    sorted_matchups = sorted(matchups.items(), key=lambda x: -x[1]["rate"])
    for opp_id, m in sorted_matchups:
        opp = _find_gladiator(opp_id)
        opp_name = opp["name"] if opp else opp_id
        rate_pct = f"{m['rate']*100:.0f}%"
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
            f"{a_vs_b['wins']}胜 {a_vs_b['rate']*100:.0f}%"
        )
    else:
        lines.append(f"  {glad_a['name']} 对 {glad_b['name']}: 无数据")
    if b_vs_a:
        lines.append(
            f"  {glad_b['name']}(攻击方) 对 {glad_a['name']}: "
            f"{b_vs_a['wins']}胜 {b_vs_a['rate']*100:.0f}%"
        )
    else:
        lines.append(f"  {glad_b['name']} 对 {glad_a['name']}: 无数据")
    return "\n".join(lines)


# ── 工具2: 查看角斗士名录 ─────────────────────────────────────────────────────

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


# ── 工具3: 列出可租角斗士 ─────────────────────────────────────────────────────

@tool
def list_available_gladiators() -> str:
    """列出 Bob 当前未被租出且休息完毕的角斗士列表，包含名字、ID 和租金。
    在租借角斗士之前，必须先调用此工具确认哪些角斗士可用。"""
    state = get_game_state()
    available = [g for g in state.bob.gladiators
                 if g.owner == "bob" and g.rest_remaining == 0]
    resting = [g for g in state.bob.gladiators
               if g.owner == "bob" and g.rest_remaining > 0]

    lines = []
    if available:
        lines.append("【可租角斗士列表】")
        for g in available:
            lines.append(f"  - {g.name} (id: {g.char_id}, 租金: {g.rent_price}万)")
    else:
        lines.append("（当前没有可租借的角斗士）")

    if resting:
        lines.append("【休息中的角斗士】")
        for g in resting:
            lines.append(f"  - {g.name} (id: {g.char_id}, 还需休息: {g.rest_remaining}轮)")

    return "\n".join(lines)


# ── 工具4: 客户选择角斗士 ─────────────────────────────────────────────────────

@tool
def select_gladiator(name: str = "", char_id: str = "") -> str:
    """当你需要从可用角斗士列表中选择一个要租借的角斗士时，调用此工具。由你亲自决定选择哪个角斗士。
    此工具记录你的选择意向，不修改资产和归属权。选择后等待 Bob 确认交易。

    重要：你必须同时填写 name 和 char_id 两个参数，直接从 list_available_gladiators
    的输出中复制对应的名称和 ID，不要自己编造。

    Args:
        name: 角斗士的中文名称，直接从 list_available_gladiators 输出中复制（如 雷神、盾卫、制毒师）
        char_id: 角斗士的英文 ID，直接从 list_available_gladiators 输出中复制（如 thor, guardian, venomancer）
    """
    state = get_game_state()
    available = [g for g in state.bob.gladiators
                 if g.owner == "bob" and g.rest_remaining == 0]

    # 匹配：同时尝试 char_id 和 name，检测是否指向不同角斗士
    char_match = None
    name_match = None
    if char_id:
        char_match = next((g for g in available if g.char_id == char_id), None)
    if name:
        name_match = next((g for g in available if g.name == name), None)

    g = char_match or name_match  # char_id 优先

    if g is None:
        # 检查是否在休息中
        resting = None
        if char_id:
            resting = next((g for g in state.bob.gladiators
                           if g.char_id == char_id and g.owner == "bob"
                           and g.rest_remaining > 0), None)
        if resting is None and name:
            resting = next((g for g in state.bob.gladiators
                           if g.name == name and g.owner == "bob"
                           and g.rest_remaining > 0), None)
        if resting is not None:
            lines = [
                f"错误：角斗士 '{resting.name}' 正在休息中，还需 {resting.rest_remaining} 轮。",
                "",
                "当前可选的角斗士：",
            ]
            for gl in available:
                lines.append(f"  {gl.name} → char_id='{gl.char_id}'")
            return "\n".join(lines)

        # 模糊匹配：对 available 做 token、前缀、子串匹配
        suggestions = []
        query = (char_id + name).lower().replace('_', ' ').replace('-', ' ')
        query_tokens = query.split()
        for gl in available:
            gl_text = (gl.char_id + gl.name).lower().replace('_', ' ').replace('-', ' ')
            gl_tokens = gl_text.split()
            token_match = any(
                qt in gt or gt in qt
                for qt in query_tokens for gt in gl_tokens
            )
            substr_match = (
                (char_id and char_id.lower() in gl.char_id.lower()) or
                (char_id and gl.char_id.lower() in char_id.lower()) or
                (name and name in gl.name) or
                (name and gl.name in name)
            )
            prefix_len = 0
            for i in range(min(len(query), len(gl.char_id))):
                if query[i] == gl.char_id[i]:
                    prefix_len += 1
                else:
                    break
            if token_match or substr_match or prefix_len >= 3:
                suggestions.append(gl)

        lines = [
            f"错误：角斗士 '{char_id or name}' 不存在。",
            "",
            "当前可选的角斗士：",
        ]
        for gl in available:
            lines.append(f"  {gl.name} → char_id='{gl.char_id}'")
        if suggestions:
            ids = [s.char_id for s in suggestions]
            lines.append("")
            lines.append(f"你可能想选: {', '.join(ids)}")
        return "\n".join(lines)

    # 检测 name 和 char_id 是否指向不同角斗士
    mismatch_warning = ""
    if char_match and name_match and char_match.char_id != name_match.char_id:
        mismatch_warning = (
            f"\n\n⚠️ 名称与ID不匹配：name='{name}' 对应 {name_match.name}"
            f"(id={name_match.char_id})，但 char_id='{char_id}' 对应"
            f" {char_match.name}(id={char_match.char_id})。"
            f"已按 char_id 选择 {char_match.name}。"
            f"如果这不是你想选的角斗士，请核对后重新调用。"
        )

    # 记录选择意向
    state.pending_selection = {"char_id": g.char_id, "name": g.name}
    return (
        f"你已选择 {g.name} (id: {g.char_id})，租金 {g.rent_price}万。\n"
        f"等待 Bob 确认并完成租借交易。{mismatch_warning}"
    )


# ── 工具5: 赛后反思 ──────────────────────────────────────────────────────────

@tool
def reflect_on_match_by_Nerd() -> str:
    """在最近一轮比赛结束后使用该工具，获取比赛结果。
    对比赛结果进行分析与反思，以及思考下一步的计划。
    """
    state = get_game_state()
    if not state.match_history:
        return "（暂无比赛数据）"

    last = state.match_history[-1]
    game = last.get("game_result", {})

    won = last['winner'] == 'Nerd'
    my_glad = last['winner_gladiator'] if won else last['loser_gladiator']
    opponent_glad = last['loser_gladiator'] if won else last['winner_gladiator']
    opponent = last['loser'] if won else last['winner']

    return (
        f"【最近一轮比赛结果】\n"
        f"你{'赢了' if won else '输了'}，对手是 {opponent}。\n"
        f"你的角斗士: {my_glad}\n"
        f"对手角斗士: {opponent_glad}\n"
        f"投注额: {last['bet_per_player']}万\n"
        f"总奖池: {last['total_pool']}万\n"
        f"抽成: {last['commission']}万\n"
        f"胜方剩余HP: {game.get('winner_final_hp', '?')}\n"
        f"败方剩余HP: {game.get('loser_final_hp', '?')}"
    )

@tool
def reflect_on_match_by_Peter() -> str:
    """在最近一轮比赛结束后使用该工具，获取比赛结果。
    对比赛结果进行分析与反思，以及思考下一步的计划。
    """
    state = get_game_state()
    if not state.match_history:
        return "（暂无比赛数据）"

    last = state.match_history[-1]
    game = last.get("game_result", {})

    won = last['winner'] == 'Peter'
    my_glad = last['winner_gladiator'] if won else last['loser_gladiator']
    opponent_glad = last['loser_gladiator'] if won else last['winner_gladiator']
    opponent = last['loser'] if won else last['winner']

    return (
        f"【最近一轮比赛结果】\n"
        f"你{'赢了' if won else '输了'}，对手是 {opponent}。\n"
        f"你的角斗士: {my_glad}\n"
        f"对手角斗士: {opponent_glad}\n"
        f"投注额: {last['bet_per_player']}万\n"
        f"总奖池: {last['total_pool']}万\n"
        f"抽成: {last['commission']}万\n"
        f"胜方剩余HP: {game.get('winner_final_hp', '?')}\n"
        f"败方剩余HP: {game.get('loser_final_hp', '?')}"
    )

@tool
def reflect_on_match_by_Bob() -> str:
    """在最近一轮比赛结束后使用该工具，获取比赛结果。
    对比赛结果进行分析与反思，以及思考下一步的计划。
    """
    state = get_game_state()
    if not state.match_history:
        return "（暂无比赛数据）"

    last = state.match_history[-1]
    game = last.get("game_result", {})

    return (
        f"【最近一轮比赛结果】\n"
        f"胜方: {last['winner']}（角斗士: {last['winner_gladiator']}）\n"
        f"败方: {last['loser']}（角斗士: {last['loser_gladiator']}）\n"
        f"投注额: 每人{last['bet_per_player']}万\n"
        f"总奖池: {last['total_pool']}万\n"
        f"你抽成: {last['commission']}万\n"
        f"胜方剩余HP: {game.get('winner_final_hp', '?')}\n"
        f"败方剩余HP: {game.get('loser_final_hp', '?')}"
    )



