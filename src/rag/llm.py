
import logging

import requests

from src.config import settings

logger = logging.getLogger(__name__)

API_URL = settings.deepseek_api_url
MODEL_NAME = settings.deepseek_model


def chat_deepseek(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
) -> dict:
    """调用 DeepSeek Chat Completions，返回 assistant message。"""

    api_key = settings.deepseek_api_key

    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件")

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    logger.info("调用 DeepSeek，model=%s tools=%s", settings.deepseek_model, bool(tools))

    response = requests.post(
        settings.deepseek_api_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=settings.deepseek_timeout,
    )

    response.raise_for_status()
    data = response.json()

    return data["choices"][0]["message"]


def call_deepseek(prompt: str) -> str:
    """调用 DeepSeek，返回模型生成的文本内容。"""

    message = chat_deepseek(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    return message.get("content") or ""


if __name__ == "__main__":
    answer = call_deepseek("请用一句话解释什么是 RAG。")
    print("DeepSeek 回答：")
    print(answer)
