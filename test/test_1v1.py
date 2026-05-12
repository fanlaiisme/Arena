#!/usr/bin/env python3
"""循环赛自动测试：所有角色两两对决，每对 200 场。

用法:
    cd /home/fanlai/Arena && .venv/bin/python test/test_1v1.py
"""

import os
import sys

# 确保能从 test/ 子目录导入 main 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SDL_VIDEODRIVER'] = 'dummy'

import json
import time
import math
from datetime import datetime

import pygame

from main import Game, CHARACTERS, FPS

MATCHES_PER_PAIR = 200
TIMEOUT_FRAMES = 7200  # 120s 等效帧数（60fps），超时判平跳过


def _reset_game(game: Game):
    """清理对局状态，准备下一场。"""
    game.mode = None
    game.selection = []
    game.players = []
    game.projectiles = []
    game.lightning_bolts = []
    game.lightning_traps = []
    game.pets = []
    game.weapons = []
    game.weapon_pickups = []
    game.clones = []
    game.palms = []
    game.fist_traps = []
    game.vortexes = []
    game.waves = []
    game.hunt_marks = []
    game.trees = []
    game.leaf_blades = []
    game.bombs = []
    game.gas_clouds = []
    game._wave_burst_remaining = 0
    game._wave_owner = None
    game.game_over = False
    game.winner = None
    game.state = "mode_select"


def run_match(game: Game, p1_idx: int, p2_idx: int) -> str | None:
    """运行一场对局，返回胜方角色名；超时返回 None。"""
    game.mode = "1v1"
    game.selection = [p1_idx, p2_idx]
    game.start_match()
    dt = 1.0 / FPS

    frame = 0
    while not game.game_over:
        pygame.event.pump()
        game._update_fighting(dt)
        frame += 1
        if frame >= TIMEOUT_FRAMES:
            return None

    return game.winner


def _char_width(name: str) -> int:
    """中英文混排字符串显示宽度（中文≈2，ASCII≈1）。"""
    w = 0
    for ch in name:
        w += 2 if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯' else 1
    return w


def _pad(name: str, target: int) -> str:
    """按显示宽度填充到 target 列宽。"""
    need = target - _char_width(name)
    return name + ' ' * max(0, need)


def main():
    chars = CHARACTERS
    n = len(chars)
    total_pairs = n * (n - 1) // 2
    total_matches = total_pairs * MATCHES_PER_PAIR

    # 胜场矩阵: matrix[i][j] = i 对 j 的胜场数
    matrix = [[0] * n for _ in range(n)]
    # 平局矩阵: ties[i][j] = i 对 j 的平局数（双方对称）
    ties_matrix = [[0] * n for _ in range(n)]

    game = Game()
    overall_start = time.monotonic()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    result_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "output", f"tournament_{timestamp}.txt")

    print("角斗场循环赛")
    print(f"角色数: {n}  配对数: {total_pairs}  每对: {MATCHES_PER_PAIR} 场")
    print(f"总场次: {total_matches}")
    print(f"结果文件: {result_path}")
    print("=" * 60)

    pair_count = 0
    timeout_count = 0

    for i in range(n):
        for j in range(i + 1, n):
            pair_count += 1
            c1, c2 = chars[i], chars[j]
            wins = {c1.name: 0, c2.name: 0}
            ties = 0

            pair_start = time.monotonic()
            for m in range(MATCHES_PER_PAIR):
                # 交替左右位置，消除初始位置偏差
                if m % 2 == 0:
                    winner = run_match(game, i, j)
                else:
                    winner = run_match(game, j, i)

                if winner is None:
                    timeout_count += 1
                    ties += 1
                elif winner == c1.name:
                    wins[c1.name] += 1
                else:
                    wins[c2.name] += 1

                _reset_game(game)

            # 写入矩阵（胜场 + 平局）
            matrix[i][j] = wins[c1.name]
            matrix[j][i] = wins[c2.name]
            ties_matrix[i][j] = ties
            ties_matrix[j][i] = ties

            elapsed = time.monotonic() - pair_start
            rate = wins[c1.name] / MATCHES_PER_PAIR * 100
            done = pair_count / total_pairs * 100
            tie_str = f"  平{ties}场" if ties > 0 else ""
            print(f"  [{pair_count:2d}/{total_pairs}] {_pad(c1.name, 12)} vs {_pad(c2.name, 12)}  "
                  f"{wins[c1.name]:3d} : {wins[c2.name]:3d}{tie_str}  "
                  f"({c1.name}胜率 {rate:5.1f}%)  "
                  f"耗时 {elapsed:.0f}s  [{done:3.0f}%]")

    overall_elapsed = time.monotonic() - overall_start

    # ── 写入结果文件 ──────────────────────────────────────────────────────────
    col_w = max(_char_width(c.name) for c in chars) + 2
    name_w = col_w

    lines = []
    lines.append(f"角斗场循环赛结果")
    lines.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"每对场次: {MATCHES_PER_PAIR}  |  超时: {timeout_count} 场  |  总耗时: {overall_elapsed:.0f}s")
    lines.append("=" * 60)
    lines.append("")

    # 矩阵表头
    header = " " * name_w + "".join(_pad(c.name, col_w) for c in chars) + "  总胜  总平"
    lines.append(header)
    lines.append("-" * len(header))

    # 矩阵行
    for i, ci in enumerate(chars):
        cells = []
        total_wins = 0
        total_ties = 0
        for j, cj in enumerate(chars):
            if i == j:
                cells.append(_pad("-", col_w))
            else:
                w = matrix[i][j]
                t = ties_matrix[i][j]
                total_wins += w
                total_ties += t
                rate = w / MATCHES_PER_PAIR * 100
                if t > 0:
                    cells.append(_pad(f"{w}({rate:.0f}%+{t})", col_w))
                else:
                    cells.append(_pad(f"{w}({rate:.0f}%)", col_w))
        lines.append(_pad(ci.name, name_w) + "".join(cells) + f"  {total_wins:4d}  {total_ties:4d}")
    lines.append("")

    # 胜率总排名
    lines.append("=" * 60)
    lines.append("总排名（按总胜场数）")
    lines.append("-" * 50)
    rankings = []
    for i, c in enumerate(chars):
        tw = sum(matrix[i][j] for j in range(n) if i != j)
        tt = sum(ties_matrix[i][j] for j in range(n) if i != j)
        tg = (n - 1) * MATCHES_PER_PAIR
        rankings.append((c.name, tw, tt, tg))
    rankings.sort(key=lambda x: x[1], reverse=True)
    for rank, (name, wins, ties_total, total) in enumerate(rankings, 1):
        tie_str = f"  平{ties_total}场" if ties_total > 0 else ""
        lines.append(f"  {rank:2d}. {_pad(name, 12)} {wins:4d}胜/{total:4d}总  ({wins/total*100:5.1f}%){tie_str}")

    lines.append("")
    lines.append(f"完整对局日志: output/match_*.log")

    with open(result_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    # 同时输出 JSON 结构化结果
    json_path = result_path.replace('.txt', '.json')
    json_data = {
        "timestamp": datetime.now().isoformat(),
        "matches_per_pair": MATCHES_PER_PAIR,
        "timeout_count": timeout_count,
        "characters": [{"id": c.id, "name": c.name} for c in chars],
        "matrix": {f"{chars[i].id}_vs_{chars[j].id}": {
            "p1_wins": matrix[i][j],
            "p2_wins": matrix[j][i],
            "ties": ties_matrix[i][j],
        } for i in range(n) for j in range(i + 1, n)},
        "rankings": [{"name": name, "wins": wins, "ties": ties_total, "total": total}
                     for name, wins, ties_total, total in rankings],
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"循环赛完成！总耗时: {overall_elapsed:.0f}s")
    print(f"结果: {result_path}")
    print(f"JSON:  {json_path}")

    game.logger.close()


if __name__ == "__main__":
    main()
