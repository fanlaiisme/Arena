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


def run_headless_match(p1_char_id: str, p2_char_id: str) -> dict:
    """运行一场头渲染对局，返回比赛结果。

    Args:
        p1_char_id: 玩家1 的角色 id（对应 CharacterTemplate.id）
        p2_char_id: 玩家2 的角色 id

    Returns:
        dict with keys: winner, loser, winner_final_hp, loser_final_hp,
                        duration_frames, p1_char, p2_char
        超时时 winner 为 None。
    """
    # 找到角色索引
    p1_idx = next(i for i, c in enumerate(CHARACTERS) if c.id == p1_char_id)
    p2_idx = next(i for i, c in enumerate(CHARACTERS) if c.id == p2_char_id)

    game = Game()
    game.selection = [p1_idx, p2_idx]
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
                "frames": frame,
                "p1_char": p1_char_id,
                "p2_char": p2_char_id,
            }

    winner_char = game.winner
    loser_char = (game.player1.char.name if winner_char == game.player2.char.name
                  else game.player2.char.name)
    winner_hp = (game.player1.hp if winner_char == game.player1.char.name
                 else game.player2.hp)
    loser_hp = (game.player2.hp if winner_char == game.player1.char.name
                else game.player1.hp)

    game.logger.close()

    return {
        "winner": winner_char,
        "loser": loser_char,
        "winner_final_hp": winner_hp,
        "loser_final_hp": loser_hp,
        "duration_frames": frame,
        "p1_char": p1_char_id,
        "p2_char": p2_char_id,
    }
