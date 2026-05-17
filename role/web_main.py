"""FastAPI 应用 —— 游戏流程可视化仪表盘。

启动方式:
    cd /home/fanlai/Arena && .venv/bin/python role/web_main.py
    浏览器打开 http://localhost:8000
"""

import sys
import os
import asyncio
import threading
from pathlib import Path

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from role.visualizer import Visualizer
from role.main import run_experiment as _run_experiment

app = FastAPI(title="Arena 可视化仪表盘")

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_AVATAR_DIR = Path(__file__).parent / "data" / "Public" / "avatar"
_PLAYERS_DIR = Path(__file__).parent / "data" / "Public" / "players"

# 挂载头像静态目录
if _AVATAR_DIR.exists():
    app.mount("/avatars", StaticFiles(directory=str(_AVATAR_DIR)), name="avatars")
if _PLAYERS_DIR.exists():
    app.mount("/players", StaticFiles(directory=str(_PLAYERS_DIR)), name="players")

# 全局单例
_viz: Visualizer | None = None
_game_thread: threading.Thread | None = None


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """返回仪表盘 HTML 页面。"""
    html_path = _TEMPLATE_DIR / "dashboard.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>dashboard.html not found</h1>", status_code=404)


@app.get("/events")
async def events():
    """SSE 端点 —— 流式推送游戏事件到前端。"""
    global _viz
    if _viz is None:
        _viz = Visualizer()

    async def generate():
        async for sse_msg in _viz.event_stream():
            yield sse_msg

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.post("/start")
async def start_game(background_tasks: BackgroundTasks):
    """启动游戏后台线程。"""
    global _viz, _game_thread

    if _game_thread and _game_thread.is_alive():
        return {"status": "error", "msg": "游戏已在运行中"}

    if _viz is None:
        _viz = Visualizer()

    viz = _viz  # 捕获引用

    def _run():
        try:
            _run_experiment(visualizer=viz)
        except Exception as e:
            import traceback
            traceback.print_exc()
            viz.emit("error", {"msg": f"{type(e).__name__}: {e}"})

    _game_thread = threading.Thread(target=_run, daemon=True)
    _game_thread.start()

    return {"status": "ok", "msg": "游戏已启动"}


@app.post("/shutdown")
async def shutdown():
    """关闭服务器。"""
    import os as _os, signal as _signal
    _os.kill(_os.getpid(), _signal.SIGTERM)
    return {"status": "shutting_down"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/reflections", response_class=HTMLResponse)
async def reflections_page():
    """返回复盘数据展示页面。"""
    html_path = _TEMPLATE_DIR / "reflections.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>reflections.html not found</h1>", status_code=404)


@app.get("/api/reflections")
async def api_reflections():
    """返回已存储的每日复盘数据。"""
    global _viz
    if _viz is None:
        return JSONResponse({"days": {}, "game_over": False})
    return JSONResponse({
        "days": _viz.get_reflections(),
        "ranking_truth": _viz._ranking_truth,
        "game_over": _viz._game_over,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("role.web_main:app", host="0.0.0.0", port=8000, reload=False)
