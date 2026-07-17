"""可视化事件发射器 —— 线程安全的事件队列，供 FastAPI SSE 消费。"""

import asyncio
import json
import re
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
        self._player_a_name: str | None = None  # 缓存用于新 SSE 连接重发
        self._player_b_name: str | None = None
        self._rules_summary: str | None = None
        self._game_started = False
        self._game_start_data: dict | None = None  # 完整 game_start 数据用于 catch-up
        # 人机对战 catch-up：记录当前等待事件，页面刷新时重发
        self._pending_wait_event: str | None = None
        self._pending_wait_data: dict | None = None
        # 替身模式：真实 char_id/name → 替身 id/name 的映射
        self._disguise_mapping: dict | None = None
        self._disguise_reverse_names: dict | None = None  # {real_name: disguise_name}
        self._disguise_reverse_ids: dict | None = None    # {real_id: disguise_id}

    def mark_game_over(self):
        self._game_over = True

    def set_disguise_mapping(self, mapping: dict):
        """设置替身映射。

        Args:
            mapping: {real_char_id: {"id": disguise_id, "name": disguise_name}, ...}
        """
        self._disguise_mapping = mapping
        # 构建逆向查找表
        from characters import CHARACTERS
        self._disguise_reverse_names = {}
        self._disguise_reverse_ids = {}
        for c in CHARACTERS:
            if c.id in mapping:
                self._disguise_reverse_ids[c.id] = mapping[c.id]["id"]
                self._disguise_reverse_names[c.name] = mapping[c.id]["name"]

    def _apply_disguise(self, data: dict) -> dict:
        """递归替换 data 中所有匹配的真实 char_id/name 为替身值。"""
        if not self._disguise_mapping:
            return data

        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                # 精确匹配 char_id
                if value in self._disguise_reverse_ids:
                    result[key] = self._disguise_reverse_ids[value]
                # 精确匹配 name
                elif value in self._disguise_reverse_names:
                    result[key] = self._disguise_reverse_names[value]
                else:
                    # 对文本内容（如 agent_message.content）做子串替换
                    v = value
                    for real_name, dis_name in self._disguise_reverse_names.items():
                        v = v.replace(real_name, dis_name)
                    for real_id, dis_id in self._disguise_reverse_ids.items():
                        v = v.replace(real_id, dis_id)
                    result[key] = v
            elif isinstance(value, dict):
                result[key] = self._apply_disguise(value)
            elif isinstance(value, list):
                result[key] = [
                    self._apply_disguise(item) if isinstance(item, dict) else
                    self._disguise_reverse_ids.get(item,
                        self._disguise_reverse_names.get(item, item))
                    if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

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
        d = data or {}
        # 替身模式：替换所有 SSE 事件中的真实名称和 ID
        if self._disguise_mapping:
            d = self._apply_disguise(d)
        # 缓存 game_start 信息，用于新 SSE 连接重发
        if event_type == "game_start":
            self._player_a_name = d.get("player_a")
            self._player_b_name = d.get("player_b")
            self._rules_summary = d.get("rules_summary")
            self._game_started = True
            self._game_start_data = dict(d)

        # 记录需要等待人类输入的事件，用于页面刷新恢复
        if event_type in ("awaiting_bid", "awaiting_deploy", "awaiting_confirm", "awaiting_summary"):
            self._pending_wait_event = event_type
            self._pending_wait_data = dict(d)

        payload = json.dumps({
            "type": event_type,
            "data": d,
            "ts": round(time.time() - self._start_time, 2),
        }, ensure_ascii=False)
        # asyncio.Queue.put_nowait 是线程安全的
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            print(f"  ⚠ [Visualizer] 队列已满，丢弃事件: {event_type}")
        else:
            if event_type.startswith("awaiting_"):
                print(f"  ✓ [Visualizer] 已发射 {event_type}: {json.dumps(d, ensure_ascii=False)[:120]}")

    def clear_pending_wait(self):
        """清除等待输入状态（人类已提交输入后调用）。"""
        self._pending_wait_event = None
        self._pending_wait_data = None

    async def event_stream(self):
        """异步生成器，逐条产出 SSE 格式的事件字符串。

        用法：
            async for sse_msg in viz.event_stream():
                yield sse_msg
        """
        # 立即发送连接确认，确保浏览器知道 SSE 已就绪
        yield ": connected\n\n"
        # 如果游戏已启动，补发 game_start 事件（处理页面刷新场景）
        if self._game_started and self._game_start_data:
            catchup = json.dumps({
                "type": "game_start",
                "data": self._game_start_data,
                "ts": round(time.time() - self._start_time, 2),
            }, ensure_ascii=False)
            yield f"data: {catchup}\n\n"
        # 如果当前正等待人类输入，补发等待事件（页面刷新恢复）
        if self._pending_wait_event and self._pending_wait_data:
            catchup = json.dumps({
                "type": self._pending_wait_event,
                "data": self._pending_wait_data,
                "ts": round(time.time() - self._start_time, 2),
            }, ensure_ascii=False)
            yield f"data: {catchup}\n\n"
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
