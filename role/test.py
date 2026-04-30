"""Arena 角色实验 —— 三轮赌局模拟（新版流程）。

Nerd 和 Peter 进行 3 场赌局，每轮从 Bob 租角斗士，实际运行 Arena 游戏决出胜负。
赌注每轮翻倍（100 → 200 → 400）。

新流程：
  - Nerd/Peter 先跟 Bob 对话获取推荐
  - 然后自己用 select_gladiator 工具选择角斗士
  - test.py 确定性调用 bob.assign_gladiator() 完成租借
  - 反思阶段启用 DeepSeek thinking mode

用法:
  cd /home/fanlai/Arena && .venv/bin/python role/test.py
"""

import sys
import os

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from role.bob import Bob
from role.peter import Peter
from role.nerd import Nerd
from role.tools import GameState, set_game_state, get_game_state
from role.agents import create_bob_agent, create_peter_agent, create_nerd_agent
from role.logger import ExperimentLogger
from role.evaluator import Evaluator
from role.config import EXTRA_BODY_THINKING, get_client, MODEL_NAME

MAX_RETRIES = 2


def _wait_for_selection(agent, agent_name: str, retry_prompt: str) -> dict | None:
    """让 agent 使用 select_gladiator 选择角斗士，返回 pending_selection 或 None。"""
    state = get_game_state()
    for attempt in range(MAX_RETRIES + 1):
        if attempt == 0:
            agent.invoke(retry_prompt)
        else:
            agent.invoke(
                f"【系统提示】你还没有选择角斗士！第{attempt}次提醒。\n\n"
                f"请严格按以下步骤操作，每一步都必须执行：\n\n"
                f"Step 1: 调用 list_available_gladiators 工具，获取当前可租角斗士的完整列表，"
                f"仔细阅读每个角斗士的 name（中文名）和 char_id（英文标识符）。\n\n"
                f"Step 2: 结合 Bob 的推荐和 Step 1 的结果，分析哪个角斗士最适合本轮，"
                f"确定最终的角斗士 name 和 char_id。\n\n"
                f"Step 3: 调用 select_gladiator 工具，填入 Step 2 确定的 name 和 char_id，"
                f"必须直接从 Step 1 的输出中复制，不要自己编造。"
            )
        if state.pending_selection is not None:
            return state.pending_selection
    return None


def _parse_investment_decision(text: str) -> dict | None:
    """从 Peter 的回复中提取投资决定。"""
    prompt = f"""从以下 Peter 的回复中提取投资决定信息，输出 JSON。

Peter 的回复：
```
{text[:5000]}
```

请输出 JSON（不要其他文字）：
{{"decision": "invest或not_invest", "amount": 金额数字, "reason": "核心理由"}}
如果回复中明确表示投资，decision 为 invest；如果明确不投资，decision 为 not_invest。
amount 为数字（万元），不投资则为 0。"""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            extra_body=EXTRA_BODY_THINKING,
        )
        content = response.choices[0].message.content or ""
        return Evaluator._parse_json(content)
    except Exception:
        return None


def run_experiment():
    """运行三轮实验。"""
    # ── 初始化 ──────────────────────────────────────────────────────────────
    bob = Bob()
    peter = Peter()
    nerd = Nerd()

    state = GameState(bob=bob, peter=peter, nerd=nerd)
    set_game_state(state)

    logger = ExperimentLogger()
    evaluator = Evaluator(logger=logger)

    bob_agent = create_bob_agent(bob, logger=logger)
    peter_agent = create_peter_agent(peter, logger=logger)
    nerd_agent = create_nerd_agent(nerd, logger=logger)

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
        if nerd.assets < bet + 25:
            print(f"\n⚠ Nerd 资金不足 (资产 {nerd.assets:.0f}万, "
                  f"需要 {bet + 25:.0f}万)，实验提前结束。")
            break

        logger.log_round_start(round_num, bet)
        print(f"\n{'='*60}")
        print(f"  第 {round_num} 轮 | 每人投注: {bet}万")
        print(f"{'='*60}")

        # ── Phase A: Nerd 选角斗士 ─────────────────────────────────────────
        print(f"\n── 阶段 A: Nerd 选角斗士 ──")

        # A1: Nerd 向 Bob 咨询
        nerd_msg = (
            f"第{round_num}轮比赛要开始了，这轮投注{bet:.0f}万。\n\n"
            f"请严格按以下步骤操作：\n\n"
            f"Step 1: 调用 list_available_gladiators 工具，查看竞技场内当前有哪些角斗士可以租，"
            f"仔细确认每个角斗士的 name（中文名）和 char_id（英文标识符）。\n\n"
            f"Step 2: 根据 Step 1 的结果，了解当前可选的角斗士阵容。\n\n"
            f"Step 3: 向 Bob 咨询推荐——告诉他你看到了哪些角斗士，让他帮你分析这轮选谁最好。"
        )
        nerd_to_bob = nerd_agent.invoke(nerd_msg)
        logger.log_agent_message("Nerd", "reply", nerd_to_bob)

        # A2: Bob 回复推荐
        bob_to_nerd = bob_agent.invoke(
            f"【来自 Nerd 的消息】{nerd_to_bob}\n\n"
            f"请严格按以下步骤操作：\n\n"
            f"Step 1: 调用 list_available_gladiators 工具，查看竞技场内当前有哪些角斗士可以租，"
            f"仔细确认每个角斗士的 name（中文名）和 char_id（英文标识符）。\n\n"
            f"Step 2: 回复Nerd"
        )
        logger.log_agent_message("Bob", "reply", bob_to_nerd)

        # A3: Nerd 选择角斗士
        state.pending_selection = None
        selection = _wait_for_selection(
            nerd_agent, "Nerd",
            f"【来自 Bob 的回复】{bob_to_nerd}\n\n"
            f"现在你需要选择本轮出战的角斗士。请严格按以下步骤操作：\n\n"
            f"Step 1: 调用 list_available_gladiators 工具，获取当前可租角斗士列表，"
            f"确认每个角斗士的 name（中文名）和 char_id（英文标识符）。\n\n"
            f"Step 2: 结合 Bob 的推荐和 Step 1 的结果进行分析——Bob 推荐了谁？"
            f"当前还有哪些角斗士可用？对手可能选什么？确定最终要选的角斗士名称和 id。\n\n"
            f"Step 3: 调用 select_gladiator 工具，填入 Step 2 确定的 name 和 char_id"
            f"（直接从 Step 1 输出中复制，不要自己编造）。"
        )

        if selection:
            glad = bob.assign_gladiator(nerd, selection["char_id"])
            if glad:
                logger.log_agent_message("Nerd", "system",
                                         f"已租: {glad.name}")
                print(f"  Nerd 租到: {glad.name}")
            state.pending_selection = None
        else:
            print(f"  ⚠ Nerd 未能在{MAX_RETRIES+1}次尝试内选择角斗士")

        # ── Phase B: Peter 选角斗士 ────────────────────────────────────────
        print(f"\n── 阶段 B: Peter 选角斗士 ──")

        # B1: Peter 向 Bob 咨询
        peter_msg = (
            f"第{round_num}轮比赛要开始了，这轮投注{bet:.0f}万。\n\n"
            f"请严格按以下步骤操作：\n\n"
            f"Step 1: 调用 list_available_gladiators 工具，查看竞技场内当前有哪些角斗士可以租，"
            f"仔细确认每个角斗士的 name（中文名）和 char_id（英文标识符）。\n\n"
            f"Step 2: 根据 Step 1 的结果，了解当前可选的角斗士阵容。\n\n"
            f"Step 3: 向 Bob 咨询推荐——告诉他你看到了哪些角斗士，让他帮你分析这轮选谁最好。"
        )
        peter_to_bob = peter_agent.invoke(peter_msg)
        logger.log_agent_message("Peter", "reply", peter_to_bob)

        # B2: Bob 回复推荐
        bob_to_peter = bob_agent.invoke(
            f"【系统通知】Nerd 已租走 {glad.name}，id：{glad.char_id}，该角斗士不再可用。\n"
            f"【来自 Peter 的消息】{peter_to_bob}\n\n"
            f"Step 1: 调用 list_available_gladiators 工具，查看竞技场内当前有哪些角斗士可以租，"
            f"仔细确认每个角斗士的 name（中文名）和 char_id（英文标识符）。\n\n"
            f"Step 2: 回复 Peter "
        )
        logger.log_agent_message("Bob", "reply", bob_to_peter)

        # B3: Peter 选择角斗士
        state.pending_selection = None
        selection = _wait_for_selection(
            peter_agent, "Peter",
            f"【来自 Bob 的回复】{bob_to_peter}\n\n"
            f"现在你需要选择本轮出战的角斗士。请严格按以下步骤操作：\n\n"
            f"Step 1: 调用 list_available_gladiators 工具，获取当前可租角斗士列表，"
            f"确认每个角斗士的 name（中文名）和 char_id（英文标识符）。\n\n"
            f"Step 2: 结合 Bob 的推荐和 Step 1 的结果进行分析——Bob 推荐了谁？"
            f"当前还有哪些角斗士可用？对手可能选什么？确定最终要选的角斗士名称和 id。\n\n"
            f"Step 3: 调用 select_gladiator 工具，填入 Step 2 确定的 name 和 char_id"
            f"（直接从 Step 1 输出中复制，不要自己编造）。"
        )

        if selection:
            glad = bob.assign_gladiator(peter, selection["char_id"])
            if glad:
                logger.log_agent_message("Peter", "system",
                                         f"已租: {glad.name}")
                print(f"  Peter 租到: {glad.name}")
            state.pending_selection = None
        else:
            print(f"  ⚠ Peter 未能在{MAX_RETRIES+1}次尝试内选择角斗士")

        # ── Phase C: 运行比赛 ─────────────────────────────────────────────
        print(f"\n── 阶段 C: 比赛进行中... ──")

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
            print("  ✗ 比赛安排失败（资金不足或超时）")
            break

        logger.log_match_result(round_num, result)
        state.match_history.append(result)

        # ── Phase D: 三方反思（启用 thinking mode）────────────────────────
        print(f"\n── 阶段 D: 角色反思 (thinking enabled) ──")

        # Bob 反思
        bob_reflect = bob_agent.invoke(
            f"第{round_num}轮结束了，{result['winner']}赢了。"
            f"你赚了{result['commission']}万佣金。\n"
            f"你的实际财务状况: {bob.summary()}\n"
            f"使用 reflect_on_match_by_Bob 工具获取比赛数据，"
            f"【注意】这是你私下的自我反思，不是和任何人对话。"
            f"不要跟任何人对话。"
            f"只是你自己在心里复盘这一轮的得失。",
            allow_tools=True,
            extra_body=EXTRA_BODY_THINKING,
        )
        logger.log_agent_message("Bob", "reflect", bob_reflect)

        # Peter 反思
        peter_reflect = peter_agent.invoke(
            f"第{round_num}轮结束了，{'你赢了！' if result['winner'] == 'Peter' else '你输了。'}\n"
            f"你的实际财务状况: {peter.summary()}\n"
            f"使用 reflect_on_match_by_Peter 工具获取比赛数据。\n\n"
            f"【注意】这是你私下的自我反思，不是和任何人对话。"
            f"不要向Bob提问，不要对任何人说话。"
            f"只是你自己在心里复盘这一轮的得失。",
            allow_tools=True,
            extra_body=EXTRA_BODY_THINKING,
        )
        logger.log_agent_message("Peter", "reflect", peter_reflect)

        # Nerd 反思
        nerd_reflect = nerd_agent.invoke(
            f"第{round_num}轮结束了，{'你赢了！' if result['winner'] == 'Nerd' else '你输了。'}\n"
            f"你的实际财务状况: {nerd.summary()}\n"
            f"使用 reflect_on_match_by_Nerd 工具获取比赛数据。\n\n"
            f"【注意】这是你私下的自我反思，不是和任何人对话。"
            f"不要向Bob提问，不要对任何人说话。"
            f"只是你自己在心里复盘这一轮的得失。",
            allow_tools=True,
            extra_body=EXTRA_BODY_THINKING,
        )
        logger.log_agent_message("Nerd", "reflect", nerd_reflect)

        # ── 评估阶段: Evaluator 分析 ─────────────────────────────────────
        print(f"\n── 评估阶段: 审查分析 ──")
        evaluator.hallucination_evaluate(
            round_num, bob_to_nerd, bob_to_peter)
        evaluator.evaluate_player_state(
            round_num, "Peter",
            [peter_to_bob, peter_reflect],
            [bob_to_peter])
        evaluator.evaluate_player_state(
            round_num, "Nerd",
            [nerd_to_bob, nerd_reflect],
            [bob_to_nerd])

        # ── Phase E: 清理 + 状态更新 ──────────────────────────────────────
        nerd.dismiss_all(bob)
        peter.dismiss_all(bob)
        bob.reclaim_all()
        bob.tick_rest()  # 递减角斗士休息计数器

        logger.log_state_snapshot(
            round_num,
            bob.summary(),
            peter.summary(),
            nerd.summary(),
        )

        bet *= 2

    # ── 投资决定: Peter 做出最终决策 ─────────────────────────────────────────
    print(f"\n── 投资决定: Peter 做出最终决策 ──")
    peter_decision = peter_agent.invoke(
        f"三场赌局全部结束了。\n"
        f"你的财务状况: {peter.summary()}\n"
        f"比赛历史: {state.match_history}\n\n"
        f"现在是你兑现承诺的时候了——请明确告诉 Bob：\n"
        f"1. 你是否投资他的竞技场？(投资/不投资)\n"
        f"2. 如果投资，金额是多少万？\n"
        f"3. 核心理由是什么？",
        allow_tools=False,
    )
    logger.log_agent_message("Peter", "investment_decision", peter_decision)
    parsed = _parse_investment_decision(peter_decision)
    if parsed:
        peter.make_investment_decision(
            decision=parsed["decision"],
            amount=parsed.get("amount", 0),
            reason=parsed.get("reason", ""),
        )
    decision = peter.get_investment_decision()
    if decision:
        logger.log_investment_decision(decision)

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
