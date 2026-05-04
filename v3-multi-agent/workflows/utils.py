import json
import os
from typing import Dict, Any

from .model_client import create_provider, chat_with_retry, tracker
from tests.security import sanitize_input, filter_output, secure_input, secure_output


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


def _chat_json(prompt: str, system: str, node_name: str = "unknown") -> Dict[str, Any]:
    """调用 LLM 并解析 JSON 响应（带安全防护）。

    Args:
        prompt: 用户提示词
        system: 系统提示词
        node_name: 节点名称，用于安全审计和成本统计

    Returns:
        解析后的 JSON 字典
    """
    # 1. 输入清洗：检测 Prompt 注入，清除控制字符
    cleaned_prompt, warnings = sanitize_input(prompt)
    if warnings:
        print(f"[security] 输入安全警告: {len(warnings)} 项")
        for w in warnings:
            print(f"  - {w['type']}: {w['description']}")

    # 2. 构建消息
    messages = [
        {"role": "system", "content": system + "\n\n输出必须是严格 JSON 格式，不要包含 Markdown 代码块标记。"},
        {"role": "user", "content": cleaned_prompt}
    ]

    try:
        # 3. 速率限制检查（通过 secure_input）
        sec_result = secure_input(cleaned_prompt, client_id=node_name)
        if not sec_result["allowed"]:
            print(f"[security] 速率限制触发，节点: {node_name}")
            return {}

        # 4. 调用 LLM（传递 node_name 给 CostGuard）
        provider = create_provider()
        response = chat_with_retry(provider, messages, node_name=node_name)
        content = response.content.strip()

        # 5. 输出过滤：检测并掩码 PII
        filtered_content, detections = filter_output(content)
        if detections:
            print(f"[security] 输出检测到 PII: {len(detections)} 项")
            for d in detections:
                print(f"  - {d['type']}: 位置 {d['start']}-{d['end']}")

        # 6. 记录输出审计
        secure_output(filtered_content, client_id=node_name)

        # 7. 解析 JSON
        if filtered_content.startswith("```json"):
            filtered_content = filtered_content[7:]
        if filtered_content.startswith("```"):
            filtered_content = filtered_content[3:]
        if filtered_content.endswith("```"):
            filtered_content = filtered_content[:-3]

        return json.loads(filtered_content.strip())
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        return {}
