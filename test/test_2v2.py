#!/usr/bin/env python3
"""2v2 循环赛自动测试：从角色池中选取 4 人组队对决。

用法:
    cd /home/fanlai/Arena && .venv/bin/python test/test_2v2.py
"""

import os
import sys

# 确保能从 test/ 子目录导入 main 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SDL_VIDEODRIVER'] = 'dummy'

import json
import time
import random
from datetime import datetime

import pygame

from main import Game, CHARACTERS, FPS

MATCHES_PER_TEAM = 100         # 每队组合对打的场数
TIMEOUT_FRAMES = 7200          # 120s 超时
TEAM_SIZE = 2                  # 每队人数
NUM_TEAM_COMBOS = 20           # 随机生成多少个队伍组合


def _build_teams():
    """从角色池中随机生成队伍组合。

    每队 2 人，队内角色不重复。生成 NUM_TEAM_COMBOS 个 A 队和 B 队。
    保证 A 队和 B 队之间可以有相同角色（跨队允许重复）。
    """
    teams_a = []
    teams_b = []
    indices = list(range(len(CHARACTERS)))
    for _ in range(NUM_TEAM_COMBOS):
        a = random.sample(indices, TEAM_SIZE)
        b = random.sample(indices, TEAM_SIZE)
        teams_a.append(sorted(a))
        teams_b.append(sorted(b))
    return teams_a, teams_b


def _team_key(indices: list[int]) -> str:
    """队伍标识，如 'snowman+lava'。"""
    return "+".join(CHARACTERS[i].id for i in sorted(indices))


def _team_name(indices: list[int]) -> str:
    """队伍中文名，如 '雪人召唤师+熔岩射手'。"""
    return "+".join(CHARACTERS[i].name for i in sorted(indices))


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


def run_2v2_match(game: Game, team_a: list[int], team_b: list[int]) -> str | None:
    """运行一场 2v2 对局。team_a 为左方（A 队），team_b 为右方（B 队）。

    角色排布: team_a[0] 左上, team_b[0] 右上, team_a[1] 左下, team_b[1] 右下。
    返回胜方 ('A队' | 'B队')，超时返回 None。
    """
    game.mode = "2v2"
    game.selection = [team_a[0], team_b[0], team_a[1], team_b[1]]
    game.start_match()
    dt = 1.0 / FPS

    frame = 0
    while not game.game_over:
        pygame.event.pump()
        game._update_fighting(dt)
        frame += 1
        if frame >= TIMEOUT_FRAMES:
            return None

    return game.winner  # "A队" or "B队"


def main():
    random.seed(42)  # 可复现

    teams_a, teams_b = _build_teams()
    total_pairs = len(teams_a)
    total_matches = total_pairs * MATCHES_PER_TEAM

    print("角斗场 2v2 循环赛")
    print(f"队伍组合数: {total_pairs}  每对: {MATCHES_PER_TEAM} 场")
    print(f"总场次: {total_matches}")
    print("=" * 60)

    game = Game()
    overall_start = time.monotonic()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    result_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "output", f"tournament_2v2_{timestamp}.txt")

    # 胜场统计: wins[(team_a_key, team_b_key)] = {A队: n, B队: n}
    wins: dict[tuple[str, str], dict[str, int]] = {}
    # 队伍总胜场
    team_total_wins: dict[str, int] = {}
    timeout_count = 0

    for pair_idx, (ta, tb) in enumerate(zip(teams_a, teams_b)):
        key_a = _team_key(ta)
        key_b = _team_key(tb)
        name_a = _team_name(ta)
        name_b = _team_name(tb)
        pair_key = (key_a, key_b)
        wins[pair_key] = {"A队": 0, "B队": 0}

        if key_a not in team_total_wins:
            team_total_wins[key_a] = 0
        if key_b not in team_total_wins:
            team_total_wins[key_b] = 0

        pair_start = time.monotonic()
        for m in range(MATCHES_PER_TEAM):
            # 交替左右位置，消除初始位置偏差
            if m % 2 == 0:
                winner = run_2v2_match(game, ta, tb)
                winner_side = "A队"
                loser_side = "B队"
            else:
                winner = run_2v2_match(game, tb, ta)
                winner_side = "B队"
                loser_side = "A队"

            if winner is None:
                timeout_count += 1
            elif winner == "A队":
                wins[pair_key][winner_side] += 1
                team_total_wins[key_a if winner_side == "A队" else key_b] += 1
            else:
                wins[pair_key][winner_side] += 1
                team_total_wins[key_b if winner_side == "B队" else key_a] += 1

            _reset_game(game)

        elapsed = time.monotonic() - pair_start
        a_wins = wins[pair_key]["A队"]
        b_wins = wins[pair_key]["B队"]
        done = (pair_idx + 1) / total_pairs * 100
        print(f"  [{pair_idx + 1:2d}/{total_pairs}] "
              f"A队({name_a}) vs B队({name_b})  "
              f"{a_wins:3d} : {b_wins:3d}  "
              f"(A队胜率 {a_wins/MATCHES_PER_TEAM*100:5.1f}%)  "
              f"耗时 {elapsed:.0f}s  [{done:3.0f}%]")

    overall_elapsed = time.monotonic() - overall_start

    # ── 写结果文件 ──
    lines = []
    lines.append("角斗场 2v2 循环赛结果")
    lines.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"队伍组合数: {total_pairs}  每对: {MATCHES_PER_TEAM} 场  超时: {timeout_count} 场")
    lines.append(f"总耗时: {overall_elapsed:.0f}s")
    lines.append("=" * 60)
    lines.append("")

    for (ka, kb), w in sorted(wins.items()):
        a_wins = w["A队"]
        b_wins = w["B队"]
        lines.append(f"  {ka}  vs  {kb}    {a_wins:3d} : {b_wins:3d}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("队伍总胜场排名")
    lines.append("-" * 30)
    rankings = sorted(team_total_wins.items(), key=lambda x: x[1], reverse=True)
    for rank, (team_key, total_w) in enumerate(rankings, 1):
        total_played = sum(1 for (ka, kb), w in wins.items()
                          if ka == team_key or kb == team_key) * MATCHES_PER_TEAM
        lines.append(f"  {rank}. {team_key}  {total_w:4d}/{total_played}  ({total_w/total_played*100:.1f}%)")

    with open(result_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    # JSON
    json_path = result_path.replace('.txt', '.json')
    json_data = {
        "timestamp": datetime.now().isoformat(),
        "matches_per_pair": MATCHES_PER_TEAM,
        "timeout_count": timeout_count,
        "total_team_combos": total_pairs,
        "wins": {f"{ka}_vs_{kb}": w for (ka, kb), w in wins.items()},
        "rankings": [{"team": k, "wins": v} for k, v in rankings],
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"2v2 循环赛完成！总耗时: {overall_elapsed:.0f}s")
    print(f"结果: {result_path}")
    print(f"JSON:  {json_path}")

    game.logger.close()


if __name__ == "__main__":
    main()
