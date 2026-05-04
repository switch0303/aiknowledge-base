import json
import os
from typing import Dict, Any

from .state import KBState
from .utils import _get_cost_data, ARTICLES_DIR


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
