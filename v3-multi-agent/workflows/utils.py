import json
import os
from typing import Dict, Any

from .model_client import create_provider, chat_with_retry, tracker


GITHUB_TOKEN = os.environ.get("AIKB_GITHUB_TOKEN", "")
ARTICLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge", "articles"
)


def _get_cost_data() -> Dict[str, Any]:
    """获取累计 Token 和成本数据。"""
    total_tokens = 0
    for provider_records in tracker.records.values():
        for usage in provider_records:
            total_tokens += usage.total_tokens
    return {
        "total_tokens": total_tokens,
        "total_cost_cny": tracker.estimated_cost(),
    }


def _chat_json(prompt: str, system: str) -> Dict[str, Any]:
    """调用 LLM 并解析 JSON 响应。"""
    messages = [
        {"role": "system", "content": system + "\n\n输出必须是严格 JSON 格式，不要包含 Markdown 代码块标记。"},
        {"role": "user", "content": prompt}
    ]

    try:
        provider = create_provider()
        response = chat_with_retry(provider, messages)
        content = response.content.strip()

        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        return json.loads(content.strip())
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        return {}
