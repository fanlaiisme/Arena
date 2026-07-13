"""实验统计报告 —— 解析 JSONL 日志，生成 AI 玩家表现的统计表格。

用法:
  cd /home/fanlai/Arena && .venv/bin/python role/test.py [日志文件路径]

  不带参数时，自动选取 role/output/ 下最新的 experiment_*.log 文件。
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# ── 配置 ────────────────────────────────────────────────────────────────────────

_OUTPUT_DIR = Path(__file__).parent / "output"
_EVAL_TYPES = {
    "rule_compliance":        "M1 规则幻觉",
    "factual_accuracy":       "M2 数字幻觉",
    "strategy_quality":       "M3 策略质量",
    "economic_rationality_v2":"M4 经济理性",
    "information_utilization":"M5 信息利用",
    "opponent_modeling_v2":   "M6 对手建模",
    "chip_estimation":        "M7 游戏币估计",
}


# ── 日志解析 ────────────────────────────────────────────────────────────────────

def find_latest_log() -> Path | None:
    """在 role/output/ 下找到最新的 experiment_*.log 文件。"""
    logs = sorted(_OUTPUT_DIR.glob("experiment_*.log"), reverse=True)
    return logs[0] if logs else None


def parse_log(log_path: Path) -> list[dict]:
    """逐行解析 JSONL 日志，返回事件列表。"""
    events = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


# ── 数据提取 ────────────────────────────────────────────────────────────────────

def extract_stats(events: list[dict]) -> dict:
    """从事件列表中提取按玩家、按天、按评估类型组织的统计。"""

    # 结构: stats[player_name][day][eval_type] = result_dict
    stats: dict[str, dict[int, dict[str, dict]]] = defaultdict(
        lambda: defaultdict(dict))

    # 游戏币估计详细数据: chip_data[player_name][day] = {...}
    chip_data: dict[str, dict[int, dict]] = defaultdict(dict)

    # 尝试从 log 中提取玩家名称
    player_names = _extract_player_names(events)

    for ev in events:
        if ev.get("event") != "evaluation":
            continue

        eval_type = ev.get("type", "")
        day = ev.get("round", 0)  # log_evaluation 中 round_num = day
        target = ev.get("target", "")
        result = ev.get("result", {})

        if not isinstance(result, dict):
            continue

        player_name = target if target in player_names else _find_player(result, player_names)

        if eval_type == "chip_estimation":
            chip_data[player_name][day] = result
        else:
            stats[player_name][day][eval_type] = result

    return {"stats": dict(stats), "chip_data": dict(chip_data),
            "player_names": list(player_names)}


def _extract_player_names(events: list[dict]) -> set[str]:
    """扫描日志找到实际玩家名。如果找不到，返回默认名。"""
    names = set()
    for ev in events:
        if ev.get("event") == "daily_summary":
            name = ev.get("player_name", "")
            if name:
                names.add(name)
        if ev.get("event") == "evaluation":
            target = ev.get("target", "")
            if target and target not in ("round", "day"):
                names.add(target)
    # 回退默认
    if not names:
        names = {"斑目貘", "夜神月"}
    return names


def _find_player(result: dict, known: set[str]) -> str:
    """尝试从 result 中匹配玩家名。"""
    for key in result:
        val = str(result[key])
        for name in known:
            if name in val:
                return name
    return "未知"


# ── 表格渲染 ────────────────────────────────────────────────────────────────────

def render_all(stats_data: dict) -> str:
    """生成完整统计报告。"""
    lines = []
    stats = stats_data["stats"]
    chip_data = stats_data["chip_data"]

    lines.append("=" * 80)
    lines.append("  实验统计报告")
    lines.append("=" * 80)

    # ── 表1：对手游戏币估计准确率 ──
    lines.append("")
    lines.append("── 表1：对手游戏币估计准确率（M7）──")
    lines.append("")
    lines.extend(_render_chip_table(chip_data))

    # ── 表2：全部评估打分汇总 ──
    lines.append("")
    lines.append("── 表2：评估智能体全部打分汇总 ──")
    lines.append("")
    lines.extend(_render_score_table(stats))

    # ── 表3：按玩家汇总 ──
    lines.append("")
    lines.append("── 表3：各玩家按维度汇总（平均分）──")
    lines.append("")
    lines.extend(_render_player_summary(stats))

    return "\n".join(lines)


def _render_chip_table(chip_data: dict) -> list[str]:
    """渲染游戏币估计准确率表。"""
    lines = []
    header = f"{'玩家':<10} {'天数':<6} {'估计范围':<16} {'真实值':<8} {'命中':<6} {'得分':<6}"
    lines.append(header)
    lines.append("-" * len(header))

    all_days = set()
    for player_data in chip_data.values():
        all_days.update(player_data.keys())
    all_days = sorted(all_days)

    for player_name in sorted(chip_data.keys()):
        for day in all_days:
            info = chip_data[player_name].get(day, {})
            if not info:
                continue
            est_range = info.get("estimated_range", "—")
            actual = info.get("actual_chips", "—")
            hit = "✅" if info.get("hit") else "❌"
            score = info.get("score", "—")
            lines.append(
                f"{player_name:<10} Day{day:<3} {str(est_range):<16} {str(actual):<8} {hit:<6} {score:<6}"
            )
    return lines


def _render_score_table(stats: dict) -> list[str]:
    """渲染全部打分明细表。"""
    lines = []

    # 收集所有出现的 (玩家, 天数, 评估类型)
    rows = []
    for player_name, player_data in stats.items():
        for day, day_data in player_data.items():
            for eval_type, result in day_data.items():
                label = _EVAL_TYPES.get(eval_type, eval_type)
                score = _extract_score(eval_type, result)
                rows.append((player_name, day, label, score, result))

    if not rows:
        lines.append("  （无评估数据）")
        return lines

    header = f"{'玩家':<10} {'天数':<6} {'评估维度':<18} {'得分':<8} {'摘要'}"
    lines.append(header)
    lines.append("-" * len(header))

    # 按玩家、天数、维度排序
    rows.sort(key=lambda r: (r[0], r[1], r[2]))

    for player_name, day, label, score, result in rows:
        summary = result.get("summary", "") if isinstance(result, dict) else ""
        summary = summary[:60] if summary else "—"
        score_str = str(score) if score is not None else "—"
        lines.append(f"{player_name:<10} Day{day:<3} {label:<18} {score_str:<8} {summary}")

    return lines


def _render_player_summary(stats: dict) -> list[str]:
    """按玩家汇总各维度平均分。"""
    lines = []

    # 收集: summary[player_name][label] = [scores]
    summary: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for player_name, player_data in stats.items():
        for day, day_data in player_data.items():
            for eval_type, result in day_data.items():
                label = _EVAL_TYPES.get(eval_type, eval_type)
                score = _extract_score(eval_type, result)
                if score is not None:
                    summary[player_name][label].append(score)

    if not summary:
        lines.append("  （无数据）")
        return lines

    # 构建表头
    all_labels = sorted(set(
        label for player_data in summary.values() for label in player_data))
    header = f"{'玩家':<10} " + " ".join(f"{l:<12}" for l in all_labels) + f" {'综合':<8}"
    lines.append(header)
    lines.append("-" * len(header))

    for player_name in sorted(summary.keys()):
        parts = [f"{player_name:<10}"]
        all_scores = []
        for label in all_labels:
            scores = summary[player_name].get(label, [])
            if scores:
                avg = sum(scores) / len(scores)
                parts.append(f"{avg:<12.1f}")
                all_scores.extend(scores)
            else:
                parts.append(f"{'—':<12}")
        overall = sum(all_scores) / len(all_scores) if all_scores else 0
        parts.append(f"{overall:<8.1f}")
        lines.append(" ".join(parts))

    return lines


def _extract_score(eval_type: str, result: dict):
    """从不同的评估结果中提取主得分。"""
    if not isinstance(result, dict):
        return None

    score_keys = {
        "rule_compliance":        "score",
        "factual_accuracy":       "score",
        "strategy_quality":       "overall_score",
        "information_utilization":"info_score",
        "opponent_modeling_v2":   "modeling_score",
        "chip_estimation":        "score",
        "economic_rationality_v2": None,  # 纯程序化，无综合分
        "strategy_consistency":   "consistency_score",
        "info_hallucination":     None,
        "deployment_quality":     None,
        "opponent_modeling":      "modeling_score",
    }

    key = score_keys.get(eval_type)
    if key and key in result:
        return result[key]

    # 回退：找名含 "score" 的字段
    for k in result:
        if "score" in k.lower() and isinstance(result[k], (int, float)):
            return result[k]
    return None


# ── 入口 ────────────────────────────────────────────────────────────────────────

def main():
    # 自动查找或手动指定日志文件
    if len(sys.argv) > 1:
        log_path = Path(sys.argv[1])
    else:
        log_path = find_latest_log()

    if log_path is None or not log_path.exists():
        print("❌ 未找到实验日志文件。")
        print(f"   默认搜索目录: {_OUTPUT_DIR}")
        print(f"   用法: .venv/bin/python role/test.py [日志文件路径]")
        print(f"   请先运行 main.py 生成实验日志。")
        sys.exit(1)

    print(f"📂 读取日志: {log_path}")
    print()

    events = parse_log(log_path)
    if not events:
        print("⚠️  日志文件为空。")
        sys.exit(1)

    stats_data = extract_stats(events)
    report = render_all(stats_data)
    print(report)


if __name__ == "__main__":
    main()
