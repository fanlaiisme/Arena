"""头渲染比赛运行器 —— 实际启动 Arena 游戏，返回胜负结果。

复用 test/ 脚本的无头渲染模式。必须在 import pygame 之前设置
SDL_VIDEODRIVER=dummy，否则会尝试打开图形窗口。
"""

import os
import sys

# 必须在 import pygame 之前设置
os.environ['SDL_VIDEODRIVER'] = 'dummy'

# 确保能导入 Arena 根目录的 main 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame
from main import Game, CHARACTERS, FPS

TIMEOUT_FRAMES = 7200  # 120s 等效帧数（60fps）


def run_headless_match(char_ids: list[str]) -> dict:
    """运行一场头渲染对局，返回比赛结果。

    Args:
        char_ids: 角色 id 列表（2个=1v1, 4个=2v2）

    Returns:
        dict with keys: winner, mode, duration_frames, char_ids
        超时时 winner 为 None。
    """
    if len(char_ids) not in (2, 4):
        raise ValueError(f"char_ids must have 2 or 4 elements, got {len(char_ids)}")

    # 找到角色索引
    indices = [next(i for i, c in enumerate(CHARACTERS) if c.id == cid) for cid in char_ids]

    game = Game()
    game.mode = "1v1" if len(char_ids) == 2 else "2v2"
    game.selection = indices
    game.start_match()
    dt = 1.0 / FPS

    frame = 0
    while not game.game_over:
        pygame.event.pump()
        game._update_fighting(dt)
        frame += 1
        if frame >= TIMEOUT_FRAMES:
            game.logger.close()
            return {
                "winner": None,
                "reason": "timeout",
                "duration_frames": frame,
                "mode": game.mode,
                "char_ids": char_ids,
            }

    game.logger.close()

    # 提取胜/败方 HP（1v1 和 2v2 均适用）
    if game.mode == "1v1":
        winner_player = next((p for p in game.players if p.alive), None)
        loser_player = next((p for p in game.players if not p.alive), None)
        winner_hp = winner_player.hp if winner_player else 0
        loser_hp = loser_player.hp if loser_player else 0
    else:
        # 2v2: 存活队伍 vs 全灭队伍
        team_a_alive = [p for p in game.players if p.team == 0 and p.alive]
        team_b_alive = [p for p in game.players if p.team == 1 and p.alive]
        winning_team = team_a_alive if team_a_alive else team_b_alive
        losing_team = team_b_alive if team_a_alive else team_a_alive
        winner_hp = round(sum(p.hp for p in winning_team), 1)
        loser_hp = round(sum(p.hp for p in losing_team), 1)

    return {
        "winner": game.winner,
        "mode": game.mode,
        "duration_frames": frame,
        "char_ids": char_ids,
        "winner_final_hp": winner_hp,
        "loser_final_hp": loser_hp,
    }
