"""实验日志 —— 记录新赌局实验的完整过程。

输出到 Arena/output/experiment_YYYYMMDD-HHMMSS.log (JSONL)。
"""

import json
import os
import threading
import time
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class ExperimentLogger:
    """实验日志记录器（线程安全）。"""

    output_dir: str = ""

    def __post_init__(self):
        # 兼容：可通过 output_dir 传递自定义路径，或使用默认
        if not self.output_dir:
            self.output_dir = os.path.join(
                os.path.dirname(__file__), "output")
        os.makedirs(self.output_dir, exist_ok=True)
        self.init_log_file()

    def init_log_file(self, filename_prefix: str = "experiment"):
        """初始化日志文件（延迟调用以支持自定义前缀）。

        兼容旧代码：旧的 __post_init__ 调用此方法完成初始化。
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = os.path.join(
            self.output_dir, f"{filename_prefix}_{timestamp}.log")
        self.log_file = open(self.log_path, "w", encoding="utf-8")
        self._lock = threading.Lock()
        self._phase_start: dict[str, float] = {}
        self._write("experiment_start", {
            "timestamp": datetime.now().isoformat(),
        })

    def _write(self, event: str, data: dict):
        """写入一条 JSONL 记录（线程安全）。"""
        record = {"event": event, **data}
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    # ── 通用日志方法 ──────────────────────────────────────────────────────

    def log_agent_message(self, agent_name: str, role: str, message: str):
        short = message[:300] + "..." if len(message) > 300 else message
        self._write("agent_message", {
            "agent": agent_name,
            "role": role,
            "content": message,
        })
        tag = "\u2192" if role == "reply" else "\u2190"
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
        print(f"  [TOOL] {agent_name}.{tool_name}({args}) \u2192 {short_result}")

    def log_thinking(self, agent_name: str, thinking: str):
        if not thinking:
            return
        short = thinking[:300] + "..." if len(thinking) > 300 else thinking
        self._write("thinking", {
            "agent": agent_name,
            "thinking": thinking,
        })
        print(f"  [THINK] {agent_name}: {short}")

    def log_evaluation(self, round_num: int, eval_type: str,
                        target: str, result: dict):
        """记录 evaluator 的分析结果。"""
        self._write("evaluation", {
            "round": round_num,
            "type": eval_type,
            "target": target,
            "result": result,
        })
        summary = result.get("summary", "")[:120] if isinstance(result, dict) else str(result)[:120]
        self._print(f"  [EVAL] {eval_type}/{target}: {summary}")

    # ── 阶段计时 ──────────────────────────────────────────────────────────

    def log_phase(self, phase: str, event: str, day: int):
        """记录阶段事件和计时。event: 'start'/'end'。
        自动计算阶段耗时并输出。
        """
        phase_key = f"day{day}_{phase}"
        if event == "start":
            self._phase_start[phase_key] = time.time()
            self._write("phase_event", {
                "day": day,
                "phase": phase,
                "event": "start",
                "timestamp": datetime.now().isoformat(),
            })
            self._print(f"\n  [Phase] 第{day}天 {phase} 开始")
        elif event == "end":
            start_ts = self._phase_start.pop(phase_key, None)
            elapsed = time.time() - start_ts if start_ts else 0
            self._write("phase_event", {
                "day": day,
                "phase": phase,
                "event": "end",
                "elapsed_seconds": round(elapsed, 1),
                "timestamp": datetime.now().isoformat(),
            })
            self._print(f"  [Phase] 第{day}天 {phase} 结束 ({elapsed:.1f}s)")

    # ── 拍卖记录 ──────────────────────────────────────────────────────────

    def log_auction_round(self, day: int, round_num: int, char_name: str,
                           char_id: str, bid_a: int, bid_b: int,
                           result: str, retry: int):
        """记录单轮拍卖出价和结果。"""
        self._write("auction_round", {
            "day": day,
            "round": round_num,
            "char_name": char_name,
            "char_id": char_id,
            "bid_a": bid_a,
            "bid_b": bid_b,
            "result": result,
            "retry": retry,
        })

    # ── 比赛结果 ──────────────────────────────────────────────────────────

    def log_match_result(self, day: int, slot: int, result: dict):
        """记录单局比赛结果。"""
        self._write("match_result", {
            "day": day,
            "slot": slot,
            "winner": result.get("winner"),
            "loser": result.get("loser"),
            "winner_char_id": result.get("winner_char_id"),
            "loser_char_id": result.get("loser_char_id"),
            "point_transferred": result.get("point_transferred", 0),
            "first_match_bonus": result.get("first_match_bonus", 0),
            "game_result": result.get("game_result"),
        })
        game = result.get("game_result", {})
        bonus = result.get("first_match_bonus", 0)
        bonus_str = f" +首局{bonus}币" if bonus else ""
        print(f"\n  ⚔  第{day}天第{slot}局: {result.get('winner')} 胜! "
              f"({result.get('winner_char_id')} vs {result.get('loser_char_id')})")
        print(f"     point转移: {result.get('point_transferred', 0)}{bonus_str}")
        if game:
            print(f"     胜者 HP: {game.get('winner_final_hp')}, "
                  f"败者 HP: {game.get('loser_final_hp')}, "
                  f"帧数: {game.get('duration_frames')}")

    # ── 部署记录 ──────────────────────────────────────────────────────────

    def log_deployment(self, day: int, player_name: str,
                        slots: dict[int, str]):
        """记录玩家部署 {slot: char_id}。"""
        self._write("deployment", {
            "day": day,
            "player": player_name,
            "slots": {str(k): v for k, v in slots.items()},
        })
        slots_str = ", ".join(f"第{k}局:{v}" for k, v in sorted(slots.items()))
        print(f"  [DEPLOY] {player_name}: {slots_str}")

    # ── 每日摘要 ──────────────────────────────────────────────────────────

    def log_daily_summary(self, day: int, player_name: str,
                           chips: int, points: int, fatigue: str):
        """记录每天结束时的玩家状态。"""
        self._write("daily_summary", {
            "day": day,
            "player": player_name,
            "chips": chips,
            "points": points,
            "fatigue": fatigue,
        })

    # ── 最终结算 ──────────────────────────────────────────────────────────

    def log_final_settlement(self, player_name: str, chips: int,
                              points: int, total_coins: int,
                              cash_back: float, final_assets: float):
        """记录最终结算详情。"""
        self._write("final_settlement", {
            "player": player_name,
            "remaining_chips": chips,
            "total_points": points,
            "total_coins": total_coins,
            "cash_back": cash_back,
            "final_assets": final_assets,
        })
        self._print(f"  [结算] {player_name}: {chips}币 + {points}point "
                     f"= {total_coins}币 → {cash_back:.1f}万 (总资产{final_assets:.0f}万)")

    # ── 状态快照 ──────────────────────────────────────────────────────────

    def log_state_snapshot(self, day: int, player_a_summary: str,
                            player_b_summary: str):
        """记录每天结束后的双方状态快照。"""
        self._write("state_snapshot", {
            "day": day,
            "player_a": player_a_summary,
            "player_b": player_b_summary,
        })
        print(f"\n  ── 第{day}天后状态 ──")
        print(f"  {player_a_summary}")
        print(f"  {player_b_summary}")

    def log_final_summary(self, player_a_summary: str,
                           player_b_summary: str):
        """记录实验结束时的最终摘要。"""
        self._write("final_summary", {
            "player_a": player_a_summary,
            "player_b": player_b_summary,
        })

    # ── 保留的旧方法（main.py 不再调用，test.py 向后兼容） ─────────────────

    def log_round_start(self, round_num: int, bet: float):
        """（已废弃）旧版轮次开始。"""
        self._write("round_start", {
            "round": round_num,
            "bet_per_player": bet,
        })
        self._print(f"\n{'='*60}")
        self._print(f"  第 {round_num} 轮开始 | 每人投注: {bet}万")
        self._print(f"{'='*60}")

    def log_investment_decision(self, decision: dict):
        """（已废弃）Peter 投资决策。"""
        self._write("investment_decision", decision)
        if decision.get("decision") == "invest":
            self._print(f"\n  [投资] Peter 决定投资 {decision['amount']}万 → {decision['reason']}")
        else:
            self._print(f"\n  [投资] Peter 决定不投资 → {decision['reason']}")

    def log_bob_final_reflection(self, reflection: str):
        """（已废弃）Bob 失败复盘。"""
        self._write("bob_final_reflection", {
            "reflection": reflection,
        })
        short = reflection[:300] + "..." if len(reflection) > 300 else reflection
        self._print(f"\n  [Bob 复盘] {short}")

    # ── 基础设施 ──────────────────────────────────────────────────────────

    def close(self):
        self._write("experiment_end", {
            "timestamp": datetime.now().isoformat(),
        })
        self.log_file.close()
        self._print(f"\n日志已保存: {self.log_path}")

    @staticmethod
    def _print(msg: str):
        print(msg)
