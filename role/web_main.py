"""FastAPI 应用 —— 游戏流程可视化仪表盘。

启动方式:
    cd /home/fanlai/Arena && .venv/bin/python role/web_main.py
    浏览器打开 http://localhost:8000
"""

import os

# 必须在任何导入 pygame 的模块之前设置，避免在服务器环境中尝试打开图形窗口
os.environ['SDL_VIDEODRIVER'] = 'dummy'

import sys
import json
import asyncio
import threading
from pathlib import Path

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from fastapi import FastAPI, Form, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from role.visualizer import Visualizer
from role.main import run_experiment as _run_experiment
from role.human_sync import HumanInputState

app = FastAPI(title="Arena 可视化仪表盘", docs_url=None, redoc_url=None, openapi_url=None)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_AVATAR_DIR = Path(__file__).parent / "data" / "Public" / "avatar"
_PLAYERS_DIR = Path(__file__).parent / "data" / "Public" / "players"
_TUTORIAL_DIR = Path(__file__).parent / "data" / "Public" / "tutorial"
_AUDIO_DIR = Path(__file__).parent / "audio"
_ALIASES_PATH = Path(__file__).parent / "data" / "disguise" / "aliases.json"

# 挂载静态目录
if _AVATAR_DIR.exists():
    app.mount("/avatars", StaticFiles(directory=str(_AVATAR_DIR)), name="avatars")
if _PLAYERS_DIR.exists():
    app.mount("/players", StaticFiles(directory=str(_PLAYERS_DIR)), name="players")
if _TUTORIAL_DIR.exists():
    app.mount("/tutorial", StaticFiles(directory=str(_TUTORIAL_DIR)), name="tutorial")
if _AUDIO_DIR.exists():
    app.mount("/audio", StaticFiles(directory=str(_AUDIO_DIR)), name="audio")

# 全局单例
_viz: Visualizer | None = None
_game_thread: threading.Thread | None = None
_human_sync: HumanInputState | None = None


# ═══════════════════════════════════════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def landing():
    """入口页面 —— 观战模式 vs 人机对战。"""
    html_path = _TEMPLATE_DIR / "landing.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>landing.html not found</h1>", status_code=404)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """观战模式仪表盘（原 AI vs AI 只读面板）。"""
    html_path = _TEMPLATE_DIR / "dashboard.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>dashboard.html not found</h1>", status_code=404)


@app.get("/play", response_class=HTMLResponse)
async def play_page():
    """人机对战页面。"""
    html_path = _TEMPLATE_DIR / "play.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>play.html not found</h1>", status_code=404)


@app.get("/rule-ref", response_class=HTMLResponse)
async def rule_ref():
    """游戏内规则参考独立页面（跳转查看详细规则）。"""
    html_path = _TEMPLATE_DIR / "rule-ref.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>rule-ref.html not found</h1>", status_code=404)


# ═══════════════════════════════════════════════════════════════════════════
# SSE 端点
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# 游戏控制
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/start")
async def start_game(mode: str = "aivai", disguise: str = "0"):
    """启动游戏后台线程。

    Args:
        mode: "aivai" = AI vs AI 观战, "play" = 人机对战
        disguise: "1" = 启用替身模式（仅人机对战有效）
    """
    global _viz, _game_thread, _human_sync

    if _game_thread and _game_thread.is_alive():
        return {"status": "error", "msg": "游戏已在运行中"}

    if _viz is None:
        _viz = Visualizer()

    viz = _viz  # 捕获引用

    # 替身模式：加载预设替身数据，随机生成映射
    disguise_mapping = None
    if disguise == "1":
        import json as _json, random as _random
        if _ALIASES_PATH.exists():
            with open(_ALIASES_PATH, "r", encoding="utf-8") as _f:
                aliases = _json.load(_f)
            # 收集 20 个真实 char_id，随机配对
            from characters import CHARACTERS
            real_ids = [c.id for c in CHARACTERS]
            shuffled = _random.sample(aliases, len(aliases))
            disguise_mapping = {}
            for real_id, alias in zip(real_ids, shuffled):
                disguise_mapping[real_id] = {"id": alias["id"], "name": alias["name"]}

    if mode == "play":
        _human_sync = HumanInputState()
        from role.main import run_human_vs_ai_experiment as _run_human
        sync = _human_sync

        def _run():
            try:
                _run_human(visualizer=viz, human_sync=sync,
                           disguise_mapping=disguise_mapping)
            except Exception as e:
                import traceback
                traceback.print_exc()
                viz.emit("error", {"msg": f"{type(e).__name__}: {e}"})
    else:
        _human_sync = None

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


@app.api_route("/reset", methods=["GET", "POST"])
async def reset_game():
    """重置游戏状态，允许重新开始（无需重启服务器）。"""
    global _viz, _game_thread, _human_sync
    _game_thread = None
    _human_sync = None
    _viz = Visualizer()
    return {"status": "ok", "msg": "游戏状态已重置，可以重新开始"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# 人机对战 API 端点
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/bid")
async def api_bid(bid: int = Form(...)):
    """人类提交拍卖出价。"""
    global _human_sync
    if _human_sync is None or _human_sync.waiting_for != "bid":
        return {"status": "error", "msg": "当前不在等待出价状态"}
    _human_sync.human_bid = bid
    _human_sync.bid_event.set()
    return {"status": "ok"}


@app.post("/api/deploy")
async def api_deploy(deployments: str = Form(...)):
    """人类提交部署。deployments 为 JSON 字符串如 {"1":"snowman","2":"thor"}。"""
    global _human_sync
    if _human_sync is None or _human_sync.waiting_for != "deploy":
        return {"status": "error", "msg": "当前不在等待部署状态"}
    try:
        deploy_dict = {int(k): v for k, v in json.loads(deployments).items()}
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        return {"status": "error", "msg": f"JSON 解析失败: {e}"}
    _human_sync.human_deployments = deploy_dict
    _human_sync.deploy_event.set()
    return {"status": "ok"}


@app.post("/api/confirm")
async def api_confirm():
    """人类确认继续（预览/规则/分析/反思阶段）。"""
    global _human_sync
    if _human_sync is None or _human_sync.waiting_for != "confirm":
        return {"status": "error", "msg": "当前不在等待确认状态"}
    _human_sync.confirm_event.set()
    return {"status": "ok"}


@app.post("/api/summary")
async def api_summary(ranking_table: str = Form(""), chip_estimate: str = Form("")):
    """人类提交每日复盘（匿名排名表 + 对手币量估算）。"""
    global _human_sync
    if _human_sync is None or _human_sync.waiting_for != "summary":
        return {"status": "error", "msg": "当前不在等待复盘状态"}
    _human_sync.ranking_table = ranking_table
    _human_sync.chip_estimate = chip_estimate
    _human_sync.summary_event.set()
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# 复盘页面（不变）
# ═══════════════════════════════════════════════════════════════════════════

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
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("role.web_main:app", host="0.0.0.0", port=port,
                reload=False, access_log=False)
