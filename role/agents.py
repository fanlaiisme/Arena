"""ArenaAgent —— 封装角色 + OpenAI 客户端 + 工具 + 消息历史。

直接使用 OpenAI 客户端（绕过 LangChain ChatOpenAI），以便传递
extra_body 禁用 DeepSeek thinking mode，避免 tool calling 兼容问题。
"""

import json
from typing import Any

from .config import get_client, MODEL_NAME, EXTRA_BODY
from .bob import Bob, SYSTEM_PROMPT as BOB_PROMPT
from .gambler import Gambler, SYSTEM_PROMPT as GAMBLER_PROMPT
from .tools import (
    get_overall_ranking,
    get_gladiator_record,
    get_head_to_head,
    get_gladiator_list,
    get_gladiator_form,
    view_player_squad_info,
    talk_to_bob,
    bribe_bob,
    view_auction_item,
    auction_bid,
    view_my_squad,
    deploy_first_match,
    deploy_remaining_matches,
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
            "get_overall_ranking": get_overall_ranking,
            "get_gladiator_record": get_gladiator_record,
            "get_head_to_head": get_head_to_head,
            "get_gladiator_list": get_gladiator_list,
            "get_gladiator_form": get_gladiator_form,
            "view_player_squad_info": view_player_squad_info,
            "talk_to_bob": talk_to_bob,
            "bribe_bob": bribe_bob,
            "view_auction_item": view_auction_item,
            "auction_bid": auction_bid,
            "view_my_squad": view_my_squad,
            "deploy_first_match": deploy_first_match,
            "deploy_remaining_matches": deploy_remaining_matches,
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

def create_bob_agent(bob: Bob, logger: Any = None,
                     extra_context: str = "") -> ArenaAgent:
    prompt = BOB_PROMPT
    if extra_context:
        prompt += extra_context
    tools = [
        get_overall_ranking,
        get_gladiator_record,
        get_head_to_head,
        get_gladiator_list,
        get_gladiator_form,
        view_player_squad_info,
    ]
    return ArenaAgent(bob, prompt, tools, "Bob", logger=logger)


def create_gambler_agent(gambler: Gambler, logger: Any = None) -> ArenaAgent:
    """为赌徒玩家创建智能体。"""
    prompt = GAMBLER_PROMPT.format(player_name=gambler.player_name)
    tools = [
        talk_to_bob,
        bribe_bob,
        view_auction_item,
        auction_bid,
        view_my_squad,
        deploy_first_match,
        deploy_remaining_matches,
    ]
    return ArenaAgent(gambler, prompt, tools, gambler.player_name, logger=logger)
