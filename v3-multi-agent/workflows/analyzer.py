from typing import Dict, Any

from .state import KBState
from .utils import _get_cost_data, _chat_json


def analyze_node(state: KBState) -> Dict[str, Any]:
    print("[analyze_node] 开始分析数据...")

    plan = state.get("plan", {}) or {}
    per_source_limit = int(plan.get("per_source_limit", 10))

    analyses = []
    sources = state.get("sources", [])

    for src in sources[:per_source_limit]:
        prompt = f"""分析以下 AI 项目信息，输出 JSON 格式：
{{
  "source_id": "{src['id']}",
  "summary": "中文摘要（100-200字）",
  "tags": ["标签1", "标签2", "标签3"],
  "category": "paper|tool|framework|news",
  "priority": "high|medium|low",
  "confidence": 0.8
}}

项目信息：
名称: {src['title']}
描述: {src['metadata'].get('description', '')}
Stars: {src['metadata'].get('stars', 0)}
语言: {src['metadata'].get('language', '')}
"""

        result = _chat_json(prompt, system="你是 AI 技术分析师，输出严格 JSON 格式。")
        if result:
            result["source_id"] = src["id"]
            result["confidence"] = result.get("confidence", 0.8)
            analyses.append(result)

    print(f"[analyze_node] 完成，分析 {len(analyses)} 条数据")
    return {"analyses": analyses, "cost_tracker": _get_cost_data()}
