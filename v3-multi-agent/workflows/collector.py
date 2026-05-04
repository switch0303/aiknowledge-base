import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from typing import Dict, Any

from .state import KBState
from .utils import GITHUB_TOKEN, _get_cost_data


def collect_node(state: KBState) -> Dict[str, Any]:
    print("[collect_node] 开始采集 GitHub 数据...")

    plan = state.get("plan", {}) or {}
    per_source_limit = int(plan.get("per_source_limit", 10))

    sources = []
    try:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"

        query = urllib.parse.quote("llm OR agent OR ai-agent OR langchain")
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page={per_source_limit}"

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
