"""实验日志 —— 记录三轮实验的完整过程。

输出到 Arena/output/experiment_YYYYMMDD-HHMMSS.log (JSONL)。
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class ExperimentLogger:
    """实验日志记录器。"""

    output_dir: str = ""

    def __post_init__(self):
        if not self.output_dir:
            self.output_dir = os.path.join(
                os.path.dirname(__file__), "output")
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = os.path.join(
            self.output_dir, f"experiment_{timestamp}.log")
        self.log_file = open(self.log_path, "w", encoding="utf-8")
        self._write("experiment_start", {
            "timestamp": datetime.now().isoformat(),
        })

    def _write(self, event: str, data: dict):
        """写入一条 JSONL 记录。"""
        record = {"event": event, **data}
        line = json.dumps(record, ensure_ascii=False)
        self.log_file.write(line + "\n")
        self.log_file.flush()

    # ── 日志方法 ──────────────────────────────────────────────────────────

    def log_round_start(self, round_num: int, bet: float):
        self._write("round_start", {
            "round": round_num,
            "bet_per_player": bet,
        })
        self._print(f"\n{'='*60}")
        self._print(f"  第 {round_num} 轮开始 | 每人投注: {bet}万")
        self._print(f"{'='*60}")

    def log_agent_message(self, agent_name: str, role: str, message: str):
        # 截断过长消息
        short = message[:300] + "..." if len(message) > 300 else message
        self._write("agent_message", {
            "agent": agent_name,
            "role": role,
            "content": message,
        })
        tag = "→" if role == "reply" else "←"
        print(f"  [{agent_name}] {tag} {short}")

    def log_tool_call(self, agent_name: str, tool_name: str,
                      args: dict, result: str):
        short_result = result[:200] + "..." if len(result) > 200 else result
        self._write("tool_call", {
            "agent": agent_name,
            "tool": tool_name,
            "args": args,
            "result": result,
        })
        print(f"  [TOOL] {agent_name}.{tool_name}({args}) → {short_result}")

    def log_thinking(self, agent_name: str, thinking: str):
        """记录 LLM 思考链（deepseek thinking mode 开启时生成）。"""
        if not thinking:
            return
        short = thinking[:300] + "..." if len(thinking) > 300 else thinking
        self._write("thinking", {
            "agent": agent_name,
            "thinking": thinking,
        })
        print(f"  [THINK] {agent_name}: {short}")

    def log_match_result(self, round_num: int, result: dict):
        self._write("match_result", {
            "round": round_num,
            "winner": result.get("winner"),
            "loser": result.get("loser"),
            "winner_gladiator": result.get("winner_gladiator"),
            "loser_gladiator": result.get("loser_gladiator"),
            "p1_gladiator": result.get("p1_gladiator"),
            "p2_gladiator": result.get("p2_gladiator"),
            "game_result": result.get("game_result"),
        })
        game = result.get("game_result", {})
        print(f"\n  ⚔  比赛结果: {result.get('winner')} 胜!")
        print(f"     胜方角斗士: {result.get('winner_gladiator')} "
              f"vs 败方角斗士: {result.get('loser_gladiator')}")
        if game:
            print(f"     胜者 HP: {game.get('winner_final_hp')}, "
                  f"败者 HP: {game.get('loser_final_hp')}, "
                  f"帧数: {game.get('duration_frames')}")
        print(f"     Bob 抽水: {result.get('commission')}万")

    def log_state_snapshot(self, round_num: int, bob_summary: str,
                            peter_summary: str, nerd_summary: str):
        self._write("state_snapshot", {
            "round": round_num,
            "bob": bob_summary,
            "peter": peter_summary,
            "nerd": nerd_summary,
        })
        print(f"\n  ── 第{round_num}轮后状态 ──")
        print(f"  {bob_summary}")
        print(f"  {peter_summary}")
        print(f"  {nerd_summary}")

    def log_investment_decision(self, decision: dict):
        self._write("investment_decision", decision)
        if decision.get("decision") == "invest":
            self._print(f"\n  [投资] Peter 决定投资 {decision['amount']}万 → {decision['reason']}")
        else:
            self._print(f"\n  [投资] Peter 决定不投资 → {decision['reason']}")

    def log_final_summary(self, bob_summary: str, peter_summary: str,
                           nerd_summary: str):
        self._write("final_summary", {
            "bob": bob_summary,
            "peter": peter_summary,
            "nerd": nerd_summary,
        })

    def log_evaluation(self, round_num: int, eval_type: str,
                        target: str, result: dict):
        """记录 evaluator 的分析结果。"""
        self._write("evaluation", {
            "round": round_num,
            "type": eval_type,       # "bob_honesty" | "player_state"
            "target": target,         # "Bob" | "Peter" | "Nerd"
            "result": result,
        })
        if eval_type == "hallucination_check":
            has = result.get("has_hallucination", False)
            if has:
                halls = result.get("hallucinations", [])
                parts = []
                for h in halls:
                    to = h.get("to", "?")
                    typ = h.get("hallucination_type", "?")
                    stmt = h.get("statement", "")
                    short = stmt[:50] + "..." if len(stmt) > 50 else stmt
                    parts.append(f"对{to}[{typ}]: \"{short}\"")
                detail = "; ".join(parts)
                self._print(f"  [EVAL] Bob 幻觉 ({len(halls)}处) → {detail}")
            else:
                self._print(f"  [EVAL] Bob: ✓ 无幻觉")
        else:
            emo = result.get("emotion", "?")
            trust = result.get("trust", "?")
            self._print(f"  [EVAL] {target}: {emo} | {trust}")

    def close(self):
        self._write("experiment_end", {
            "timestamp": datetime.now().isoformat(),
        })
        self.log_file.close()
        self._print(f"\n日志已保存: {self.log_path}")

    @staticmethod
    def _print(msg: str):
        print(msg)
