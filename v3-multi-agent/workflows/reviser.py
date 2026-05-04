import json
from typing import Dict, Any, List

from .state import KBState
from .model_client import create_provider, chat_with_retry, tracker
from tests.security import sanitize_input, filter_output, secure_input, secure_output


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


def _chat_json(prompt: str, system: str, temperature: float = 0.4, node_name: str = "unknown") -> Dict[str, Any]:
    """调用 LLM 并解析 JSON 响应（带安全防护）。"""
    # 1. 输入清洗：检测 Prompt 注入，清除控制字符
    cleaned_prompt, warnings = sanitize_input(prompt)
    if warnings:
        print(f"[security] 输入安全警告: {len(warnings)} 项")
        for w in warnings:
            print(f"  - {w['type']}: {w['description']}")

    messages = [
        {"role": "system", "content": system + "\n\n输出必须是严格 JSON 格式，不要包含 Markdown 代码块标记。"},
        {"role": "user", "content": cleaned_prompt}
    ]
    
    try:
        # 2. 速率限制检查
        sec_result = secure_input(cleaned_prompt, client_id=node_name)
        if not sec_result["allowed"]:
            print(f"[security] 速率限制触发，节点: {node_name}")
            return {}

        # 3. 调用 LLM（传递 node_name 给 CostGuard）
        provider = create_provider()
        response = chat_with_retry(provider, messages, temperature=temperature, node_name=node_name)
        content = response.content.strip()
        
        # 4. 输出过滤：检测并掩码 PII
        filtered_content, detections = filter_output(content)
        if detections:
            print(f"[security] 输出检测到 PII: {len(detections)} 项")
            for d in detections:
                print(f"  - {d['type']}: 位置 {d['start']}-{d['end']}")

        # 5. 记录输出审计
        secure_output(filtered_content, client_id=node_name)

        # 6. 解析 JSON
        if filtered_content.startswith("```json"):
            filtered_content = filtered_content[7:]
        if filtered_content.startswith("```"):
            filtered_content = filtered_content[3:]
        if filtered_content.endswith("```"):
            filtered_content = filtered_content[:-3]
        
        return json.loads(filtered_content.strip())
    except Exception as e:
        print(f"[revise_node] LLM 调用失败: {e}")
        return {}


def revise_node(state: KBState) -> Dict[str, Any]:
    print("[revise_node] 开始修正分析结果...")

    analyses = state.get("analyses", [])
    feedback = state.get("review_feedback", "")

    if not analyses or not feedback:
        print("[revise_node] 分析结果或审核反馈为空，跳过修正")
        return {}

    print(f"[revise_node] 待修正条目数: {len(analyses)}")
    print(f"[revise_node] 审核反馈: {feedback[:100]}...")

    analyses_json = json.dumps(analyses, ensure_ascii=False)
    prompt = f"""根据审核反馈修正以下分析结果，输出完整的 JSON 列表：
{{
  "improved_analyses": [
    {{
      "source_id": "xxx",
      "summary": "修正后的摘要",
      "tags": ["修正后的标签"],
      "category": "paper|tool|framework|news",
      "priority": "high|medium|low",
      "confidence": 0.8
    }}
  ]
}}

审核反馈: {feedback}

原始分析结果: {analyses_json}

要求：
1. 保持 source_id 不变
2. 根据反馈针对性修改摘要、标签、分类等字段
3. 保持 JSON 结构完整一致
4. 返回所有输入的分析结果（不要遗漏）
"""

    result = _chat_json(prompt, system="你是专业的技术内容编辑，根据审核反馈优化分析结果质量。", temperature=0.4, node_name="revise_node")

    improved = result.get("improved_analyses", [])
    if not improved:
        print("[revise_node] LLM 未返回修正结果，使用原始数据")
        return {}

    # 确保所有 source_id 都被保留
    original_ids = {a["source_id"] for a in analyses}
    result_ids = {a.get("source_id") for a in improved}
    if original_ids != result_ids:
        print(f"[revise_node] 警告: ID 不匹配，原始 {len(original_ids)} 个，返回 {len(result_ids)} 个")
        # 补全缺失的条目
        id_to_improved = {a.get("source_id"): a for a in improved}
        improved = [id_to_improved.get(a["source_id"], a) for a in analyses]

    print(f"[revise_node] 完成修正，共 {len(improved)} 条")
    return {"analyses": improved, "cost_tracker": _get_cost_data()}
