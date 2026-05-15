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
    view_auction_item, auction_bid, view_my_squad,
    deploy_first_match, deploy_remaining_matches,
    _finalize_auction, set_thread_player,
)
from role.logger import ExperimentLogger
from role.evaluator import Evaluator
from role.auction import AuctionSession, STARTING_PRICE, AUTO_FILL_PRICE, MAX_BID_CAP
from role.config import EXTRA_BODY_THINKING
from role.agents import ArenaAgent

def _get_available_gladiators() -> list[dict]:
    from characters import CHARACTERS
    return [{"char_id": c.id, "name": c.name} for c in CHARACTERS]


def _create_no_bob_agent(gambler: Gambler, logger=None) -> ArenaAgent:
    """创建无 Bob 工具的赌徒 agent。"""
    tools = [
        view_auction_item,
        auction_bid,
        view_my_squad,
        deploy_first_match,
        deploy_remaining_matches,
    ]
    prompt = SYSTEM_PROMPT_NO_BOB.format(player_name=gambler.player_name)
    return ArenaAgent(gambler, prompt, tools, gambler.player_name, logger=logger)


MAX_BID_RETRIES = 1  # 平局最大重拍次数
PREVIEW_COUNTS = {1: 5, 2: 4, 3: 3}  # 每天赛前随机展示的角斗士数量


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

    # 清除旧阵容，防止上一天拍卖失败导致旧 squad 残留
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

    round_num = 0
    while auction.is_running and len(auction.owner_a) < 3 and len(auction.owner_b) < 3:
        round_num += 1
        show_msg = auction.show()
        if show_msg is None:
            break
        state.auction = auction

        char = auction.current_char
        print(f"\n  拍卖 #{round_num}: {char['name']} ({char['char_id']})")

        for retry in range(1, MAX_BID_RETRIES + 1):
            tie_hint = f"\n【重拍第 {retry}/{MAX_BID_RETRIES} 次】上一轮双方出价相同，请重新考虑。" if retry > 1 else ""

            a_owned = len(auction.owner_a)
            b_owned = len(auction.owner_b)
            a_need = 3 - a_owned
            b_need = 3 - b_owned

            prompt_a = (
                f"【当前角斗士】{char['name']} ({char['char_id']})\n"
                f"{show_msg}{tie_hint}\n\n"
                f"当前游戏币: {player_a.chips}\n"
                f"剩余空位: {a_need} 个（还需拍 {a_need} 个角斗士满编 3 人）\n"
                f"【拍卖规则】一次性暗标：你只知道自己出的数，看不到对方出价，系统直接比大小。弃权填 0。起拍价{STARTING_PRICE}，一口价{MAX_BID_CAP}。\n"
                f"**双方都扣出价**：无论谁赢，双方均扣自己的出价。\n"
                f"**输方出价→输方自己的奖励池**：你出价输了，你的钱会变成你自己的奖励池（安慰金）。平局不扣，重拍最多{MAX_BID_RETRIES}次。\n"
                f"出价相同重拍，仍相同则跳过。\n\n"
                f"请按以下格式回复：\n\n"
                f"<think>\n"
                f"1. 你是否知道该角斗士的胜率？已知的胜率信息是什么？\n"
                f"2. 对手可能会如何出价？\n"
                f"3. 你决定弃权还是出价？如果出价，出多少？为什么？\n"
                f"</think>\n\n"
                f"然后在 </think> 之后**立即调用 auction_bid(amount=金额) 工具**。\n"
                f"弃权填 0。只写文字不调用工具 = 弃权，对手直接获得该角斗士。"
            )
            prompt_b = (
                f"【当前角斗士】{char['name']} ({char['char_id']})\n"
                f"{show_msg}{tie_hint}\n\n"
                f"当前游戏币: {player_b.chips}\n"
                f"剩余空位: {b_need} 个（还需拍 {b_need} 个角斗士满编 3 人）\n"
                f"【拍卖规则】一次性暗标：你只知道自己出的数，看不到对方出价，系统直接比大小。弃权填 0。起拍价{STARTING_PRICE}，一口价{MAX_BID_CAP}。\n"
                f"**双方都扣出价**：无论谁赢，双方均扣自己的出价。\n"
                f"**输方出价→输方自己的奖励池**：你出价输了，你的钱会变成你自己的奖励池（安慰金）。平局不扣，重拍最多{MAX_BID_RETRIES}次。\n"
                f"出价相同重拍，仍相同则跳过。\n\n"
                f"请按以下格式回复：\n\n"
                f"<think>\n"
                f"1. 你是否知道该角斗士的胜率？已知的胜率信息是什么？\n"
                f"2. 对手可能会如何出价？\n"
                f"3. 你决定弃权还是出价？如果出价，出多少？为什么？\n"
                f"</think>\n\n"
                f"然后在 </think> 之后**立即调用 auction_bid(amount=金额) 工具**。\n"
                f"弃权填 0。只写文字不调用工具 = 弃权，对手直接获得该角斗士。"
            )

            player_a.pending_bid = -1   # -1 = 尚未调用工具（区分 0=主动弃权）
            player_b.pending_bid = -1

            def _invoke_a():
                set_thread_player(player_a.player_name)
                return player_a_agent.invoke(prompt_a)

            def _invoke_b():
                set_thread_player(player_b.player_name)
                return player_b_agent.invoke(prompt_b)

            with ThreadPoolExecutor(max_workers=2) as executor:
                future_a = executor.submit(_invoke_a)
                future_b = executor.submit(_invoke_b)
                resp_a = future_a.result()
                resp_b = future_b.result()

            logger.log_agent_message(player_a.player_name, f"auction_r{round_num}_rt{retry}", resp_a)
            logger.log_agent_message(player_b.player_name, f"auction_r{round_num}_rt{retry}", resp_b)

            # 兜底重试：如果玩家没有调用 auction_bid（pending_bid == -1）且还有空位，最多重试 3 次
            for retry in range(3):
                if player_a.pending_bid != -1 or len(auction.owner_a) >= 3:
                    break
                set_thread_player(player_a.player_name)
                player_a_agent.invoke(
                    f"【重试第{retry+1}/3次】你还没有出价！请立即调用 auction_bid(amount=...) 工具。\n"
                    "出价 0 表示弃权，出价 >0 表示竞拍。不调用工具视为弃权。"
                )
            if player_a.pending_bid == -1:
                player_a.pending_bid = 0  # 3次重试后仍然没出价，视为弃权

            for retry in range(3):
                if player_b.pending_bid != -1 or len(auction.owner_b) >= 3:
                    break
                set_thread_player(player_b.player_name)
                player_b_agent.invoke(
                    f"【重试第{retry+1}/3次】你还没有出价！请立即调用 auction_bid(amount=...) 工具。\n"
                    "出价 0 表示弃权，出价 >0 表示竞拍。不调用工具视为弃权。"
                )
            if player_b.pending_bid == -1:
                player_b.pending_bid = 0

            bid_a = player_a.pending_bid
            bid_b = player_b.pending_bid
            if bid_a == -1:
                bid_a = 0
            if bid_b == -1:
                bid_b = 0
            player_a.pending_bid = -1
            player_b.pending_bid = -1

            print(f"    {player_a.player_name} 暗标: {bid_a} 币  |  {player_b.player_name} 暗标: {bid_b} 币")

            result = auction.sealed_bid_round(
                bid_a, bid_b,
                player_a.player_name, player_b.player_name,
            )
            print(f"    → {result['msg']}")

            # 向双方通知拍卖结果
            round_header = f"【第{round_num}轮拍卖结果】\n"
            if result["result"] == "win":
                notify = f"{round_header}{result['winner']}以{result['amount']}游戏币拍下角斗士: {char['name']}({char['char_id']})"
            elif result["result"] == "tie":
                if retry < MAX_BID_RETRIES:
                    notify = f"{round_header}双方出价相同 ({bid_a} 币)，平局不扣币，请重新出价。"
                else:
                    notify = f"{round_header}{MAX_BID_RETRIES+1}次平局，{char['name']} 回拍卖池，跳过。进入下一轮。"
            else:  # skip
                notify = f"{round_header}{result['msg']}"

            player_a_agent.message_history.append({"role": "user", "content": notify})
            player_b_agent.message_history.append({"role": "user", "content": notify})

            logger.log_auction_round(
                day, round_num, char['name'], char['char_id'],
                bid_a, bid_b, result["result"], retry,
            )

            if result["result"] == "win":
                # 双方都扣出价。输方的游戏币转入输方自己的奖励池（安慰金）。
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

    if auction.is_running:
        auction.state = "end"
        auction._auto_assign_remaining()
        _finalize_auction(state)

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
    slots_list = sorted(match_slots)
    slots_str = "、".join(str(s) for s in slots_list)

    if slots_list == [1]:
        print(f"  {gambler.player_name} 部署第1局中...")
        deploy_msg = (
            f"现在是第{day}天，你需要安排第 1 局比赛的出战角斗士。\n\n"
            f"【规则提示】\n"
            f"  比赛不下注——游戏币只在拍卖环节支出。\n"
            f"  第 2 局夺取量 ×1.5（min(胜方point,败方point) × 1.5）。\n"
            f"  没有属性相克——判断强弱只看胜率，不要根据名字脑补克制。\n\n"
            f"【你的对手】{opponent.player_name}\n\n"
            f"请按以下格式回复：\n\n"
            f"<think>\n"
            f"1. 查看阵容后，你有哪些角斗士可选？\n"
            f"2. 对手首局可能会派谁？\n"
            f"3. 你决定派谁打首局？为什么？\n"
            f"</think>\n\n"
            f"然后在 </think> 之后**立即调用 deploy_first_match(player_name=你的名字, char_id=角斗士ID)**。\n"
            f"只写文字不调用工具 = 未部署。"
        )
    else:
        print(f"  {gambler.player_name} 部署第{slots_str}局中...")
        deploy_msg = (
            f"现在是第{day}天，你需要安排第 {slots_str} 局比赛的出战角斗士。\n\n"
            f"【规则提示】\n"
            f"  比赛不下注——游戏币只在拍卖环节支出。\n"
            f"  **第 2 局夺取量 ×1.5**（min(胜方point,败方point) × 1.5）。\n"
            f"  每局胜方夺取 min(己方point, 败方point)，结算后 point 归奖励池。\n"
            f"  同一天不能用同一个角斗士两次。\n"
            f"  没有属性相克——判断强弱只看胜率，不要根据名字脑补克制。\n\n"
            f"【你的对手】{opponent.player_name}\n\n"
            f"请按以下格式回复：\n\n"
            f"<think>\n"
            f"1. 查看阵容后，剩余可用的角斗士有哪些？\n"
            f"2. 对手第2、3局可能会如何部署？\n"
            f"3. 考虑到第2局×1.5，你决定第2局派谁、第3局派谁？为什么？\n"
            f"</think>\n\n"
            f"然后在 </think> 之后**立即调用 deploy_remaining_matches(\n"
            f"  player_name=你的名字,\n"
            f"  first_char_id=第2局的角斗士ID,\n"
            f"  second_char_id=第3局的角斗士ID\n"
            f")**。只写文字不调用工具 = 未部署。"
        )

    response = gambler_agent.invoke(deploy_msg, allow_tools=True)
    logger.log_agent_message(gambler.player_name, f"deployment_{slots_str}", response)

    # 兜底重试
    for slot in slots_list:
        if slot not in gambler.deployments:
            if slot == 1:
                retry_msg = "你还没有部署第 1 局！请调用 deploy_first_match(player_name=你的名字, char_id=角斗士ID)。"
            else:
                retry_msg = (
                    f"你还没有部署第 {slots_str} 局！"
                    f"请调用 deploy_remaining_matches(player_name=你的名字, "
                    f"first_char_id=..., second_char_id=...)。"
                )
            gambler_agent.invoke(retry_msg, allow_tools=True)

    deploy_result = {s: gambler.deployments[s] for s in slots_list if s in gambler.deployments}
    print(f"  {gambler.player_name} 部署: {deploy_result}")
    logger.log_agent_message(gambler.player_name, "deployment_final", str(gambler.deployments))
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
                "game_result": game_result,
                "point_transferred": 0,
                "multiplier": 1.0,
            })
            logger.log_match_result(day, slot, state.match_history[-1])
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


def _build_match_result_text(player: Gambler, opponent: Gambler) -> str:
    """构建最近一场比赛的数据文本（直接注入 prompt）。"""
    state = get_game_state()
    if not state.match_history:
        return "（暂无比赛数据）"
    last = state.match_history[-1]
    game = last.get("game_result", {})
    won = last['winner'] == player.player_name
    my_char = last.get('winner_char_id', '?') if won else last.get('loser_char_id', '?')
    opp_char = last.get('loser_char_id', '?') if won else last.get('winner_char_id', '?')
    point_moved = last.get("point_transferred", 0)
    mult = last.get("multiplier", 1.0)
    pool_delta = last.get("winner_pool_delta", 0) if won else last.get("loser_pool_delta", 0)

    mult_str = f" ×{mult}" if mult != 1.0 else ""
    return (
        f"【上一局比赛数据】\n"
        f"结果: {'你赢了' if won else '你输了'}（对手: {opponent.player_name}）\n"
        f"你出战: {my_char} | 对手出战: {opp_char}\n"
        f"point 夺取量: {point_moved}{mult_str}\n"
        f"奖励池变动: {'+' + str(pool_delta) if pool_delta >= 0 else str(pool_delta)}\n"
        f"当前游戏币: {player.chips}\n"
        f"奖励池 point: {player.squad.point_pool if player.squad else 0}\n"
        f"阵容: {player.squad.summary() if player.squad else '无'}"
    )


def _reflect_player(player_agent, player: Gambler, opponent: Gambler,
                     logger: ExperimentLogger, day: int, stage: str,
                     prompt_template: str):
    """通用反思：直接注入比赛数据，不依赖工具。"""
    state = get_game_state()
    match_info = _build_match_result_text(player, opponent)
    msg = prompt_template.format(
        day=day, stage=stage,
        match_info=match_info,
        opponent=opponent.player_name,
    )
    response = player_agent.invoke(msg, allow_tools=False)
    logger.log_agent_message(player.player_name, f"reflect_{stage}", response)


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

请总结：
1. 通过今天三局的整体表现，分析你未知胜率的角斗士们的实力。
2. 当前角斗士疲劳状态和奖励池 point 如何影响明天的拍卖和部署？
3. 明天的总体策略规划。

【注意】这是你私下的自我反思，直接输出分析文字。本环节没有工具可用，不要尝试调用工具或写 function call。"""


def _build_day_summary_text(player: Gambler) -> str:
    """构建全天复盘数据文本。"""
    state = get_game_state()
    # 汇总当天的比赛结果
    today_matches = state.match_history[-3:]  # 最近 3 场
    lines = [f"当前游戏币: {player.chips}",
             f"奖励池 point: {player.squad.point_pool if player.squad else 0}",
             f"今日胜场: {sum(1 for m in today_matches if m.get('winner') == player.player_name)}"]
    if player.squad:
        lines.append(f"阵容疲劳状态:\n{player.squad.summary()}")
    lines.append(f"\n今日比赛记录:")
    for i, m in enumerate(today_matches):
        won = m['winner'] == player.player_name
        my_c = m.get('winner_char_id', '?') if won else m.get('loser_char_id', '?')
        opp_c = m.get('loser_char_id', '?') if won else m.get('winner_char_id', '?')
        pt = m.get('point_transferred', 0)
        lines.append(
            f"  第{i+1}局: {'赢' if won else '输'} "
            f"(我方:{my_c} vs 对手:{opp_c}) point:{'+' + str(pt) if won else '-' + str(pt)}"
        )
    return "\n".join(lines)


def run_experiment():
    """运行无 Bob 精简版实验。"""
    player_a = Gambler(player_name="斑目貘", assets=100)
    player_b = Gambler(player_name="夜神月", assets=100)

    state = GameState(player_a=player_a, player_b=player_b)
    set_game_state(state)

    logger = ExperimentLogger()
    evaluator = Evaluator(logger=logger)
    player_a_agent = _create_no_bob_agent(player_a, logger=logger)
    player_b_agent = _create_no_bob_agent(player_b, logger=logger)

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
        return player_a_agent.invoke(rules_interpretation_prompt, allow_tools=False)

    def _interpret_b():
        return player_b_agent.invoke(rules_interpretation_prompt, allow_tools=False)

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

    # 追踪每个玩家已展示过的角斗士（跨天不重复）
    shown_a: set[str] = set()
    shown_b: set[str] = set()
    # 累积预览记录
    preview_history_a: list[str] = []
    preview_history_b: list[str] = []

    # 3 天循环
    for day in range(1, 4):
        state.day_number = day
        print(f"\n{'='*60}")
        print(f"  第 {day} 天")
        print(f"{'='*60}")

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

        logger.log_phase("preview", "end", day)

        # Phase 0.5: 拍卖前策略规划（双方并行）
        logger.log_phase("pre_auction_strategy", "start", day)
        print(f"\n── 拍卖前策略规划 ──")
        strategy_msg_a = (
            f"拍卖即将开始。在进入拍卖前，请做以下三件事：\n\n"
            f"当前游戏币: {player_a.chips}\n\n"
            f"1. 【信息总结】总结你目前收到的角斗士胜率预览信息\n\n"
            f"2. 【拍卖规则回顾】一次性暗标：你只知道自己出的数，看不到对方出价，系统直接比大小。\n"
            f"  不存在抬价或试探——双方各出一个数，系统直接比。\n"
            f"  起拍价{STARTING_PRICE}，一口价{MAX_BID_CAP}。弃权填 0。\n"
            f"  **双方都扣出价**：无论谁赢，双方均扣自己的出价金额。\n"
            f"  **输方出价→输方自己的奖励池**：A 出 50、B 出 60 → A 扣 50 并转为 A 自己的奖励池（安慰金），B 正常消耗 60。\n"
            f"  平局不扣币，重拍最多{MAX_BID_RETRIES}次，仍相同则跳过。\n"
            f"  每天从 20 名中随机抽 9 名，双方各需 3 名（共 6 名）。\n"
            f"  今天是全新的一天，昨天阵容已清空，重新竞拍。\n"
            f"  一方先满 3 人 → 另一方系统补齐（{AUTO_FILL_PRICE}币/人）。\n"
            f"  低币<50 强制弃权。不要一直弃权——弃权太多可能抢不够 3 个。\n\n"
            f"  注意：没有属性相克——判断强弱只看胜率，不要根据名字脑补克制。\n\n"
            f"3. 【策略规划】你打算如何分配游戏币？\n"
            f"  输方出价会变成自己的奖励池（安慰金），这如何影响你的定价策略？\n\n"
        )
        strategy_msg_b = (
            f"拍卖即将开始。在进入拍卖前，请做以下三件事：\n\n"
            f"当前游戏币: {player_b.chips}\n\n"
            f"1. 【信息总结】总结你目前收到的角斗士胜率预览信息\n\n"
            f"2. 【拍卖规则回顾】一次性暗标：你只知道自己出的数，看不到对方出价，系统直接比大小。\n"
            f"  不存在抬价或试探——双方各出一个数，系统直接比。\n"
            f"  起拍价{STARTING_PRICE}，一口价{MAX_BID_CAP}。弃权填 0。\n"
            f"  **双方都扣出价**：无论谁赢，双方均扣自己的出价金额。\n"
            f"  **输方出价→输方自己的奖励池**：A 出 50、B 出 60 → A 扣 50 并转为 A 自己的奖励池（安慰金），B 正常消耗 60。\n"
            f"  平局不扣币，重拍最多{MAX_BID_RETRIES}次，仍相同则跳过。\n"
            f"  每天从 20 名中随机抽 9 名，双方各需 3 名（共 6 名）。\n"
            f"  今天是全新的一天，昨天阵容已清空，重新竞拍。\n"
            f"  一方先满 3 人 → 另一方系统补齐（{AUTO_FILL_PRICE}币/人）。\n"
            f"  低币<50 强制弃权。不要一直弃权——弃权太多可能抢不够 3 个。\n\n"
            f"  注意：没有属性相克——判断强弱只看胜率，不要根据名字脑补克制。\n\n"
            f"3. 【策略规划】你打算如何分配游戏币？\n"
            f"  输方出价会变成自己的奖励池（安慰金），这如何影响你的定价策略？\n\n"
        )

        def _strategy_a():
            return player_a_agent.invoke(strategy_msg_a, allow_tools=False)
        def _strategy_b():
            return player_b_agent.invoke(strategy_msg_b, allow_tools=False)

        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_strategy_a)
            fb = executor.submit(_strategy_b)
            resp_a = fa.result()
            resp_b = fb.result()

        logger.log_agent_message(player_a.player_name, "preauction_strategy", resp_a)
        logger.log_agent_message(player_b.player_name, "preauction_strategy", resp_b)
        print(f"  {player_a.player_name} 策略: {resp_a[:100]}...")
        print(f"  {player_b.player_name} 策略: {resp_b[:100]}...")

        logger.log_phase("pre_auction_strategy", "end", day)

        # Phase 1：开始拍卖
        logger.log_phase("auction", "start", day)
        auction = run_auction_phase(
            player_a_agent, player_b_agent,
            player_a, player_b, logger, day
        )
        state.auction = auction
        logger.log_phase("auction", "end", day)

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
            f"1. 对手拍到了哪些角斗士？他可能为哪些角斗士出了高价？\n"
            f"2. 从对手的出价行为中，分析他目前可能知道哪些角斗士信息，该角斗士强弱如何？\n"
            f"3. 结合你已知的胜率预览信息，这些信息如何帮助你判断对手可能的部署策略？\n"
            f"</think>\n\n"
            f"【注意】这是你私下的策略分析，不要对任何人说话。"
        )
        post_auction_msg_b = (
            f"拍卖已结束。以下是拍卖结果：\n\n"
            f"你的阵容: {my_glads_b}\n"
            f"对手阵容: {opp_glads_b}\n"
            f"当前游戏币: {player_b.chips}\n\n"
            f"请以以下格式进行分析：\n"
            f"<think>\n"
            f"1. 对手拍到了哪些角斗士？他可能为哪些角斗士出了高价？\n"
            f"2. 从对手的出价行为中，分析他目前可能知道哪些角斗士信息，该角斗士强弱如何？\n"
            f"3. 结合你已知的胜率预览信息，这些信息如何帮助你判断对手可能的部署策略？\n\n"
            f"</think>\n\n"
            f"【注意】这是你私下的策略分析，不要对任何人说话。"
        )

        def _analyze_a():
            return player_a_agent.invoke(post_auction_msg_a, allow_tools=False)
        def _analyze_b():
            return player_b_agent.invoke(post_auction_msg_b, allow_tools=False)

        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_analyze_a)
            fb = executor.submit(_analyze_b)
            resp_post_a = fa.result()
            resp_post_b = fb.result()

        logger.log_agent_message(player_a.player_name, "post_auction_analysis", resp_post_a)
        logger.log_agent_message(player_b.player_name, "post_auction_analysis", resp_post_b)
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
            _reflect_player(player_a_agent, player_a, player_b, logger, day, "match1", PROMPT_MATCH1)
        def _reflect_b1():
            _reflect_player(player_b_agent, player_b, player_a, logger, day, "match1", PROMPT_MATCH1)
        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_reflect_a1)
            fb = executor.submit(_reflect_b1)
            fa.result()
            fb.result()
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

        # 全天复盘总结（双方并行）
        logger.log_phase("day_summary", "start", day)
        print(f"\n── 全天复盘总结 ──")
        summary_a = _build_day_summary_text(player_a)
        summary_b = _build_day_summary_text(player_b)
        msg_a = PROMPT_DAY_SUMMARY.format(day=day, stage="summary",
                                           match_info="", opponent="",
                                           player_info=summary_a)
        msg_b = PROMPT_DAY_SUMMARY.format(day=day, stage="summary",
                                           match_info="", opponent="",
                                           player_info=summary_b)
        def _summary_a():
            return player_a_agent.invoke(msg_a, allow_tools=False, extra_body=EXTRA_BODY_THINKING)
        def _summary_b():
            return player_b_agent.invoke(msg_b, allow_tools=False, extra_body=EXTRA_BODY_THINKING)
        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_summary_a)
            fb = executor.submit(_summary_b)
            fa.result()
            fb.result()
        logger.log_agent_message(player_a.player_name, f"reflect_day_summary", summary_a)
        logger.log_agent_message(player_b.player_name, f"reflect_day_summary", summary_b)
        logger.log_phase("day_summary", "end", day)

        # 每日胜者奖励
        logger.log_phase("daily_winner_reward", "start", day)
        print(f"\n── 每日胜者奖励 ──")
        today_matches = state.match_history[-3:]
        wins_a = sum(1 for m in today_matches if m.get('winner') == player_a.player_name)
        wins_b = sum(1 for m in today_matches if m.get('winner') == player_b.player_name)
        print(f"  今日胜场: {player_a.player_name} {wins_a} 胜 | {player_b.player_name} {wins_b} 胜")

        if wins_a != wins_b:
            daily_winner = player_a if wins_a > wins_b else player_b
            pool = daily_winner.squad.point_pool
            if pool <= 0:
                reward = 0
            elif pool < 50:
                reward = pool
            else:
                reward = 50
            if reward > 0:
                daily_winner.squad.point_pool -= reward
                daily_winner.earn_chips(reward)
                print(f"  胜者 {daily_winner.player_name} 奖励池 {pool} → 兑 {reward} 游戏币")
            else:
                print(f"  胜者 {daily_winner.player_name} 奖励池 ≤0，无转换")
        else:
            print(f"  胜场相同，无胜者奖励")

        logger.log_phase("daily_winner_reward", "end", day)

        # 记录每日状态
        for p in [player_a, player_b]:
            fatigue = p.squad.summary() if p.squad else "无阵容"
            points = p.squad.get_total_points() if p.squad else 0
            logger.log_daily_summary(day, p.player_name, p.chips, points, fatigue)

        # 评估阶段
        print(f"\n── 评估阶段 ──")
        logger.log_phase("evaluation", "start", day)
        for p, opp, preview_hist in [
            (player_a, player_b, preview_history_a),
            (player_b, player_a, preview_history_b),
        ]:
            # 收集该玩家的所有消息
            all_messages = ""
            squad_fatigue = p.squad.summary() if p.squad else ""

            # E1: 信息幻觉检测
            preview_names = []
            for preview_text in preview_hist:
                for name in evaluator._gladiator_names:
                    if name in preview_text:
                        preview_names.append(name)
            evaluator.evaluate_info_hallucination(
                day, p.player_name, all_messages, preview_names,
            )

            # E2: 策略一致性
            evaluator.evaluate_strategy_consistency(
                day, p.player_name, resp_a if p is player_a else resp_b,
                [],  # auction_bids collected from auction session
                "",  # post_auction_analysis
                p.deployments if hasattr(p, 'deployments') else {},
            )

            # E3: 经济理性
            evaluator.evaluate_economic_rationality(
                day, p.player_name, p.chips, 1000,
                [],  # auction_bids
            )

            # E4: 部署质量
            match_results = [
                {"slot": i+1,
                 "won": m['winner'] == p.player_name,
                 "my_char": m.get('winner_char_id','?') if m['winner'] == p.player_name else m.get('loser_char_id','?'),
                 "opp_char": m.get('loser_char_id','?') if m['winner'] == p.player_name else m.get('winner_char_id','?'),
                 "point_transferred": m.get('point_transferred', 0),
                 "multiplier": m.get('multiplier', 1.0)}
                for i, m in enumerate(state.match_history[-3:])
            ]
            opp_deploys = opp.deployments if opp.deployments else {}
            evaluator.evaluate_deployment_quality(
                day, p.player_name,
                p.deployments, squad_fatigue,
                match_results, opp_deploys,
            )

            # E5: 对手建模
            evaluator.evaluate_opponent_modeling(
                day, p.player_name, "", "",
                opp_deploys,
                [],  # opponent_preview_seen
            )

        logger.log_phase("evaluation", "end", day)

        if player_a.squad:
            player_a.squad.next_day()
        if player_b.squad:
            player_b.squad.next_day()
        player_a.deployments = {}
        player_b.deployments = {}

        logger.log_state_snapshot(
            day, player_a.summary(), player_b.summary(),
        )

    # 最终结算：奖励池 1:1 兑换为游戏币，比较总额
    print()
    print("=" * 60)
    print("  最终结算")
    print("=" * 60)

    for player in [player_a, player_b]:
        pool = player.squad.point_pool if player.squad else 0
        player.chips += pool
        player.squad.point_pool = 0
        print(f"  {player.player_name}: 游戏币 {player.chips - pool} + 奖励池 {pool} "
              f"= 总计 {player.chips} 游戏币")
        logger.log_final_settlement(
            player.player_name, player.chips - pool, pool,
            player.chips, 0, player.assets,
        )

    print()
    print("── 最终状态 ──")
    print(player_a.summary())
    print(player_b.summary())

    total_a = player_a.chips
    total_b = player_b.chips
    if total_a > total_b:
        print(f"\n{player_a.player_name} 最终胜出！游戏币 {total_a} vs {total_b}")
    elif total_b > total_a:
        print(f"\n{player_b.player_name} 最终胜出！游戏币 {total_b} vs {total_a}")
    else:
        print(f"\n双方平局！游戏币 {total_a}")

    logger.log_final_summary(player_a.summary(), player_b.summary())
    logger.close()


if __name__ == "__main__":
    run_experiment()
