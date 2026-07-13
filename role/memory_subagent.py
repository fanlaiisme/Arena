"""MemorySubagent —— 后台渐进式记忆提取器。

每个 AI 玩家对应一个 MemorySubagent 实例。
每次玩家产出完整输出后，submit() 非阻塞地提交给 subagent 处理。
Subagent 通过独立 API 调用（无状态），使用 read_memory / edit_memory 工具维护记忆文件。
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from openai import OpenAI

from .memory_tools import list_memory_files, read_memory, edit_memory, set_memory_base_dir, clear_read_tracking
from .config import MEMORY_MODEL_NAME, create_memory_client


# ── Subagent 系统提示词 ─────────────────────────────────────────────────────────

SYSTEM_PROMPT_MEMORY = """你是 {player_name} 的记忆管家。你的任务是渐进式地维护三个记忆文件，
从玩家的思考输出中提取关键信息，写入 markdown 格式的记忆文档。

你的记忆目录：{memory_dir}/
包含以下文件：

1. day{day}.md              — 每日笔记（当天概述、教训、明日策略调整）
2. opponent_model.md        — 对手模型（出价模式、部署偏好、关键观察，跨天累积）
3. gladiator_knowledge.md   — 角斗士认知（胜率排名推测、实战表现记录，跨天累积）

工作流程：
1. 每次收到新内容时，**首先调用 list_memory_files()** 查看所有文件的 frontmatter 元信息
2. 根据 frontmatter 中的 name、description、type 字段判断哪些文件与当前内容相关
3. 用 read_memory 读取相关文件的完整内容
4. 用 edit_memory 精确修改对应章节
5. 如果新内容没有增量信息（如纯粹的规则复述、确认收到等），不做任何修改

⚠️ **强制规则：在调用 edit_memory 之前，必须先调用 read_memory 读取同一个文件。**
   系统会拒绝未读先改的操作。这是为了确保 old_str 精确匹配文件原文。

各文件的章节结构和更新规则：

【day{day}.md】—— 每日笔记
章节：
  ## 当天概述
  ## 教训
  ## 对手观察
  ## 角斗士认知更新
  ## 明日策略调整

更新规则：
- "当天概述"：记录当天的拍卖结果、比赛胜负、point转移等关键事件
- "教训"：玩家自己明确总结的经验教训（如"把强角斗士放第2局是正确的"）
- "对手观察"：对对手行为的即时观察（不同于 opponent_model 的长期模式）
- "角斗士认知更新"：某角斗士在实战中的表现
- "明日策略调整"：玩家提到面向明天的策略意图

【opponent_model.md】—— 对手模型（跨天累积）
章节：
  ## 出价模式
  ## 部署模式
  ## 关键观察

更新规则：
- "出价模式"：更新对手的出价区间、激进程度、弃权率等模式化信息
  格式: - 激进程度: high/medium/low
        - 偏好出价区间: N~M
        - 弃权率: X%
- "部署模式"：更新对手的部署策略偏好
  格式: - 第2局策略: strongest/weakest/balanced
        - 疲劳管理: aggressive/conservative
- "关键观察"：追加新的观察条目，标注天数
  格式: - (dayN) 观察内容

【gladiator_knowledge.md】—— 角斗士认知（跨天累积）
章节：
  ## 胜率排名推测
  ## 实战表现记录

更新规则：
- "胜率排名推测"：更新表格行，记录玩家对匿名排名表中某胜率对应哪个角斗士的推测
  表格格式: | 排名 | 胜率 | 推测角色 | 置信度 | 依据 |
- "实战表现记录"：更新表格行，记录角斗士在比赛中的表现
  表格格式: | 角斗士 | 出场次数 | 胜场 | 印象 |

标签说明：
每次收到的内容都有一个标签，表示这是哪个阶段的输出：
- rules_interpretation：规则解读
- auction_round{{N}}：第N轮拍卖出价思考
- post_auction_analysis：拍卖后分析
- deploy_match1 / deploy_match23：部署分析
- reflect_match1：第1局反思
- day_summary：全天复盘（信息量最大）

重要原则：
- 保持描述简洁，每条不超过一句话
- 宁可漏记，不要编造
- 如果玩家的输出中没有实质内容（如纯格式性回复），不要强行写入
- edit_memory 的 old_str 必须精确匹配文件中的原文，包括空格和换行"""


# ── MemorySubagent 类 ───────────────────────────────────────────────────────────

class MemorySubagent:
    """后台渐进式记忆提取器。

    每次 submit() 发起一次独立的 API 调用，不保留对话历史。
    通过内部 ThreadPoolExecutor(max_workers=1) 串行处理同一玩家的记忆更新。
    """

    def __init__(self, player_name: str, memory_dir: str, day: int,
                 client: OpenAI | None = None):
        self.player_name = player_name
        self.memory_dir = Path(memory_dir)
        self.day = day
        self.client = client or create_memory_client()

        # 单线程执行器，保证同一玩家的记忆更新串行
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"mem-{player_name}")
        self._futures: list = []
        self._lock = threading.Lock()

        # 设置工具可访问的全局记忆目录
        set_memory_base_dir(str(self.memory_dir))

        # 构建系统提示词
        self.system_prompt = SYSTEM_PROMPT_MEMORY.format(
            player_name=player_name,
            memory_dir=str(self.memory_dir),
            day=day,
        )

        # 工具列表（LangChain @tool 转为 OpenAI function calling 格式）
        self.tools = [list_memory_files, read_memory, edit_memory]
        self._openai_tools = [_convert_tool(t) for t in self.tools]

        # 操作日志文件
        self._log_dir = Path(memory_dir).parent / "memory_logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        self._log_path = self._log_dir / f"{player_name}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        self._log_file = open(self._log_path, "w", encoding="utf-8")
        self._write_log("init", f"记忆 subagent 启动，day={day}，目录={memory_dir}")

    def _write_log(self, event: str, detail: str = ""):
        """写入一条操作日志（线程安全）。"""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] {event}"
        if detail:
            line += f" | {detail}"
        with self._lock:
            self._log_file.write(line + "\n")
            self._log_file.flush()

    def set_day(self, day: int):
        """更新当前天数（每天开始时调用）。"""
        self.day = day
        self.system_prompt = SYSTEM_PROMPT_MEMORY.format(
            player_name=self.player_name,
            memory_dir=str(self.memory_dir),
            day=day,
        )

    def submit(self, label: str, content: str):
        """非阻塞提交一段玩家输出。

        立即返回，后台异步处理。不阻碍游戏进程。

        Args:
            label: 阶段标签（如 "auction_round1"、"day_summary" 等）
            content: 玩家的完整输出文本
        """
        if not content or not content.strip():
            return
        self._write_log("submit", f"label={label}, len={len(content)}")
        with self._lock:
            f = self._executor.submit(self._process, label, content)
            self._futures.append(f)

    def wait_all(self):
        """阻塞直到所有已提交的记忆提取任务完成。"""
        with self._lock:
            futures = list(self._futures)
        for f in futures:
            try:
                f.result()
            except Exception as e:
                print(f"  [MemorySubagent:{self.player_name}] 任务出错: {e}")
        with self._lock:
            self._futures.clear()

    def _process(self, label: str, content: str):
        """单次独立 API 调用，带工具调用循环。

        不保存对话历史——每次都是全新的上下文。
        在同一 subagent 的线程中，重置线程局部存储确保路径隔离。
        """
        set_memory_base_dir(str(self.memory_dir))  # 线程安全：设置本线程的 memory_dir
        clear_read_tracking()  # 每轮重置 read-before-edit 跟踪
        self._write_log("process_start", f"label={label}")

        user_msg = (
            f"[标签: {label}]\n\n"
            f"以下是 {self.player_name} 在「{label}」阶段的思考输出：\n\n"
            f"{content[:6000]}\n\n"
            f"请分析以上内容，判断是否需要更新记忆文件。"
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_msg},
        ]

        max_iterations = 3
        for iteration in range(max_iterations):
            kwargs = {
                "model": MEMORY_MODEL_NAME,
                "messages": messages,
                "tools": self._openai_tools,
            }
            response = self.client.chat.completions.create(**kwargs)
            msg = response.choices[0].message

            if not msg.tool_calls:
                # 无工具调用 → subagent 决定不修改
                self._write_log("no_action", f"iteration={iteration+1}, reply={msg.content if msg.content else '(空)'}")
                return

            # 追加 assistant 消息
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # 执行工具并追加结果
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_args = tc.function.arguments
                self._write_log("tool_call", f"iteration={iteration+1}, tool={tool_name}, args={tool_args}")
                tool_result = self._execute_tool(tool_name, tool_args)
                self._write_log("tool_result", f"result={tool_result}")
                messages.append({
                    "role": "tool",
                    "content": tool_result,
                    "tool_call_id": tc.id,
                })

        # 超过最大迭代次数，不再继续

    def _execute_tool(self, tool_name: str, args_str: str) -> str:
        """执行工具调用。"""
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            return f"参数解析失败: {args_str[:200]}"

        tool_map = {
            "list_memory_files": list_memory_files,
            "read_memory": read_memory,
            "edit_memory": edit_memory,
        }
        tool_func = tool_map.get(tool_name)
        if tool_func is None:
            return f"未知工具: {tool_name}"

        try:
            result = str(tool_func.invoke(args))
            if tool_name == "edit_memory":
                print(f"  [Memory:{self.player_name}] {result}")
            return result
        except Exception as e:
            return f"工具执行错误: {e}"


# ── 工具函数转换 ────────────────────────────────────────────────────────────────

def _convert_tool(t) -> dict:
    """将 LangChain @tool 转为 OpenAI function calling 格式。"""
    schema = t.args_schema.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            },
        },
    }
