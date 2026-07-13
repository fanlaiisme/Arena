"""记忆日志分析脚本 —— 遍历 memory_logs 下所有日志，输出统计报告。

用法:
  cd /home/fanlai/Arena && .venv/bin/python role/memory/analyze_logs.py
"""

import re
from pathlib import Path
from collections import defaultdict

_LOG_DIR = Path(__file__).parent / "memory_logs"
_MEMORY_DIR = Path(__file__).parent  # 斑目貘/ 和 夜神月/ 的父目录


def parse_logs():
    """解析所有日志文件，返回结构化数据。"""
    logs = defaultdict(list)  # player_name → [events]

    for log_path in sorted(_LOG_DIR.glob("*.log")):
        player_name = log_path.stem.rsplit("_", 1)[0]  # "斑目貘_20260713-132044" → "斑目貘"
        logs[player_name].extend(_parse_one(log_path))

    return dict(logs)


def _parse_one(path: Path) -> list[dict]:
    events = []
    last_tool = ""      # 跟踪最近一次 tool_call 的工具名
    last_filepath = ""  # 跟踪最近一次 tool_call 的文件路径参数
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ev = _parse_line(line)
            if ev:
                if ev["type"] == "tool_call":
                    last_tool = ev.get("tool", "")
                    last_filepath = ev.get("filepath", "")
                elif ev["type"] == "tool_result":
                    # 从上一个 tool_call 继承文件路径
                    if not ev.get("filepath"):
                        ev["filepath"] = last_filepath
                    if last_tool == "read_memory" and ev["filepath"]:
                        ev["was_read"] = True
                events.append(ev)
    return events


def _parse_line(line: str) -> dict | None:
    m = re.match(r'\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s+(\S+)', line)
    if not m:
        return None
    h, ms_c, s, ms = int(m[1]), int(m[2]), int(m[3]), int(m[4])
    timestamp = h * 3600 + ms_c * 60 + s + ms / 1000.0
    event_type = m[5]
    rest = line[m.end():].strip().lstrip("|").strip()  # 去除 " | " 分隔符

    ev = {"ts": timestamp, "type": event_type}

    if event_type == "init":
        ev["player"] = rest.split("，")[0].replace("记忆 subagent 启动", "").strip()
        m2 = re.search(r"目录=(.+)", rest)
        if m2:
            ev["dir"] = m2.group(1)

    elif event_type == "submit":
        m2 = re.match(r"label=([^,]+),\s*len=(\d+)", rest)
        if m2:
            ev["label"] = m2.group(1)
            ev["len"] = int(m2.group(2))

    elif event_type == "process_start":
        m2 = re.match(r"label=([^,]+)", rest)
        if m2:
            ev["label"] = m2.group(1)

    elif event_type == "tool_call":
        m2 = re.match(r"iteration=(\d+),\s*tool=([^,]+),\s*args=(.+)", rest)
        if m2:
            ev["iteration"] = int(m2.group(1))
            ev["tool"] = m2.group(2)
            ev["args"] = m2.group(3)
            # 从 args 中提取 filepath
            m3 = re.search(r'"filepath":\s*"([^"]+)"', m2.group(3))
            if m3:
                ev["filepath"] = m3.group(1)

    elif event_type == "tool_result":
        ev["result"] = rest
        # 提取文件路径
        m2 = re.search(r'"filepath":\s*"([^"]+)"', rest)
        if m2:
            ev["filepath"] = m2.group(1)
        # 提取操作类型
        if "修改了已有内容" in rest or rest.startswith("✏️"):
            ev["action"] = "edit"
            m3 = re.search(r'✏️\s*修改了已有内容：(.+)', rest)
            if m3:
                ev["section"] = m3.group(1)
        elif "填充了空模板" in rest or rest.startswith("✅ 填"):
            ev["action"] = "fill"
            m3 = re.search(r'✅\s*填充了空模板：(.+)', rest)
            if m3:
                ev["section"] = m3.group(1)
        elif "创建了新文件" in rest or rest.startswith("✅ 创"):
            ev["action"] = "create"
            m3 = re.search(r'✅\s*创建了新文件：(.+)', rest)
            if m3:
                ev["section"] = m3.group(1)
        elif "未找到匹配" in rest or rest.startswith("❌ 未"):
            ev["action"] = "not_found"
        elif "禁止操作" in rest or rest.startswith("⛔"):
            ev["action"] = "blocked"
        elif "路径错误" in rest or rest.startswith("❌ 路径"):
            ev["action"] = "path_error"
        elif "工具执行错误" in rest:
            ev["action"] = "tool_error"

    elif event_type == "no_action":
        ev["reason"] = rest

    return ev


# ═══════════════════════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════════════════════

def analyze(events_by_player: dict) -> dict:
    stats = {
        "total_tool_calls": 0,
        "tool_counts": defaultdict(int),           # tool → count
        "read_counts": defaultdict(int),            # file → count
        "edit_counts": defaultdict(int),            # file → count
        "edit_results": defaultdict(int),           # action type → count
        "submit_labels": defaultdict(int),          # label → count
        "per_player": defaultdict(lambda: defaultdict(int)),  # player → stat → count
        "time_range": {"start": float("inf"), "end": 0},
        "day_edits": defaultdict(int),              # day{N} → edit count
    }

    for player, events in events_by_player.items():
        for ev in events:
            # 时间范围
            if ev["ts"] < stats["time_range"]["start"]:
                stats["time_range"]["start"] = ev["ts"]
            if ev["ts"] > stats["time_range"]["end"]:
                stats["time_range"]["end"] = ev["ts"]

            if ev["type"] == "tool_call":
                stats["total_tool_calls"] += 1
                tool = ev.get("tool", "unknown")
                stats["tool_counts"][tool] += 1
                stats["per_player"][player]["tool_calls"] += 1

            elif ev["type"] == "tool_result":
                filepath = _short_filepath(ev.get("filepath", ""))
                action = ev.get("action", "")

                # read 计数
                if ev.get("was_read"):
                    stats["read_counts"][filepath] += 1

                # edit 计数
                if action in ("edit", "fill", "create"):
                    stats["edit_counts"][filepath] += 1
                    # 按天统计
                    day = _extract_day(filepath)
                    if day:
                        stats["day_edits"][day] += 1

                if action:
                    stats["edit_results"][action] += 1
                    stats["per_player"][player][action] += 1

            elif ev["type"] == "submit":
                label = ev.get("label", "unknown")
                stats["submit_labels"][label] += 1
                stats["per_player"][player]["submits"] += 1

            elif ev["type"] == "no_action":
                stats["per_player"][player]["no_actions"] += 1

    return stats


def _short_filepath(filepath: str) -> str:
    """提取文件名部分。"""
    if not filepath:
        return ""
    # 取最后一个路径段
    parts = filepath.replace("\\", "/").split("/")
    return parts[-1] if parts else filepath


def _extract_day(filepath: str) -> str:
    """从文件路径提取天数。"""
    m = re.search(r'day(\d)\.md', filepath)
    return f"day{m.group(1)}" if m else ""


# ═══════════════════════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════════════════════

def render(stats: dict, events_by_player: dict) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("  记忆日志分析报告")
    lines.append("=" * 70)

    # ── 基本信息 ──
    duration = stats["time_range"]["end"] - stats["time_range"]["start"]
    lines.append(f"\n📂 玩家数: {len(events_by_player)}")
    lines.append(f"📂 时间跨度: {duration/60:.1f} 分钟")
    players = list(events_by_player.keys())
    lines.append(f"📂 玩家: {', '.join(players)}")

    # ── 工具调用总次数 ──
    lines.append(f"\n{'─'*50}")
    lines.append(f"🔧 工具调用总次数: {stats['total_tool_calls']}")
    lines.append("")

    for tool, count in sorted(stats["tool_counts"].items(), key=lambda x: -x[1]):
        bar = "█" * min(count // 5, 40)
        lines.append(f"  {tool:<25} {count:>4}  {bar}")

    # ── 每人工具调用 ──
    lines.append(f"\n{'─'*50}")
    lines.append("👤 每个玩家的工具调用次数")
    lines.append("")
    for player in players:
        pp = stats["per_player"][player]
        lines.append(f"  {player}: {pp['tool_calls']} 次工具调用, "
                     f"{pp['submits']} 次提交, {pp['no_actions']} 次无操作")

    # ── 每个文件被 read 的次数 ──
    lines.append(f"\n{'─'*50}")
    lines.append("📖 每个文件被 read 工具读取的次数")
    lines.append("")
    if stats["read_counts"]:
        for file, count in sorted(stats["read_counts"].items(), key=lambda x: -x[1]):
            bar = "█" * min(count, 40)
            lines.append(f"  {file:<30} {count:>4}  {bar}")
    else:
        lines.append("  （无记录——检查日志中的 tool_result 解析）")

    # ── 每个文件被 edit 的次数 ──
    lines.append(f"\n{'─'*50}")
    lines.append("✏️  每个文件被 edit 工具修改的次数")
    lines.append("")
    total_edits = sum(stats["edit_counts"].values())
    for file, count in sorted(stats["edit_counts"].items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 40)
        lines.append(f"  {file:<30} {count:>4}  {bar}")
    lines.append(f"  {'合计':<30} {total_edits:>4}")

    # ── 编辑操作分布 ──
    lines.append(f"\n{'─'*50}")
    lines.append("📊 编辑操作结果分布")
    lines.append("")
    action_labels = {
        "edit": "✏️  修改已有内容",
        "fill": "✅ 填充空模板",
        "create": "✅ 创建新文件",
        "blocked": "⛔ 被拒绝（未先 read）",
        "not_found": "❌ 未找到匹配内容",
        "path_error": "❌ 路径错误",
        "tool_error": "❌ 工具执行错误",
    }
    success = stats["edit_results"]["edit"] + stats["edit_results"]["fill"] + stats["edit_results"]["create"]
    total = sum(stats["edit_results"].values())
    for key, label in action_labels.items():
        count = stats["edit_results"].get(key, 0)
        if count:
            lines.append(f"  {label:<32} {count:>4}")

    if total > 0:
        lines.append(f"\n  ✅ 成功率: {success}/{total} = {success/total*100:.1f}%")

    # ── 按天编辑分布 ──
    if stats["day_edits"]:
        lines.append(f"\n{'─'*50}")
        lines.append("📅 按天编辑分布")
        lines.append("")
        for day in sorted(stats["day_edits"].keys()):
            count = stats["day_edits"][day]
            bar = "█" * min(count, 40)
            lines.append(f"  {day}: {count:>4}  {bar}")

    # ── 提交标签分布 ──
    lines.append(f"\n{'─'*50}")
    lines.append("🏷️  提交标签分布（玩家思考输出的阶段）")
    lines.append("")
    for label, count in sorted(stats["submit_labels"].items(), key=lambda x: -x[1]):
        if count >= 3:
            bar = "█" * count
        else:
            bar = "▌" * count
        lines.append(f"  {label:<30} {count:>4}  {bar}")

    # ── 补充：处理效率 ──
    lines.append(f"\n{'─'*50}")
    lines.append("⚡ 处理效率（补充）")
    lines.append("")

    # 统计每次 process 的完成时间
    process_times = []
    for player in players:
        events = events_by_player[player]
        in_progress = {}
        for ev in events:
            if ev["type"] == "process_start":
                label = ev.get("label", "")
                in_progress[label] = ev["ts"]
            elif ev["type"] in ("no_action", "tool_call"):
                # 找最后一个 tool_call 之后的 no_action，或直接用 no_action
                pass
        # 简化：用相邻 process_start 间隔估算
        starts = [ev["ts"] for ev in events if ev["type"] == "process_start"]
        for i in range(1, len(starts)):
            dt = starts[i] - starts[i-1]
            if 0 < dt < 300:  # 忽略超过 5 分钟的（可能跨天）
                process_times.append(dt)

    if process_times:
        avg = sum(process_times) / len(process_times)
        lines.append(f"  平均每次处理间隔: {avg:.1f}s")
        lines.append(f"  最快: {min(process_times):.1f}s  最慢: {max(process_times):.1f}s")

    # subagent 无操作率
    for player in players:
        pp = stats["per_player"][player]
        total = pp["submits"]
        no_op = pp["no_actions"]
        pct = no_op / total * 100 if total > 0 else 0
        lines.append(f"  {player} 无操作率: {no_op}/{total} = {pct:.0f}%（正确跳过了非记忆事件）")

    lines.append(f"\n{'='*70}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════

def main():
    if not _LOG_DIR.exists() or not list(_LOG_DIR.glob("*.log")):
        print(f"❌ 未找到日志文件（目录: {_LOG_DIR}）")
        return

    print("📂 正在解析日志...")
    events_by_player = parse_logs()
    stats = analyze(events_by_player)
    print(render(stats, events_by_player))


if __name__ == "__main__":
    main()
