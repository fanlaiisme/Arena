"""LangChain 工具定义 —— 角色智能体可调用的函数。

所有工具通过模块级 _state 共享访问游戏状态。
"""

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


# ── 工具1: 查看角斗士战绩 ─────────────────────────────────────────────────────

_tournament_stats_cache: str | None = None


@tool
def get_tournament_stats() -> str:
    """查看角斗士历史循环赛战绩数据，包含每个角斗士的胜率排名和对战详情。
    当需要了解角斗士实力强弱时调用此工具。
    数据为静态文件，不会随比赛轮次变化。"""
    global _tournament_stats_cache
    if _tournament_stats_cache is not None:
        return _tournament_stats_cache
    stats_file = os.path.join(
        os.path.dirname(__file__),
        "data", "Bob", "tournament_stats-1.txt"
    )
    if not os.path.exists(stats_file):
        return "（暂无赛事数据）"
    with open(stats_file, "r", encoding="utf-8") as f:
        _tournament_stats_cache = f.read()
    return _tournament_stats_cache


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
def select_gladiator(char_id: str) -> str:
    """客户从可用角斗士列表中选择一个要租借的角斗士。你必须自己做决定。
    此工具记录你的选择意向，不修改资产和归属权。选择后等待 Bob 确认交易。

    Args:
        char_id: 角斗士的 ID（如 thor, guardian, frost 等）
    """
    state = get_game_state()
    available = [g for g in state.bob.gladiators
                 if g.owner == "bob" and g.rest_remaining == 0]
    g = next((g for g in available if g.char_id == char_id), None)
    if g is None:
        # 检查是否 ID 正确但在休息中
        resting = next((g for g in state.bob.gladiators
                        if g.char_id == char_id and g.owner == "bob"
                        and g.rest_remaining > 0), None)
        if resting is not None:
            avail_ids = [gl.char_id for gl in available]
            return (
                f"错误：角斗士 '{char_id}'（{resting.name}）正在休息中，"
                f"还需 {resting.rest_remaining} 轮。\n"
                f"当前可用: {', '.join(avail_ids) if avail_ids else '无'}"
            )

        # 模糊匹配：对 available + resting 做 token 和前缀匹配
        all_glads = [g for g in state.bob.gladiators if g.owner == "bob"]
        suggestions = []
        input_lower = char_id.lower()
        input_tokens = input_lower.replace('_', ' ').replace('-', ' ').split()
        for gl in all_glads:
            gl_tokens = gl.char_id.lower().replace('_', ' ').replace('-', ' ').split()
            # token 匹配：任一词包含或被包含
            token_match = any(
                it in gt or gt in it
                for it in input_tokens for gt in gl_tokens
            )
            # 前缀匹配：至少 3 个字符相同
            min_len = min(len(input_lower), len(gl.char_id))
            prefix_len = 0
            for i in range(min_len):
                if input_lower[i] == gl.char_id[i]:
                    prefix_len += 1
                else:
                    break
            if token_match or prefix_len >= 3:
                suggestions.append(gl)

        avail_ids = [gl.char_id for gl in available]
        hint = ""
        if len(suggestions) == 1:
            hint = f" 你是不是想选 '{suggestions[0].char_id}'（{suggestions[0].name}）？"
        elif len(suggestions) > 1:
            ids = [s.char_id for s in suggestions]
            hint = f" 你可能想选: {', '.join(ids)}"
        return (
            f"错误：角斗士 '{char_id}' 不存在。{hint}\n"
            f"当前可用: {', '.join(avail_ids) if avail_ids else '无'}"
        )

    # 记录选择意向，不修改状态
    state.pending_selection = {"char_id": char_id, "name": g.name}
    return (
        f"你已选择 {g.name} (id: {char_id})，租金 {g.rent_price}万。\n"
        f"等待 Bob 确认并完成租借交易。"
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