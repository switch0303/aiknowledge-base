import json
import os
from datetime import datetime
from typing import Dict, Any

from .state import KBState


HUMAN_REVIEW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge", "human_review"
)
MAX_ITERATIONS = 2


def human_flag_node(state: KBState) -> Dict[str, Any]:
    """将超过最大迭代次数仍未通过的条目标记为人工审核。

    当审核循环超过 MAX_ITERATIONS 次仍未通过时，将问题条目写入
    knowledge/human_review/ 目录，不污染主知识库。
    """
    print("[human_flag_node] 超过最大迭代次数，标记为人工审核...")

    iteration = state.get("iteration", 0)
    analyses = state.get("analyses", [])
    sources = state.get("sources", [])
    review_feedback = state.get("review_feedback", "")

    os.makedirs(HUMAN_REVIEW_DIR, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"human_review_{timestamp}.json"
    filepath = os.path.join(HUMAN_REVIEW_DIR, filename)

    review_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "iteration_count": iteration,
        "max_iterations": MAX_ITERATIONS,
        "final_feedback": review_feedback,
        "analyses": analyses,
        "sources": sources,
        "status": "pending_human_review",
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(review_data, f, ensure_ascii=False, indent=2)

    print(f"[human_flag_node] 已保存 {len(analyses)} 条待人工审核")
    print(f"[human_flag_node] 文件: {filename}")

    return {
        "review_passed": True,  # 强制通过以退出循环
        "review_feedback": f"已标记为人工审核（迭代 {iteration} 次仍未通过）",
        "iteration": iteration + 1,
        "needs_human_review": True,
        "human_review_file": filename,
    }
