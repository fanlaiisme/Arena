"""将 output/ 目录下的竞技场循环赛结果转换为 Bob 工具使用的 tournament_stats.json 格式。

用法:
  cd /home/fanlai/Arena
  .venv/bin/python role/data/Bob/convert_to_stats_json.py                        # 自动选最新
  .venv/bin/python role/data/Bob/convert_to_stats_json.py <tournament.json>     # 指定文件
"""

import json
import os
import glob
import sys

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "output")
STATS_OUTPUT = os.path.join(os.path.dirname(__file__), "tournament_stats.json")


def find_latest_tournament(output_dir: str) -> str | None:
    """在 output 目录找最新的 tournament_*.json 文件。"""
    pattern = os.path.join(output_dir, "tournament_*.json")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def convert(tournament_file: str, stats_file: str,
            duration_seconds: int = 0) -> dict:
    """将 tournament JSON 转换为 tournament_stats JSON 格式。"""
    with open(tournament_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    mp = data["matches_per_pair"]

    # ── 构建 char_id → name 映射 ──
    id_to_name = {c["id"]: c["name"] for c in data["characters"]}
    name_to_id = {c["name"]: c["id"] for c in data["characters"]}

    # ── rankings：补充 char_id、rank、win_rate、ties ──
    rankings = []
    ranked = sorted(data["rankings"], key=lambda r: -r["wins"])
    for i, r in enumerate(ranked):
        char_id = name_to_id.get(r["name"], r["name"])
        win_rate = round(r["wins"] / r["total"], 3) if r["total"] > 0 else 0.0
        rankings.append({
            "rank": i + 1,
            "char_id": char_id,
            "name": r["name"],
            "wins": r["wins"],
            "ties": r.get("ties", 0),
            "total": r["total"],
            "win_rate": win_rate,
        })

    # ── matchups：展开 matrix 为双向嵌套 dict ──
    matchups: dict[str, dict] = {c["id"]: {} for c in data["characters"]}
    for key, m in data["matrix"].items():
        # key 格式: "snowman_vs_lava"
        parts = key.rsplit("_vs_", 1)
        if len(parts) != 2:
            continue
        id_a, id_b = parts
        ties = m.get("ties", 0)
        matchups[id_a][id_b] = {
            "wins": m["p1_wins"],
            "ties": ties,
            "win_rate": round(m["p1_wins"] / mp, 2) if mp > 0 else 0.0,
        }
        matchups[id_b][id_a] = {
            "wins": m["p2_wins"],
            "ties": ties,
            "win_rate": round(m["p2_wins"] / mp, 2) if mp > 0 else 0.0,
        }

    # ── 构建最终结构 ──
    ts = data.get("timestamp", "")
    date_str = ts.replace("T", " ").split(".")[0] if ts else ""
    result = {
        "meta": {
            "date": date_str,
            "matches_per_pair": mp,
            "timeout_count": data.get("timeout_count", 0),
            "duration_seconds": duration_seconds,
        },
        "rankings": rankings,
        "matchups": matchups,
    }
    return result


def main():
    # 确定输入文件
    if len(sys.argv) > 1:
        tournament_file = sys.argv[1]
    else:
        tournament_file = find_latest_tournament(OUTPUT_DIR)
        if tournament_file is None:
            print(f"错误: 在 {OUTPUT_DIR} 下没有找到 tournament_*.json 文件")
            sys.exit(1)

    if not os.path.exists(tournament_file):
        print(f"错误: 文件不存在 {tournament_file}")
        sys.exit(1)

    print(f"输入: {tournament_file}")
    print(f"输出: {STATS_OUTPUT}")

    # 尝试从同名的 .txt 文件获取耗时
    duration = 0
    txt_file = tournament_file.replace(".json", ".txt")
    if os.path.exists(txt_file):
        with open(txt_file, "r", encoding="utf-8") as f:
            for line in f:
                if "总耗时:" in line:
                    import re
                    m = re.search(r"总耗时:\s*(\d+)s", line)
                    if m:
                        duration = int(m.group(1))
                    break

    result = convert(tournament_file, STATS_OUTPUT, duration)

    with open(STATS_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 摘要
    n = len(result["rankings"])
    print(f"  角斗士: {n} 人")
    print(f"  每对场次: {result['meta']['matches_per_pair']}")
    print(f"  超时: {result['meta']['timeout_count']} 场")
    print(f"  总耗时: {result['meta']['duration_seconds']}s")
    if n > 0:
        top = result["rankings"][0]
        print(f"  胜率第一: {top['name']} ({top['wins']}胜, {top['win_rate']*100:.1f}%)")


if __name__ == "__main__":
    main()
