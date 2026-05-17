"""可视化事件发射器 —— 线程安全的事件队列，供 FastAPI SSE 消费。"""

import asyncio
import json
import time


class Visualizer:
    """将游戏运行时事件推送到 asyncio.Queue，供 SSE 端点流式输出。

    使用方式：
      viz = Visualizer()
      # 在 run_experiment 中调用
      viz.emit("auction_show", {"char_name": "雷神", "char_id": "thor"})
      # 在 FastAPI 端点中消费
      async for event in viz.event_stream():
          yield event
    """

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._start_time = time.time()
        self._reflections: dict[int, dict] = {}  # {day: {player_name: {"text": ..., "opponent_chips": N}}}
        self._ranking_truth: list[dict] = []  # [{rank, name, char_id, win_rate}, ...]
        self._game_over = False

    def mark_game_over(self):
        self._game_over = True

    def set_ranking_truth(self, data: list[dict]):
        """设置完整胜率排名 ground truth。"""
        self._ranking_truth = data

    def store_reflection(self, day: int, player_key: str, text: str, opponent_chips: int | None = None):
        """存储每日复盘文本（线程安全）。"""
        if day not in self._reflections:
            self._reflections[day] = {}
        self._reflections[day][player_key] = {"text": text, "opponent_chips": opponent_chips}

    def get_reflections(self) -> dict:
        """获取所有已存储的复盘数据。"""
        return dict(self._reflections)

    def emit(self, event_type: str, data: dict | None = None):
        """线程安全地将事件推入队列。

        可从任意线程调用（如后台游戏线程）。
        """
        payload = json.dumps({
            "type": event_type,
            "data": data or {},
            "ts": round(time.time() - self._start_time, 2),
        }, ensure_ascii=False)
        # asyncio.Queue.put_nowait 是线程安全的
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # 丢弃旧事件，避免阻塞游戏线程

    async def event_stream(self):
        """异步生成器，逐条产出 SSE 格式的事件字符串。

        用法：
            async for sse_msg in viz.event_stream():
                yield sse_msg
        """
        while True:
            payload = await self._queue.get()
            yield f"data: {payload}\n\n"

    def emit_phase(self, phase: str, day: int, status: str = "start"):
        """快捷方法：发射阶段事件。"""
        self.emit("phase", {
            "phase": phase,
            "day": day,
            "status": status,
        })
