"""ArenaAgent —— 封装角色 + OpenAI 客户端 + 工具 + 消息历史。

直接使用 OpenAI 客户端（绕过 LangChain ChatOpenAI），以便传递
extra_body 禁用 DeepSeek thinking mode，避免 tool calling 兼容问题。
"""

import json
from typing import Any

from .config import get_client, MODEL_NAME, EXTRA_BODY
from .bob import Bob, SYSTEM_PROMPT as BOB_PROMPT
from .peter import Peter, SYSTEM_PROMPT as PETER_PROMPT
from .nerd import Nerd, SYSTEM_PROMPT as NERD_PROMPT
from .tools import (
    get_tournament_stats,
    get_gladiator_list,
    list_available_gladiators,
    select_gladiator,
    reflect_on_match_by_Bob,
    reflect_on_match_by_Nerd,
    reflect_on_match_by_Peter,
)

MAX_TOOL_ITERATIONS = 5


def _convert_to_openai_tool(t) -> dict:
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


class ArenaAgent:
    """封装一个角色，提供 LLM 驱动的对话能力（含工具调用）。"""

    def __init__(self, character: Any, system_prompt: str,
                 tools: list, agent_name: str, logger: Any = None):
        self.character = character
        self.system_prompt = system_prompt
        self.tools = tools
        self.agent_name = agent_name
        self.client = get_client()
        self.logger = logger
        self.message_history: list[dict] = []  # OpenAI 格式的对话历史

    def invoke(self, user_message: str, allow_tools: bool = True,
               extra_body: dict | None = None) -> str:
        """发送消息给此智能体并获取回复。"""
        # 构建完整消息列表
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.message_history)
        messages.append({"role": "user", "content": user_message})

        openai_tools = [_convert_to_openai_tool(t) for t in self.tools] if self.tools else []
        body = extra_body if extra_body is not None else EXTRA_BODY

        # 工具调用循环
        for _ in range(MAX_TOOL_ITERATIONS):
            kwargs = {
                "model": MODEL_NAME,
                "messages": messages,
                "extra_body": body,
            }
            if allow_tools and openai_tools:
                kwargs["tools"] = openai_tools

            response = self.client.chat.completions.create(**kwargs)
            msg = response.choices[0].message

            # 捕获 thinking 内容
            thinking = getattr(msg, 'reasoning_content', None)
            if thinking and self.logger:
                self.logger.log_thinking(self.agent_name, thinking)

            # 无工具调用 → 返回文本回复
            if not msg.tool_calls or not allow_tools or not openai_tools:
                self.message_history.append(
                    {"role": "user", "content": user_message})
                assistant_entry = {"role": "assistant", "content": msg.content or ""}
                if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
                    assistant_entry["reasoning_content"] = msg.reasoning_content
                self.message_history.append(assistant_entry)
                return msg.content or ""

            # 有工具调用 → 追加 assistant 消息（含 reasoning_content）
            assistant_msg = {
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
            }
            if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
                assistant_msg["reasoning_content"] = msg.reasoning_content
            messages.append(assistant_msg)

            # 执行工具并追加结果
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}
                result = self._execute_tool(tool_name, tool_args)
                messages.append({
                    "role": "tool",
                    "content": str(result),
                    "tool_call_id": tc.id,
                })

            # 继续循环，让模型看到工具结果后生成最终回复

        # 超过最大迭代次数，强制不带工具获取回复
        kwargs = {
            "model": MODEL_NAME,
            "messages": messages,
            "extra_body": body,
        }
        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        thinking = getattr(msg, 'reasoning_content', None)
        if thinking and self.logger:
            self.logger.log_thinking(self.agent_name, thinking)
        content = msg.content or ""
        self.message_history.append({"role": "user", "content": user_message})
        assistant_entry = {"role": "assistant", "content": content}
        if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
            assistant_entry["reasoning_content"] = msg.reasoning_content
        self.message_history.append(assistant_entry)
        return content

    def _execute_tool(self, tool_name: str, args: dict) -> str:
        """执行工具调用并返回结果字符串。"""
        tool_map = {
            "get_tournament_stats": get_tournament_stats,
            "get_gladiator_list": get_gladiator_list,
            "list_available_gladiators": list_available_gladiators,
            "select_gladiator": select_gladiator,
            "reflect_on_match_by_Bob": reflect_on_match_by_Bob,
            "reflect_on_match_by_Nerd": reflect_on_match_by_Nerd,
            "reflect_on_match_by_Peter": reflect_on_match_by_Peter,
        }
        tool_func = tool_map.get(tool_name)
        if tool_func is None:
            return f"未知工具: {tool_name}"
        try:
            result = str(tool_func.invoke(args))
        except Exception as e:
            result = f"工具执行错误: {e}"
        if self.logger:
            self.logger.log_tool_call(self.agent_name, tool_name, args, result)
        return result


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

def create_bob_agent(bob: Bob, logger: Any = None) -> ArenaAgent:
    tools = [
        get_tournament_stats,       # 工具1: 查战绩
        list_available_gladiators,  # 工具3: 查可用
        reflect_on_match_by_Bob,    # 工具5: 反思
    ]
    return ArenaAgent(bob, BOB_PROMPT, tools, "Bob", logger=logger)


def create_peter_agent(peter: Peter, logger: Any = None) -> ArenaAgent:
    tools = [
        select_gladiator,           # 工具4: 自选角斗士
        list_available_gladiators,  # 工具3: 查可用
        reflect_on_match_by_Peter,  # 工具5: 反思
    ]
    return ArenaAgent(peter, PETER_PROMPT, tools, "Peter", logger=logger)


def create_nerd_agent(nerd: Nerd, logger: Any = None) -> ArenaAgent:
    tools = [
        select_gladiator,           # 工具4: 自选角斗士
        list_available_gladiators,  # 工具3: 查可用
        reflect_on_match_by_Nerd,   # 工具5: 赛后反思（Nerd专属）
    ]
    return ArenaAgent(nerd, NERD_PROMPT, tools, "Nerd", logger=logger)
