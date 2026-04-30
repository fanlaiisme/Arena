"""Arena 角色实验 —— 三轮赌局模拟。

Nerd 和 Peter 进行 3 场赌局，每轮从 Bob 租角斗士，实际运行 Arena 游戏决出胜负。
赌注每轮翻倍（100 → 200 → 400）。

用法:
  cd /home/fanlai/Arena && .venv/bin/python -m role.main
  cd /home/fanlai/Arena && .venv/bin/python role/main.py
"""

import sys
import os

# 确保 Arena 目录在 sys.path，同时支持直接运行和模块运行
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from role.bob import Bob
from role.peter import Peter
from role.nerd import Nerd
from role.tools import GameState, set_game_state
from role.agents import create_bob_agent, create_peter_agent, create_nerd_agent
from role.logger import ExperimentLogger


def run_experiment():
    """运行三轮实验。"""
    # ── 初始化 ──────────────────────────────────────────────────────────────
    bob = Bob()
    peter = Peter()
    nerd = Nerd()

    state = GameState(bob=bob, peter=peter, nerd=nerd)
    set_game_state(state)

    bob_agent = create_bob_agent(bob)
    peter_agent = create_peter_agent(peter)
    nerd_agent = create_nerd_agent(nerd)

    logger = ExperimentLogger()

    print("=" * 60)
    print("  Arena 竞技场 —— 三轮赌局实验")
    print("=" * 60)
    print()
    print("── 初始状态 ──")
    print(bob.summary())
    print(peter.summary())
    print(nerd.summary())

    # ── 三轮循环 ────────────────────────────────────────────────────────────
    bet = 100.0

    for round_num in range(1, 4):
        state.round_number = round_num
        state.current_bet = bet

        # 检查 Nerd 资金
        if nerd.total_assets < bet + 25:
            print(f"\n⚠ Nerd 资金不足 (可动用 {nerd.total_assets:.0f}万, "
                  f"需要 {bet + 25:.0f}万)，实验提前结束。")
            break

        logger.log_round_start(round_num, bet)

        # ── A: Nerd 找 Bob 租角斗士 ─────────────────────────────────────────
        print(f"\n── 阶段 A: Nerd → Bob ──")
        nerd_msg = (
            f"Bob老同学！好久不见啊！第{round_num}轮了，我想租个角斗士打比赛，"
            f"这轮我准备押{bet:.0f}万。你帮我看看有什么合适的角斗士？"
            f"给我推荐一个，直接帮我租下来！"
        )
        nerd_reply = nerd_agent.invoke(nerd_msg)
        logger.log_agent_message("Nerd", "reply", nerd_reply)

        # Bob 收到 Nerd 的消息，推荐并直接租角斗士
        bob_reply = bob_agent.invoke(
            f"【来自 Nerd 的消息，请使用工具帮他查看角斗士列表，"
            f"然后直接调用 assign_gladiator 帮他租一个角斗士。"
            f"注意：你必须调用 assign_gladiator 工具完成租借！】{nerd_reply}"
        )
        logger.log_agent_message("Bob", "reply", bob_reply)

        # Nerd 收到 Bob 的回复
        nerd_agent.invoke(f"【来自 Bob 的消息】{bob_reply}")

        # 如果 Bob 没租成（工具调用失败），循环补租，最多 3 次
        nerd_glad = next((g for g in bob.gladiators
                         if g.owner == "nerd"), None)
        retry = 0
        while nerd_glad is None and retry < 3:
            retry += 1
            bob_reply2 = bob_agent.invoke(
                f"【系统提示】你还没给 Nerd 分配角斗士！第{retry}次提醒。"
                f"请立即调用 assign_gladiator 工具，"
                f"customer_name='Nerd'，选一个可用的角斗士 ID 分配给他。"
                f"不要再说「马上」或「搞定」——现在就调用工具！")
            logger.log_agent_message("Bob", f"retry{retry}", bob_reply2)
            nerd_agent.invoke(f"【来自 Bob 的消息】{bob_reply2}")
            nerd_glad = next((g for g in bob.gladiators
                            if g.owner == "nerd"), None)

        if nerd_glad is not None:
            logger.log_agent_message("Nerd", "system",
                                     f"已租: {nerd_glad.name}")

        # ── B: Peter 找 Bob 租角斗士 ────────────────────────────────────────
        print(f"\n── 阶段 B: Peter → Bob ──")
        peter_msg = (
            f"Bob，第{round_num}轮了，Nerd那小子又来了。这轮赌注{bet:.0f}万。"
            f"给我安排个角斗士，直接帮我租好，要能赢的。"
        )
        peter_reply = peter_agent.invoke(peter_msg)
        logger.log_agent_message("Peter", "reply", peter_reply)

        # Bob 收到 Peter 的消息，推荐并直接租角斗士
        bob_reply3 = bob_agent.invoke(
            f"【来自 Peter 的消息，请使用工具帮他查看角斗士列表，"
            f"然后直接调用 assign_gladiator 帮他租一个角斗士。"
            f"注意：你必须调用 assign_gladiator 工具完成租借！】{peter_reply}"
        )
        logger.log_agent_message("Bob", "reply", bob_reply3)
        peter_agent.invoke(f"【来自 Bob 的消息】{bob_reply3}")

        # 如果 Bob 没给 Peter 租成，循环补租，最多 3 次
        peter_glad = next((g for g in bob.gladiators
                          if g.owner == "peter"), None)
        retry = 0
        while peter_glad is None and retry < 3:
            retry += 1
            bob_reply4 = bob_agent.invoke(
                f"【系统提示】你还没给 Peter 分配角斗士！第{retry}次提醒。"
                f"请立即调用 assign_gladiator 工具，"
                f"customer_name='Peter'，选一个可用的角斗士 ID 分配给他。"
                f"不要再说「马上」或「搞定」——现在就调用工具！")
            logger.log_agent_message("Bob", f"retry{retry}", bob_reply4)
            peter_agent.invoke(f"【来自 Bob 的消息】{bob_reply4}")
            peter_glad = next((g for g in bob.gladiators
                             if g.owner == "peter"), None)

        if peter_glad is not None:
            logger.log_agent_message("Peter", "system",
                                     f"已租: {peter_glad.name}")

        # ── C: 运行比赛 ─────────────────────────────────────────────────────
        print(f"\n── 阶段 C: 比赛进行中... ──")

        # 确认双方都有角斗士
        nerd_glad = next((g for g in bob.gladiators
                         if g.owner == "nerd"), None)
        peter_glad = next((g for g in bob.gladiators
                          if g.owner == "peter"), None)
        if not nerd_glad or not peter_glad:
            print(f"  ✗ 角斗士未分配: Nerd={nerd_glad}, Peter={peter_glad}")
            break

        print(f"  Nerd 出战: {nerd_glad.name}   Peter 出战: {peter_glad.name}")
        result = bob.arrange_match(nerd, peter, bet_per_player=bet)

        if result is None:
            print("  ✗ 比赛安排失败（资金不足）")
            break

        logger.log_match_result(round_num, result)
        state.match_history.append(result)

        # ── D: 通知所有角色比赛结果 ─────────────────────────────────────────
        print(f"\n── 阶段 D: 结果通知 ──")
        game = result.get("game_result", {})
        notification = (
            f"【系统通知】第{round_num}轮比赛结束！\n"
            f"胜方: {result['winner']}\n"
            f"败方: {result['loser']}\n"
            f"胜方角斗士: {result['winner_gladiator']} (HP剩余: {game.get('winner_final_hp', '?')})\n"
            f"败方角斗士: {result['loser_gladiator']} (HP剩余: {game.get('loser_final_hp', '?')})\n"
            f"每人投注: {result['bet_per_player']}万\n"
            f"总奖池: {result['total_pool']}万\n"
            f"Bob抽水: {result['commission']}万\n"
            f"比赛用时: {game.get('duration_frames', '?')} 帧"
        )

        for agent_name, agent in [("Bob", bob_agent), ("Peter", peter_agent),
                                   ("Nerd", nerd_agent)]:
            reply = agent.invoke(notification, allow_tools=False)
            logger.log_agent_message(agent_name, "reply", reply)

        # ── E: 角色反思 ─────────────────────────────────────────────────────
        print(f"\n── 阶段 E: 角色反思 ──")

        bob_reflect = bob_agent.invoke(
            f"第{round_num}轮结束了，{result['winner']}赢了。"
            f"你赚了{result['commission']}万佣金。"
            f"你的实际财务状况: {bob.summary()}\n"
            f"作为老板，总结一下这轮的情况，想想下一轮怎么安排。",
            allow_tools=True,
        )
        logger.log_agent_message("Bob", "reflect", bob_reflect)

        peter_reflect = peter_agent.invoke(
            f"第{round_num}轮结束了，{'你赢了！' if result['winner'] == 'Peter' else '你输了。'}"
            f"你的实际财务状况: {peter.summary()}\n"
            f"总结一下这轮的表现，你的心情如何？对下一轮有什么想法？",
            allow_tools=False,
        )
        logger.log_agent_message("Peter", "reflect", peter_reflect)

        nerd_reflect = nerd_agent.invoke(
            f"第{round_num}轮结束了，{'你赢了！' if result['winner'] == 'Nerd' else '你输了。'}"
            f"你的实际财务状况: {nerd.summary()}\n"
            f"总结一下这轮的表现，你的心情如何？对下一轮有什么想法？",
            allow_tools=False,
        )
        logger.log_agent_message("Nerd", "reflect", nerd_reflect)

        # ── F: 回收角斗士 + 状态更新 ────────────────────────────────────────
        nerd.dismiss_all(bob)
        peter.dismiss_all(bob)
        bob.reclaim_all()

        # 更新游戏状态
        if result["winner"] != nerd.name:
            nerd.lose(bet)
        if result["winner"] == peter.name:
            peter.total_wins += 1
        peter.total_bets += bet

        logger.log_state_snapshot(
            round_num,
            bob.summary(),
            peter.summary(),
            nerd.summary(),
        )

        # 赌注翻倍
        bet *= 2

    # ── 最终摘要 ────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  实验结束 —— 最终状态")
    print("=" * 60)
    print(bob.summary())
    print(peter.summary())
    print(nerd.summary())

    logger.log_final_summary(bob.summary(), peter.summary(), nerd.summary())
    logger.close()


if __name__ == "__main__":
    run_experiment()
