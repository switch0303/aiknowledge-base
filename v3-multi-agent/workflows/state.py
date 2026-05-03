"""知识库工作流共享状态定义。

遵循报告式通信原则：所有字段存储结构化摘要而非原始数据，
确保 Agent 之间传递的是经过提炼的关键信息。
"""

from typing import TypedDict, List, Dict


class KBState(TypedDict):
    """知识库多 Agent 工作流共享状态。

    所有字段均为结构化摘要数据，不包含原始 HTML 或大文本内容。
    """

    sources: List[Dict]
    """采集到的原始数据摘要列表。

    每个 dict 包含：id, source, source_url, title, metadata, collected_at
    """

    analyses: List[Dict]
    """LLM 分析后的结构化结果列表。

    每个 dict 包含：source_id, summary, tags, category, priority, confidence
    """

    articles: List[Dict]
    """格式化、去重后的最终知识条目列表。

    每个 dict 包含：id, title, source_url, source_type, summary, tags,
    category, priority, status, collected_at, processed_at, channels
    """

    review_feedback: str
    """审核反馈意见。

    存储整理 Agent 对分析结果的审核建议，如："需补充技术细节"、
    "标签分类不准确"、"通过"等。空字符串表示暂无反馈。
    """

    review_passed: bool
    """审核是否通过。

    True 表示审核通过可进入分发队列，False 表示需退回分析 Agent 重处理。
    """

    iteration: int
    """当前审核循环次数。

    用于限制重试次数，最多 3 次。初始值为 0，每次审核不通过加 1。
    达到 3 次时自动标记为 rejected。
    """

    cost_tracker: Dict
    """Token 用量追踪统计。

    包含：total_tokens, prompt_tokens, completion_tokens, total_cost_usd
    每个字段为累计值，按调用累加。
    """
