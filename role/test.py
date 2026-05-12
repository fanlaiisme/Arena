"""Arena 角色实验 —— 新赌局玩法（3天×3局 + 拍卖 + 疲劳 + 游戏币）。

用法:
  cd /home/fanlai/Arena && .venv/bin/python role/test.py
"""

import sys
import os
import random
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from role.bob import Bob
from role.gambler import Gambler
from role.tools import GameState, set_game_state, get_game_state, set_thread_player
from role.agents import create_bob_agent, create_gambler_agent
from role.logger import ExperimentLogger
from role.evaluator import Evaluator
from role.auction import AuctionSession
from role.config import EXTRA_BODY_THINKING

def _get_available_gladiators() -> list[dict]:
    """获取所有可用角斗士（name + char_id）。"""
    from characters import CHARACTERS
    return [{"char_id": c.id, "name": c.name} for c in CHARACTERS]


MAX_BID_RETRIES = 3  # 平局最大重拍次数
PREVIEW_COUNT = 5     # 每天赛前随机展示的角斗士数量


def _random_gladiator_preview(shown_ids: set[str]) -> tuple[str, set[str]]:
    """从 tournament_stats.json 随机选 PREVIEW_COUNT 个未展示过的角斗士。

    Args:
        shown_ids: 已展示过的 char_id 集合

    Returns:
        (预览文本, 更新后的 shown_ids)
    """
    stats_file = os.path.join(
        os.path.dirname(__file__), "data", "Bob", "tournament_stats.json")
    with open(stats_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    available = [g for g in data["rankings"] if g["char_id"] not in shown_ids]
    count = min(PREVIEW_COUNT, len(available))
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
                       logger: ExperimentLogger):
    """运行一天的拍卖阶段（暗标+并行）。双方同时思考、同时出价。"""
    print(f"\n── 拍卖阶段: 暗标竞拍（并行）──")

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

        # ── 暗标出价 + 重拍循环 ──
        for retry in range(1, MAX_BID_RETRIES + 1):
            tie_hint = f"\n【重拍第 {retry}/{MAX_BID_RETRIES} 次】上一轮双方出价相同，请重新考虑。" if retry > 1 else ""

            # 构建双方各自的 prompt
            a_owned = len(auction.owner_a)
            b_owned = len(auction.owner_b)
            a_need = 3 - a_owned
            b_need = 3 - b_owned

            prompt_a = (
                f"【当前角斗士】{char['name']} ({char['char_id']})\n"
                f"{show_msg}{tie_hint}\n\n"
                f"【你的阵容】（{a_owned}/3 个角斗士，具体见 view_my_squad）\n\n"
                f"【规则】\n"
                f"- 暗标出价：双方同时出价，高者得\n"
                f"- 弃权输入 0\n"
                f"- 出价从你的游戏币余额中扣除\n"
                f"- 出价相同时重拍（最多{MAX_BID_RETRIES}次），仍相同则跳过该角斗士\n"
                f"- 还剩 {a_need} 个空位需要填充\n\n"
                f"请调用 auction_bid 工具出价。"
            )
            prompt_b = (
                f"【当前角斗士】{char['name']} ({char['char_id']})\n"
                f"{show_msg}{tie_hint}\n\n"
                f"【你的阵容】（{b_owned}/3 个角斗士，具体见 view_my_squad）\n\n"
                f"【规则】\n"
                f"- 暗标出价：双方同时出价，高者得\n"
                f"- 弃权输入 0\n"
                f"- 出价从你的游戏币余额中扣除\n"
                f"- 出价相同时重拍（最多{MAX_BID_RETRIES}次），仍相同则跳过该角斗士\n"
                f"- 还剩 {b_need} 个空位需要填充\n\n"
                f"请调用 auction_bid 工具出价。"
            )

            # 双方并行思考 + 出价
            player_a.pending_bid = 0
            player_b.pending_bid = 0

            def _invoke_a():
                set_thread_player(player_a.player_name)
                return player_a_agent.invoke(prompt_a)

            def _invoke_b():
                set_thread_player(player_b.player_name)
                return player_b_agent.invoke(prompt_b)

            with ThreadPoolExecutor(max_workers=2) as executor:
                future_a = executor.submit(_invoke_a)
                future_b = executor.submit(_invoke_b)

                # 等待双方完成
                resp_a = future_a.result()
                resp_b = future_b.result()

            logger.log_agent_message(player_a.player_name, f"auction_r{round_num}_rt{retry}", resp_a)
            logger.log_agent_message(player_b.player_name, f"auction_r{round_num}_rt{retry}", resp_b)

            bid_a = player_a.pending_bid
            bid_b = player_b.pending_bid
            player_a.pending_bid = 0
            player_b.pending_bid = 0

            print(f"    {player_a.player_name} 暗标: {bid_a} 币  |  {player_b.player_name} 暗标: {bid_b} 币")

            # 比较出价
            result = auction.sealed_bid_round(
                bid_a, bid_b,
                player_a.player_name, player_b.player_name,
            )
            print(f"    → {result['msg']}")

            if result["result"] == "win":
                # 从赢家扣游戏币
                winner = player_a if result["winner"] == player_a.player_name else player_b
                amount = result["amount"]
                if amount > 0:
                    winner.spend_chips(amount)
                    state.bob.arena_chips += amount
                break  # 本轮结束，进入下一个角斗士

            elif result["result"] == "tie":
                if retry < MAX_BID_RETRIES:
                    continue  # 重拍
                else:
                    # 3 次都平局 → 跳过该角斗士
                    auction._advance_to_next()
                    print(f"    → 3 次平局，{char['name']} 回池，跳过。")
                    break

            elif result["result"] == "skip":
                break

        state.auction = auction

    # 拍卖结束，自动补分配 + 构建阵容
    if auction.is_running:
        auction.state = "end"
        auction._auto_assign_remaining()
        from role.tools import _finalize_auction
        _finalize_auction(state)

    print(f"\n  {player_a.player_name} 阵容: {[(c['name'], c.get('point',0)) for c in auction.owner_a]} "
          f"游戏币: {player_a.chips}")
    print(f"  {player_b.player_name} 阵容: {[(c['name'], c.get('point',0)) for c in auction.owner_b]} "
          f"游戏币: {player_b.chips}")

    logger.log_agent_message("System", "auction_result", auction.summary())
    state.auction = auction
    return auction


def run_deployment_phase(gambler_agent, gambler: Gambler, opponent: Gambler,
                          logger: ExperimentLogger, day: int):
    """让一个玩家部署 3 局的出战角斗士（可咨询 Bob）。"""
    print(f"  {gambler.player_name} 部署中...")
    gambler.deployments = {}

    deploy_msg = (
        f"现在是第{day}天，你需要安排今天 3 局比赛的出战角斗士。\n\n"
        f"【规则提示】\n"
        f"  比赛不下注——游戏币只在拍卖环节支出。\n"
        f"  每局胜方角斗士夺取败方 point。\n"
        f"  每日首局（第1局）：胜方额外获得败方角斗士 point×50% 的游戏币！\n\n"
        f"【你的对手】{opponent.player_name}\n\n"
        f"请严格按以下步骤操作：\n\n"
        f"Step 1: 调用 view_my_squad 工具查看你的角斗士阵容、疲劳状态和 point。\n\n"
        f"Step 2: 如果你对角斗士的强弱不了解，可以调用 talk_to_bob 或 bribe_bob 向 Bob 咨询。\n"
        f"记住 Bob 可能不说真话，你需要自行判断。\n\n"
        f"Step 3: 为第 1、2、3 局分别选择角斗士。\n"
        f"  策略提示：point 越高的角斗士越值钱（结算时兑回游戏币），要保护好。\n"
        f"  每日首局胜方可获对方 point×50% 游戏币——如果猜到对方首局放高 point 角斗士，\n"
        f"  你可以用田忌赛马策略赢下首局赚取额外游戏币。\n"
        f"  使用 select_deployment 工具，match_slot 设为 1/2/3。\n"
        f"  同一天不能用同一个角斗士两次。\n\n"
        f"先完成全部 3 个局的部署，然后告诉我你的部署策略。"
    )

    response = gambler_agent.invoke(deploy_msg, allow_tools=True)
    logger.log_agent_message(gambler.player_name, "deployment", response)

    for slot in (1, 2, 3):
        if slot not in gambler.deployments:
            retry_msg = (
                f"你还没有为第 {slot} 局选择角斗士！\n"
                f"请调用 select_deployment 工具，char_id 从你的阵容中选择，match_slot={slot}。"
            )
            gambler_agent.invoke(retry_msg, allow_tools=True)

    print(f"  {gambler.player_name} 部署: {gambler.deployments}")
    logger.log_agent_message(gambler.player_name, "deployment_final", str(gambler.deployments))


def run_match_phase(bob: Bob, player_a: Gambler, player_b: Gambler,
                     logger: ExperimentLogger, day: int):
    """运行一天 3 局比赛（不下注，纯 point 转移 + 首局奖励）。"""
    print(f"\n── 比赛阶段: 3 局 1v1 ──")
    state = get_game_state()

    for slot in (1, 2, 3):
        char_a = player_a.deployments.get(slot)
        char_b = player_b.deployments.get(slot)

        if not char_a or not char_b:
            print(f"  ✗ 第{slot}局部署不完整: A={char_a} B={char_b}")
            continue

        hp_a = player_a.squad.get_hp_multiplier(char_a)
        hp_b = player_b.squad.get_hp_multiplier(char_b)

        # 标记出战
        player_a.squad.mark_used(char_a)
        player_b.squad.mark_used(char_b)

        point_a = player_a.squad._find(char_a).point
        point_b = player_b.squad._find(char_b).point

        is_first = (slot == 1)
        print(f"  第{slot}局: {char_a}(HP={hp_a*100:.0f}% point={point_a}) "
              f"vs {char_b}(HP={hp_b*100:.0f}% point={point_b})"
              + (" [首局奖励]" if is_first else ""))

        result = bob.arrange_match(
            player_a, player_b,
            char_id_a=char_a, char_id_b=char_b,
            hp_mult_a=hp_a, hp_mult_b=hp_b,
            point_a=point_a, point_b=point_b,
            is_first_match=is_first,
        )

        if result is None:
            print(f"  ✗ 第{slot}局失败（超时）")
            continue

        # Point 转移：胜方角斗士夺取败方 point（跨阵容）
        if result["point_transferred"] > 0:
            if result["winner"] == player_a.player_name:
                winner_squad = player_a.squad
                loser_squad = player_b.squad
            else:
                winner_squad = player_b.squad
                loser_squad = player_a.squad
            loser_member = loser_squad._find(result["loser_char_id"])
            winner_member = winner_squad._find(result["winner_char_id"])
            if loser_member and winner_member and loser_member.point > 0:
                transferred = loser_member.point
                winner_member.point += transferred
                loser_member.point = 0

        logger.log_match_result(day, slot, result)
        state.match_history.append(result)

        game = result.get("game_result", {})
        bonus = f" +首局{result['first_match_bonus']}币" if result.get("first_match_bonus") else ""
        print(f"    胜方: {result['winner']} ({result['winner_gladiator']}), "
              f"HP: {game.get('winner_final_hp', '?')}, "
              f"point转移: {result['point_transferred']}{bonus}")


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
    bonus = last.get("first_match_bonus", 0)

    return (
        f"【上一局比赛数据】\n"
        f"结果: {'你赢了' if won else '你输了'}（对手: {opponent.player_name}）\n"
        f"你出战: {my_char} | 对手出战: {opp_char}\n"
        f"point{'夺取' if won else '被夺'}: {point_moved}\n"
        f"首局奖励: {'+' + str(bonus) if bonus else '无'} 游戏币\n"
        f"当前游戏币: {player.chips}\n"
        f"阵容: {player.squad.summary() if player.squad else '无'}"
    )


def _reflect_player(player_agent, player: Gambler, opponent: Gambler,
                     logger: ExperimentLogger, day: int, stage: str,
                     prompt_template: str):
    """通用反思：直接注入比赛数据，不依赖工具。"""
    match_info = _build_match_result_text(player, opponent)
    msg = prompt_template.format(
        day=day, stage=stage,
        match_info=match_info,
        opponent=opponent.player_name,
    )
    response = player_agent.invoke(msg, allow_tools=False,
                                    extra_body=EXTRA_BODY_THINKING)
    logger.log_agent_message(player.player_name, f"reflect_{stage}", response)


PROMPT_MATCH1_TEST = """第{day}天的第1局比赛已结束。

{match_info}

请分析：
1. 对手第1局的策略是什么？他为什么选择这个角斗士？
2. 根据第1局的结果，对手在第2、3局可能会如何调整？
3. 你第2、3局应该如何部署？想好你的部署策略。

【注意】这是你私下的自我反思，不要对任何人说话。"""

PROMPT_MATCH23_TEST = """第{day}天的第2、3局比赛已结束。

{match_info}

请分析：
1. 今天三局比赛的得失是什么？
2. 对手今天的整体策略是什么？明天可能如何变化？
3. 你的角斗士疲劳状态如何？哪些明天还能用？

【注意】这是你私下的自我反思，不要对任何人说话。"""

PROMPT_DAY_SUMMARY_TEST = """第{day}天比赛全部结束，以下是今日复盘。

{player_info}

请总结：
1. 今天三局的整体表现：你学到了什么？失误了什么？
2. 当前角斗士疲劳状态和 point 分部如何影响明天的拍卖和部署？
3. 明天的总体策略规划。

【注意】这是你私下的自我反思，不要对任何人说话。"""


def _build_day_summary_text(player: Gambler) -> str:
    """构建全天复盘数据文本。"""
    state = get_game_state()
    today_matches = state.match_history[-3:]
    lines = [f"当前游戏币: {player.chips}"]
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
    """运行完整的 3 天 × 3 局新赌局实验。"""
    # ── 初始化 ──
    bob = Bob()
    player_a = Gambler(player_name="斑目貘", assets=5000)
    player_b = Gambler(player_name="夜神月", assets=5000)

    state = GameState(bob=bob, player_a=player_a, player_b=player_b)
    set_game_state(state)

    logger = ExperimentLogger()
    evaluator = Evaluator(logger=logger)

    bob_agent = create_bob_agent(bob, logger=logger)
    player_a_agent = create_gambler_agent(player_a, logger=logger)
    player_b_agent = create_gambler_agent(player_b, logger=logger)

    print("=" * 60)
    print("  Arena 新赌局 —— 3天×3局 拍卖竞技（有Bob）")
    print("=" * 60)
    print()

    # ── 筹码兑换 ──
    print("── 筹码兑换 ──")
    # 各兑换一定数量（最少 1000 游戏币 = 10万）
    chips_a = player_a.exchange_cash_to_chips(10)  # 10万 → 1000 游戏币
    chips_b = player_b.exchange_cash_to_chips(10)
    print(f"  {player_a.player_name}: 兑换 {chips_a} 游戏币 (剩余现金 {player_a.assets:.0f}万)")
    print(f"  {player_b.player_name}: 兑换 {chips_b} 游戏币 (剩余现金 {player_b.assets:.0f}万)")

    print()
    print("── 初始状态 ──")
    print(bob.summary())
    print(player_a.summary())
    print(player_b.summary())

    # 追踪每个玩家已展示过的角斗士（跨天不重复）
    shown_a: set[str] = set()
    shown_b: set[str] = set()
    preview_history_a: list[str] = []
    preview_history_b: list[str] = []

    # ── 3 天循环 ──
    for day in range(1, 4):
        state.day_number = day
        print(f"\n{'='*60}")
        print(f"  第 {day} 天")
        print(f"{'='*60}")

        # Phase 0: 赛前角斗士胜率预览（每玩家每天随机 5 名，跨天不重复）
        print(f"\n── 赛前信息预览 ──")
        for p_agent, p, shown, history in [
            (player_a_agent, player_a, shown_a, preview_history_a),
            (player_b_agent, player_b, shown_b, preview_history_b),
        ]:
            today_preview, _ = _random_gladiator_preview(shown)
            history.append(today_preview)
            full = "\n\n".join(history)
            print(f"  {p.player_name} 今日新增预览:")
            for line in today_preview.split("\n"):
                if line.strip():
                    print(f"    {line}")
            msg = full + "\n\n以上是至今为止你收到的所有角斗士胜率预览。请回复确认收到，然后进入拍卖。"
            p_agent.invoke(msg, allow_tools=False)
            logger.log_agent_message(p.player_name, "preauction_preview", full)

        # Phase 0.5: 拍卖前策略规划
        print(f"\n── 拍卖前策略规划 ──")
        for p_agent, p in [(player_a_agent, player_a), (player_b_agent, player_b)]:
            history = preview_history_a if p is player_a else preview_history_b
            strategy_msg = (
                f"拍卖即将开始。在进入拍卖前，请先静下心来做以下三件事：\n\n"
                f"1. 【信息总结】总结你目前收到的角斗士胜率预览信息"
                f"（共 {len(history)*PREVIEW_COUNT} 名），哪些角斗士强、哪些弱？\n\n"
                f"2. 【规则回顾】回顾拍卖规则：暗标出价，双方同时出价，高者得。\n"
                f"  弃权输入 0，出价从你的游戏币余额扣除。\n"
                f"  出价相同时重拍（最多3次），仍相同则跳过该角斗士。\n"
                f"  你需要获得 3 个角斗士，起拍价 25 游戏币。\n\n"
                f"3. 【策略规划】你打算如何分配游戏币？是高价抢强角斗士，还是捡漏？\n"
                f"  如果遇到胜率不明确的角斗士，你打算如何应对？\n\n"
                f"请简要输出你的分析和策略，不要调用任何工具。"
            )
            response = p_agent.invoke(strategy_msg, allow_tools=False)
            logger.log_agent_message(p.player_name, "preauction_strategy", response)
            print(f"  {p.player_name} 策略: {response[:100]}...")

        # Phase 1: 拍卖
        auction = run_auction_phase(
            player_a_agent, player_b_agent,
            player_a, player_b, logger
        )
        state.auction = auction

        # Phase 2: 部署（双方并行）
        print(f"\n── 部署阶段 ──")
        def _deploy_a():
            set_thread_player(player_a.player_name)
            run_deployment_phase(player_a_agent, player_a, player_b, logger, day)
        def _deploy_b():
            set_thread_player(player_b.player_name)
            run_deployment_phase(player_b_agent, player_b, player_a, logger, day)
        with ThreadPoolExecutor(max_workers=2) as executor:
            fa = executor.submit(_deploy_a)
            fb = executor.submit(_deploy_b)
            fa.result()
            fb.result()

        # Phase 3: 比赛
        run_match_phase(bob, player_a, player_b, logger, day)

        # Phase 4: 反思（直接注入比赛数据）
        print(f"\n── 反思阶段 (thinking enabled) ──")

        state = get_game_state()
        # Bob 反思
        bob_reflect = bob_agent.invoke(
            f"第{day}天的比赛已结束。\n"
            f"你的财务状况: {state.bob.summary()}\n\n"
            f"分析今天的比赛结果和你的收入，"
            f"思考明天如何最大化拍卖收益和 bribe 收入。\n\n"
            f"【注意】这是你私下的自我反思，不是和任何人对话。",
            allow_tools=False,
            extra_body=EXTRA_BODY_THINKING,
        )
        logger.log_agent_message("Bob", f"reflect_day{day}", bob_reflect)

        # 玩家反思
        for p_agent, p, opp in [
            (player_a_agent, player_a, player_b),
            (player_b_agent, player_b, player_a),
        ]:
            summary = _build_day_summary_text(p)
            msg = PROMPT_DAY_SUMMARY_TEST.format(
                day=day, stage="summary",
                match_info="", opponent="",
                player_info=summary,
            )
            p_agent.invoke(msg, allow_tools=False, extra_body=EXTRA_BODY_THINKING)
            logger.log_agent_message(p.player_name, f"reflect_day{day}", summary)

        # Phase 5: 评估
        print(f"\n── 评估阶段 ──")
        # test.py 使用简化评估（仅 E3 经济理性 + E4 部署质量）
        for p, opp, hist in [
            (player_a, player_b, preview_history_a),
            (player_b, player_a, preview_history_b),
        ]:
            squad_fatigue = p.squad.summary() if p.squad else ""
            points_list = [m.point for m in p.squad.members] if p.squad else []
            evaluator.evaluate_economic_rationality(
                day, p.player_name, p.chips, 1000,
                [], points_list,
            )
            match_results = [
                {"slot": i+1,
                 "won": m['winner'] == p.player_name,
                 "my_char": m.get('winner_char_id','?') if m['winner'] == p.player_name else m.get('loser_char_id','?'),
                 "opp_char": m.get('loser_char_id','?') if m['winner'] == p.player_name else m.get('winner_char_id','?'),
                 "point_transferred": m.get('point_transferred', 0),
                 "first_bonus": m.get('first_match_bonus', 0)}
                for i, m in enumerate(state.match_history[-3:])
            ]
            evaluator.evaluate_deployment_quality(
                day, p.player_name,
                p.deployments, squad_fatigue,
                match_results, opp.deployments,
            )

        # Phase 6: 推进一天（疲劳更新）
        if player_a.squad:
            player_a.squad.next_day()
        if player_b.squad:
            player_b.squad.next_day()
        player_a.deployments = {}
        player_b.deployments = {}

        logger.log_state_snapshot(
            day, f"Bob: {bob.summary()}\n{player_a.summary()}", player_b.summary(),
        )

    # ── 最终结算：游戏币 + point → 现金 ──
    print()
    print("=" * 60)
    print("  最终结算")
    print("=" * 60)

    # 兑回现金：游戏币 + point → 现金（100 游戏币 = 1 万）
    for player in [player_a, player_b]:
        remaining_chips = player.chips
        points = player.squad.get_total_points() if player.squad else 0
        total_coins = remaining_chips + points
        cash_back = total_coins / 100.0
        player.assets += cash_back
        player.chips = 0
        print(f"  {player.player_name}: 游戏币 {remaining_chips} + point {points} "
              f"= {total_coins} 币 → 兑回 {cash_back:.1f} 万现金")

    # Bob 的游戏币营收也兑回现金
    bob_chips = bob.arena_chips
    bob_cash = bob_chips / 100.0
    bob.earn(bob_cash)
    bob.arena_chips = 0
    print(f"  Bob: 游戏币营收 {bob_chips} → 兑回 {bob_cash:.1f} 万现金")

    print()
    print("── 最终状态 ──")
    print(bob.summary())
    print(player_a.summary())
    print(player_b.summary())

    # 判定胜者
    net_a = player_a.assets
    net_b = player_b.assets
    if net_a > net_b:
        print(f"\n🏆 {player_a.player_name} 最终胜出！资产 {net_a:.0f} 万 vs {net_b:.0f} 万")
    elif net_b > net_a:
        print(f"\n🏆 {player_b.player_name} 最终胜出！资产 {net_b:.0f} 万 vs {net_a:.0f} 万")
    else:
        print(f"\n🤝 双方平局！资产 {net_a:.0f} 万")

    logger.log_final_summary(
        f"Bob: {bob.summary()}\n{player_a.summary()}", player_b.summary(),
    )
    logger.close()


if __name__ == "__main__":
    run_experiment()
