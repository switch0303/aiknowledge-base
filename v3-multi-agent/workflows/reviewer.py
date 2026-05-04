import json
from typing import Dict, Any

from .state import KBState
from .model_client import create_provider, chat_with_retry, tracker


WEIGHTS = {
    "summary_quality": 0.25,
    "technical_depth": 0.25,
    "relevance": 0.20,
    "originality": 0.15,
    "formatting": 0.15,
}


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


def _chat_json(prompt: str, system: str, temperature: float = 0.1) -> Dict[str, Any]:
    """调用 LLM 并解析 JSON 响应。"""
    messages = [
        {"role": "system", "content": system + "\n\n输出必须是严格 JSON 格式，不要包含 Markdown 代码块标记。"},
        {"role": "user", "content": prompt}
    ]
    
    try:
        provider = create_provider()
        response = chat_with_retry(provider, messages, temperature=temperature)
        content = response.content.strip()
        
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        return json.loads(content.strip())
    except Exception as e:
        print(f"[review_node] LLM 调用失败: {e}")
        return {}


def review_node(state: KBState) -> Dict[str, Any]:
    print("[review_node] 开始审核分析结果...")

    # 读取 Planner 配置
    plan = state.get("plan", {}) or {}
    per_source_limit = int(plan.get("per_source_limit", 10))
    max_iterations = int(plan.get("max_iterations", 3))

    analyses = state.get("analyses", [])[:per_source_limit]
    iteration = state.get("iteration", 0)

    # Planner 兜底：达到最大迭代次数时强制通过
    if iteration >= max_iterations:
        print(f"[review_node] 达到最大迭代次数 {max_iterations}，强制通过")
        return {
            "review_passed": True,
            "review_feedback": f"达到最大迭代次数 {max_iterations}，强制通过",
            "iteration": iteration + 1,
            "cost_tracker": _get_cost_data(),
        }

    if not analyses:
        print("[review_node] 没有分析结果需要审核，直接通过")
        return {
            "review_passed": True,
            "review_feedback": "无分析结果，自动通过",
            "iteration": iteration + 1,
            "cost_tracker": _get_cost_data(),
        }

    analyses_json = json.dumps(analyses, ensure_ascii=False)
    prompt = f"""审核以下 AI 项目分析结果，输出 JSON：
{{
  "overall_feedback": "整体审核意见，50-100字",
  "scores": {{
    "summary_quality": 8,
    "technical_depth": 7,
    "relevance": 8,
    "originality": 6,
    "formatting": 9
  }},
  "item_feedback": [
    {{"source_id": "xxx", "issue": "具体问题描述"}}
  ]
}}

评分维度（1-10分）：
- summary_quality: 摘要质量（信息完整性、准确性、简洁性）
- technical_depth: 技术深度（技术细节、专业程度）
- relevance: 相关性（与 AI/LLM/Agent 领域的相关度）
- originality: 原创性（创新性、独特性）
- formatting: 格式规范（JSON结构、字段完整性）

分析结果列表: {analyses_json}
"""

    result = _chat_json(prompt, system="你是严格的技术内容审核员，评分要客观公正，输出严格 JSON 格式。", temperature=0.1)

    if not result:
        print("[review_node] LLM 审核失败，自动通过（不阻塞流程）")
        return {
            "review_passed": True,
            "review_feedback": "LLM 审核失败，自动通过",
            "iteration": iteration + 1,
            "cost_tracker": _get_cost_data(),
        }

    scores = result.get("scores", {})
    weighted_score = 0.0
    for dimension, weight in WEIGHTS.items():
        score = max(1, min(10, scores.get(dimension, 7.0)))
        weighted_score += score * weight

    review_passed = weighted_score >= 7.0
    feedback = result.get("overall_feedback", "")
    item_issues = result.get("item_feedback", [])

    print(f"[review_node] 加权总分: {weighted_score:.2f}, 通过: {review_passed}")
    print(f"[review_node] 审核意见: {feedback}")
    if item_issues:
        print(f"[review_node] 具体问题: {len(item_issues)} 项")

    return {
        "review_passed": review_passed,
        "review_feedback": f"加权总分 {weighted_score:.2f}。{feedback}",
        "iteration": iteration + 1,
        "cost_tracker": _get_cost_data(),
    }
