"""Arena 角色实验 —— 无 Bob 精简版（3天×3局 + 拍卖 + 疲劳 + 游戏币）。

与 test.py 的区别：无 Bob 角色，玩家不问 Bob，纯靠自己判断。
用法:
  cd /home/fanlai/Arena && .venv/bin/python role/main.py
"""

import sys
import os
import random
import json
from concurrent.futures import ThreadPoolExecutor

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from role.gambler import Gambler, SYSTEM_PROMPT_NO_BOB
from role.tools import (
    GameState, set_game_state, get_game_state,
    _finalize_auction, set_thread_player,
)
from role.logger import ExperimentLogger
from role.evaluator import Evaluator
from role.auction import AuctionSession, STARTING_PRICE, AUTO_FILL_PRICE, MAX_BID_CAP
from role.config import EXTRA_BODY_THINKING
from role.agents import ArenaAgent
from role.memory_subagent import MemorySubagent

def _get_available_gladiators() -> list[dict]:
    from characters import CHARACTERS
    return [{"char_id": c.id, "name": c.name} for c in CHARACTERS]


def _create_no_bob_agent(gambler: Gambler, logger=None) -> ArenaAgent:
    """创建无工具的赌徒 agent（纯提示词驱动）。"""
    prompt = SYSTEM_PROMPT_NO_BOB.format(player_name=gambler.player_name)
    return ArenaAgent(gambler, prompt, [], gambler.player_name, logger=logger)


MAX_BID_RETRIES = 2  # 平局最大重拍次数（初始1次 + 最多重拍1次 = 共2次）
PREVIEW_COUNTS = {1: 5, 2: 4, 3: 3}  # 每天赛前随机展示的角斗士数量
MAX_PARSE_RETRIES = 3  # 文本解析最大重试次数


def _emit_bankruptcy_final(state, viz, logger, day: int):
    """破产时发射游戏结束事件。"""
    w = state.winner_name
    b = state.bankrupt_player
    print(f"\n{'='*60}")
    print(f"  {b} 破产！游戏立即结束")
    print(f"  {b}: 游戏币 0")
    print(f"  {w}: 游戏币 1600")
    print(f"{'='*60}")
    if viz:
        p = state.player_a
        viz.emit("final_result", {
            "winner": w,
            "chips_a": p.chips if p else 0,
            "chips_b": state.player_b.chips if state.player_b else 0,
            "reason": "bankruptcy",
            "msg": f"{b} 资金不足触发破产！{w} 获得全部 1600 游戏币。",
        })
    logger.log_agent_message("System", "bankruptcy",
        f"Day{day}: {b} 破产，{w} 1600 游戏币")

def _parse_bid(text: str) -> int | None:
    """从回复中解析 <bid>N</bid>，返回出价金额或 None。"""
    import re
    m = re.search(r'<bid>\s*(-?\d+)\s*</bid>', text)
    if m:
        return int(m.group(1))
    return None


def _parse_deploy(text: str) -> dict[int, str]:
    """从回复中解析 <deploy slot="N">char_id</deploy>，返回 {slot: char_id}。"""
    import re
    result = {}
    for m in re.finditer(r'<deploy\s+slot="(\d+)"\s*>\s*(\S+)\s*</deploy>', text):
        slot = int(m.group(1))
        char_id = m.group(2)
        result[slot] = char_id
    return result


def _build_ranking_ground_truth() -> list[dict]:
    """从 tournament_stats.json 读取胜率排名，返回排序后的含名字列表。"""
    stats_file = os.path.join(
        os.path.dirname(__file__), "data", "Bob", "tournament_stats.json")
    with open(stats_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    sorted_ranks = sorted(data["rankings"], key=lambda g: g["win_rate"], reverse=True)
    return [
        {"rank": g["rank"], "name": g["name"], "char_id": g["char_id"], "win_rate": g["win_rate"]}
        for g in sorted_ranks
    ]


def _show_pre_game_info() -> str:
    """生成开局前展示信息：全部角斗士名单（随机顺序）+ 匿名胜率排名。"""
    stats_file = os.path.join(
        os.path.dirname(__file__), "data", "Bob", "tournament_stats.json")
    with open(stats_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    rankings = data["rankings"]

    # 1. 全部 20 名角斗士名单（随机顺序）
    shuffled = random.sample(rankings, len(rankings))
    lines = ["【开局前 — 全部角斗士名单】（共 20 名，顺序随机）"]
    for i, g in enumerate(shuffled):
        lines.append(f"  {i+1}. {g['name']} ({g['char_id']})")

    lines.append("")

    # 2. 匿名胜率排名（从高到低，只显示胜率百分比，不告知对应哪个角斗士）
    lines.append("【开局前 — 匿名胜率排名】（从高到低，不告知对应哪个角斗士）")
    lines.append("胜率数据来源：每两名角斗士对战 200 场，每名角斗士总计 3800 场\n")
    sorted_ranks = sorted(rankings, key=lambda g: g['win_rate'], reverse=True)
    for i, g in enumerate(sorted_ranks):
        pct = f"{g['win_rate']*100:.1f}%"
        lines.append(f"  {i+1}. 胜率 {pct}  ({g['wins']}胜/{g['total']}场, 平{g['ties']}场)")

    return "\n".join(lines)


def _random_gladiator_preview(shown_ids: set[str], count: int) -> tuple[str, set[str]]:
    """从 tournament_stats.json 随机选 count 个未展示过的角斗士。

    Args:
        shown_ids: 已展示过的 char_id 集合
        count: 展示数量

    Returns:
        (预览文本, 更新后的 shown_ids)
    """
    stats_file = os.path.join(
        os.path.dirname(__file__), "data", "Bob", "tournament_stats.json")
    with open(stats_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    available = [g for g in data["rankings"] if g["char_id"] not in shown_ids]
    count = min(count, len(available))
    sample = random.sample(available, count)
    for g in sample:
        shown_ids.add(g["char_id"])

    lines = [f"【今日角斗士胜率预览】（随机展示 {count} 名，双方看到的不一样）"]
    for g in sample:
        pct = f"{g['win_rate']*100:.1f}%"
        lines.append(f"  {g['rank']}. {g['name']} ({g['char_id']}): "
                     f"{g['wins']}胜/{g['total']}场, 平{g['ties']}场, 胜率{pct}")
    return "\n".join(lines), shown_ids


def run_auction_phase(player_a_agent, player_b_agent,
                       player_a: Gambler, player_b: Gambler,
                       logger: ExperimentLogger, day: int = 0):
    """拍卖阶段（无 Bob，暗标+并行）。"""
    print(f"\n── 拍卖阶段: 暗标竞拍（并行，无Bob）──")

    # 保存旧阵容的 point_pool，然后清除阵容
    old_pool_a = player_a.squad.point_pool if player_a.squad else 0
    old_pool_b = player_b.squad.point_pool if player_b.squad else 0
    player_a.squad = None
    player_b.squad = None

    all_glads = _get_available_gladiators()
    auction = AuctionSession(
        all_gladiators=all_glads,
        player_a_name=player_a.player_name,
        player_b_name=player_b.player_name,
    )
    state = get_game_state()
    state.auction = auction
    viz = state.viz  # 可视化发射器

    round_num = 0
    _low_notified_a = False  # 已通知对方 A 游戏币 < 50
    _low_notified_b = False  # 已通知对方 B 游戏币 < 50
    while auction.is_running and len(auction.owner_a) < 3 and len(auction.owner_b) < 3:
        round_num += 1
        show_msg = auction.show()
        if show_msg is None:
            break
        state.auction = auction

        char = auction.current_char
        print(f"\n  拍卖 #{round_num}: {char['name']} ({char['char_id']})")
        if viz:
            viz.emit("auction_show", {"day": day, "round": round_num,
                     "char_name": char['name'], "char_id": char['char_id']})

        for retry in range(1, MAX_BID_RETRIES + 1):
            if retry > 1:
                tie_hint = (
                    f"\n【重拍第 {retry}/{MAX_BID_RETRIES} 次】\n"
                    f"上一轮双方出价相同。请仔细思考以下问题：\n"
                    f"1. 对方出了和你一样的价格，说明他对这个角斗士的估值与你接近。他是否也掌握了类似的情报？\n"
                    f"2. 他是想拿下这个角斗士，还是只想抬价消耗你的活钱？\n"
                    f"3. 基于以上判断，你接下来应该：升高价格以压过对方？降低价格减少风险？保持原价赌对方改变？还是直接弃权？\n"
                    f"请重新做出你的出价决定。"
                )
            else:
                tie_hint = ""

            a_owned = len(auction.owner_a)
            b_owned = len(auction.owner_b)
            a_need = 3 - a_owned
            b_need = 3 - b_owned

            pool_pos = f"（拍卖池第 {auction.shown_index + 1}/{len(auction.pool)} 个）"
            prompt_a = (
                f"【当前角斗士】{char['name']} ({char['char_id']}) {pool_pos}\n"
                f"{show_msg}\n\n"
                f"当前游戏币: {player_a.chips}\n"
                f"已拥有: {a_owned}/3 人 | 剩余空位: {a_need} 个\n"
                f"【拍卖规则】一次性暗标：你只知道自己出的数，看不到对方出价，系统直接比大小。弃权填 0。起拍价{STARTING_PRICE}，最高价{MAX_BID_CAP}。\n"
                f"**双方都扣出价**：无论谁赢，双方均扣自己的出价。\n"
                f"**输方出价→输方自己的奖励池**：你出价输了，你的游戏币会转移到奖励池里。平局不扣，重拍最多{MAX_BID_RETRIES}次。\n"
                f"出价相同重拍，仍相同则跳过。\n\n"
                f"{tie_hint}\n"
                f"请分析后做出出价决定，并在回复末尾单独一行输出:\n"
                f"<bid>金额</bid>\n"
                f"例: <bid>50</bid> 或 <bid>0</bid>（弃权）。必须输出此标签，否则视为弃权。"
            )
            prompt_b = (
                f"【当前角斗士】{char['name']} ({char['char_id']}) {pool_pos}\n"
                f"{show_msg}\n\n"
                f"当前游戏币: {player_b.chips}\n"
                f"已拥有: {b_owned}/3 人 | 剩余空位: {b_need} 个\n"
                f"【拍卖规则】一次性暗标：你只知道自己出的数，看不到对方出价，系统直接比大小。弃权填 0。起拍价{STARTING_PRICE}，最高价{MAX_BID_CAP}。\n"
                f"**双方都扣出价**：无论谁赢，双方均扣自己的出价。\n"
                f"**输方出价→输方自己的奖励池**：你出价输了，你的游戏币会转移到奖励池里。平局不扣，重拍最多{MAX_BID_RETRIES}次。\n"
                f"出价相同重拍，仍相同则跳过。\n\n"
                f"{tie_hint}\n"
                f"请分析后做出出价决定，并在回复末尾单独一行输出:\n"
                f"<bid>金额</bid>\n"
                f"例: <bid>50</bid> 或 <bid>0</bid>（弃权）。必须输出此标签，否则视为弃权。"
            )

            # 暗标出价（纯文本解析，无工具）
            def _invoke_a():
                set_thread_player(player_a.player_name)
                return player_a_agent.invoke(prompt_a, allow_tools=False, label=f"auction_round{round_num}")

            def _invoke_b():
                set_thread_player(player_b.player_name)
                return player_b_agent.invoke(prompt_b, allow_tools=False, label=f"auction_round{round_num}")

            with ThreadPoolExecutor(max_workers=2) as executor:
                future_a = executor.submit(_invoke_a)
                future_b = executor.submit(_invoke_b)
                resp_a = future_a.result()
                resp_b = future_b.result()

            logger.log_agent_message(player_a.player_name, f"auction_r{round_num}_rt{retry}", resp_a)
            logger.log_agent_message(player_b.player_name, f"auction_r{round_num}_rt{retry}", resp_b)

            # 从文本中解析出价
            bid_a = _parse_bid(resp_a)
            bid_b = _parse_bid(resp_b)

            # 兜底重试：未找到出价标签且玩家还有空位，最多重试 MAX_PARSE_RETRIES 次
            if bid_a is None and len(auction.owner_a) < 3:
                for pr in range(MAX_PARSE_RETRIES):
                    set_thread_player(player_a.player_name)
                    retry_resp = player_a_agent.invoke(
                        f"【重试第{pr+1}/{MAX_PARSE_RETRIES}次】"
                        f"你没有输出出价标签！请在回复末尾单独一行输出 <bid>金额</bid>。"
                        f"出价 0 表示弃权，出价 50~150 表示竞拍。不输出标签视为弃权。",
                        allow_tools=False
                    )
                    bid_a = _parse_bid(retry_resp)
                    if bid_a is not None:
                        break
            if bid_a is None:
                bid_a = 0

            if bid_b is None and len(auction.owner_b) < 3:
                for pr in range(MAX_PARSE_RETRIES):
                    set_thread_player(player_b.player_name)
                    retry_resp = player_b_agent.invoke(
                        f"【重试第{pr+1}/{MAX_PARSE_RETRIES}次】"
                        f"你没有输出出价标签！请在回复末尾单独一行输出 <bid>金额</bid>。"
                        f"出价 0 表示弃权，出价 50~150 表示竞拍。不输出标签视为弃权。",
                        allow_tools=False
                    )
                    bid_b = _parse_bid(retry_resp)
                    if bid_b is not None:
                        break
            if bid_b is None:
                bid_b = 0

            # ── 余额校验：出价超过当前游戏币时通知玩家重新出价 ──
            _BALANCE_RETRIES = 2
            for _p_agent, _p, _bid_key in [
                (player_a_agent, player_a, 'a'),
                (player_b_agent, player_b, 'b'),
            ]:
                _bid = bid_a if _bid_key == 'a' else bid_b
                if _bid > 0 and _bid > _p.chips:
                    for _br in range(_BALANCE_RETRIES):
                        if _p.chips < STARTING_PRICE:
                            _hint = (f"你的游戏币只剩 {_p.chips}，不足以支付起拍价 {STARTING_PRICE}。"
                                     f"请出价 0（弃权）。")
                        else:
                            _hint = (f"你的游戏币只有 {_p.chips}，不足支付出价 {_bid}。"
                                     f"请重新出价，不超过 {_p.chips}。")
                        set_thread_player(_p.player_name)
                        _retry_resp = _p_agent.invoke(
                            f"【余额不足警告 - 第{_br+1}/{_BALANCE_RETRIES}次重试】{_hint}\n"
                            f"请在回复末尾单独一行输出 <bid>金额</bid>。",
                            allow_tools=False,
                        )
                        logger.log_agent_message(_p.player_name, f"auction_r{round_num}_balance_retry{_br+1}", _retry_resp)
                        _new_bid = _parse_bid(_retry_resp)
                        if _new_bid is not None:
                            if _bid_key == 'a':
                                bid_a = _new_bid
                            else:
                                bid_b = _new_bid
                            _bid = _new_bid
                            if _bid <= _p.chips:
                                break  # 新出价合法
                    else:
                        # 重试耗尽，强制截断到余额；若截断后低于起拍价则设为 0
                        _capped = min(_bid, _p.chips)
                        if _capped < STARTING_PRICE:
                            _capped = 0
                        if _bid_key == 'a':
                            bid_a = _capped
                        else:
                            bid_b = _capped
                        print(f"    ⚠ {_p.player_name} 余额不足重试耗尽，出价 {_bid} → {_capped}")

            print(f"    {player_a.player_name} 暗标: {bid_a} 币  |  {player_b.player_name} 暗标: {bid_b} 币")
            if viz:
                viz.emit("auction_bid", {"bid_a": bid_a, "bid_b": bid_b})

            result = auction.sealed_bid_round(
                bid_a, bid_b,
                player_a.player_name, player_b.player_name,
                round_num=round_num,
            )
            print(f"    → {result['msg']}")

            # 先扣款（确保通知里显示的是扣后的余额）
            # 赢方出价 → 角斗士 point（通过比赛结算流转）；输方出价 → reward_pool（最终结算兑回）
            if result["result"] == "win":
                if bid_a > 0:
                    player_a.spend_chips(bid_a)
                    if state.bob is not None:
                        state.bob.arena_chips += bid_a
                if bid_b > 0:
                    player_b.spend_chips(bid_b)
                    if state.bob is not None:
                        state.bob.arena_chips += bid_b
                # 输方的出价转入输方自己的奖励池
                if result["winner"] == player_a.player_name:
                    if bid_b > 0:
                        player_b.reward_pool += bid_b
                else:
                    if bid_a > 0:
                        player_a.reward_pool += bid_a

            # 向双方通知拍卖结果（各自视角：只展示自己的游戏币，隐藏对手游戏币）
            round_header = f"【第{round_num}轮拍卖结果】\n"
            if result["result"] == "win":
                winner_name = result["winner"]
                winner_amount = result["amount"]
                w_chips = player_a.chips if winner_name == player_a.player_name else player_b.chips
                w_owned = len(auction.owner_a) if winner_name == player_a.player_name else len(auction.owner_b)
                l_name = player_b.player_name if winner_name == player_a.player_name else player_a.player_name
                l_chips = player_b.chips if winner_name == player_a.player_name else player_a.chips
                l_owned = len(auction.owner_b) if winner_name == player_a.player_name else len(auction.owner_a)
                # 赢家视角
                notify_winner = (
                    f"{round_header}"
                    f"{winner_name} 以 {winner_amount} 游戏币拍下角斗士: {char['name']}({char['char_id']})。\n\n"
                    f"当前状态:\n"
                    f"  {winner_name}: 游戏币 {w_chips} | 已拥有 {w_owned}/3 人\n"
                    f"  对手 | 已拥有 {l_owned}/3 人\n\n"
                    f"请思考：对手可能做出了什么行动？是出价低，还是弃权了？"
                    f"他是知道这个角斗士的胜率？还是想要以低价甚至弃权消耗你的游戏币？"
                    f"这对接下来的拍卖有什么影响？"
                )
                # 输家视角
                notify_loser = (
                    f"{round_header}"
                    f"{winner_name} 以 {winner_amount} 游戏币拍下角斗士: {char['name']}({char['char_id']})。\n\n"
                    f"当前状态:\n"
                    f"  {l_name}: 游戏币 {l_chips} | 已拥有 {l_owned}/3 人\n"
                    f"  对手 | 已拥有 {w_owned}/3 人\n\n"
                    f"请思考：对手这次出价透露出什么信息？"
                    f"他是知道这个角斗士的胜率？还是想要以更高的价格买入角斗士让你浪费掉游戏币？"
                    f"这对接下来的拍卖有什么影响？"
                )
                if winner_name == player_a.player_name:
                    notify_a = notify_winner
                    notify_b = notify_loser
                else:
                    notify_a = notify_loser
                    notify_b = notify_winner
            elif result["result"] == "tie":
                if retry < MAX_BID_RETRIES:
                    notify_a = f"{round_header}双方出价相同，平局不扣币，思考接下来的出价策略\
                        是保持不变，还是出更多或者更少，还是弃权。思考完后请重新出价。"
                    notify_b = notify_a
                else:
                    notify_a = f"{round_header}{MAX_BID_RETRIES+1}次平局，{char['name']} 回拍卖池，跳过。进入下一轮。"
                    notify_b = notify_a
            else:  # skip
                notify_a = f"{round_header}{result['msg']}"
                notify_b = notify_a

            player_a_agent.message_history.append({"role": "user", "content": notify_a})
            player_b_agent.message_history.append({"role": "user", "content": notify_b})

            # 检查单方游戏币 < 50：通知富裕方对手已无力竞拍
            a_low = player_a.chips < 50 and len(auction.owner_a) < 3
            b_low = player_b.chips < 50 and len(auction.owner_b) < 3
            if a_low and not b_low and not _low_notified_a:
                _low_notified_a = True
                player_b_agent.message_history.append({"role": "user", "content": (
                    f"【系统提示】{player_a.player_name} 的游戏币已不足 50（当前 {player_a.chips}），"
                    f"无法支撑后续拍卖。在接下来的拍卖中，对方只能弃权（出价 0）。"
                    f"系统仍会按顺序展示角斗士，请你正常出价竞拍。"
                    f"你弃权系统会按顺序展示下一个角斗士。"
                    f"注意：对方后续的角斗士将通过奖励池积蓄来支付系统的随机分配。"
                )})
            elif b_low and not a_low and not _low_notified_b:
                _low_notified_b = True
                player_a_agent.message_history.append({"role": "user", "content": (
                    f"【系统提示】{player_b.player_name} 的游戏币已不足 50（当前 {player_b.chips}），"
                    f"无法支撑后续拍卖。在接下来的拍卖中，对方只能弃权（出价 0）。"
                    f"系统仍会按顺序展示角斗士，请你正常出价竞拍。"
                    f"你弃权系统会按顺序展示下一个角斗士。"
                    f"注意：对方后续的角斗士将通过奖励池积蓄来支付系统的随机分配。"
                )})

            if viz and result["result"] == "win":
                viz.emit("auction_result", {
                    "day": day, "round": round_num,
                    "char_name": char['name'], "char_id": char['char_id'],
                    "winner": result["winner"], "amount": result["amount"],
                    "chips_a": player_a.chips, "chips_b": player_b.chips,
                    "owned_a": len(auction.owner_a), "owned_b": len(auction.owner_b),
                    "reward_pool_a": player_a.reward_pool, "reward_pool_b": player_b.reward_pool,
                })

            # 记录对手操作
            if result["result"] == "win":
                winner = player_a if result["winner"] == player_a.player_name else player_b
                loser = player_b if result["winner"] == player_a.player_name else player_a
                w_amt = result["amount"]
                auction_entry = (
                    f"第{round_num}轮拍卖: {winner.player_name} "
                    f"以 {w_amt} 游戏币拍下 {char['name']}({char['char_id']})"
                )
                # 双方都记录（各自看到对手的操作）
                loser._opponent_actions.append(auction_entry)
                winner._opponent_actions.append(auction_entry)

            logger.log_auction_round(
                day, round_num, char['name'], char['char_id'],
                bid_a, bid_b, result["result"], retry,
            )

            if result["result"] == "win":
                break
            elif result["result"] == "tie":
                if retry < MAX_BID_RETRIES:
                    continue
                else:
                    auction._advance_to_next()
                    print(f"    → {MAX_BID_RETRIES+1} 次平局，{char['name']} 回池，跳过。")
                    break
            elif result["result"] == "skip":
                break

        state.auction = auction

    if player_a.squad is None or player_b.squad is None:
        auction.state = "end"
        fill_msg = auction._auto_assign_remaining()
        bankrupt = _finalize_auction(state, old_pool_a, old_pool_b)
        if bankrupt:
            _emit_bankruptcy_final(state, viz, logger, day)
            state.auction = auction
            return auction  # 返回，调用方检测到破产
        if viz:
            if fill_msg:
                viz.emit("auto_fill", {"msg": fill_msg})
            viz.emit("squad_update", {
                "chips_a": player_a.chips, "chips_b": player_b.chips,
                "owned_a": len(auction.owner_a), "owned_b": len(auction.owner_b),
                "pool_a": player_a.squad.point_pool if player_a.squad else 0,
                "pool_b": player_b.squad.point_pool if player_b.squad else 0,
                "reward_pool_a": player_a.reward_pool, "reward_pool_b": player_b.reward_pool,
            })

    print(f"\n  {player_a.player_name} 阵容: {[(c['name'], c.get('point',0)) for c in auction.owner_a]} "
          f"游戏币: {player_a.chips}")
    print(f"  {player_b.player_name} 阵容: {[(c['name'], c.get('point',0)) for c in auction.owner_b]} "
          f"游戏币: {player_b.chips}")

    logger.log_agent_message("System", "auction_result", auction.summary())
    state.auction = auction
    return auction


def run_deployment_phase(gambler_agent, gambler: Gambler, opponent: Gambler,
                          logger: ExperimentLogger, day: int, match_slots: list[int]):
    """部署阶段（无 Bob 咨询，纯靠自己判断）。单槽用 deploy_first_match，多槽用 deploy_remaining_matches。"""
    state = get_game_state()
    viz = state.viz  # 可视化发射器
    slots_list = sorted(match_slots)
    slots_str = "、".join(str(s) for s in slots_list)

    # 注入阵容信息到提示词
    squad_info = gambler.squad.summary() if gambler.squad else "无阵容"

    if slots_list == [1]:
        print(f"  {gambler.player_name} 部署第1局中...")
        deploy_msg = (
            f"现在是第{day}天，你需要安排第 1 局比赛的出战角斗士。\n\n"
            f"【你的阵容】\n{squad_info}\n\n"
            f"【规则提示】\n"
            f"  比赛不下注——游戏币只在拍卖环节支出。\n"
            f"  第 2 局夺取量 ×1.5（min(胜方point,败方point) × 1.5）。\n"
            f"  没有属性相克——判断强弱只看胜率，不要根据名字脑补克制。\n"
            f"  角斗士每天只能出战一轮。\n"
            f"  【每日胜者奖励：死钱变活钱】3 局结束后，胜场数多者为今日胜者。胜者奖励池 ≤0 无转换；\n"
            f"  0<pool<50 全部兑为游戏币；pool≥50 兑 50 游戏币。\n\n"
            f"【你的对手】{opponent.player_name}\n\n"
            f"请分析后做出部署决定，并在回复末尾单独一行输出:\n"
            f"<deploy slot=\"1\">char_id</deploy>\n"
            f"必须输出此标签，否则视为未部署。当前只需要部署第一个角斗士"
        )
    else:
        print(f"  {gambler.player_name} 部署第{slots_str}局中...")
        deploy_msg = (
            f"现在是第{day}天，你需要安排第 {slots_str} 局比赛的出战角斗士。\n\n"
            f"【你的阵容】\n{squad_info}\n\n"
            f"【规则提示】\n"
            f"  比赛不下注——游戏币只在拍卖环节支出。\n"
            f"  **第 2 局夺取量 ×1.5**（min(胜方point,败方point) × 1.5）。\n"
            f"  每局胜方夺取 min(己方point, 败方point)，结算后 point 归奖励池。\n"
            f"  同一天不能用同一个角斗士两次。\n"
            f"  没有属性相克——判断强弱只看胜率，不要根据名字脑补克制。\n"
            f"  角斗士每天只能出战一轮。\n"
            f"  【每日胜者奖励：死钱变活钱】3 局结束后，胜场数多者为今日胜者。胜者奖励池 ≤0 无转换；\n"
            f"  0<pool<50 全部兑为游戏币；pool≥50 兑 50 游戏币。\n\n"
            f"【你的对手】{opponent.player_name}\n\n"
            f"请分析后做出部署决定，并在回复末尾单独一行输出（多局写多行）:\n"
            f"<deploy slot=\"2\">char_id</deploy>\n"
            f"<deploy slot=\"3\">char_id</deploy>\n"
            f"必须输出此标签，否则视为未部署。当前需要部署第二个和第三个角斗士。"
        )

    slots_label = "deploy_match1" if slots_list == [1] else "deploy_match23"
    response = gambler_agent.invoke(deploy_msg, allow_tools=False, label=slots_label)
    logger.log_agent_message(gambler.player_name, f"deployment_{slots_str}", response)

    # 从文本中解析部署
    parsed = _parse_deploy(response)
    for slot in slots_list:
        if slot in parsed:
            gambler.deployments[slot] = parsed[slot]

    # 兜底重试：未部署的 slot
    missing = [s for s in slots_list if s not in gambler.deployments]
    if missing:
        missing_str = "、".join(str(s) for s in missing)
        retry_msg = (
            f"你还没有为第 {missing_str} 局输出部署标签！"
            f"请在回复末尾输出 <deploy slot=\"N\">char_id</deploy>。"
        )
        retry_resp = gambler_agent.invoke(retry_msg, allow_tools=False)
        parsed2 = _parse_deploy(retry_resp)
        for slot in missing:
            if slot in parsed2:
                gambler.deployments[slot] = parsed2[slot]

    deploy_result = {s: gambler.deployments[s] for s in slots_list if s in gambler.deployments}
    print(f"  {gambler.player_name} 部署: {deploy_result}")
    logger.log_agent_message(gambler.player_name, "deployment_final", str(gambler.deployments))
    if viz:
        # 构建 char_id → name 查找表
        _name_lookup = {}
        if gambler.squad:
            for m in gambler.squad.members:
                _name_lookup[m.char_id] = m.name
        for slot, char_id in deploy_result.items():
            viz.emit("deployment", {"player": gambler.player_name, "day": day,
                     "slot": slot, "slots": str(slot),
                     "char_id": char_id, "char_name": _name_lookup.get(char_id, char_id)})
    if deploy_result:
        logger.log_deployment(day, gambler.player_name, deploy_result)


def run_match_phase(player_a: Gambler, player_b: Gambler,
                     logger: ExperimentLogger, day: int, slots: list[int] | None = None):
    """运行指定局次的比赛。slots=None 默认全部 3 局。

    新结算规则：
    - 胜方夺取 min(己方point, 败方point)
    - 第2局 ×1.5
    - 平局各自 point 归奖励池
    - 结算后角斗士 point 清零
    """
    if slots is None:
        slots = [1, 2, 3]
    slots_str = "、".join(str(s) for s in slots)
    print(f"\n── 比赛阶段: 第{slots_str}局 1v1 ──")
    state = get_game_state()
    viz = state.viz  # 可视化发射器

    for slot in slots:
        char_a = player_a.deployments.get(slot)
        char_b = player_b.deployments.get(slot)

        if not char_a or not char_b:
            print(f"  ✗ 第{slot}局部署不完整")
            continue

        hp_a = player_a.squad.get_hp_multiplier(char_a)
        hp_b = player_b.squad.get_hp_multiplier(char_b)

        player_a.squad.mark_used(char_a)
        player_b.squad.mark_used(char_b)

        point_a = player_a.squad._find(char_a).point
        point_b = player_b.squad._find(char_b).point

        # 运行比赛（不下注）
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        if viz:
            viz.emit("match_start", {"day": day, "slot": slot,
                     "char_a": char_a, "char_b": char_b})
        from role.match_runner import run_headless_match
        game_result = run_headless_match(
            [char_a, char_b],
            hp_multipliers={char_a: hp_a, char_b: hp_b}
        )

        if game_result["winner"] is None:
            # 平局/超时：各自 point 归入各自奖励池
            print(f"  ✗ 第{slot}局超时/平局，各自 point 归池")
            for p, cid in [(player_a, char_a), (player_b, char_b)]:
                member = p.squad._find(cid) if p.squad else None
                if member:
                    p.squad.settle_points_to_pool(cid, member.point)
            state.match_history.append({
                "winner": None,
                "loser": None,
                "winner_char_id": char_a,
                "loser_char_id": char_b,
                "tie": True,
                "_p1_name": player_a.player_name,
                "_p2_name": player_b.player_name,
                "game_result": game_result,
                "point_transferred": 0,
                "multiplier": 1.0,
            })
            logger.log_match_result(day, slot, state.match_history[-1])
            if viz:
                viz.emit("match_result", {
                    "day": day, "slot": slot,
                    "winner": None, "loser": None,
                    "winner_char": char_a, "loser_char": char_b,
                    "point_transfer": 0, "multiplier": 1.0,
                    "tie": True,
                    "pool_a": player_a.squad.point_pool if player_a.squad else 0,
                    "pool_b": player_b.squad.point_pool if player_b.squad else 0,
                    "reward_pool_a": player_a.reward_pool, "reward_pool_b": player_b.reward_pool,
                })
            continue

        from characters import CHARACTERS
        a_char = next(c for c in CHARACTERS if c.id == char_a)

        if game_result["winner"] == a_char.name:
            winner, loser = player_a, player_b
            winner_char, loser_char = char_a, char_b
            w_pt, l_pt = point_a, point_b
        else:
            winner, loser = player_b, player_a
            winner_char, loser_char = char_b, char_a
            w_pt, l_pt = point_b, point_a

        # 第 2 局夺取量 ×1.5
        multiplier = 1.5 if slot == 2 else 1.0
        transfer = int(min(w_pt, l_pt) * multiplier)

        # 胜方奖励池 += 己方point + 夺取
        winner.squad.settle_points_to_pool(winner_char, w_pt + transfer)
        # 败方奖励池 += 己方point - 夺取（可为负）
        loser.squad.settle_points_to_pool(loser_char, l_pt - transfer)

        mult_str = f" ×{multiplier}" if multiplier != 1.0 else ""
        print(f"  第{slot}局: 胜方 {winner.player_name}, "
              f"min({w_pt},{l_pt}){mult_str}={transfer}, "
              f"胜方池+{w_pt + transfer}, 败方池+{l_pt - transfer}")
        if viz:
            viz.emit("match_result", {
                "day": day, "slot": slot,
                "winner": winner.player_name,
                "loser": loser.player_name,
                "winner_char": winner_char, "loser_char": loser_char,
                "point_transfer": transfer, "multiplier": multiplier,
                "pool_a": player_a.squad.point_pool if player_a.squad else 0,
                "pool_b": player_b.squad.point_pool if player_b.squad else 0,
                "reward_pool_a": player_a.reward_pool, "reward_pool_b": player_b.reward_pool,
            })

        state.match_history.append({
            "winner": winner.player_name,
            "loser": loser.player_name,
            "winner_char_id": winner_char,
            "loser_char_id": loser_char,
            "game_result": game_result,
            "point_transferred": transfer,
            "multiplier": multiplier,
            "winner_pool_delta": w_pt + transfer,
            "loser_pool_delta": l_pt - transfer,
        })
        logger.log_match_result(day, slot, state.match_history[-1])

        # 记录对手部署操作
        from characters import CHARACTERS as _all_chars
        _char_map = {c.id: c.name for c in _all_chars}
        w_name = _char_map.get(winner_char, winner_char)
        l_name = _char_map.get(loser_char, loser_char)
        match_entry = (
            f"第{slot}局: {winner.player_name} 派 {w_name} 出战，"
            f"{loser.player_name} 派 {l_name} 出战 → {winner.player_name} 胜"
        )
        loser._opponent_actions.append(match_entry)
        winner._opponent_actions.append(match_entry)


def _build_match_result_text(player: Gambler, opponent: Gambler) -> str:
    """构建最近一场比赛的数据文本（直接注入 prompt）。"""
    state = get_game_state()
    if not state.match_history:
        return "（暂无比赛数据）"
    last = state.match_history[-1]
    game = last.get("game_result", {})
    is_tie = last.get("tie", False)
    if is_tie:
        # 平局：双方均未获胜，不能用 winner/loser 判定 my_char
        is_p1 = player.player_name == last.get("_p1_name")
        my_char = last['winner_char_id'] if is_p1 else last['loser_char_id']
        opp_char = last['loser_char_id'] if is_p1 else last['winner_char_id']
        result_text = "平局"
        pool_delta = 0
    else:
        won = last['winner'] == player.player_name
        my_char = last.get('winner_char_id', '?') if won else last.get('loser_char_id', '?')
        opp_char = last.get('loser_char_id', '?') if won else last.get('winner_char_id', '?')
        result_text = '你赢了' if won else '你输了'
        pool_delta = last.get("winner_pool_delta", 0) if won else last.get("loser_pool_delta", 0)
    point_moved = last.get("point_transferred", 0)
    mult = last.get("multiplier", 1.0)

    mult_str = f" ×{mult}" if mult != 1.0 else ""
    return (
        f"【上一局比赛数据】\n"
        f"结果: {result_text}（对手: {opponent.player_name}）\n"
        f"你出战: {my_char} | 对手出战: {opp_char}\n"
        f"point 夺取量: {point_moved}{mult_str}\n"
        f"奖励池变动: {'+' + str(pool_delta) if pool_delta >= 0 else str(pool_delta)}\n"
        f"当前游戏币: {player.chips}\n"
        f"奖励池 point: {player.squad.point_pool if player.squad else 0}\n"
        f"阵容: {player.squad.summary() if player.squad else '无'}"
    )


def _reflect_player(player_agent, player: Gambler, opponent: Gambler,
                     logger: ExperimentLogger, day: int, stage: str,
                     prompt_template: str) -> str:
    """通用反思：直接注入比赛数据，不依赖工具。返回 response 字符串。"""
    match_info = _build_match_result_text(player, opponent)
    msg = prompt_template.format(
        day=day, stage=stage,
        match_info=match_info,
        opponent=opponent.player_name,
    )
    response = player_agent.invoke(msg, allow_tools=False, label=f"reflect_{stage}")
    logger.log_agent_message(player.player_name, f"reflect_{stage}", response)
    return response


# ── 各阶段反思模板 ──

PROMPT_MATCH1 = """第{day}天的第1局比赛已结束。

{match_info}

请分析：
1. 对手第1局为什么选择这个角斗士？
2. 根据第1局的结果，对手在第2、3局可能会如何调整？
3. 考虑到第2局夺取量×1.5，你第2、3局应该如何部署？想好你的部署策略。

【注意】这是你私下的自我反思，直接输出分析文字。本环节没有工具可用，不要尝试调用工具或写 function call。"""

PROMPT_DAY_SUMMARY = """第{day}天比赛全部结束，以下是今日复盘。

{player_info}

请完成以下三件事：

1. 【填写匿名胜率排名表】下面是开局前展示的 20 名胜率排名（从高到低），但原来没有名字。
   请将你**已经确认或推测**出的角色名字填入对应位置。不确定的可以留空。
   格式：
   （98.4%）--> （角色名/暂时不确定） [来源：系统情报/对手操作推测]
   （88.2%）--> （角色名/暂时不确定） [来源：...]
   ...
   （1.4%）--> （角色名/暂时不确定） [来源：...]

2. 【推断对手游戏币区间】推算对手可用于拍卖的游戏币范围。
   **重要：只需计算「游戏币」，不要考虑奖励池（reward_pool）。奖励池是死钱，不能用于拍卖。**

   计算方法：
   a) 对手游戏币 = 初始800 + 每日胜者奖励收入 - 拍卖总支出
   b) 拍卖总支出：回顾对手的拍卖出价和系统补齐
   c) 每日胜者奖励收入：回顾每日胜者结果——
      - 对手是胜者时：对手奖励池≤0→收入0；0<对手奖励池<50→收入对手奖励池数额；对手奖励池≥50→收入50
      - 对手非胜者时：不转换

    **重要提醒：对手作为拍卖输的一方时，系统不显示他的出价，请把该因素考虑进去，估计对手的下限**

   严格遵从以下输出格式：
   ##对手游戏币估计在**下限~上限**之间##
   推理依据：...

3. 【明天策略】基于以上分析，明天的总体策略规划。

【注意】这是你私下的自我反思，直接输出分析文字。"""


def _build_anonymous_ranking_for_prompt() -> str:
    """构建匿名胜率排名表，供玩家在复盘时填写。"""
    stats_file = os.path.join(
        os.path.dirname(__file__), "data", "Bob", "tournament_stats.json")
    with open(stats_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    sorted_ranks = sorted(data["rankings"], key=lambda g: g['win_rate'], reverse=True)
    lines = [""]
    for i, g in enumerate(sorted_ranks):
        pct = f"{g['win_rate']*100:.1f}%"
        lines.append(f"    ({pct})--> __________  [来源: __________]")
    return "\n".join(lines)


def _build_day_summary_text(player: Gambler, daily_winner_info: str) -> str:
    """构建全天复盘数据文本（包含对手操作记录和每日胜者信息）。"""
    state = get_game_state()
    today_matches = state.match_history[-3:]
    my_wins = sum(1 for m in today_matches if m.get('winner') == player.player_name)

    lines = [
        f"当前游戏币: {player.chips}",
        f"奖励池 point: {player.squad.point_pool if player.squad else 0}",
        f"今日胜场: {my_wins}",
    ]
    if player.squad:
        lines.append(f"你的阵容疲劳状态:\n{player.squad.summary()}")

    # 每日胜者信息
    lines.append(f"\n【每日胜者奖励结果】")
    lines.append(daily_winner_info)

    # 对手操作记录
    if hasattr(player, '_opponent_actions') and player._opponent_actions:
        lines.append(f"\n【对手操作记录】")
        for action in player._opponent_actions:
            lines.append(f"  - {action}")

    # 今日比赛记录
    lines.append(f"\n【今日比赛记录】")
    for i, m in enumerate(today_matches):
        is_tie = m.get("tie", False)
        if is_tie:
            is_p1 = player.player_name == m.get("_p1_name")
            my_c = m['winner_char_id'] if is_p1 else m['loser_char_id']
            opp_c = m['loser_char_id'] if is_p1 else m['winner_char_id']
            result = "平"
        else:
            won = m['winner'] == player.player_name
            my_c = m.get('winner_char_id', '?') if won else m.get('loser_char_id', '?')
            opp_c = m.get('loser_char_id', '?') if won else m.get('winner_char_id', '?')
            result = '赢' if won else '输'
        pt = m.get('point_transferred', 0)
        mult = m.get('multiplier', 1.0)
        mult_str = f" ×{mult}" if mult != 1.0 else ""
        lines.append(
            f"  第{i+1}局: {result} "
            f"(我方:{my_c} vs 对手:{opp_c}) point转移:{pt}{mult_str}"
        )

    # 匿名排名表
    lines.append(f"\n【匿名胜率排名表（待填写）】")
    lines.append(_build_anonymous_ranking_for_prompt())

    return "\n".join(lines)


# ── 辅助函数（评估用）──────────────────────────────────────────────────────


def _extract_assistant_messages(agent) -> str:
    """从 agent 的 message_history 中提取所有 assistant content，用换行拼接。"""
    messages = []
    for msg in agent.message_history:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if content:
                messages.append(content)
    return "\n\n---\n\n".join(messages)


def _parse_preview_history(history: list[str]) -> list[dict]:
    """解析预览历史文本为结构化数据 [{char_id, name, win_rate, wins, total, draws}, ...]。

    预览文本格式：
      1. 暗夜猎手 (hunter): 3739胜/3800场, 平0场, 胜率98.4%
    """
    import re
    result = []
    seen = set()
    for text in history:
        for line in text.split("\n"):
            # 匹配: "  排名. 名称 (char_id): 胜场/总场, 平X场, 胜率XX.X%"
            m = re.search(
                r'\d+\.\s*(.+?)\s*\((\w+)\):\s*(\d+)胜/(\d+)场,\s*平(\d+)场,\s*胜率([\d.]+)%',
                line
            )
            if m:
                name = m.group(1).strip()
                char_id = m.group(2)
                wins = int(m.group(3))
                total = int(m.group(4))
                draws = int(m.group(5))
                win_rate = float(m.group(6)) / 100.0
                if char_id not in seen:
                    seen.add(char_id)
                    result.append({
                        "char_id": char_id, "name": name,
                        "win_rate": win_rate, "wins": wins,
                        "total": total, "draws": draws,
                    })
    return result


def _estimate_opponent_chips(opp, auction) -> str:
    """从初始 800 减去可观察花费，估算对手游戏币范围。

    Returns:
        描述字符串，如 "约 600~700 游戏币"
    """
    initial = 800
    min_spent = 0
    max_spent = 0

    # 从 bid_history 中提取对手的出价
    opp_name = opp.player_name
    for record in (auction.bid_history if auction else []):
        bids = record.get("bids", {})
        opp_bid = bids.get(opp_name, 0)
        if record.get("result") == "win":
            # 赢了或输了都花了出价
            min_spent += opp_bid
            max_spent += opp_bid
        elif record.get("result") == "skip":
            pass

    # 系统补齐费用（从拍卖结果推算）
    if opp.squad:
        for member in opp.squad.members:
            if getattr(member, 'auto_filled', False) or member.point == 85:
                min_spent += 85
                max_spent += 85

    # 考虑奖励池转换（每日胜者最多50）
    est_low = max(0, initial - max_spent)
    est_high = max(0, initial - min_spent + 50)

    if est_low == est_high:
        return f"约 {est_low} 游戏币"
    return f"约 {est_low}~{est_high} 游戏币"


def _inject_memory(player_name: str, agent: ArenaAgent, day: int,
                   memory_subagent: MemorySubagent):
    """每天开始时注入前一天的记忆到 agent 上下文。"""
    if day == 1:
        return  # 第1天没有记忆

    base = memory_subagent.memory_dir
    parts = []

    # 1. 对手模型（跨天累积）
    opponent_path = base / "opponent_model.md"
    if opponent_path.exists():
        body = opponent_path.read_text(encoding="utf-8")
        parts.append(_extract_md_body(body))

    # 2. 角斗士认知（跨天累积）
    gladiator_path = base / "gladiator_knowledge.md"
    if gladiator_path.exists():
        body = gladiator_path.read_text(encoding="utf-8")
        parts.append(_extract_md_body(body))

    # 3. 前一天笔记
    prev_day_path = base / f"day{day-1}.md"
    if prev_day_path.exists():
        body = prev_day_path.read_text(encoding="utf-8")
        parts.append(_extract_md_body(body))

    if not parts:
        return

    body = "\n\n---\n\n".join(parts)
    memory_msg = (
        f"[系统记忆] 以下是你在前 {day-1} 天积累的经验，请在做决策时参考：\n\n{body}"
    )
    agent.message_history.append({"role": "user", "content": memory_msg})
    print(f"  [记忆] 已注入 {player_name} 的历史记忆（{len(parts)} 个文件）")


def _extract_md_body(md_text: str) -> str:
    """提取 markdown 正文（去掉 YAML frontmatter）。"""
    lines = md_text.split("\n")
    if lines and lines[0].strip() == "---":
        end = 1
        while end < len(lines) and lines[end].strip() != "---":
            end += 1
        return "\n".join(lines[end+1:]).strip()
    return md_text.strip()


def run_experiment(visualizer=None):
    """运行无 Bob 精简版实验。

    Args:
        visualizer: 可选 Visualizer 实例，非 None 时会推送可视化事件
    """
    viz = visualizer  # 局部别名
    player_a = Gambler(player_name="斑目貘", assets=100)
    player_b = Gambler(player_name="夜神月", assets=100)

    state = GameState(player_a=player_a, player_b=player_b)
    set_game_state(state)
    state.viz = viz  # 供 run_auction_phase / run_match_phase 等函数访问

    # 对手操作追踪
    player_a._opponent_actions = []
    player_b._opponent_actions = []

    logger = ExperimentLogger()
    evaluator = Evaluator(logger=logger)
    player_a_agent = _create_no_bob_agent(player_a, logger=logger)
    player_b_agent = _create_no_bob_agent(player_b, logger=logger)

    # ── 记忆模块初始化 ──
    import os as _os
    _memory_base = _os.path.join(_os.path.dirname(__file__), "memory")

    # 重置记忆文件：清除上局残留，恢复模板状态
    from role.memory_tools import reset_player_memories
    reset_player_memories(player_a.player_name, f"{_memory_base}/{player_a.player_name}")
    reset_player_memories(player_b.player_name, f"{_memory_base}/{player_b.player_name}")

    memory_a = MemorySubagent(player_a.player_name, f"{_memory_base}/{player_a.player_name}", day=1)
    memory_b = MemorySubagent(player_b.player_name, f"{_memory_base}/{player_b.player_name}", day=1)

    # 设置回调：每次玩家 agent 产出完整输出，自动提交到记忆 subagent
    player_a_agent.on_response = lambda label, content: memory_a.submit(label, content)
    player_b_agent.on_response = lambda label, content: memory_b.submit(label, content)

    print("=" * 60)
    print("  Arena 新赌局 —— 3天×3局 拍卖竞技（无Bob）")
    print("=" * 60)
    print()

    # 初始游戏币
    print("── 初始游戏币 ──")
    player_a.chips = 800
    player_b.chips = 800
    print(f"  {player_a.player_name}: {player_a.chips} 游戏币")
    print(f"  {player_b.player_name}: {player_b.chips} 游戏币")

    print()
    print("── 初始状态 ──")
    print(player_a.summary())
    print(player_b.summary())

    # 开局前：展示全部 20 名角斗士名单（随机顺序）+ 匿名胜率排名
    print(f"\n{'='*60}")
    print(f"  开局前 — 角斗士名单与匿名胜率排名")
    print(f"{'='*60}")
    print()
    pre_game_info = _show_pre_game_info()
    print(pre_game_info)
    if viz:
        viz.emit("game_start", {
            "player_a": player_a.player_name, "player_b": player_b.player_name,
            "rules_summary": "双方初始各800游戏币 | 每天暗标拍卖3名角斗士 | 3局1v1比赛 | 第2局×1.5 | 无属性相克 | 3天后奖励池1:1兑回"
        })
        viz.emit("progress", {"msg": "正在向双方展示开局信息..."})
    player_a_agent.invoke(pre_game_info + "\n\n以上是开局前展示的全部 20 名角斗士名单（随机顺序）和匿名胜率排名（高到低）。注意：胜率百分比与名单顺序无关，无法对应。请回复确认收到。", allow_tools=False)
    player_b_agent.invoke(pre_game_info + "\n\n以上是开局前展示的全部 20 名角斗士名单（随机顺序）和匿名胜率排名（高到低）。注意：胜率百分比与名单顺序无关，无法对应。请回复确认收到。", allow_tools=False)

    # 开局前规则解读（双线程并行）
    print(f"\n{'='*60}")
    print(f"  开局前 — 规则解读")
    print(f"{'='*60}")
    print()
    rules_interpretation_prompt = """现在是开局前的规则解读环节。请结合你已知的所有信息，对游戏规则进行全面分析：

1. 【游戏机制理解】用自己的话总结：游戏币、奖励池、拍卖、比赛、point 结算、疲劳机制的关系和运作方式。
2. 【关键策略点】哪些规则对你的胜率影响最大？如何利用这些规则？

请直接输出你的分析，本环节不需要使用工具。"""

    def _interpret_a():
        return player_a_agent.invoke(rules_interpretation_prompt, allow_tools=False, label="rules_interpretation")

    def _interpret_b():
        return player_b_agent.invoke(rules_interpretation_prompt, allow_tools=False, label="rules_interpretation")

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(_interpret_a)
        future_b = executor.submit(_interpret_b)
        interpretation_a = future_a.result()
        interpretation_b = future_b.result()

    print(f"\n── {player_a.player_name} 的规则解读 ──")
    print(interpretation_a)
    print(f"\n── {player_b.player_name} 的规则解读 ──")
    print(interpretation_b)
    logger.log_agent_message(player_a.player_name, "rules_interpretation", interpretation_a)
    logger.log_agent_message(player_b.player_name, "rules_interpretation", interpretation_b)
    if viz:
        viz.emit("agent_message", {"player": player_a.player_name, "content": interpretation_a,
                 "label": "规则解读", "role": "speak"})
        viz.emit("agent_message", {"player": player_b.player_name, "content": interpretation_b,
                 "label": "规则解读", "role": "speak"})
        viz.emit("rules_done", {})

    # 追踪每个玩家已展示过的角斗士（跨天不重复）
    shown_a: set[str] = set()
    shown_b: set[str] = set()
    # 累积预览记录
    preview_history_a: list[str] = []
    preview_history_b: list[str] = []
    # 每天数据汇总（供最终分析）
    all_days_data: list[dict] = []

    # 3 天循环
    for day in range(1, 4):
        state.day_number = day
        print(f"\n{'='*60}")
        print(f"  第 {day} 天")
        print(f"{'='*60}")

        # ── 记忆注入：每天开始前注入历史记忆 ──
        memory_a.set_day(day)
        memory_b.set_day(day)
        _inject_memory(player_a.player_name, player_a_agent, day, memory_a)
        _inject_memory(player_b.player_name, player_b_agent, day, memory_b)

        # Phase 0: 赛前角斗士胜率预览（每天数量不同，跨天不重复）
        logger.log_phase("preview", "start", day)
        preview_count = PREVIEW_COUNTS[day]
        print(f"\n── 赛前信息预览（第{day}天，{preview_count}名）──")
        for p_agent, p, shown, history in [
            (player_a_agent, player_a, shown_a, preview_history_a),
            (player_b_agent, player_b, shown_b, preview_history_b),
        ]:
            today_preview, _ = _random_gladiator_preview(shown, preview_count)
            history.append(today_preview)
            full = "\n\n".join(history)
            print(f"  {p.player_name} 今日新增预览:")
            for line in today_preview.split("\n"):
                if line.strip():
                    print(f"    {line}")
            msg = full + "\n\n以上是至今为止你收到的所有角斗士胜率预览。请回复确认收到，然后进入拍卖。"
            p_agent.invoke(msg, allow_tools=False)
            logger.log_agent_message(p.player_name, "preauction_preview", full)
            if viz:
                viz.emit("preview", {"player": p.player_name, "day": day,
                         "gladiators": _parse_preview_history(history)})

        logger.log_phase("preview", "end", day)

        # Phase 1：开始拍卖
        logger.log_phase("auction", "start", day)
        auction = run_auction_phase(
            player_a_agent, player_b_agent,
            player_a, player_b, logger, day
        )
        state.auction = auction
        logger.log_phase("auction", "end", day)

        # 破产检查：拍卖中触发破产则直接跳到最终结算
        if getattr(state, 'game_over', False):
            logger.log_agent_message("System", "auction_result", f"Day{day}: {state.bankrupt_player} 破产，游戏结束")
            break

        # Phase 1.5: 拍卖后分析（从对手的出价行为中推断角斗士信息）—— 并行
        logger.log_phase("post_auction_analysis", "start", day)
        print(f"\n── 拍卖后分析 ──")
        my_glads_a = ", ".join(f"{g['name']}({g['char_id']}, point={g.get('point',0)})" for g in auction.owner_a)
        opp_glads_a = ", ".join(f"{g['name']}({g['char_id']})" for g in auction.owner_b)
        my_glads_b = ", ".join(f"{g['name']}({g['char_id']}, point={g.get('point',0)})" for g in auction.owner_b)
        opp_glads_b = ", ".join(f"{g['name']}({g['char_id']})" for g in auction.owner_a)
        post_auction_msg_a = (
            f"拍卖已结束。以下是拍卖结果：\n\n"
            f"你的阵容: {my_glads_a}\n"
            f"对手阵容: {opp_glads_a}\n"
            f"当前游戏币: {player_a.chips}\n\n"
            f"请以以下格式进行分析：\n"
            f"<think>\n"
            f"1. 回顾对手在拍卖环节的出价行为\n"
            f"2. 回顾之前你在拍卖时的分析，结合你已知的胜率预览信息，猜测双方角斗士阵容的强度\n"
            f"3. 思考你要如何安排角斗士的上场顺序\n"
            f"</think>\n\n"
        )
        post_auction_msg_b = (
            f"拍卖已结束。以下是拍卖结果：\n\n"
            f"你的阵容: {my_glads_b}\n"
            f"对手阵容: {opp_glads_b}\n"
            f"当前游戏币: {player_b.chips}\n\n"
            f"请以以下格式进行分析：\n"
            f"<think>\n"
            f"1. 回顾对手在拍卖环节的出价行为\n"
            f"2. 回顾之前你在拍卖时的分析，结合你已知的胜率预览信息，猜测双方角斗士阵容的强度\n"
            f"3. 思考你要如何安排角斗士的上场顺序\n\n"
            f"</think>\n\n"
        )

        def _analyze_a():
            return player_a_agent.invoke(post_auction_msg_a, allow_tools=False, label="post_auction_analysis")
        def _analyze_b():
            return player_b_agent.invoke(post_auction_msg_b, allow_tools=False, label="post_auction_analysis")

        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_analyze_a)
            fb = executor.submit(_analyze_b)
            resp_post_a = fa.result()
            resp_post_b = fb.result()

        logger.log_agent_message(player_a.player_name, "post_auction_analysis", resp_post_a)
        logger.log_agent_message(player_b.player_name, "post_auction_analysis", resp_post_b)
        if viz:
            viz.emit("agent_message", {"player": player_a.player_name, "content": resp_post_a,
                     "label": "拍卖后分析", "role": "speak"})
            viz.emit("agent_message", {"player": player_b.player_name, "content": resp_post_b,
                     "label": "拍卖后分析", "role": "speak"})
        logger.log_phase("post_auction_analysis", "end", day)

        # 迭代 1：部署 + 比赛（第 1 局）+ 反思
        logger.log_phase("deploy_match1", "start", day)
        print(f"\n── 部署阶段（第1局）──")
        def _deploy_a1():
            set_thread_player(player_a.player_name)
            run_deployment_phase(player_a_agent, player_a, player_b, logger, day, [1])
        def _deploy_b1():
            set_thread_player(player_b.player_name)
            run_deployment_phase(player_b_agent, player_b, player_a, logger, day, [1])
        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_deploy_a1)
            fb = executor.submit(_deploy_b1)
            fa.result()
            fb.result()
        run_match_phase(player_a, player_b, logger, day, slots=[1])

        print(f"\n── 反思阶段（第1局）──")
        logger.log_phase("reflect_match1", "start", day)
        def _reflect_a1():
            return _reflect_player(player_a_agent, player_a, player_b, logger, day, "match1", PROMPT_MATCH1)
        def _reflect_b1():
            return _reflect_player(player_b_agent, player_b, player_a, logger, day, "match1", PROMPT_MATCH1)
        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_reflect_a1)
            fb = executor.submit(_reflect_b1)
            resp_match1_a = fa.result()
            resp_match1_b = fb.result()
        if viz:
            viz.emit("agent_message", {"player": player_a.player_name, "content": resp_match1_a,
                     "label": "第1局反思", "role": "speak"})
            viz.emit("agent_message", {"player": player_b.player_name, "content": resp_match1_b,
                     "label": "第1局反思", "role": "speak"})
        logger.log_phase("reflect_match1", "end", day)

        # 迭代 2：部署 + 比赛（第 2、3 局）
        logger.log_phase("iteration2", "start", day)
        print(f"\n── 部署阶段（第2、3局）──")
        def _deploy_a23():
            set_thread_player(player_a.player_name)
            run_deployment_phase(player_a_agent, player_a, player_b, logger, day, [2, 3])
        def _deploy_b23():
            set_thread_player(player_b.player_name)
            run_deployment_phase(player_b_agent, player_b, player_a, logger, day, [2, 3])
        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_deploy_a23)
            fb = executor.submit(_deploy_b23)
            fa.result()
            fb.result()
        run_match_phase(player_a, player_b, logger, day, slots=[2, 3])
        logger.log_phase("iteration2", "end", day)

        # 每日胜者奖励（先结算，再复盘）
        logger.log_phase("daily_winner_reward", "start", day)
        print(f"\n── 每日胜者奖励 ──")
        today_matches = state.match_history[-3:]
        wins_a = sum(1 for m in today_matches if m.get('winner') == player_a.player_name)
        wins_b = sum(1 for m in today_matches if m.get('winner') == player_b.player_name)
        print(f"  今日胜场: {player_a.player_name} {wins_a} 胜 | {player_b.player_name} {wins_b} 胜")

        daily_winner_info_a = ""
        daily_winner_info_b = ""
        # Step 1: 先将双方的 point_pool 全部转入 reward_pool
        for p in [player_a, player_b]:
            if p.squad:
                p.reward_pool += p.squad.point_pool
                p.squad.point_pool = 0

        # Step 2: 每日胜者从 reward_pool 兑换游戏币
        if wins_a != wins_b:
            daily_winner = player_a if wins_a > wins_b else player_b
            daily_loser = player_b if wins_a > wins_b else player_a
            pool = daily_winner.reward_pool
            if pool <= 0:
                reward = 0
            elif pool < 50:
                reward = pool
            else:
                reward = 50
            if reward > 0:
                daily_winner.reward_pool -= reward
                daily_winner.earn_chips(reward)
                print(f"  胜者 {daily_winner.player_name} 奖励池 {pool} → 兑 {reward} 游戏币")
            else:
                print(f"  胜者 {daily_winner.player_name} 奖励池 ≤0，无转换")
            if viz:
                viz.emit("daily_winner", {"day": day, "winner": daily_winner.player_name,
                         "wins_a": wins_a, "wins_b": wins_b, "reward": reward,
                         "pool_a": player_a.squad.point_pool if player_a.squad else 0,
                         "pool_b": player_b.squad.point_pool if player_b.squad else 0,
                         "reward_pool_a": player_a.reward_pool, "reward_pool_b": player_b.reward_pool,
                         "chips_a": player_a.chips, "chips_b": player_b.chips})
            daily_winner_info_a = (
                f"今日胜者: {daily_winner.player_name}（胜场 {max(wins_a, wins_b)}:{min(wins_a, wins_b)}）\n"
                f"奖励池转换: 原池 {pool} → 兑 {reward} 游戏币\n"
                f"你当前的游戏币: {player_a.chips}"
            )
            daily_winner_info_b = (
                f"今日胜者: {daily_winner.player_name}（胜场 {max(wins_a, wins_b)}:{min(wins_a, wins_b)}）\n"
                f"奖励池转换: 原池 {pool} → 兑 {reward} 游戏币\n"
                f"你当前的游戏币: {player_b.chips}"
            )
        else:
            print(f"  胜场相同，无胜者奖励")
            daily_winner_info_a = f"今日胜场打平（{wins_a}:{wins_b}），无胜者奖励。"
            daily_winner_info_b = daily_winner_info_a
            if viz:
                viz.emit("daily_winner", {"day": day, "winner": None, "reward": 0,
                         "wins_a": wins_a, "wins_b": wins_b,
                         "pool_a": player_a.squad.point_pool if player_a.squad else 0,
                         "pool_b": player_b.squad.point_pool if player_b.squad else 0,
                         "reward_pool_a": player_a.reward_pool, "reward_pool_b": player_b.reward_pool,
                         "chips_a": player_a.chips, "chips_b": player_b.chips})

        logger.log_phase("daily_winner_reward", "end", day)

        # 全天复盘总结（双方并行，在每日胜者奖励之后）
        logger.log_phase("day_summary", "start", day)
        print(f"\n── 全天复盘总结 ──")
        summary_a = _build_day_summary_text(player_a, daily_winner_info_a)
        summary_b = _build_day_summary_text(player_b, daily_winner_info_b)
        msg_a = PROMPT_DAY_SUMMARY.format(day=day, player_info=summary_a)
        msg_b = PROMPT_DAY_SUMMARY.format(day=day, player_info=summary_b)
        def _summary_a():
            return player_a_agent.invoke(msg_a, allow_tools=False, extra_body=EXTRA_BODY_THINKING, label="day_summary")
        def _summary_b():
            return player_b_agent.invoke(msg_b, allow_tools=False, extra_body=EXTRA_BODY_THINKING, label="day_summary")
        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_summary_a)
            fb = executor.submit(_summary_b)
            resp_summary_a = fa.result()
            logger.log_agent_message(player_a.player_name, "reflect_day_summary", resp_summary_a)
            resp_summary_b = fb.result()
            logger.log_agent_message(player_b.player_name, "reflect_day_summary", resp_summary_b)
            if viz:
                if day == 1:
                    viz.set_ranking_truth(_build_ranking_ground_truth())
                viz.store_reflection(day, player_a.player_name, resp_summary_a, player_b.chips)
                viz.store_reflection(day, player_b.player_name, resp_summary_b, player_a.chips)
                viz.emit("agent_message", {"player": player_a.player_name, "content": resp_summary_a,
                         "label": "全天复盘", "role": "speak"})
                viz.emit("agent_message", {"player": player_b.player_name, "content": resp_summary_b,
                         "label": "全天复盘", "role": "speak"})
                viz.emit("daily_summary", {"player": player_a.player_name, "day": day})
        logger.log_phase("day_summary", "end", day)

        # ── 收集当天数据（供评估使用） ──
        day_data = {
            "post_auction_a": resp_post_a,
            "post_auction_b": resp_post_b,
            "reflect_match1_a": resp_match1_a,
            "reflect_match1_b": resp_match1_b,
            "reflect_day_a": resp_summary_a,
            "reflect_day_b": resp_summary_b,
        }
        all_days_data.append(day_data)

        # 记录每日状态
        for p in [player_a, player_b]:
            fatigue = p.squad.summary() if p.squad else "无阵容"
            points = p.squad.get_total_points() if p.squad else 0
            logger.log_daily_summary(day, p.player_name, p.chips, points, fatigue)

        # ── 评估阶段（M1-M6 新方法） ──
        print(f"\n── 评估阶段 ──")
        logger.log_phase("evaluation", "start", day)

        # 加载真实胜率数据（所有评估共享）
        ground_truth = evaluator.load_ground_truth()

        # 解析双方的预览历史
        parsed_preview_a = _parse_preview_history(preview_history_a)
        parsed_preview_b = _parse_preview_history(preview_history_b)

        # 提取双方的发言
        agent_msgs_a = _extract_assistant_messages(player_a_agent)
        agent_msgs_b = _extract_assistant_messages(player_b_agent)

        # 估算双方对手游戏币范围
        opp_chips_range_a = _estimate_opponent_chips(player_b, auction)
        opp_chips_range_b = _estimate_opponent_chips(player_a, auction)

        # 构建比赛结果（双方视角）
        match_results_a = [
            {"slot": i + 1,
             "won": m['winner'] == player_a.player_name,
             "my_char": m.get('winner_char_id', '?') if m['winner'] == player_a.player_name else m.get('loser_char_id', '?'),
             "opp_char": m.get('loser_char_id', '?') if m['winner'] == player_a.player_name else m.get('winner_char_id', '?'),
             "point_transferred": m.get('point_transferred', 0),
             "multiplier": m.get('multiplier', 1.0)}
            for i, m in enumerate(state.match_history[-3:])
        ]
        match_results_b = [
            {"slot": i + 1,
             "won": m['winner'] == player_b.player_name,
             "my_char": m.get('winner_char_id', '?') if m['winner'] == player_b.player_name else m.get('loser_char_id', '?'),
             "opp_char": m.get('loser_char_id', '?') if m['winner'] == player_b.player_name else m.get('winner_char_id', '?'),
             "point_transferred": m.get('point_transferred', 0),
             "multiplier": m.get('multiplier', 1.0)}
            for i, m in enumerate(state.match_history[-3:])
        ]

        # 构建拍卖结果摘要
        auction_summary_a = json.dumps({
            "my_gladiators": [{"name": g["name"], "char_id": g["char_id"], "point": g.get("point", 0)} for g in auction.owner_a],
            "opponent_gladiators": [{"name": g["name"], "char_id": g["char_id"]} for g in auction.owner_b],
            "bid_history": [r for r in auction.bid_history if player_a.player_name in str(r.get("bids", {}))],
        }, ensure_ascii=False, indent=2)
        auction_summary_b = json.dumps({
            "my_gladiators": [{"name": g["name"], "char_id": g["char_id"], "point": g.get("point", 0)} for g in auction.owner_b],
            "opponent_gladiators": [{"name": g["name"], "char_id": g["char_id"]} for g in auction.owner_a],
            "bid_history": [r for r in auction.bid_history if player_b.player_name in str(r.get("bids", {}))],
        }, ensure_ascii=False, indent=2)

        # 筛选各玩家相关的出价记录
        my_bids_a = [r for r in auction.bid_history
                      if player_a.player_name in str(r.get("bids", {}))]
        my_bids_b = [r for r in auction.bid_history
                      if player_b.player_name in str(r.get("bids", {}))]

        # 对每个玩家执行 M1-M6
        for p, opp, _p_agent, _opp_agent, agent_msgs, parsed_preview, \
            my_bids, opp_chips_range, post_auction, reflect_match1, \
            reflect_day, _opp_preview, match_results_for_p, auction_summary in [
            (player_a, player_b, player_a_agent, player_b_agent,
             agent_msgs_a, parsed_preview_a, my_bids_a, opp_chips_range_a,
             resp_post_a, resp_match1_a, resp_summary_a,
             parsed_preview_b, match_results_a, auction_summary_a),
            (player_b, player_a, player_b_agent, player_a_agent,
             agent_msgs_b, parsed_preview_b, my_bids_b, opp_chips_range_b,
             resp_post_b, resp_match1_b, resp_summary_b,
             parsed_preview_a, match_results_b, auction_summary_b),
        ]:
            print(f"\n  ── {p.player_name} 评估 ──")

            # M1: 规则幻觉检测
            _r = evaluator.evaluate_rule_compliance(day, p.player_name, agent_msgs)
            if viz:
                viz.emit("evaluation", {"player": p.player_name, "day": day,
                         "eval_type": "M1_规则幻觉", "summary": _r.get("summary", "")[:120]})

            # M2: 数字幻觉检测
            evaluator.evaluate_factual_accuracy(
                day, p.player_name, agent_msgs, parsed_preview,
                my_bids, opp_chips_range, ground_truth,
            )

            # M3: 策略质量
            evaluator.evaluate_strategy_quality(
                day, p.player_name,
                post_auction,
                f"第1局反思:\n{reflect_match1}\n\n全天复盘:\n{reflect_day}",
                reflect_day,
                auction_summary,
                p.deployments if hasattr(p, 'deployments') else {},
                match_results_for_p,
            )

            # M4: 经济理性（程序化，增强版）
            point_pool = p.squad.point_pool if p.squad else 0
            evaluator.evaluate_economic_rationality_v2(
                day, p.player_name,
                p.chips, 800,
                p.reward_pool, point_pool,
                my_bids,
            )

            # M5: 信息利用
            evaluator.evaluate_information_utilization(
                day, p.player_name,
                agent_msgs, parsed_preview,
                reflect_day,
                ground_truth,
            )

            # M6: 对手建模
            opp_actions = getattr(p, '_opponent_actions', [])
            opp_deploys = opp.deployments if opp.deployments else {}
            evaluator.evaluate_opponent_modeling_v2(
                day, p.player_name,
                agent_msgs,
                opp_actions,
                opp_deploys,
                post_auction,
                f"第1局反思:\n{reflect_match1}",
            )

            # M7: 对手游戏币估计精确度（程序化，ground truth = 实际对手 chips）
            evaluator.evaluate_chip_estimation(
                day, p.player_name, reflect_day, opp.chips,
            )

        logger.log_phase("evaluation", "end", day)

        if player_a.squad:
            player_a.squad.next_day()
        if player_b.squad:
            player_b.squad.next_day()
        player_a.deployments = {}
        player_b.deployments = {}

        # ── 等待记忆 subagent 完成当天所有提取 ──
        print(f"\n── 等待记忆提取完成 ──")
        memory_a.wait_all()
        memory_b.wait_all()
        print(f"  [记忆] 第{day}天记忆提取完成")

        # ── 清理临时消息：删除拍卖/部署/反思环节的上下文 ──                                                                              
        _DAILY_CLEANUP_LABELS = {                                                                                                         
            "post_auction_analysis", "deploy_match1", "reflect_match1", "deploy_match23",                                                 
        }                                                                                                                                 
        def _cleanup_message_history(agent, name):                                                                                        
            before = len(agent.message_history)                                                                                           
            agent.message_history = [                                                                                                     
                m for m in agent.message_history                                                                                          
                if not (                                                                                                                  
                    m.get("label", "").startswith("auction_round")                                                                        
                    or m.get("label", "") in _DAILY_CLEANUP_LABELS                                                                        
                )                                                                                                                         
            ]                                                                                                                             
            after = len(agent.message_history)                                                                                            
            print(f"  [清理] {name}: {before} → {after} 条消息 (删除 {before - after})")                                                  
                                                                                                                                          
        _cleanup_message_history(player_a_agent, player_a.player_name)                                                                    
        _cleanup_message_history(player_b_agent, player_b.player_name)                                                                                                                                     

        logger.log_state_snapshot(
            day, player_a.summary(), player_b.summary(),
        )

    # 最终结算：奖励池 1:1 兑换为游戏币，比较总额
    # 破产情况下已在 _execute_bankruptcy 中完成清算，跳过正常结算
    if getattr(state, 'game_over', False): 
        print()
        print("=" * 60)
        print("  最终结算（破产）")
        print("=" * 60)
        print(f"  {state.bankrupt_player}: 游戏币 0")
        print(f"  {state.winner_name}: 游戏币 1600")
        total_a = player_a.chips
        total_b = player_b.chips
    else:
        print()
        print("=" * 60)
        print("  最终结算")
        print("=" * 60)

        for player in [player_a, player_b]:
            pool = player.squad.point_pool if player.squad else 0
            rp = player.reward_pool
            player.chips += pool + rp
            if player.squad:
                player.squad.point_pool = 0
            player.reward_pool = 0
            print(f"  {player.player_name}: 游戏币 {player.chips - pool - rp} + squad奖励池 {pool} + 拍卖死钱 {rp}"
                  f" = 总计 {player.chips} 游戏币")
            logger.log_final_settlement(
                player.player_name, player.chips - pool, pool,
                player.chips, 0, player.assets,
            )

        total_a = player_a.chips
        total_b = player_b.chips
    if not getattr(state, 'game_over', False):
        if total_a > total_b:
            print(f"\n{player_a.player_name} 最终胜出！游戏币 {total_a} vs {total_b}")
        elif total_b > total_a:
            print(f"\n{player_b.player_name} 最终胜出！游戏币 {total_b} vs {total_a}")
        else:
            print(f"\n双方平局！游戏币 {total_a}")
        if viz:
            winner = player_a.player_name if total_a > total_b else (player_b.player_name if total_b > total_a else "平局")
            viz.emit("final_result", {"winner": winner, "chips_a": total_a, "chips_b": total_b})
            viz.mark_game_over()

    logger.log_final_summary(player_a.summary(), player_b.summary())
    logger.close()


def run_human_vs_ai_experiment(visualizer=None, human_sync=None, disguise_mapping=None):
    """运行人机对战实验 —— 人类 vs 一个 AI 智能体。

    流程与 run_experiment() 完全一致（3天×3局 + 拍卖 + 疲劳），
    但每次需要人类决策时阻塞等待 Web 前端提交输入。

    Args:
        visualizer: Visualizer 实例
        human_sync: HumanInputState 实例，用于线程同步
        disguise_mapping: 替身映射 {real_char_id: {"id": dis_id, "name": dis_name}}
    """
    viz = visualizer
    sync = human_sync
    # 替身模式：在 Visualizer 层面替换所有 SSE 事件中的角色名称和 ID
    if disguise_mapping and viz:
        viz.set_disguise_mapping(disguise_mapping)
    # 构建逆向映射：前端提交的是替身 ID，需要转回真实 char_id
    _disguise_id_to_real = {v["id"]: k for k, v in (disguise_mapping or {}).items()}

    def _real_char_id(disguise_id: str) -> str:
        """替身 ID → 真实 char_id，非替身模式原样返回。"""
        return _disguise_id_to_real.get(disguise_id, disguise_id)

    def _squad_name(player, char_id: str) -> str:
        """从玩家阵容中查找 char_id 对应的名称。"""
        if player.squad:
            for m in player.squad.members:
                if m.char_id == char_id:
                    return m.name
        return char_id

    human = Gambler(player_name="人类玩家", assets=100)
    ai = Gambler(player_name="智能体", assets=100)

    state = GameState(player_a=human, player_b=ai)
    set_game_state(state)
    state.viz = viz

    # 对手操作追踪
    human._opponent_actions = []
    ai._opponent_actions = []

    logger = ExperimentLogger()
    logger.init_log_file(filename_prefix="human_vs_ai")
    evaluator = Evaluator(logger=logger)
    ai_agent = _create_no_bob_agent(ai, logger=logger)

    print("=" * 60)
    print("  Arena 人机对战 —— 3天×3局 拍卖竞技")
    print(f"  人类: {human.player_name}  vs  AI: {ai.player_name}")
    print("=" * 60)

    human.chips = 800
    ai.chips = 800
    print(f"  {human.player_name}: {human.chips} 游戏币")
    print(f"  {ai.player_name}: {ai.chips} 游戏币")

    # 开局信息
    pre_game_info = _show_pre_game_info()
    print(pre_game_info)
    if viz:
        viz.emit("game_start", {
            "player_a": human.player_name, "player_b": ai.player_name,
            "mode": "play",
            "rules_summary": "双方初始各800游戏币 | 每天暗标拍卖3名角斗士 | 3局1v1比赛 | 第2局×1.5 | 无属性相克 | 3天后奖励池1:1兑回"
        })

    # 构建匿名排名和角斗士名单（AI 和人类共用）
    stats_file = os.path.join(os.path.dirname(__file__), "data", "Bob", "tournament_stats.json")
    with open(stats_file, "r", encoding="utf-8") as f:
        ranking_data = json.load(f)
    sorted_by_rank = sorted(ranking_data["rankings"], key=lambda g: g["win_rate"], reverse=True)
    ranking_lines = []
    for g in sorted_by_rank:
        pct = f"{g['win_rate']*100:.1f}%"
        ranking_lines.append(f"第{g['rank']}名: 胜率 {pct}   (可在此处填写角色名称)")
    anonymous_ranking = "\n".join(ranking_lines)

    all_chars = _get_available_gladiators()
    char_lines = [f"{c['name']} ({c['char_id']})" for c in all_chars]
    all_chars_text = "、".join(char_lines)

    # 先发送人类确认表单（含匿名排名和角斗士表），让人类在 AI 处理期间即可查看
    if viz and sync:
        sync.reset()
        sync.waiting_for = "confirm"
        viz.emit("awaiting_confirm", {
            "label": "开局信息",
            "msg": "查看开局信息和规则（AI 正在接收开局信息...）",
            "detail": (
                f"【匿名胜率排名】（从高到低，不告知对应角斗士）\n{anonymous_ranking}\n\n"
                f"【全部 20 名角斗士】\n{all_chars_text}\n\n"
                f"【每日预览数量】第1天: 5名 | 第2天: 4名 | 第3天: 3名\n"
                f"确认后点击'继续'进入规则解读。"
            )
        })

    # AI 接收开局信息（同时人类在查看排名）
    if viz:
        viz.emit("progress", {"msg": "AI 正在接收开局信息..."})
    ai_agent.invoke(pre_game_info + "\n\n以上是开局前展示的全部 20 名角斗士名单（随机顺序）和匿名胜率排名（高到低）。注意：胜率百分比与名单顺序无关，无法对应。请回复确认收到。", allow_tools=False)

    # 等待人类确认
    if viz and sync:
        sync.confirm_event.wait()
        sync.confirm_event.clear()

    # 规则解读（仅 AI）
    if viz:
        viz.emit("progress", {"msg": "AI 正在进行规则解读..."})
        viz.emit("agent_message", {"player": ai.player_name,
                 "content": "AI 正在进行规则解读...", "label": "系统", "role": "think"})
    rules_interpretation_prompt = """现在是开局前的规则解读环节。请结合你已知的所有信息，对游戏规则进行全面分析：

1. 【游戏机制理解】用自己的话总结：游戏币、奖励池、拍卖、比赛、point 结算、疲劳机制的关系和运作方式。
2. 【关键策略点】哪些规则对你的胜率影响最大？如何利用这些规则？

请直接输出你的分析，本环节不需要使用工具。"""
    interpretation_ai = ai_agent.invoke(rules_interpretation_prompt, allow_tools=False)
    print(f"\n── {ai.player_name} 的规则解读 ──")
    print(interpretation_ai)
    logger.log_agent_message(ai.player_name, "rules_interpretation", interpretation_ai)

    if viz:
        viz.emit("progress", {"msg": "AI 正在进行规则解读..."})
        viz.emit("rules_done", {})

    # 人类确认规则解读
    if viz and sync:
        sync.waiting_for = "confirm"
        viz.emit("awaiting_confirm", {
            "label": "规则解读",
            "msg": "规则解读完成",
            "detail": "AI 已完成规则解读。\n请确认你已理解规则（可在顶部 📋规则参考 随时查看），点击'继续'进入情报阶段。"
        })
        sync.confirm_event.wait()
        sync.confirm_event.clear()

    # 追踪已展示的角斗士
    shown_human: set[str] = set()
    shown_ai: set[str] = set()
    preview_history_ai: list[str] = []
    all_days_data: list[dict] = []

    # ── 3 天循环 ──
    for day in range(1, 4):
        state.day_number = day
        print(f"\n{'='*60}")
        print(f"  第 {day} 天")
        print(f"{'='*60}")

        # Phase 0: 赛前预览
        logger.log_phase("preview", "start", day)
        preview_count = PREVIEW_COUNTS[day]
        print(f"\n── 赛前信息预览（第{day}天，{preview_count}名）──")

        # 生成预览数据（AI 和人类分别随机抽取）
        today_preview_ai, _ = _random_gladiator_preview(shown_ai, preview_count)
        preview_history_ai.append(today_preview_ai)

        today_preview_human, shown_ids_human = _random_gladiator_preview(shown_human, preview_count)
        parsed_human = _parse_preview_history([today_preview_human])

        # 先发送人类预览卡和确认表单，让人类在 AI 处理期间即可查看
        if viz:
            viz.emit("preview", {"player": human.player_name, "day": day,
                     "gladiators": parsed_human})
        if viz and sync:
            sync.waiting_for = "confirm"
            viz.emit("awaiting_confirm", {
                "label": "情报预览",
                "msg": f"第{day}天 — 你看到了 {preview_count} 名角斗士的胜率预览",
                "detail": (
                    f"本日系统随机抽取 {preview_count} 名角斗士向你展示胜率数据。\n"
                    f"AI 对手也看到了 {preview_count} 名角斗士的胜率数据（同为随机抽取）。\n\n"
                    f"请仔细查看左侧情报卡片中的角斗士信息。\n"
                    f"确认后点击'继续'进入拍卖阶段。"
                )
            })

        # AI 接收预览（人类在查看卡片的同时进行）
        if viz:
            viz.emit("progress", {"msg": "AI 正在查看情报预览..."})
        full_ai = "\n\n".join(preview_history_ai)
        ai_agent.invoke(full_ai + "\n\n以上是至今为止你收到的所有角斗士胜率预览。请回复确认收到，然后进入拍卖。", allow_tools=False)
        logger.log_agent_message(ai.player_name, "preauction_preview", full_ai)

        # 等待人类确认
        if viz and sync:
            sync.confirm_event.wait()
            sync.confirm_event.clear()

        logger.log_phase("preview", "end", day)

        # Phase 1: 拍卖（暗标，人类逐轮出价 vs AI invoke）
        logger.log_phase("auction", "start", day)
        print(f"\n── 拍卖阶段 ──")

        old_pool_human = human.squad.point_pool if human.squad else 0
        old_pool_ai = ai.squad.point_pool if ai.squad else 0
        human.squad = None
        ai.squad = None

        all_glads = _get_available_gladiators()
        auction = AuctionSession(
            all_gladiators=all_glads,
            player_a_name=human.player_name,
            player_b_name=ai.player_name,
        )
        state.auction = auction

        round_num = 0
        _low_notified_human = False
        _low_notified_ai = False
        while auction.is_running and len(auction.owner_a) < 3 and len(auction.owner_b) < 3:
            round_num += 1
            show_msg = auction.show()
            if show_msg is None:
                break
            state.auction = auction

            char = auction.current_char
            print(f"\n  拍卖 #{round_num}: {char['name']} ({char['char_id']})")
            if viz:
                viz.emit("auction_show", {"day": day, "round": round_num,
                         "char_name": char['name'], "char_id": char['char_id']})

            for retry in range(1, MAX_BID_RETRIES + 1):
                if retry > 1:
                    tie_hint = (
                        f"\n【重拍第 {retry}/{MAX_BID_RETRIES} 次】\n"
                        f"上一轮双方出价相同。请重新做出你的出价决定。"
                    )
                else:
                    tie_hint = ""

                a_owned = len(auction.owner_a)
                b_owned = len(auction.owner_b)

                # 先显示人类出价表单（人类在 AI 思考期间即可开始填写）
                if viz and sync:
                    sync.reset()
                    sync.waiting_for = "bid"
                    viz.clear_pending_wait()
                    hint = ""
                    if retry > 1:
                        hint = f"\n上一轮双方出价相同，请重新出价。"
                    viz.emit("awaiting_bid", {
                        "char_name": char['name'],
                        "char_id": char['char_id'],
                        "chips": human.chips,
                        "owned": a_owned,
                        "remaining": 3 - a_owned,
                        "retry_hint": hint,
                    })

                # AI 出价（人类在填写出价表单的同时进行）
                if viz:
                    viz.emit("progress", {"msg": "AI 正在思考出价..."})
                pool_pos = f"（拍卖池第 {auction.shown_index + 1}/{len(auction.pool)} 个）"
                prompt_ai = (
                    f"【当前角斗士】{char['name']} ({char['char_id']}) {pool_pos}\n"
                    f"{show_msg}\n\n"
                    f"当前游戏币: {ai.chips}\n"
                    f"已拥有: {b_owned}/3 人 | 剩余空位: {3 - b_owned} 个\n"
                    f"【拍卖规则】一次性暗标：你只知道自己出的数，看不到对方出价，系统直接比大小。弃权填 0。起拍价{STARTING_PRICE}，最高价{MAX_BID_CAP}。\n"
                    f"**双方都扣出价**：无论谁赢，双方均扣自己的出价。\n"
                    f"**输方出价→输方自己的奖励池**。平局不扣，重拍最多{MAX_BID_RETRIES}次。\n\n"
                    f"{tie_hint}\n"
                    f"请分析后做出出价决定，并在回复末尾单独一行输出:\n"
                    f"<bid>金额</bid>\n"
                    f"例: <bid>50</bid> 或 <bid>0</bid>（弃权）。必须输出此标签，否则视为弃权。"
                )
                set_thread_player(ai.player_name)
                bid_ai = 0
                resp_ai = ""
                try:
                    resp_ai = ai_agent.invoke(prompt_ai, allow_tools=False)
                    logger.log_agent_message(ai.player_name, f"auction_r{round_num}_rt{retry}", resp_ai)
                    bid_ai = _parse_bid(resp_ai)
                    # 解析失败且还有空位 → 重试（与 AI-vs-AI 一致）
                    if bid_ai is None and b_owned < 3:
                        for pr in range(MAX_PARSE_RETRIES):
                            set_thread_player(ai.player_name)
                            retry_resp = ai_agent.invoke(
                                f"【重试第{pr+1}/{MAX_PARSE_RETRIES}次】"
                                f"你没有输出出价标签！请在回复末尾单独一行输出 <bid>金额</bid>。"
                                f"出价 0 表示弃权，出价 {STARTING_PRICE}~{MAX_BID_CAP} 表示竞拍。不输出标签视为弃权。",
                                allow_tools=False
                            )
                            bid_ai = _parse_bid(retry_resp)
                            if bid_ai is not None:
                                resp_ai = retry_resp
                                logger.log_agent_message(ai.player_name, f"auction_r{round_num}_rt{retry}_parse_r{pr+1}", retry_resp)
                                break
                    if bid_ai is None:
                        bid_ai = 0

                    # 余额校验：AI 出价超过当前游戏币时通知重新出价
                    if bid_ai > 0 and bid_ai > ai.chips:
                        for _br in range(2):
                            if ai.chips < STARTING_PRICE:
                                _hint = (f"你的游戏币只剩 {ai.chips}，不足以支付起拍价 {STARTING_PRICE}。"
                                         f"请出价 0（弃权）。")
                            else:
                                _hint = (f"你的游戏币只有 {ai.chips}，不足支付出价 {bid_ai}。"
                                         f"请重新出价，不超过 {ai.chips}。")
                            set_thread_player(ai.player_name)
                            _retry_resp = ai_agent.invoke(
                                f"【余额不足警告 - 第{_br+1}/2次重试】{_hint}\n"
                                f"请在回复末尾单独一行输出 <bid>金额</bid>。",
                                allow_tools=False,
                            )
                            logger.log_agent_message(ai.player_name, f"auction_r{round_num}_balance_retry{_br+1}", _retry_resp)
                            _new_bid = _parse_bid(_retry_resp)
                            if _new_bid is not None:
                                bid_ai = _new_bid
                                if bid_ai <= ai.chips:
                                    break
                        else:
                            _capped = min(bid_ai, ai.chips)
                            if _capped < STARTING_PRICE:
                                _capped = 0
                            bid_ai = _capped
                            print(f"    ⚠ {ai.player_name} 余额不足重试耗尽，出价 → {_capped}")
                except Exception as e:
                    print(f"  ⚠ AI 出价失败（第{round_num}轮/重试{retry}）: {e}")
                    import traceback
                    traceback.print_exc()
                    logger.log_agent_message(ai.player_name, f"auction_r{round_num}_rt{retry}_error", str(e))
                    # 用随机中低出价兜底，保证游戏不卡死
                    bid_ai = random.randint(STARTING_PRICE, min(80, ai.chips, MAX_BID_CAP)) if ai.chips >= STARTING_PRICE else 0
                    if viz:
                        viz.emit("agent_message", {
                            "player": ai.player_name,
                            "content": f"AI 出价异常，系统自动出价 {bid_ai} 币",
                            "label": "系统",
                            "role": "system",
                        })

                # 等待人类出价（若人类在 AI 处理期间已提交，bid_event 已 set 会立即返回）
                if viz and sync:
                    sync.bid_event.wait()
                    sync.bid_event.clear()
                    bid_human = sync.human_bid
                    viz.clear_pending_wait()
                else:
                    bid_human = 0

                print(f"    {human.player_name} 暗标: {bid_human} 币  |  {ai.player_name} 暗标: {bid_ai} 币")
                if viz:
                    if bid_human == 0 and bid_ai == 0:
                        viz.emit("auction_bid", {"bid_a": bid_human, "bid_b": bid_ai, "msg": "双方均弃权，该角斗士跳回拍卖池。"})
                    elif bid_human == bid_ai:
                        viz.emit("auction_bid", {"bid_a": bid_human, "bid_b": bid_ai, "msg": f"双方出价相同 ({bid_human} 币)，需要重新出价。"})
                    else:
                        viz.emit("auction_bid", {"bid_a": bid_human, "bid_b": bid_ai})

                result = auction.sealed_bid_round(
                    bid_human, bid_ai,
                    human.player_name, ai.player_name,
                    round_num=round_num,
                )
                print(f"    → {result['msg']}")

                # 扣款
                if result["result"] == "win":
                    if bid_human > 0:
                        human.spend_chips(bid_human)
                    if bid_ai > 0:
                        ai.spend_chips(bid_ai)
                    if result["winner"] == human.player_name:
                        if bid_ai > 0:
                            ai.reward_pool += bid_ai
                    else:
                        if bid_human > 0:
                            human.reward_pool += bid_human

                # 通知 AI（用"你"指 AI，"对手"指人类，避免玩家名歧义）
                round_header = f"【第{round_num}轮拍卖结果】\n"
                if result["result"] == "win":
                    w_amt = result["amount"]
                    ai_owned = len(auction.owner_b)
                    opp_owned = len(auction.owner_a)
                    if result["winner"] == ai.player_name:
                        # AI 赢了
                        notify_ai = (
                            f"{round_header}你 以 {w_amt} 游戏币拍下了角斗士: {char['name']}({char['char_id']})。\n\n"
                            f"当前状态:\n"
                            f"  你: 游戏币 {ai.chips} | 已拥有 {ai_owned}/3 人\n"
                            f"  对手({human.player_name}): 已拥有 {opp_owned}/3 人\n\n"
                            f"请思考：对手出价是多少？是对手出价低还是弃权了？"
                        )
                    else:
                        # 人类赢了
                        notify_ai = (
                            f"{round_header}对手({human.player_name}) 以 {w_amt} 游戏币拍下了角斗士: {char['name']}({char['char_id']})。\n\n"
                            f"当前状态:\n"
                            f"  你: 游戏币 {ai.chips} | 已拥有 {ai_owned}/3 人\n"
                            f"  对手({human.player_name}): 已拥有 {opp_owned}/3 人\n\n"
                            f"请思考：对手这次出价透露出什么信息？"
                        )
                elif result["result"] == "tie":
                    if retry < MAX_BID_RETRIES:
                        notify_ai = f"{round_header}双方出价相同，平局不扣币，请重新出价。"
                    else:
                        notify_ai = f"{round_header}{MAX_BID_RETRIES+1}次平局，{char['name']} 回拍卖池，跳过。"
                else:
                    notify_ai = f"{round_header}{result['msg']}"
                ai_agent.message_history.append({"role": "user", "content": notify_ai})

                # 低币通知 AI
                h_low = human.chips < 50 and len(auction.owner_a) < 3
                if h_low and not _low_notified_ai and ai.chips >= 50:
                    _low_notified_ai = True
                    ai_agent.message_history.append({"role": "user", "content": (
                        f"【系统提示】{human.player_name} 的游戏币已不足 50（当前 {human.chips}），"
                        f"无法支撑后续拍卖。对方只能弃权（出价 0）。"
                    )})
                a_low = ai.chips < 50 and len(auction.owner_b) < 3
                if a_low and not _low_notified_human:
                    _low_notified_human = True
                    # 通知人类（通过聊天）
                    if viz:
                        viz.emit("agent_message", {"player": human.player_name,
                                 "content": f"AI 对手游戏币不足 50，后续只能弃权", "label": "系统提示", "role": "speak"})

                if viz and result["result"] == "win":
                    viz.emit("auction_result", {
                        "day": day, "round": round_num,
                        "char_name": char['name'], "char_id": char['char_id'],
                        "winner": result["winner"], "amount": result["amount"],
                        "chips_a": human.chips, "chips_b": ai.chips,
                        "owned_a": len(auction.owner_a), "owned_b": len(auction.owner_b),
                        "reward_pool_a": human.reward_pool, "reward_pool_b": ai.reward_pool,
                    })

                logger.log_auction_round(
                    day, round_num, char['name'], char['char_id'],
                    bid_human, bid_ai, result["result"], retry,
                )

                if result["result"] == "win":
                    break
                elif result["result"] == "tie":
                    if retry < MAX_BID_RETRIES:
                        continue
                    else:
                        auction._advance_to_next()
                        break
                elif result["result"] == "skip":
                    break

            state.auction = auction

        # 自动补齐
        if human.squad is None or ai.squad is None:
            auction.state = "end"
            fill_msg = auction._auto_assign_remaining()
            bankrupt = _finalize_auction(state, old_pool_human, old_pool_ai)
            if bankrupt:
                _emit_bankruptcy_final(state, viz, logger, day)
                state.auction = auction
                logger.log_phase("auction", "end", day)
                break
            if viz:
                if fill_msg:
                    viz.emit("auto_fill", {"msg": fill_msg})
                viz.emit("squad_update", {
                    "chips_a": human.chips, "chips_b": ai.chips,
                    "owned_a": len(auction.owner_a), "owned_b": len(auction.owner_b),
                    "pool_a": human.squad.point_pool if human.squad else 0,
                    "pool_b": ai.squad.point_pool if ai.squad else 0,
                    "reward_pool_a": human.reward_pool, "reward_pool_b": ai.reward_pool,
                })

        print(f"\n  {human.player_name} 阵容: {[(c['name'], c.get('point',0)) for c in auction.owner_a]} 游戏币: {human.chips}")
        print(f"  {ai.player_name} 阵容: {[(c['name'], c.get('point',0)) for c in auction.owner_b]} 游戏币: {ai.chips}")
        logger.log_agent_message("System", "auction_result", auction.summary())
        state.auction = auction
        logger.log_phase("auction", "end", day)

        # Phase 1.5: 拍卖后分析
        logger.log_phase("post_auction_analysis", "start", day)
        # 展示双方阵容到前端
        if viz:
            ai_squad_info = ", ".join(f"{g['name']}({g['char_id']}, point={g.get('point',0)})" for g in auction.owner_b)
            viz.emit("agent_message", {"player": ai.player_name, "content": "AI 阵容: " + ai_squad_info, "label": "拍卖结果", "role": "info"})

        # 先发送人类确认表单
        my_glads_human = ", ".join(f"{g['name']}({g['char_id']}, point={g.get('point',0)})" for g in auction.owner_a)
        opp_glads_human = ", ".join(f"{g['name']}({g['char_id']}, point={g.get('point',0)})" for g in auction.owner_b)
        if viz and sync:
            sync.waiting_for = "confirm"
            viz.emit("awaiting_confirm", {
                "label": "拍卖后分析",
                "msg": "拍卖结束，查看阵容",
                "detail": (
                    f"你的阵容:\n  {my_glads_human}\n\n"
                    f"AI 对手阵容:\n  {opp_glads_human}\n\n"
                    f"剩余游戏币: {human.chips}\n\n"
                    f"请分析双方阵容，思考部署策略。确认后点击'继续'。"
                )
            })

        # AI 分析拍卖结果（人类在查看阵容的同时进行）
        if viz:
            viz.emit("progress", {"msg": "AI 正在分析拍卖结果..."})
        my_glads_ai = ", ".join(f"{g['name']}({g['char_id']}, point={g.get('point',0)})" for g in auction.owner_b)
        opp_glads_ai = ", ".join(f"{g['name']}({g['char_id']})" for g in auction.owner_a)
        post_msg_ai = (
            f"拍卖已结束。以下是拍卖结果：\n\n"
            f"你的阵容: {my_glads_ai}\n"
            f"对手阵容: {opp_glads_ai}\n"
            f"当前游戏币: {ai.chips}\n\n"
            f"请以以下格式进行分析：<think>\n"
            f"1. 回顾对手在拍卖环节的出价行为\n"
            f"2. 猜测双方角斗士阵容的强度\n"
            f"3. 思考你要如何安排角斗士的上场顺序\n</think>"
        )
        resp_post_ai = ai_agent.invoke(post_msg_ai, allow_tools=False)
        logger.log_agent_message(ai.player_name, "post_auction_analysis", resp_post_ai)

        # 等待人类确认
        if viz and sync:
            sync.confirm_event.wait()
            sync.confirm_event.clear()

        logger.log_phase("post_auction_analysis", "end", day)

        # Phase 2: 部署 Match 1
        logger.log_phase("deploy_match1", "start", day)
        squad_info_ai = ai.squad.summary() if ai.squad else "无阵容"

        # 先发送人类部署表单
        human_squad_list = []
        if human.squad:
            for m in human.squad.members:
                human_squad_list.append({
                    "char_id": m.char_id,
                    "name": m.name,
                    "fatigue": round(human.squad.get_hp_multiplier(m.char_id), 2),
                    "point": m.point,
                })
        if viz and sync:
            sync.reset()
            sync.waiting_for = "deploy"
            viz.clear_pending_wait()
            viz.emit("awaiting_deploy", {
                "slots": [1],
                "day": day,
                "squad": human_squad_list,
                "chips": human.chips,
            })

        # AI 部署第1局（人类在填写部署表单的同时进行）
        if viz:
            viz.emit("progress", {"msg": "AI 正在部署第1局..."})
        deploy_msg_ai = (
            f"现在是第{day}天，你需要安排第 1 局比赛的出战角斗士。\n\n"
            f"【你的阵容】\n{squad_info_ai}\n\n"
            f"【规则提示】比赛不下注。第 2 局夺取量 ×1.5。没有属性相克。角斗士每天只能出战一轮。\n\n"
            f"【你的对手】{human.player_name}\n\n"
            f"请分析后做出部署决定，并在回复末尾单独一行输出:\n"
            f"<deploy slot=\"1\">char_id</deploy>"
        )
        resp_deploy_ai1 = ai_agent.invoke(deploy_msg_ai, allow_tools=False)
        parsed_ai1 = _parse_deploy(resp_deploy_ai1)
        if 1 in parsed_ai1:
            ai.deployments[1] = parsed_ai1[1]
        # AI 部署暂不展示，等人类确认后再展示

        # 等待人类部署
        if viz and sync:
            sync.deploy_event.wait()
            sync.deploy_event.clear()
            viz.clear_pending_wait()
            for s, cid in sync.human_deployments.items():
                human.deployments[s] = _real_char_id(cid)
            if viz:
                for s, cid in sync.human_deployments.items():
                    viz.emit("deployment", {"player": human.player_name, "day": day,
                             "slot": s, "slots": str(s),
                             "char_id": cid, "char_name": _squad_name(human, _real_char_id(cid))})
        logger.log_deployment(day, human.player_name, {1: human.deployments.get(1, "?")})
        logger.log_deployment(day, ai.player_name, {1: ai.deployments.get(1, "?")})

        # 运行 Match 1
        run_match_phase(human, ai, logger, day, slots=[1])

        # 人类确认比赛结果（先显示确认表单，AI 在后台反思）
        logger.log_phase("reflect_match1", "start", day)
        if viz and sync:
            viz.emit("deployment", {"player": ai.player_name, "day": day,
                     "slot": 1, "slots": "1",
                     "char_id": ai.deployments.get(1, "?"),
                     "char_name": _squad_name(ai, ai.deployments.get(1, ""))})
            sync.waiting_for = "confirm"
            viz.emit("awaiting_confirm", {
                "label": "第1局赛后",
                "msg": "第1局比赛结果已出",
                "detail": "查看比赛结果，思考后续部署策略。确认后点击'继续'。"
            })

        # AI 赛后反思（人类在查看比赛结果的同时进行）
        if viz:
            viz.emit("progress", {"msg": "AI 正在反思第1局..."})
        resp_match1_ai = _reflect_player(ai_agent, ai, human, logger, day, "match1", PROMPT_MATCH1)

        # 等待人类确认
        if viz and sync:
            sync.confirm_event.wait()
            sync.confirm_event.clear()
        logger.log_phase("reflect_match1", "end", day)

        # Phase 3: 部署 Match 2+3
        logger.log_phase("deploy_match23", "start", day)

        # 先发送人类部署表单
        human_squad_list = []
        if human.squad:
            for m in human.squad.members:
                human_squad_list.append({
                    "char_id": m.char_id,
                    "name": m.name,
                    "fatigue": round(human.squad.get_hp_multiplier(m.char_id), 2),
                    "point": m.point,
                })
        if viz and sync:
            sync.reset()
            sync.waiting_for = "deploy"
            viz.clear_pending_wait()
            viz.emit("awaiting_deploy", {
                "slots": [2, 3],
                "day": day,
                "squad": human_squad_list,
                "chips": human.chips,
                "deployed_already": [human.deployments.get(1)] if human.deployments.get(1) else [],
            })

        # AI 部署第2、3局（人类在填写部署表单的同时进行）
        if viz:
            viz.emit("progress", {"msg": "AI 正在部署第2、3局..."})
        deploy_msg_ai23 = (
            f"现在是第{day}天，你需要安排第 2、3 局比赛的出战角斗士。\n\n"
            f"【你的阵容】\n{squad_info_ai}\n\n"
            f"【规则提示】第 2 局夺取量 ×1.5。同一天不能用同一个角斗士两次。没有属性相克。\n\n"
            f"【你的对手】{human.player_name}\n\n"
            f"请在回复末尾输出:\n"
            f"<deploy slot=\"2\">char_id</deploy>\n"
            f"<deploy slot=\"3\">char_id</deploy>"
        )
        resp_deploy_ai23 = ai_agent.invoke(deploy_msg_ai23, allow_tools=False)
        parsed_ai23 = _parse_deploy(resp_deploy_ai23)
        for s in [2, 3]:
            if s in parsed_ai23:
                ai.deployments[s] = parsed_ai23[s]
        # AI 部署暂不展示，等人类确认后再展示

        # 等待人类部署
        if viz and sync:
            sync.deploy_event.wait()
            sync.deploy_event.clear()
            viz.clear_pending_wait()
            for s, cid in sync.human_deployments.items():
                human.deployments[s] = _real_char_id(cid)
            # 验证：不能选已在第1局出战过的角斗士
            already_used = human.deployments.get(1)
            vals23 = list(sync.human_deployments.values())
            if already_used and already_used in vals23:
                if viz:
                    sync.reset()
                    sync.waiting_for = "deploy"
                    viz.emit("awaiting_deploy", {
                        "slots": [2, 3],
                        "day": day,
                        "squad": human_squad_list,
                        "chips": human.chips,
                        "deployed_already": [already_used],
                        "error": "角斗士 " + already_used + " 已在第1局出战，不能再次选择！请重新选择。",
                    })
                    sync.deploy_event.wait()
                    sync.deploy_event.clear()
                    viz.clear_pending_wait()
                    for s, cid in sync.human_deployments.items():
                        human.deployments[s] = _real_char_id(cid)
            if viz:
                for s, cid in sync.human_deployments.items():
                    viz.emit("deployment", {"player": human.player_name, "day": day,
                             "slot": s, "slots": str(s),
                             "char_id": cid, "char_name": _squad_name(human, _real_char_id(cid))})

        # 运行 Match 2+3
        run_match_phase(human, ai, logger, day, slots=[2, 3])
        logger.log_phase("deploy_match23", "end", day)

        # 人类确认 Match 2+3 结果
        if viz and sync:
            # 展示 AI 的部署（延迟到人类确认后）
            for s in [2, 3]:
                if s in ai.deployments:
                    viz.emit("deployment", {"player": ai.player_name, "day": day,
                             "slot": s, "slots": str(s),
                             "char_id": ai.deployments[s],
                             "char_name": _squad_name(ai, ai.deployments[s])})
            sync.waiting_for = "confirm"
            viz.emit("awaiting_confirm", {
                "label": "比赛结果",
                "msg": "第2、3局比赛已结束",
                "detail": "所有比赛已完成。查看结果后点击'继续'。"
            })
            sync.confirm_event.wait()
            sync.confirm_event.clear()

        # Phase 4: 每日胜者奖励
        logger.log_phase("daily_winner_reward", "start", day)
        today_matches = state.match_history[-3:]
        wins_human = sum(1 for m in today_matches if m.get('winner') == human.player_name)
        wins_ai = sum(1 for m in today_matches if m.get('winner') == ai.player_name)
        print(f"  今日胜场: {human.player_name} {wins_human} 胜 | {ai.player_name} {wins_ai} 胜")

        # point_pool → reward_pool
        for p in [human, ai]:
            if p.squad:
                p.reward_pool += p.squad.point_pool
                p.squad.point_pool = 0

        if wins_human != wins_ai:
            daily_winner = human if wins_human > wins_ai else ai
            pool = daily_winner.reward_pool
            if pool <= 0:
                reward = 0
            elif pool < 50:
                reward = pool
            else:
                reward = 50
            if reward > 0:
                daily_winner.reward_pool -= reward
                daily_winner.earn_chips(reward)
            if viz:
                viz.emit("daily_winner", {"day": day, "winner": daily_winner.player_name,
                         "wins_a": wins_human, "wins_b": wins_ai, "reward": reward,
                         "pool_a": human.squad.point_pool if human.squad else 0,
                         "pool_b": ai.squad.point_pool if ai.squad else 0,
                         "reward_pool_a": human.reward_pool, "reward_pool_b": ai.reward_pool,
                         "chips_a": human.chips, "chips_b": ai.chips})
        else:
            if viz:
                viz.emit("daily_winner", {"day": day, "winner": None, "reward": 0,
                         "wins_a": wins_human, "wins_b": wins_ai,
                         "chips_a": human.chips, "chips_b": ai.chips})
        logger.log_phase("daily_winner_reward", "end", day)

        # Phase 5: 每日复盘
        logger.log_phase("day_summary", "start", day)

        # 先发送人类复盘表单（人类在 AI 复盘期间即可开始填写）
        if viz and sync:
            sync.reset()
            sync.waiting_for = "summary"
            viz.clear_pending_wait()
            viz.emit("awaiting_summary", {
                "day": day,
                "label": f"第{day}天复盘",
                "msg": "请填写每日复盘",
            })

        # AI 复盘（人类在填写复盘表单的同时进行）
        if viz:
            viz.emit("progress", {"msg": "AI 正在进行每日复盘..."})
            viz.emit("agent_message", {"player": ai.player_name,
                     "content": "AI 正在复盘...", "label": "系统", "role": "think"})
        daily_winner_info_ai = (
            f"今日胜者: {daily_winner.player_name if wins_human != wins_ai else '平局'}\n"
            f"你当前的游戏币: {ai.chips}"
        )
        summary_ai = _build_day_summary_text(ai, daily_winner_info_ai)
        msg_ai_summary = PROMPT_DAY_SUMMARY.format(day=day, player_info=summary_ai)
        resp_summary_ai = ai_agent.invoke(msg_ai_summary, allow_tools=False, extra_body=EXTRA_BODY_THINKING)
        logger.log_agent_message(ai.player_name, "reflect_day_summary", resp_summary_ai)

        # 等待人类复盘提交
        if viz and sync:
            sync.summary_event.wait()
            sync.summary_event.clear()
            viz.clear_pending_wait()
            logger.log_agent_message(human.player_name, "reflect_day_summary", sync.ranking_table)
            logger.log_agent_message(human.player_name, "chip_estimate", sync.chip_estimate)

        logger.log_phase("day_summary", "end", day)

        # Phase 6: 评估（仅 AI）
        print(f"\n── 评估阶段（仅 AI）──")
        logger.log_phase("evaluation", "start", day)
        if viz:
            viz.emit("progress", {"msg": "正在评估 AI 智能体表现，请稍等..."})

        ground_truth = evaluator.load_ground_truth()
        parsed_preview_ai = _parse_preview_history(preview_history_ai)
        agent_msgs_ai = _extract_assistant_messages(ai_agent)

        match_results_ai = [
            {"slot": i + 1,
             "won": m.get('winner') == ai.player_name,
             "my_char": m.get('winner_char_id', '?') if m.get('winner') == ai.player_name else m.get('loser_char_id', '?'),
             "opp_char": m.get('loser_char_id', '?') if m.get('winner') == ai.player_name else m.get('winner_char_id', '?'),
             "point_transferred": m.get('point_transferred', 0),
             "multiplier": m.get('multiplier', 1.0)}
            for i, m in enumerate(state.match_history[-3:])
        ]

        auction_summary_ai = json.dumps({
            "my_gladiators": [{"name": g["name"], "char_id": g["char_id"], "point": g.get("point", 0)} for g in auction.owner_b],
            "opponent_gladiators": [{"name": g["name"], "char_id": g["char_id"]} for g in auction.owner_a],
        }, ensure_ascii=False, indent=2)

        my_bids_ai = [r for r in auction.bid_history if ai.player_name in str(r.get("bids", {}))]
        opp_chips_range_ai = _estimate_opponent_chips(human, auction)

        # M1-M7 评估 AI
        print(f"\n  ── {ai.player_name} 评估 ──")
        evaluator.evaluate_rule_compliance(day, ai.player_name, agent_msgs_ai)
        evaluator.evaluate_factual_accuracy(day, ai.player_name, agent_msgs_ai, parsed_preview_ai, my_bids_ai, opp_chips_range_ai, ground_truth)
        evaluator.evaluate_strategy_quality(day, ai.player_name, resp_post_ai,
            f"全天复盘:\n{resp_summary_ai}", resp_summary_ai, auction_summary_ai,
            ai.deployments if hasattr(ai, 'deployments') else {}, match_results_ai)
        point_pool_ai = ai.squad.point_pool if ai.squad else 0
        evaluator.evaluate_economic_rationality_v2(day, ai.player_name, ai.chips, 800, ai.reward_pool, point_pool_ai, my_bids_ai)
        evaluator.evaluate_information_utilization(day, ai.player_name, agent_msgs_ai, parsed_preview_ai, resp_summary_ai, ground_truth)
        opp_actions_ai = getattr(ai, '_opponent_actions', [])
        opp_deploys_ai = human.deployments if human.deployments else {}
        evaluator.evaluate_opponent_modeling_v2(day, ai.player_name, agent_msgs_ai, opp_actions_ai, opp_deploys_ai, resp_post_ai, resp_match1_ai)
        evaluator.evaluate_chip_estimation(day, ai.player_name, resp_summary_ai, human.chips)

        logger.log_phase("evaluation", "end", day)

        # Day advancement
        if human.squad:
            human.squad.next_day()
        if ai.squad:
            ai.squad.next_day()
        human.deployments = {}
        ai.deployments = {}

        for p in [human, ai]:
            fatigue = p.squad.summary() if p.squad else "无阵容"
            points = p.squad.get_total_points() if p.squad else 0
            logger.log_daily_summary(day, p.player_name, p.chips, points, fatigue)

        logger.log_state_snapshot(day, human.summary(), ai.summary())

    # ── 最终结算 ──
    # 破产情况下已在 _execute_bankruptcy 中完成清算，跳过正常结算
    if getattr(state, 'game_over', False):
        print()
        print("=" * 60)
        print("  最终结算（破产）")
        print("=" * 60)
        print(f"  {state.bankrupt_player}: 游戏币 0")
        print(f"  {state.winner_name}: 游戏币 1600")
        total_human = human.chips
        total_ai = ai.chips
    else:
        print()
        print("=" * 60)
        print("  最终结算")
        print("=" * 60)

        for player in [human, ai]:
            pool = player.squad.point_pool if player.squad else 0
            rp = player.reward_pool
            player.chips += pool + rp
            if player.squad:
                player.squad.point_pool = 0
            player.reward_pool = 0
            print(f"  {player.player_name}: 总计 {player.chips} 游戏币")

        total_human = human.chips
        total_ai = ai.chips

    if not getattr(state, 'game_over', False):
        if total_human > total_ai:
            print(f"\n{human.player_name} 最终胜出！游戏币 {total_human} vs {total_ai}")
            winner_name = human.player_name
        elif total_ai > total_human:
            print(f"\n{ai.player_name} 最终胜出！游戏币 {total_ai} vs {total_human}")
            winner_name = ai.player_name
        else:
            print(f"\n双方平局！游戏币 {total_human}")
            winner_name = "平局"

        if viz:
            viz.emit("final_result", {"winner": winner_name, "chips_a": total_human, "chips_b": total_ai})
            viz.mark_game_over()

    logger.log_final_summary(human.summary(), ai.summary())
    logger.close()


if __name__ == "__main__":
    run_experiment()
