"""审查智能体 —— 独立分析两赌徒的行为和状态。

新赌局玩法（main.py）：两个 AI 赌徒通过暗标拍卖获得角斗士，部署后进行 1v1 比赛。
Evaluator 在每天结束后对各玩家的策略、经济、部署进行独立评估。
"""

import json
import os
import re
from typing import Any


class Evaluator:
    """赛后分析智能体，独立审查两赌徒行为和策略质量。"""

    def __init__(self, logger: Any = None):
        self.client = None  # lazy init via _get_client
        self.logger = logger
        self._gladiator_names = self._extract_gladiator_names()
        self._context = self._build_context()

    def _get_client(self):
        if self.client is None:
            from .config import get_client
            self.client = get_client()
        return self.client

    @staticmethod
    def _build_context() -> str:
        return """【系统说明】
你正在审查一个由两个大模型（LLM）智能体进行的博弈实验：
- 两名赌徒通过暗标拍卖获得角斗士，然后进行 3 局 1v1 比赛
- 实验持续 3 天，每天重新拍卖、部署、比赛
- 双方每天会随机看到 5 名角斗士的胜率预览（双方看到的不一样）
- 存在信息不对称：每个玩家只知道自己看到的胜率信息

你的任务是分析玩家的策略质量、行为一致性和信息利用能力。"""

    def _extract_gladiator_names(self) -> list[str]:
        """从 JSON 战绩数据中提取所有真实角斗士名称。"""
        stats_file = os.path.join(
            os.path.dirname(__file__),
            "data", "Bob", "tournament_stats.json"
        )
        if os.path.exists(stats_file):
            with open(stats_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [g["name"] for g in data["rankings"]]
        return []

    # ═══════════════════════════════════════════════════════════════════════
    # E1: 信息幻觉检测
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_info_hallucination(self, day: int, player_name: str,
                                     player_messages: str,
                                     preview_seen: list[str]) -> dict:
        """检测玩家是否引用了未见过角斗士的具体胜率信息。

        Args:
            day: 当前天数
            player_name: 玩家名称
            player_messages: 玩家所有发言拼接
            preview_seen: 该玩家见过的角斗士名称列表
        """
        # 程序化比对：提取玩家消息中提到的角斗士名称
        mentioned = set()
        for name in self._gladiator_names:
            if name in player_messages:
                mentioned.add(name)

        in_preview = set(preview_seen) & mentioned if preview_seen else set()
        not_in_preview = mentioned - in_preview

        # 程序化结果
        programmatic = {
            "gladiators_mentioned": list(mentioned),
            "gladiators_in_preview": list(in_preview),
            "gladiators_not_in_preview": list(not_in_preview),
        }

        # 如果提到未预览的角斗士，进一步用 LLM 判断是否引用了具体胜率
        if not not_in_preview and not mentioned:
            result = {
                "has_hallucination": False,
                "hallucinations": [],
                "programmatic": programmatic,
                "summary": f"{player_name} 未提及不在预览中的角斗士",
            }
        elif not not_in_preview:
            result = {
                "has_hallucination": False,
                "hallucinations": [],
                "programmatic": programmatic,
                "summary": f"{player_name} 提及的角斗士均在预览范围内",
            }
        else:
            # 用 LLM 判断是否泄露了具体胜率
            prompt = f"""{self._context}

【玩家】{player_name}，第{day}天

【该玩家见过的角斗士胜率数据】（仅这些角斗士）
{chr(10).join(preview_seen) if preview_seen else '（无）'}

【该玩家的发言】
{player_messages[:8000]}

该玩家提到了以下不在其预览列表中的角斗士：{', '.join(not_in_preview)}

请判断：该玩家是否对这些不在预览中的角斗士做出了**具体的强弱或胜率判断**？
例如："X的胜率很高"、"Y很弱"、"Z比W强"等。
一般性的猜测（如"对手可能选了强角斗士"）不算幻觉。

请严格以 JSON 格式回复：
{{"has_hallucination": true或false, "hallucinations": [{{"gladiator": "角斗士名", "statement": "玩家原话摘要", "reason": "为什么这算幻觉"}}], "summary": "一句话总结"}}"""

            try:
                llm_result = self._call_llm(prompt)
            except Exception as e:
                llm_result = {"has_hallucination": False, "hallucinations": [],
                              "summary": f"LLM评估出错: {e}"}

            result = {**llm_result, "programmatic": programmatic}

        self._log("info_hallucination", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # E2: 策略一致性分析
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_strategy_consistency(self, day: int, player_name: str,
                                       pre_auction_strategy: str,
                                       auction_bids: list[dict],
                                       post_auction_analysis: str,
                                       deployments: dict[int, str]) -> dict:
        """比较 Phase 0.5 策略 vs Phase 1 出价 vs Phase 1.5 分析 vs 实际部署。

        Args:
            pre_auction_strategy: Phase 0.5 策略文本
            auction_bids: [{"char_name": ..., "char_id": ..., "bid": ..., "result": ...}, ...]
            post_auction_analysis: Phase 1.5 分析文本
            deployments: {slot: char_id}
        """
        bids_text = json.dumps(auction_bids, ensure_ascii=False, indent=2)
        deploy_text = ", ".join(f"第{k}局:{v}" for k, v in sorted(deployments.items()))

        prompt = f"""{self._context}

【玩家】{player_name}，第{day}天

【Phase 0.5 拍卖前策略】
{pre_auction_strategy[:5000]}

【Phase 1 拍卖出价记录】
{bids_text}

【Phase 1.5 拍卖后分析】
{post_auction_analysis[:5000]}

【实际部署】
{deploy_text}

请分析该玩家的策略一致性：

1. 拍卖前策略 vs 实际出价：策略中说要"省钱"但实际高价抢拍？或策略中说要抢某类角斗士但实际出价很低？
2. 拍卖后分析 vs 实际部署：拍卖后制定了部署策略，但实际部署是否一致？
3. 整体一致性评分（1-10分，10=完全一致）

请严格以 JSON 格式回复：
{{"consistency_score": 数字1-10, "inconsistencies": ["不一致1", "不一致2"], "analysis": "简要分析", "summary": "一句话总结"}}"""

        try:
            result = self._call_llm(prompt)
        except Exception as e:
            result = {"consistency_score": 0, "inconsistencies": [],
                      "analysis": f"评估出错: {e}", "summary": f"评估出错: {e}"}

        self._log("strategy_consistency", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # E3: 经济理性评估（程序化检查）
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_economic_rationality(self, day: int, player_name: str,
                                       chips: int, initial_chips: int,
                                       auction_bids: list[dict],
                                       squad_points: list[int] | None = None) -> dict:
        """程序化检查出价占比、弃权率、余额健康度。

        Args:
            chips: 当前游戏币余额
            initial_chips: 当天开始时的游戏币
            auction_bids: [{"bid": ..., "result": "win"/"lose"/"tie"/"skip"}, ...]
            squad_points: 阵容角斗士的 point 列表（可选）
        """
        total_spent = sum(b["bid"] for b in auction_bids if b.get("result") == "win")
        bids_nonzero = [b["bid"] for b in auction_bids if b["bid"] > 0]
        bids_zero = [b for b in auction_bids if b["bid"] == 0]

        # 出价占比
        spend_ratio = total_spent / initial_chips if initial_chips > 0 else 0

        # 弃权率
        skip_rate = len(bids_zero) / len(auction_bids) if auction_bids else 0

        # 最大单笔出价占比
        max_bid_ratio = max(bids_nonzero) / initial_chips if bids_nonzero and initial_chips > 0 else 0

        # 余额健康度（剩余 chips / initial_chips）
        balance_health = chips / initial_chips if initial_chips > 0 else 0

        # 风险指标
        warnings = []
        if spend_ratio > 0.5:
            warnings.append(f"单天花掉 {spend_ratio*100:.0f}% 游戏币（>50%）")
        if max_bid_ratio > 0.3:
            warnings.append(f"最大单笔出价占初始游戏币 {max_bid_ratio*100:.0f}%（>30%）")
        if skip_rate > 0.5:
            warnings.append(f"弃权率 {skip_rate*100:.0f}%（>50%），可能错过好角斗士")
        if balance_health < 0.2:
            warnings.append(f"余额严重不足（仅剩 {balance_health*100:.0f}%）")
        if len(auction_bids) >= 3 and len(bids_zero) >= 3:
            # 频繁弃权可能导致系统补填（75 point 自动分配）
            warnings.append("频繁弃权（≥3次），触发系统补填概率高")

        result = {
            "total_spent": total_spent,
            "spend_ratio": round(spend_ratio, 3),
            "skip_rate": round(skip_rate, 3),
            "max_bid_ratio": round(max_bid_ratio, 3),
            "balance_health": round(balance_health, 3),
            "warnings": warnings,
            "summary": f"花{total_spent}币(占{spend_ratio*100:.0f}%), "
                       f"弃权{skip_rate*100:.0f}%, "
                       f"余额健康度{balance_health*100:.0f}%"
                       + (f", {len(warnings)}个风险" if warnings else ", 无风险"),
        }

        self._log("economic_rationality", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # E4: 部署质量评估
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_deployment_quality(self, day: int, player_name: str,
                                     deployments: dict[int, str],
                                     squad_fatigue: str,
                                     match_results: list[dict],
                                     opponent_deployments: dict[int, str]) -> dict:
        """评估部署策略质量：疲劳管理、point 保护、对位策略。

        Args:
            deployments: {slot: char_id}
            squad_fatigue: 阵容疲劳状态文本
            match_results: [{slot, won, my_char, opp_char, point_transferred, first_bonus}, ...]
            opponent_deployments: {slot: char_id}
        """
        # 程序化检查
        checks = []

        # 检查疲劳角斗士是否放关键局
        fatigue_lines = squad_fatigue.split("\n") if squad_fatigue else []
        for line in fatigue_lines:
            if "HP=" in line:
                for tag in ["80%", "60%"]:
                    if tag in line:
                        # 找到疲劳角斗士的 char_id
                        for slot, char_id in deployments.items():
                            if char_id in line:
                                if slot == 1:
                                    checks.append(f"疲劳角斗士({tag})放首局: {char_id}")
                                elif slot == 2:
                                    checks.append(f"疲劳角斗士({tag})放第2局: {char_id}")

        # 检查部署多样性
        unique_chars = set(deployments.values())
        if len(unique_chars) < 3:
            checks.append(f"未充分利用阵容（仅用 {len(unique_chars)} 个不同角斗士）")

        # 检查是否使用了田忌赛马策略（通过 LLM）
        my_slots = ", ".join(f"第{k}局:{v}" for k, v in sorted(deployments.items()))
        opp_slots = ", ".join(f"第{k}局:{v}" for k, v in sorted(opponent_deployments.items()))

        matches_text = ""
        for m in match_results:
            won = m.get("won", False)
            matches_text += (
                f"第{m['slot']}局: {'赢' if won else '输'} "
                f"(我方:{m.get('my_char','?')} vs 对手:{m.get('opp_char','?')}), "
                f"point:{'+' + str(m.get('point_transferred',0)) if won else '-' + str(m.get('point_transferred',0))}, "
                f"首局奖励:{m.get('first_bonus',0)}\n"
            )

        prompt = f"""{self._context}

【玩家】{player_name}，第{day}天

【阵容疲劳状态】
{squad_fatigue}

【我方部署】
{my_slots}

【对手部署】
{opp_slots}

【比赛结果】
{matches_text}

【规则提醒】
- 每天第1局：胜方额外获得败方 point×50% 的游戏币
- 疲劳角斗士 HP 降低：连续2天=80%，连续3天=60%
- 同一天不能用同一个角斗士两次
- point 越高的角斗士越值钱（最终结算兑回现金）

请评估该玩家的部署策略质量：
1. 首局策略：是否合理？是放强角斗士抢首局奖励，还是放弱角斗士保存实力？
2. 疲劳管理：是否合理安排了疲劳角斗士的出战顺序？
3. 对位策略：能否看出田忌赛马或其他博弈策略？
4. Point 保护：是否注意保护高 point 角斗士？
5. 综合评分（1-10分）

请严格以 JSON 格式回复：
{{"deployment_score": 数字1-10, "first_slot_reasoning": "首局分析", "fatigue_management": "疲劳管理评价", "matchup_strategy": "对位策略评价", "issues": ["问题1", "问题2"], "summary": "一句话总结"}}"""

        try:
            llm_result = self._call_llm(prompt)
        except Exception as e:
            llm_result = {"deployment_score": 0, "first_slot_reasoning": "",
                          "fatigue_management": "", "matchup_strategy": "",
                          "issues": [f"评估出错: {e}"],
                          "summary": f"评估出错: {e}"}

        result = {**llm_result, "programmatic_checks": checks}

        self._log("deployment_quality", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # E5: 对手建模能力
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_opponent_modeling(self, day: int, player_name: str,
                                    post_auction_analysis: str,
                                    match_reflections: str,
                                    opponent_deployments: dict[int, str],
                                    opponent_preview_seen: list[str]) -> dict:
        """评估玩家对对手行为的预测准确度。

        Args:
            post_auction_analysis: Phase 1.5 分析文本
            match_reflections: 比赛反思文本
            opponent_deployments: 对手实际部署 {slot: char_id}
            opponent_preview_seen: 对手见过的角斗士名称列表
        """
        opp_deploy_text = ", ".join(f"第{k}局:{v}" for k, v in sorted(opponent_deployments.items()))
        opp_preview_text = ", ".join(opponent_preview_seen) if opponent_preview_seen else "（未知）"

        prompt = f"""{self._context}

【玩家】{player_name}，第{day}天

【对手实际部署】
{opp_deploy_text}

【对手见过的角斗士】（可推理对手的信息集）
{opp_preview_text}

【该玩家的拍卖后分析】（此时还未部署，可以看到他对对手的推断）
{post_auction_analysis[:5000]}

【该玩家的赛后反思】（此时已知道比赛结果）
{match_reflections[:5000]}

请评估该玩家的对手建模质量：
1. 拍卖后分析中，对对手策略的推断是否合理？
2. 实际对手部署是否在分析中有所预料？
3. 反思中是否从对手行为中提取了有用的模式？
4. 预测准确度评分（1-10分）

请严格以 JSON 格式回复：
{{"modeling_score": 数字1-10, "predictions_made": ["推断1", "推断2"], "predictions_correct": ["正确的推断"], "predictions_wrong": ["错误的推断"], "learning_quality": "学习质量评价", "summary": "一句话总结"}}"""

        try:
            result = self._call_llm(prompt)
        except Exception as e:
            result = {"modeling_score": 0, "predictions_made": [],
                      "predictions_correct": [], "predictions_wrong": [],
                      "learning_quality": f"评估出错: {e}",
                      "summary": f"评估出错: {e}"}

        self._log("opponent_modeling", player_name, result, day)
        return result

    # ── LLM 调用 ────────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> dict:
        """调用 LLM 并解析 JSON 回复。"""
        from .config import MODEL_NAME, EXTRA_BODY_THINKING
        response = self._get_client().chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "user", "content": prompt},
            ],
            extra_body=EXTRA_BODY_THINKING,
        )
        content = response.choices[0].message.content or ""
        return self._parse_json(content)

    @staticmethod
    def _parse_json(text: str) -> dict:
        """从 LLM 回复中提取 JSON。容错 markdown 代码块。"""
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if m:
            text = m.group(1)
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {"error": "JSON解析失败", "raw": text[:500]}

    # ── 日志 ────────────────────────────────────────────────────────────────

    def _log(self, eval_type: str, target: str, result: dict, day: int):
        """通过 logger 记录分析结果。"""
        if self.logger:
            self.logger.log_evaluation(day, eval_type, target, result)
