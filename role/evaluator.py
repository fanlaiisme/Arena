"""审查智能体 —— 独立分析两赌徒的行为和状态。

新赌局玩法（main.py）：两个 AI 赌徒通过暗标拍卖获得角斗士，部署后进行 1v1 比赛。
Evaluator 在每天结束后对各玩家的策略、经济、部署进行独立评估。
"""

import json
import os
import re
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# 游戏规则摘要 —— 供 M1 规则幻觉检测参考
# ═══════════════════════════════════════════════════════════════════════════

GAME_RULES_SNIPPET = """## 拍卖规则
- 每天从20名角斗士中随机抽9名进入拍卖池，逐个展示。
- **一次性暗标**：双方各自提交一个出价数字（0=弃权，50~150），系统直接比大小。**不存在抬价、加价、试探对方底线的操作**——你只有一个数字的机会。
- **双方都扣出价**：无论谁赢，双方均扣自己的出价。输方的出价转入输方自己的**奖励池**。
- **奖励池不能用于竞拍**：奖励池的point是死钱，唯一用途：(1)系统补齐时游戏币不够作后备；(2)每日胜者最多转50→游戏币；(3)3天后1:1兑换。
- 出价相同重拍（最多1次），再次相同则跳过该角斗士。平局重拍不扣游戏币。
- 一方先满3人→另一方系统补齐（85币/人）。
- 低币<50强制弃权。
- 每天重新拍卖，前一天阵容清空。

## 比赛与point结算
- 比赛不下注——游戏币只在拍卖环节支出。
- 拍卖获得角斗士时 point=成交价；系统补齐 point=85。
- 比赛后胜方夺取 min(己方point, 败方point)。
- **每天第2局**夺取量×1.5。
- 胜方：己方point+夺取→奖励池；败方：己方point-夺取→奖励池（可为负）。
- 平局/超时：各自point归各自奖励池。结算后角斗士point清零。
- 同一天不能用同一个角斗士两次。

## 每日胜者奖励
- 3局结束后胜场多者为今日胜者。
- 胜者奖励池≤0无转换；0<pool<50全部兑为游戏币；pool≥50兑50游戏币。

## 疲劳机制
- 出战角斗士疲劳恶化：1.0→0.8, 0.9→0.8, 0.8→0.6, 0.6→0.6。
- 每日结算时未出战角斗士恢复一级：0.6→0.8, 0.8→0.9, 0.9→1.0。

## 最终结算
- 3天结束后奖励池point 1:1兑换为游戏币，比较总额。

## 重要：无属性相克
- 判断强弱只看胜率，不存在冰克火、光克暗等属性克制关系。不要根据名字脑补克制。"""


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

    # ═══════════════════════════════════════════════════════════════════════
    # M1: 规则幻觉检测 (LLM)
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_rule_compliance(self, day: int, player_name: str,
                                  agent_messages: str) -> dict:
        """检测玩家是否误解游戏规则。

        核心检测点：奖励池不能竞拍、一次性暗标不能加价、无属性克制、
        同一角斗士每天只能出战一次等。
        """
        if not agent_messages.strip():
            return {"rule_violations": [], "score": 10,
                    "summary": f"{player_name} 第{day}天无消息，跳过规则检测"}

        prompt = f"""{self._context}

【玩家】{player_name}，第{day}天

【游戏规则（正确版本）】
{GAME_RULES_SNIPPET}

【该玩家当天所有发言】
{agent_messages[:8000]}

请逐条对比该玩家的发言与正确规则，检测是否存在以下类型的**规则误解**：

1. **奖励池误解**：是否认为奖励池可以用于拍卖出价？是否把奖励池当活钱？
2. **暗标误解**：是否认为暗标过程中可以"加价"、"抬价"、"试探对方底线"？
3. **属性克制幻觉**：是否凭空编造了属性克制关系（如"冰克火"）？
4. **重复出战**：是否计划让同一角斗士在一天内出战多次？
5. **其他规则误解**：是否对第2局×1.5、疲劳机制、每日胜者奖励、最终结算等有错误理解？

**注意**：对于最终结算，"奖励池1:1兑回游戏币"是正确的理解，不算误解。
"奖励池不能用于拍卖"也是正确的。

请严格以 JSON 格式回复：
{{"rule_violations": [{{"rule": "被违反的规则", "player_statement": "玩家原话摘要", "why_wrong": "为什么理解错了"}}], "score": 数字1-10（10=完全正确无误解）, "summary": "一句话总结"}}"""

        try:
            result = self._call_llm(prompt)
        except Exception as e:
            result = {"rule_violations": [], "score": 0,
                      "summary": f"LLM评估出错: {e}"}

        self._log("rule_compliance", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # M2: 数字幻觉检测 (LLM)
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_factual_accuracy(self, day: int, player_name: str,
                                   agent_messages: str,
                                   preview_seen: list[dict],
                                   my_bids: list[dict],
                                   opponent_chips_range: str,
                                   ground_truth: dict | None = None) -> dict:
        """检测玩家是否虚构了数字数据。

        检测：声称角斗士胜率与真实值不符、声称花了Y实际花了X、
        声称对手有N币但逻辑不支持。
        """
        if not agent_messages.strip():
            return {"factual_errors": [], "score": 10,
                    "summary": f"{player_name} 第{day}天无消息，跳过数字检测"}

        # 构建真实数据参考
        preview_text = json.dumps(preview_seen, ensure_ascii=False, indent=2) if preview_seen else "（无预览数据）"
        bids_text = json.dumps(my_bids, ensure_ascii=False, indent=2) if my_bids else "（无出价记录）"

        gt_text = ""
        if ground_truth:
            rankings = ground_truth.get("rankings", [])
            gt_lines = ["【真实胜率排名（ground truth）】"]
            for g in rankings:
                gt_lines.append(f"  {g['rank']}. {g['name']}({g['char_id']}): 胜率{g['win_rate']*100:.1f}%")
            gt_text = "\n".join(gt_lines)

        prompt = f"""{self._context}

【玩家】{player_name}，第{day}天

【真实胜率数据（权威）】
{gt_text if gt_text else "（未提供）"}

【该玩家见过的角斗士胜率预览】
{preview_text}

【该玩家在拍卖中的出价记录】
{bids_text}

【对手游戏币估算】
{opponent_chips_range}

【该玩家当天所有发言】
{agent_messages[:8000]}

请检测该玩家是否在发言中**虚构了数字数据**：

1. **胜率虚构**：是否声称某角斗士的胜率是X%，但真实胜率与X不符（或该玩家根本没看过该角斗士的数据）？
2. **花费虚构**：是否声称"我花了X币买Y"但实际出价记录显示不同？
3. **对手币量虚构**：是否声称"对手有N币"但这个数字没有逻辑依据？
4. **其他数字虚构**：是否编造了不存在的比赛数据、point数值等？

**注意**：合理的推测（如"对手大概还有600左右"且与估算范围一致）不算虚构。
只有与已知事实明确矛盾或毫无根据的断言才算。

请严格以 JSON 格式回复：
{{"factual_errors": [{{"claim": "玩家的声称", "actual": "真实情况", "error_type": "win_rate/spend/opponent_chips/other"}}], "score": 数字1-10（10=完全准确无虚构）, "summary": "一句话总结"}}"""

        try:
            result = self._call_llm(prompt)
        except Exception as e:
            result = {"factual_errors": [], "score": 0,
                      "summary": f"LLM评估出错: {e}"}

        self._log("factual_accuracy", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # M3: 策略质量 (LLM)
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_strategy_quality(self, day: int, player_name: str,
                                   post_auction_analysis: str,
                                   match_reflections: str,
                                   day_summary: str,
                                   auction_results: str,
                                   deployments: dict[int, str],
                                   match_results: list[dict]) -> dict:
        """评估拍卖策略、部署策略、第2局×1.5利用、疲劳管理等。综合评分1-10。"""
        deploy_text = ", ".join(f"第{k}局:{v}" for k, v in sorted(deployments.items())) if deployments else "（无部署）"

        matches_text = ""
        for m in (match_results or []):
            won = m.get("won", False)
            matches_text += (
                f"第{m.get('slot','?')}局: {'赢' if won else '输'} "
                f"(我方:{m.get('my_char','?')} vs 对手:{m.get('opp_char','?')}), "
                f"point转移:{m.get('point_transferred',0)}, "
                f"倍率:{m.get('multiplier',1.0)}\n"
            )

        prompt = f"""{self._context}

【玩家】{player_name}，第{day}天

【拍卖结果】
{auction_results[:3000]}

【拍卖后分析】
{post_auction_analysis[:4000]}

【实际部署】
{deploy_text}

【比赛结果】
{matches_text}

【比赛反思】
{match_reflections[:4000]}

【全天复盘】
{day_summary[:4000]}

【规则提醒】
- 每天第2局夺取量×1.5——这是最重要的策略杠杆
- 疲劳角斗士HP降低：连续2天=80%，连续3天=60%
- 同一天不能用同一角斗士两次
- 没有属性相克

请综合评估该玩家的策略质量（1-10分），从以下维度分析：

1. **拍卖策略**：出价是否理性？是否合理利用预览信息？是否有明确的估值逻辑？
2. **部署策略**：第1/2/3局的角斗士安排是否合理？是否利用了第2局×1.5的杠杆？
3. **疲劳管理**：是否妥善安排了疲劳角斗士的休息和出战？
4. **Point管理**：是否注意保护高point角斗士？是否尝试夺取对方高point？
5. **学习与适应**：是否从当天结果中学习并调整策略？

请严格以 JSON 格式回复：
{{"overall_score": 数字1-10, "auction_strategy": "拍卖策略评价", "deployment_strategy": "部署策略评价", "fatigue_management": "疲劳管理评价", "point_management": "point管理评价", "learning_adaptation": "学习适应评价", "strengths": ["优点1"], "weaknesses": ["缺点1"], "summary": "一句话总结"}}"""

        try:
            result = self._call_llm(prompt)
        except Exception as e:
            result = {"overall_score": 0, "auction_strategy": "", "deployment_strategy": "",
                      "fatigue_management": "", "point_management": "", "learning_adaptation": "",
                      "strengths": [], "weaknesses": [f"评估出错: {e}"],
                      "summary": f"评估出错: {e}"}

        self._log("strategy_quality", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # M4: 经济理性 (纯程序化，增强版 E3)
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_economic_rationality_v2(self, day: int, player_name: str,
                                          chips: int, initial_chips: int,
                                          reward_pool: int, point_pool: int,
                                          my_bids: list[dict]) -> dict:
        """程序化检查：总花费/初始币比、跳过率、最大单笔/初始币比、
        死钱比例、系统补齐次数和费用、破产风险评估。

        Args:
            chips: 当前游戏币余额
            initial_chips: 当天开始时的游戏币（通常800）
            reward_pool: 奖励池（旧死钱）
            point_pool: 阵容当前point池
            my_bids: 拍卖出价记录 [{round_num, char_id, char_name, bids, winner, result, amount}, ...]
        """
        # ── 基础指标 ──
        total_spent = sum(b["amount"] for b in my_bids if b.get("result") == "win" and b.get("winner") == player_name)
        bids_nonzero = [b for b in my_bids if b.get("amount", 0) > 0]
        bids_zero = [b for b in my_bids if b.get("amount", 0) == 0]
        all_bids_amounts = [b.get("amount", 0) for b in my_bids]

        spend_ratio = total_spent / initial_chips if initial_chips > 0 else 0
        skip_rate = len(bids_zero) / len(my_bids) if my_bids else 0
        max_bid = max(all_bids_amounts) if all_bids_amounts else 0
        max_bid_ratio = max_bid / initial_chips if initial_chips > 0 else 0
        balance_health = chips / initial_chips if initial_chips > 0 else 0

        # ── 死钱比例 ──
        dead_money = reward_pool + point_pool
        dead_money_ratio = dead_money / initial_chips if initial_chips > 0 else 0

        # ── 系统补齐次数和费用 ──
        auto_fill_count = sum(1 for b in my_bids if b.get("auto_filled"))
        auto_fill_cost = auto_fill_count * 85  # AUTO_FILL_PRICE

        # ── 破产风险评估 ──
        bankruptcy_risk = "low"
        if chips < 100:
            bankruptcy_risk = "critical"
        elif chips < 200:
            bankruptcy_risk = "high"
        elif chips < 400:
            bankruptcy_risk = "moderate"

        # ── 风险指标汇总 ──
        warnings = []
        if spend_ratio > 0.5:
            warnings.append(f"单天花掉{spend_ratio*100:.0f}%游戏币（>50%）")
        if max_bid_ratio > 0.3:
            warnings.append(f"最大单笔出价占初始游戏币{max_bid_ratio*100:.0f}%（>30%）")
        if skip_rate > 0.5:
            warnings.append(f"弃权率{skip_rate*100:.0f}%（>50%），可能错过好角斗士")
        if balance_health < 0.2:
            warnings.append(f"余额严重不足（仅剩{balance_health*100:.0f}%）")
        if dead_money_ratio > 0.3:
            warnings.append(f"死钱比例{dead_money_ratio*100:.0f}%（>30%），大量游戏币冻结在奖励池")
        if auto_fill_count > 0:
            warnings.append(f"触发{auto_fill_count}次系统补齐，额外花费{auto_fill_cost}币")
        if bankruptcy_risk in ("critical", "high"):
            warnings.append(f"破产风险: {bankruptcy_risk}（仅剩{chips}币）")

        result = {
            "total_spent": total_spent,
            "spend_ratio": round(spend_ratio, 3),
            "skip_rate": round(skip_rate, 3),
            "max_bid": max_bid,
            "max_bid_ratio": round(max_bid_ratio, 3),
            "balance_health": round(balance_health, 3),
            "dead_money": dead_money,
            "dead_money_ratio": round(dead_money_ratio, 3),
            "auto_fill_count": auto_fill_count,
            "auto_fill_cost": auto_fill_cost,
            "bankruptcy_risk": bankruptcy_risk,
            "warnings": warnings,
            "summary": (
                f"花费{total_spent}币({spend_ratio*100:.0f}%), "
                f"弃权{skip_rate*100:.0f}%, "
                f"死钱{dead_money}({dead_money_ratio*100:.0f}%), "
                f"补齐{auto_fill_count}次, "
                f"破产风险:{bankruptcy_risk}"
                + (f", {len(warnings)}个警告" if warnings else "")
            ),
        }

        self._log("economic_rationality_v2", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # M5: 信息利用 (LLM)
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_information_utilization(self, day: int, player_name: str,
                                          agent_messages: str,
                                          preview_seen: list[dict],
                                          day_summary: str,
                                          ground_truth: dict | None = None) -> dict:
        """评估玩家是否有效利用预览情报和拍卖信号推断角斗士强弱、填写匿名排名表。"""
        if not agent_messages.strip():
            return {"info_score": 0, "inferences": [], "ranking_fill_quality": "",
                    "summary": f"{player_name} 第{day}天无消息，跳过信息利用评估"}

        preview_text = json.dumps(preview_seen, ensure_ascii=False, indent=2) if preview_seen else "（无预览数据）"

        gt_text = ""
        if ground_truth:
            rankings = ground_truth.get("rankings", [])
            gt_lines = ["【真实胜率排名】"]
            for g in rankings:
                gt_lines.append(f"  {g['rank']}. {g['name']}({g['char_id']}): 胜率{g['win_rate']*100:.1f}%")
            gt_text = "\n".join(gt_lines)

        prompt = f"""{self._context}

【玩家】{player_name}，第{day}天

【真实胜率排名（ground truth）】
{gt_text if gt_text else "（未提供）"}

【该玩家见过的角斗士胜率预览】
{preview_text}

【该玩家当天所有发言】
{agent_messages[:8000]}

【全天复盘（含排名表填写）】
{day_summary[:5000]}

请评估该玩家的**信息利用能力**：

1. **预览信息利用**：是否有效利用预览中的胜率数据来指导拍卖和部署？是否只使用了实际看过的数据？
2. **拍卖信号解读**：是否从对手的出价行为中推断出角斗士强弱信息？
3. **匿名排名表填写质量**：在复盘时填写的匿名胜率排名表质量如何？推断是否合理？来源标注是否诚实？
4. **信息整合**：是否能将碎片化的预览信息整合成对整体实力格局的判断？

综合评分 1-10。

请严格以 JSON 格式回复：
{{"info_score": 数字1-10, "inferences": [{{"inference": "推断内容", "basis": "依据", "correct": true/false/"不确定"}}], "ranking_fill_quality": "排名表填写质量评价", "strengths": ["信息利用优点"], "weaknesses": ["信息利用不足"], "summary": "一句话总结"}}"""

        try:
            result = self._call_llm(prompt)
        except Exception as e:
            result = {"info_score": 0, "inferences": [],
                      "ranking_fill_quality": "", "strengths": [], "weaknesses": [],
                      "summary": f"评估出错: {e}"}

        self._log("information_utilization", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # M6: 对手建模 (LLM)
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_opponent_modeling_v2(self, day: int, player_name: str,
                                       agent_messages: str,
                                       opponent_actions: list[str],
                                       opponent_deployments: dict[int, str],
                                       post_auction_analysis: str,
                                       match_reflections: str) -> dict:
        """评估玩家对对手行为的预测准确度。

        输入对手可观察行为（_opponent_actions）、对手实际部署、拍卖后分析、赛后反思。
        """
        opp_actions_text = "\n".join(f"  - {a}" for a in opponent_actions) if opponent_actions else "（无记录）"
        opp_deploy_text = ", ".join(f"第{k}局:{v}" for k, v in sorted(opponent_deployments.items())) if opponent_deployments else "（无部署）"

        if not agent_messages.strip():
            return {"modeling_score": 0, "predictions": [],
                    "summary": f"{player_name} 第{day}天无消息，跳过对手建模评估"}

        prompt = f"""{self._context}

【玩家】{player_name}，第{day}天

【对手可观察行为记录】
{opp_actions_text}

【对手实际部署】
{opp_deploy_text}

【该玩家的拍卖后分析】（此时已知对手阵容但未知部署）
{post_auction_analysis[:4000]}

【该玩家的赛后反思】（此时已知全部结果）
{match_reflections[:4000]}

【该玩家当天其他发言】
{agent_messages[:4000]}

请评估该玩家的**对手建模能力**：

1. **对手拍卖行为解读**：是否从对手的出价模式中识别出对手的策略偏好？
2. **对手部署预测**：拍卖后分析中是否准确预测了对手的部署策略？
3. **赛后学习**：反思中是否从对手行为中提取了有用的模式？是否更新了对对手的认知？
4. **对手信息集推理**：是否能站在对手角度思考对方知道什么、不知道什么？

综合评分 1-10。

请严格以 JSON 格式回复：
{{"modeling_score": 数字1-10, "predictions": [{{"prediction": "预测内容", "accuracy": "准确/部分准确/错误", "evidence": "依据"}}], "learning_quality": "从对手行为中学习的质量评价", "theory_of_mind": "换位思考能力评价", "summary": "一句话总结"}}"""

        try:
            result = self._call_llm(prompt)
        except Exception as e:
            result = {"modeling_score": 0, "predictions": [],
                      "learning_quality": "", "theory_of_mind": "",
                      "summary": f"评估出错: {e}"}

        self._log("opponent_modeling_v2", player_name, result, day)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # M7: 对手游戏币估计精确度 (程序化)
    # ═══════════════════════════════════════════════════════════════════════

    def evaluate_chip_estimation(self, day: int, player_name: str,
                                  reflection_text: str,
                                  actual_opponent_chips: int) -> dict:
        """程序化检测：玩家复盘中的对手游戏币估计是否准确。

        从复盘文本中提取估计范围（如"600~700"或"约 650"），
        与真实对手游戏币（ground truth）比对，判断是否命中。
        """
        if not reflection_text:
            return {"estimated_range": None, "actual_chips": actual_opponent_chips,
                    "hit": None, "score": 0,
                    "summary": f"{player_name} 第{day}天无复盘文本，跳过游戏币估计检测"}

        # 匹配模式：对手游戏币估计：下限~上限 或 对手游戏币估计：约 NNN
        patterns = [
            # "对手游戏币估计：600~700" 或 "对手游戏币估计: 600~700"
            r'对手游戏币估[算计][：:]\s*[约大约]?\s*(\d+)\s*[~\-–—至到]\s*(\d+)',
            # "约 600~700 游戏币"
            r'[约大约]?\s*(\d+)\s*[~\-–—至到]\s*(\d+)\s*游戏币',
            # "估计对手.*?(\d+)\s*[~\-–—至到]\s*(\d+)"
            r'估计对手.*?(\d+)\s*[~\-–—至到]\s*(\d+)',
            # "对手大概还有 600 左右"
            r'对手[大大概还][约概还有]*\s*(\d+)\s*[左以右内]',
            # "对手.*?(\d+).*?游戏币" (single number)
            r'对手.*?[约大约]?\s*(\d+)\s*游戏币[^\+]',
        ]

        estimated_low = None
        estimated_high = None

        for pattern in patterns:
            m = re.search(pattern, reflection_text)
            if m:
                groups = m.groups()
                if len(groups) == 2:
                    estimated_low = int(groups[0])
                    estimated_high = int(groups[1])
                elif len(groups) == 1:
                    # Single number → treat as ±25 range
                    mid = int(groups[0])
                    estimated_low = max(0, mid - 25)
                    estimated_high = mid + 25
                break

        if estimated_low is None:
            return {"estimated_range": None, "actual_chips": actual_opponent_chips,
                    "hit": False, "score": 0,
                    "summary": f"{player_name} 第{day}天未在复盘中发现对手游戏币估计"}

        # 确保 low <= high
        if estimated_low > estimated_high:
            estimated_low, estimated_high = estimated_high, estimated_low

        hit = estimated_low <= actual_opponent_chips <= estimated_high
        score = 10 if hit else (6 if abs(actual_opponent_chips - estimated_low) <= 30 or
                                 abs(actual_opponent_chips - estimated_high) <= 30 else 2)

        summary = (
            f"{player_name} 估计对手游戏币 {estimated_low}~{estimated_high}，"
            f"真实值 {actual_opponent_chips} → {'✅ 命中' if hit else '❌ 偏离'}"
        )

        result = {
            "estimated_range": f"{estimated_low}~{estimated_high}",
            "actual_chips": actual_opponent_chips,
            "hit": hit,
            "score": score,
            "summary": summary,
        }
        self._log("chip_estimation", player_name, result, day)
        return result

    # ── 辅助：加载 ground truth 数据 ─────────────────────────────────────

    def load_ground_truth(self) -> dict:
        """加载真实胜率统计数据。"""
        stats_file = os.path.join(
            os.path.dirname(__file__),
            "data", "Bob", "tournament_stats.json"
        )
        if os.path.exists(stats_file):
            with open(stats_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

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
