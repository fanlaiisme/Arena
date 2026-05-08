"""将 tournament_stats-1.txt 转换为 Markdown 表格格式。

用法: cd /home/fanlai/Arena && .venv/bin/python role/data/Bob/convert_stats.py
"""

import os
import re

INPUT = os.path.join(os.path.dirname(__file__), "tournament_stats-1.txt")
OUTPUT = os.path.join(os.path.dirname(__file__), "tournament_stats-1.md")


def parse_table(all_lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """解析纯文本矩阵，返回 (列名列表, 数据行列表)。

    列名 = 9个角斗士名 + "总胜"（分隔线上方的表头行）
    数据行 = 行名 + 9个值（含自对 "-"）+ 总胜（分隔线下方到 === 之间）
    """
    # 找到分隔线位置
    sep_idx = None
    for i, line in enumerate(all_lines):
        if line.startswith("---"):
            sep_idx = i
            break
    if sep_idx is None:
        return [], []

    # 分隔线上一行是表头
    header = re.split(r"\s{2,}", all_lines[sep_idx - 1].strip())

    # 分隔线之后到 === 之间是数据行
    data_rows = []
    for i in range(sep_idx + 1, len(all_lines)):
        line = all_lines[i]
        if line.startswith("===") or not line.strip():
            break
        parts = re.split(r"\s{2,}", line.strip())
        if parts:
            data_rows.append(parts)

    return header, data_rows


def _parse_cell(cell: str) -> tuple[int, float]:
    """解析 "199(100%)" → (199, 1.0)"""
    m = re.match(r"(\d+)\(([\d.]+)%\)", cell)
    if m:
        return int(m.group(1)), float(m.group(2)) / 100
    return 0, 0.0


def generate_markdown(header: list[str], data_rows: list[list[str]],
                      ranking_lines: list[str], meta: dict) -> str:
    out = []

    out.append("# 角斗场循环赛结果")
    out.append("")
    out.append(f"- 时间: {meta.get('time', '?')}")
    out.append(f"- 每对场次: {meta.get('mp', '?')}")
    out.append(f"- 超时: {meta.get('to', '?')} 场")
    out.append(f"- 总耗时: {meta.get('dur', '?')}")
    out.append("")

    # ── 总排名 ──
    out.append("## 总排名（按总胜场数）")
    out.append("")
    out.append("| 排名 | 角斗士 | 胜场 | 总场 | 胜率 |")
    out.append("|------|--------|------|------|------|")
    for rl in ranking_lines:
        m = re.match(r"\s*(\d+)\.\s+(\S+)\s+(\d+)/(\d+)\s+\(\s*([\d.]+%)\)", rl)
        if m:
            out.append(f"| {m.group(1)} | {m.group(2)} | {m.group(3)} | {m.group(4)} | {m.group(5)} |")
    out.append("")

    # ── 各角斗士对战详情 ──
    out.append("## 各角斗士对战详情")
    out.append("")
    out.append("> 每个角斗士列出其对所有对手的历史战绩，按胜率从高到低排列。")
    out.append("> 数值含义：该角斗士（攻击方）对阵某对手时，赢了 X 场，胜率 Y%。")
    out.append("")

    # 列名（去掉"总胜"）
    col_names = header[:-1]  # 9 个角斗士名

    for row in data_rows:
        name = row[0]
        total_wins = int(row[-1]) if row[-1].isdigit() else 0
        overall_rate = total_wins / (len(col_names) - 1) / 200  # 近似

        # 解析每个对战 (跳过 row[0]=名字, row[-1]=总胜, 自对="-")
        matchups = []
        for i, cell in enumerate(row[1:-1]):
            opponent = col_names[i]
            if cell == "-":
                continue
            wins, rate = _parse_cell(cell)
            matchups.append((opponent, wins, rate))

        # 按胜率降序
        matchups.sort(key=lambda x: x[2], reverse=True)

        out.append(f"### {name}")
        out.append("")
        out.append("| 对手 | 胜场 | 胜率 |")
        out.append("|------|------|------|")
        for opponent, wins, rate in matchups:
            rate_pct = f"{rate*100:.0f}%"
            out.append(f"| {opponent} | {wins} | {rate_pct} |")
        out.append("")

    return "\n".join(out)


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        content = f.read()

    all_lines = content.split("\n")

    # 解析元数据（第2行包含三个字段）
    meta = {}
    for line in all_lines[:4]:
        if m := re.match(r"时间:\s*(.+)", line):
            meta["time"] = m.group(1).strip()
        elif m := re.match(r"每对场次:\s*(\d+)", line):
            meta["mp"] = m.group(1)
            # 同一行还包含 超时 和 总耗时
            if m2 := re.search(r"超时:\s*(\d+)", line):
                meta["to"] = m2.group(1)
            if m2 := re.search(r"总耗时:\s*(.+)", line):
                meta["dur"] = m2.group(1).strip()

    # 提取排名
    ranking_lines = []
    in_ranking = False
    for line in all_lines:
        if "总排名" in line:
            in_ranking = True
            continue
        if in_ranking and re.match(r"\s*\d+\.", line):
            ranking_lines.append(line)

    # 解析矩阵
    header, data_rows = parse_table(all_lines)

    md = generate_markdown(header, data_rows, ranking_lines, meta)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"✓ 转换完成: {OUTPUT}")
    print(f"  角斗士: {len(data_rows)} 人")
    print(f"  排名行: {len(ranking_lines)} 条")
    print(f"  矩阵列: {len(header)}")


if __name__ == "__main__":
    main()
