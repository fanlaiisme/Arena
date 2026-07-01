"""共享配置：加载 .env，创建 DeepSeek 客户端。"""

import os
from dotenv import load_dotenv
from openai import OpenAI

# 从 Arena 根目录加载 .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
MODEL_NAME = "deepseek-v4-flash"

# 禁用 thinking mode，避免 tool calling 兼容问题
EXTRA_BODY = {"thinking": {"type": "disabled"}}

# 反思阶段启用 thinking mode，捕获推理链
EXTRA_BODY_THINKING = {"thinking": {"type": "enabled"}}


def create_client() -> OpenAI:
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=60.0)


_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = create_client()
    return _client
