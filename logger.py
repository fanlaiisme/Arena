"""对局日志系统 —— 将每场对局信息以 JSON Lines 格式写入日志文件。"""

import json
import os
import time
from datetime import datetime, timezone


class MatchLogger:
    """记录一场或多场对局到单个日志文件。"""

    def __init__(self, output_dir: str):
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._session_id = timestamp
        self._match_index = 0

        filepath = os.path.join(output_dir, f"match_{timestamp}.log")
        self._file = open(filepath, "w", encoding="utf-8")
        self._filepath = filepath

        self._pending: dict | None = None  # 当前对局暂存数据

    def start_match(self, p1_char, p2_char):
        """对局开始时调用，记录双方角色信息。"""
        self._match_index += 1
        self._pending = {
            "session_id": self._session_id,
            "match_index": self._match_index,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "p1": {
                "character": p1_char.name,
                "character_id": p1_char.id,
            },
            "p2": {
                "character": p2_char.name,
                "character_id": p2_char.id,
            },
        }
        self._start_ts = time.monotonic()

    def end_match(self, winner_name: str, loser_name: str,
                  winner_hp: float, loser_hp: float):
        """对局结束时调用，写入一行 JSON 日志。"""
        if self._pending is None:
            return

        duration = time.monotonic() - self._start_ts

        self._pending["end_time"] = datetime.now(timezone.utc).isoformat()
        self._pending["duration_seconds"] = round(duration, 2)
        self._pending["winner"] = winner_name
        self._pending["loser"] = loser_name

        # Fill in final HP
        if self._pending["p1"]["character"] == winner_name:
            self._pending["p1"]["final_hp"] = winner_hp
            self._pending["p2"]["final_hp"] = loser_hp
        else:
            self._pending["p1"]["final_hp"] = loser_hp
            self._pending["p2"]["final_hp"] = winner_hp

        self._file.write(json.dumps(self._pending, ensure_ascii=False) + "\n")
        self._file.flush()
        self._pending = None

    def close(self):
        """关闭日志文件。"""
        self._file.close()
