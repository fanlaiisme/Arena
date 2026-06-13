"""世界可视化面板 — FastAPI + WebSocket + Three.js 3D 地图。

启动方式:
    .venv/bin/python world/web_main.py
    浏览器打开 http://localhost:8001
"""

import sys
import os
import asyncio
import threading
import time
import random
import json
from pathlib import Path

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from world import World, build_map_data
from world.agents.base import WorldAgent
from world.time import Phase

# ===== App =====

app = FastAPI(title="虚拟世界 3D 可视化")

_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# WebSocket 连接管理 + 消息队列
_ws_connections: set[WebSocket] = set()
_ws_lock = asyncio.Lock()
_ws_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
_ws_start_time = 0.0

_world_thread: threading.Thread | None = None
_running = False

# ===== 智能体预设 =====

AGENT_PRESETS = [
    WorldAgent(name="张铁柱", gender="男", age=35,
               personality="勤劳朴实的农民，日出而作日落而息",
               goal="经营好农场，养活一家人", cash=500, food=30),
    WorldAgent(name="李富贵", gender="男", age=42,
               personality="精明的商人，嗅觉敏锐，善于发现机会",
               goal="通过各种手段积累财富", cash=1500, food=20),
    WorldAgent(name="陈剑豪", gender="男", age=28,
               personality="热血自信的角斗士，渴望在竞技场扬名立万",
               goal="在竞技场击败所有对手", cash=800, food=15),
    WorldAgent(name="王美琳", gender="女", age=26,
               personality="聪慧沉静的观察者，喜欢在酒馆收集情报",
               goal="掌握这个世界的一切信息", cash=1000, food=25),
]

PLACE_NAMES = ["居民A区", "居民B区", "农场", "银行", "酒馆", "Bob竞技场",
               "商场", "公园", "诊所", "餐厅", "市政厅", "办公大楼", "法庭", "监狱"]


# ===== WebSocket 广播 =====

def emit_threadsafe(event_type: str, data: dict):
    """从仿真线程安全地向队列推送事件。"""
    payload = json.dumps({
        "type": event_type, "data": data,
        "ts": time.time() - _ws_start_time,
    }, ensure_ascii=False)
    try:
        _ws_queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass  # 队列满时丢弃（后端比前端快）


async def _broadcast_worker():
    """后台任务：从队列取事件，广播到所有 WebSocket 连接。"""
    global _ws_connections
    while True:
        payload = await _ws_queue.get()
        async with _ws_lock:
            if not _ws_connections:
                continue
            dead: set[WebSocket] = set()
            for ws in list(_ws_connections):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.add(ws)
            _ws_connections -= dead


# ===== 路由 =====

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = _STATIC_DIR / "map_3d.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>map_3d.html not found</h1>", status_code=404)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _ws_start_time
    await websocket.accept()
    if _ws_start_time == 0:
        _ws_start_time = time.time()

    # 发送连接确认
    await websocket.send_text(json.dumps({
        "type": "connected", "data": {}, "ts": 0,
    }, ensure_ascii=False))
    # 发送地图初始化数据（道路图 + 建筑坐标，后端唯一定义）
    await websocket.send_text(json.dumps({
        "type": "init_map", "data": build_map_data(), "ts": 0,
    }, ensure_ascii=False))

    # 注册
    async with _ws_lock:
        _ws_connections.add(websocket)

    try:
        while True:
            # 接收客户端消息（保活用）
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _ws_lock:
            _ws_connections.discard(websocket)


_broadcast_started = False


@app.post("/start")
async def start_simulation():
    global _world_thread, _running, _broadcast_started

    if _world_thread and _world_thread.is_alive():
        return {"status": "error", "msg": "模拟已在运行中"}

    if not _broadcast_started:
        asyncio.create_task(_broadcast_worker())
        _broadcast_started = True

    _running = True

    def _run():
        w = World.create_default()
        for agent in AGENT_PRESETS:
            w.add_agent(agent)

        emit_threadsafe("world_state", _build_state(w))
        time.sleep(0.5)

        TICK_INTERVAL = 0.8

        while _running:
            for agent in w.agents.values():
                if not agent.is_busy:
                    _agent_random_action(w, agent)

            events = w.step()
            for e in events:
                emit_threadsafe("log", {"msg": e})

            emit_threadsafe("world_state", _build_state(w))

            if w.time.day > 5:
                emit_threadsafe("game_over", {"msg": f"模拟结束，共 {w.time.day - 1} 天"})
                break

            time.sleep(TICK_INTERVAL)

        emit_threadsafe("game_over", {"msg": "模拟已停止"})

    _world_thread = threading.Thread(target=_run, daemon=True)
    _world_thread.start()
    return {"status": "ok", "msg": "模拟已启动"}


@app.post("/stop")
async def stop_simulation():
    global _running
    _running = False
    return {"status": "ok", "msg": "正在停止..."}


@app.get("/api/state")
async def get_state():
    return JSONResponse({"status": "running" if _running else "idle"})


@app.get("/health")
async def health():
    return {"status": "ok"}


# ===== 智能体随机行为 =====

_MOVE_COOLDOWN: dict[str, str] = {}


def _agent_random_action(w: World, agent: WorldAgent):
    # 嫌疑值太高 → 去法庭自首
    if agent.suspicion > 80 and not agent.confined and agent.location:
        if agent.location.name == "法庭":
            pass  # 已经在法庭，_place_action 会处理
        else:
            _try_move(w, agent, "法庭")
            return

    # 健康太低 → 优先去诊所
    if agent.health < 40 and agent.cash >= 50 and agent.location:
        if agent.location.name == "诊所":
            pass
        else:
            _try_move(w, agent, "诊所")
            return

    if agent.energy < 25 and not agent.sleeping and agent.location:
        home_name = agent.location.name
        if home_name in ("居民A区", "居民B区"):
            agent.sleep()
            emit_threadsafe("agent_state", {"agent": agent.name, "state": "sleeping"})
            return
        else:
            _try_move(w, agent, random.choice(["居民A区", "居民B区"]))
            return

    if agent.hunger < 25 and agent.food >= 5:
        agent.start_eating(5)
        emit_threadsafe("agent_state", {"agent": agent.name, "state": "eating"})
        return

    if agent.food < 10 and agent.cash >= 30 and agent.location:
        r = w.buy_food(agent.name, 10)
        emit_threadsafe("log", {"msg": r})
        return

    loc_name = agent.location.name if agent.location else None
    if loc_name:
        last_action = _MOVE_COOLDOWN.get(agent.name, "")
        if last_action != loc_name:
            _MOVE_COOLDOWN[agent.name] = loc_name
            _place_action(w, agent)
            return

    if loc_name and random.random() < 0.4:
        others = [p for p in PLACE_NAMES if p != loc_name]
        _try_move(w, agent, random.choice(others))
    else:
        _place_action(w, agent)


def _try_move(w: World, agent: WorldAgent, target: str):
    old = agent.location.name if agent.location else "无"
    result = w.agent_move(agent.name, target)
    if "离开" in result:
        emit_threadsafe("agent_move", {"agent": agent.name, "from": old, "to": target})


def _place_action(w: World, agent: WorldAgent):
    loc_name = agent.location.name if agent.location else ""

    if loc_name == "农场":
        farm = w.get_place("农场")
        status = farm.get_crop_status(agent.name)
        if "已成熟" in status:
            food, msg = farm.harvest(agent.name)
            agent.start_work(w.WORK_TICKS.get("harvest", 10), "收割作物")
            emit_threadsafe("log", {"msg": msg})
        elif "没有" in status and agent.cash >= farm.seed_price:
            farm.plant(agent.name)
            agent.cash -= farm.seed_price
            agent.start_work(w.WORK_TICKS.get("plant", 10), "播种")
            emit_threadsafe("log", {"msg": f"{agent.name} 播种，花费 {farm.seed_price} 金币"})
        else:
            _stand_idle(agent)

    elif loc_name == "银行":
        bank = w.get_place("银行")
        balance = bank.get_balance(agent.name)
        if balance == 0 and agent.cash > 200:
            amt = min(random.choice([100, 200, 300]), agent.cash)
            bank.deposit(agent.name, amt)
            agent.cash -= amt
            agent.start_work(w.WORK_TICKS.get("bank", 5), "办理存款")
            emit_threadsafe("log", {"msg": f"{agent.name} 存入 {amt} 金币"})
        elif balance > 0 and agent.cash < 100:
            amt = random.choice([50, 100])
            got, _ = bank.withdraw(agent.name, amt)
            agent.cash += got
            if got > 0:
                agent.start_work(w.WORK_TICKS.get("bank", 5), "办理取款")
                emit_threadsafe("log", {"msg": f"{agent.name} 取出 {got} 金币"})
        else:
            _stand_idle(agent)

    elif loc_name == "酒馆":
        tavern = w.get_place("酒馆")
        if random.random() < 0.5:
            messages = ["有人要打一场吗？", "最近竞技场有什么新闻？", "谁想合作赚钱？", "今天天气不错！"]
            tavern.post_message(agent.name, random.choice(messages))
            agent.start_work(w.WORK_TICKS.get("tavern_chat", 8), "在酒馆聊天")
            agent.happiness = min(100, agent.happiness + 3)
            emit_threadsafe("log", {"msg": f"{agent.name} 在酒馆与人交谈"})
        else:
            _stand_idle(agent)

    elif loc_name == "Bob竞技场":
        agent.start_work(w.WORK_TICKS.get("tavern_chat", 8), "观看比赛")
        agent.happiness = min(100, agent.happiness + 2)
        emit_threadsafe("log", {"msg": f"{agent.name} 在竞技场观看比赛"})

    elif loc_name in ("居民A区", "居民B区"):
        if agent.energy < 40:
            agent.sleep()
            emit_threadsafe("agent_state", {"agent": agent.name, "state": "sleeping"})
        else:
            _stand_idle(agent)

    elif loc_name == "商场":
        mall = w.get_place("商场")
        if agent.food < 20 and agent.cash >= mall.food_price * 3:
            amt, spent, _ = mall.buy(agent.name, agent.cash, random.randint(5, 15))
            if amt > 0:
                agent.cash -= spent
                agent.food += amt
                agent.start_work(6, "在商场购物")
                emit_threadsafe("log", {"msg": f"{agent.name} 在商场买了 {amt} 食物，花费 {spent}"})
            else:
                _stand_idle(agent)
        elif agent.food > 30 and random.random() < 0.5:
            amt = random.randint(10, 20)
            actual = min(amt, agent.food)
            earned, _ = mall.sell_food(agent.name, actual)
            agent.cash += earned
            agent.food -= actual
            agent.start_work(5, "卖食物给商场")
            emit_threadsafe("log", {"msg": f"{agent.name} 在商场卖了 {actual} 食物，获得 {earned}"})
        else:
            _stand_idle(agent)

    elif loc_name == "公园":
        park = w.get_place("公园")
        if agent.energy < 70 or agent.health < 80:
            agent.energy = min(100, agent.energy + park.rest_energy * 10)
            agent.health = min(100, agent.health + park.rest_health * 10)
            agent.start_work(8, "在公园休息")
            agent.happiness = min(100, agent.happiness + 4)
            emit_threadsafe("log", {"msg": f"{agent.name} 在公园休息，恢复精力和健康"})
        else:
            agent.start_work(random.randint(3, 6), "在公园散步")
            agent.happiness = min(100, agent.happiness + 2)
            emit_threadsafe("log", {"msg": f"{agent.name} 在公园散步"})

    elif loc_name == "诊所":
        clinic = w.get_place("诊所")
        if (agent.energy < 60 or agent.health < 60) and agent.cash >= clinic.heal_price:
            spent, healed_energy, healed_health, msg = clinic.heal(agent.name, agent.cash)
            if spent > 0:
                agent.cash -= spent
                agent.energy = min(100, agent.energy + healed_energy)
                agent.health = min(100, agent.health + healed_health)
                agent.start_work(8, "接受治疗")
                emit_threadsafe("log", {"msg": msg})
            else:
                _stand_idle(agent)
        else:
            _stand_idle(agent)

    elif loc_name == "餐厅":
        restaurant = w.get_place("餐厅")
        if agent.hunger < 60 and agent.cash >= restaurant.meal_price:
            spent, hunger_restored, msg = restaurant.dine(agent.name, agent.cash)
            if spent > 0:
                agent.cash -= spent
                agent.hunger = min(100, agent.hunger + hunger_restored)
                agent.start_work(8, "在餐厅用餐")
                agent.happiness = min(100, agent.happiness + 5)
                emit_threadsafe("log", {"msg": msg})
            else:
                _stand_idle(agent)
        else:
            agent.start_work(random.randint(3, 5), "在餐厅小坐")
            emit_threadsafe("log", {"msg": f"{agent.name} 在餐厅小坐"})

    elif loc_name == "市政厅":
        cityhall = w.get_place("市政厅")
        if random.random() < 0.4:
            cityhall.read_announcements()
            agent.start_work(5, "查看公告")
            emit_threadsafe("log", {"msg": f"{agent.name} 在市政厅查看公告"})
        else:
            tax, msg = cityhall.collect_tax(agent.name, agent.cash)
            agent.cash -= tax
            agent.start_work(5, "缴纳税金")
            agent.happiness = max(0, agent.happiness - 2)
            emit_threadsafe("log", {"msg": msg})
            if random.random() < 0.2:
                announcements = [
                    "下月将举办丰收节庆典！",
                    "请居民注意防火安全。",
                    "新税法已通过，税率维持不变。",
                    "竞技场冠军将获得额外奖金！",
                ]
                cityhall.post_announcement(random.choice(announcements))

    elif loc_name == "办公大楼":
        office = w.get_place("办公大楼")
        earned, msg = office.work(agent.name)
        agent.cash += earned
        agent.start_work(10, "上班工作")
        agent.happiness = min(100, agent.happiness + 3)
        emit_threadsafe("log", {"msg": msg})

    elif loc_name == "法庭":
        court = w.get_place("法庭")
        result = court.trial(agent.name, agent.cash)
        agent.suspicion = 0  # 审判后清零
        if result["verdict"] == "fine":
            agent.cash -= result["fine_amount"]
            agent.start_work(8, "接受审判")
            agent.happiness = max(0, agent.happiness - 4)
        elif result["verdict"] == "prison":
            prison = w.get_place("监狱")
            ticks = result["prison_ticks"]
            prison.imprison(agent.name, ticks, w.time.tick)
            agent.confined = True
            agent.work_ticks = ticks  # 用 work_ticks 倒计时
            agent.happiness = max(0, agent.happiness - 8)
            emit_threadsafe("agent_state", {"agent": agent.name, "state": "imprisoned"})
        else:
            agent.start_work(5, "接受审判")
        emit_threadsafe("log", {"msg": result["msg"]})

    elif loc_name == "监狱":
        prison = w.get_place("监狱")
        if agent.confined:
            # 检查是否已刑满 (work_ticks 倒计时已归零)
            if agent.work_ticks <= 0:
                msg = prison.release(agent.name)
                agent.confined = False
                emit_threadsafe("log", {"msg": msg})
            else:
                pass  # 仍在服刑，tick_physiology 会倒计时
        else:
            _stand_idle(agent)

    else:
        _stand_idle(agent)


def _stand_idle(agent: WorldAgent):
    agent.start_work(random.randint(2, 4), "发呆")
    agent.happiness = max(0, agent.happiness - 1)


# ===== 世界状态构建 =====

def _build_state(w: World) -> dict:
    agents_data = []
    for a in w.agents.values():
        data = {
            "name": a.name,
            "cash": a.cash,
            "food": a.food,
            "hunger": round(a.hunger, 0),
            "energy": round(a.energy, 0),
            "health": round(a.health, 0),
            "happiness": round(a.happiness, 0),
            "suspicion": round(a.suspicion, 0),
            "confined": a.confined,
            "sleeping": a.sleeping,
            "eating": a.eating,
            "travelling": a.travelling,
            "work_ticks": a.work_ticks,
            "busy_reason": a.busy_reason,
            "gender": a.gender,
            "age": a.age,
            "goal": a.goal,
        }
        if a.travelling:
            data["location"] = None
            data["travel_from"] = a.travel_from
            data["travel_to"] = a.travel_to
            data["travel_progress"] = round(a.travel_progress, 2)
        else:
            data["location"] = a.location.name if a.location else "路上"
        agents_data.append(data)

    return {
        "tick": w.time.tick,
        "day": w.time.day,
        "phase": w.time.phase.label,
        "phase_id": int(w.time.phase),
        "tick_in_day": w.time.tick_in_day,
        "description": w.time.describe(),
        "agents": agents_data,
    }


# ===== 入口 =====

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("world.web_main:app", host="0.0.0.0", port=8001, reload=False)
