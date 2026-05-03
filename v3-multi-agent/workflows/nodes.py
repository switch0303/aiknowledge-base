import json
import os
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from typing import Dict, Any

from .state import KBState
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
        
        # 移除可能的 Markdown 代码块标记
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


def collect_node(state: KBState) -> Dict[str, Any]:
    print("[collect_node] 开始采集 GitHub 数据...")

    sources = []
    try:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"

        query = urllib.parse.quote("llm OR agent OR ai-agent OR langchain")
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=20"

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())

        for item in data.get("items", []):
            sources.append(
                {
                    "id": f'github-{item["id"]}',
                    "source": "github",
                    "source_url": item["html_url"],
                    "title": item["name"],
                    "metadata": {
                        "stars": item["stargazers_count"],
                        "language": item["language"] or "",
                        "author": item["owner"]["login"],
                        "description": item["description"] or "",
                    },
                    "collected_at": datetime.utcnow().isoformat() + "Z",
                }
            )

    except urllib.error.URLError as e:
        print(f"[collect_node] 请求失败: {e}")

    print(f"[collect_node] 完成，采集到 {len(sources)} 条数据")
    return {"sources": sources, "iteration": 0, "cost_tracker": _get_cost_data()}


def analyze_node(state: KBState) -> Dict[str, Any]:
    print("[analyze_node] 开始分析数据...")

    analyses = []
    sources = state.get("sources", [])

    for src in sources[:5]:  # 只处理前 5 个，避免 Token 消耗过大
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


def organize_node(state: KBState) -> Dict[str, Any]:
    print("[organize_node] 开始整理数据...")

    analyses = state.get("analyses", [])
    sources = state.get("sources", [])
    feedback = state.get("review_feedback", "")
    iteration = state.get("iteration", 0)

    filtered = [a for a in analyses if a.get("confidence", 0) >= 0.6]

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


def save_node(state: KBState) -> Dict[str, Any]:
    print("[save_node] 开始保存文章...")

    articles = state.get("articles", [])
    os.makedirs(ARTICLES_DIR, exist_ok=True)

    index_path = os.path.join(ARTICLES_DIR, "index.json")
    existing_index = []
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            existing_index = json.load(f)

    for article in articles:
        filename = f"{article['id']}.json"
        filepath = os.path.join(ARTICLES_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

        existing_index.append(
            {"id": article["id"], "title": article["title"], "saved_at": article["processed_at"]}
        )

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(existing_index, f, ensure_ascii=False, indent=2)

    print(f"[save_node] 完成，保存 {len(articles)} 篇文章")
    return {"cost_tracker": _get_cost_data()}
