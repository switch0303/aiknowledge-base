import json
from datetime import datetime
from typing import Dict, Any

from .state import KBState
from .utils import _get_cost_data, _chat_json


def organize_node(state: KBState) -> Dict[str, Any]:
    print("[organize_node] 开始整理数据...")

    plan = state.get("plan", {}) or {}
    relevance_threshold = float(plan.get("relevance_threshold", 0.5))

    analyses = state.get("analyses", [])
    sources = state.get("sources", [])
    feedback = state.get("review_feedback", "")
    iteration = state.get("iteration", 0)

    filtered = [a for a in analyses if a.get("confidence", 0) >= relevance_threshold]

    seen_urls = set()
    deduped = []
    for a in filtered:
        src = next((s for s in sources if s["id"] == a["source_id"]), None)
        if not src:
            continue
        url = src["source_url"]
        if url not in seen_urls:
            seen_urls.add(url)
            deduped.append({"analysis": a, "source": src})

    if iteration > 0 and feedback:
        for item in deduped:
            prompt = f"""根据审核反馈修改分析结果，输出 JSON：
审核反馈: {feedback}
原始分析: {json.dumps(item['analysis'], ensure_ascii=False)}
"""
            revised = _chat_json(prompt, system="你是内容修正助手，输出 JSON。")
            if revised:
                item["analysis"].update(revised)

    articles = []
    for item in deduped:
        a = item["analysis"]
        s = item["source"]
        articles.append(
            {
                "id": s["id"],
                "title": s["title"],
                "source_url": s["source_url"],
                "source_type": s["source"],
                "summary": a.get("summary", ""),
                "tags": a.get("tags", []),
                "category": a.get("category", "tool"),
                "priority": a.get("priority", "medium"),
                "status": "pending",
                "collected_at": s["collected_at"],
                "processed_at": datetime.utcnow().isoformat() + "Z",
                "published_at": None,
                "channels": ["telegram", "feishu"],
            }
        )

    print(f"[organize_node] 完成，生成 {len(articles)} 篇文章")
    return {"articles": articles, "cost_tracker": _get_cost_data()}
