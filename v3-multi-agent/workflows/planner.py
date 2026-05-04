import os
from typing import Dict, Any

from .state import KBState


def plan_strategy(target_count: int = None) -> Dict[str, Any]:
    """根据目标采集量制定执行策略。

    Args:
        target_count: 目标采集的数据源数量，None 时从环境变量 PLANNER_TARGET_COUNT 读取

    Returns:
        策略字典，包含:
        - name: 策略名称 (lite/standard/full)
        - per_source_limit: 单数据源处理上限
        - relevance_threshold: 相关性过滤阈值
        - max_iterations: 最大审核迭代次数
        - rationale: 策略选择理由
    """
    # 从环境变量读取默认值（默认 standard 策略）
    if target_count is None:
        env_target = os.getenv("PLANNER_TARGET_COUNT", "10")
        try:
            target_count = int(env_target)
        except (ValueError, TypeError):
            target_count = 10

    # 三档策略判断
    if target_count < 10:
        return {
            "name": "lite",
            "per_source_limit": 5,
            "relevance_threshold": 0.7,
            "max_iterations": 1,
            "rationale": "目标采集量小(<10)，采用轻量策略：低迭代快速产出，高阈值保证质量"
        }
    elif 10 <= target_count < 20:
        return {
            "name": "standard",
            "per_source_limit": 10,
            "relevance_threshold": 0.5,
            "max_iterations": 2,
            "rationale": "目标采集量中等(10-19)，采用平衡策略：中等迭代，平衡质量和产出量"
        }
    else:  # target >= 20
        return {
            "name": "full",
            "per_source_limit": 20,
            "relevance_threshold": 0.4,
            "max_iterations": 3,
            "rationale": "目标采集量大(>=20)，采用全量策略：高迭代提质量，低阈值保覆盖度"
        }


def planner_node(state: KBState) -> Dict[str, Any]:
    """LangGraph 节点：Planner Agent，只规划不执行。

    根据实际采集到的数据源数量动态制定执行策略，
    输出写入 state["plan"]，下游所有节点读取此配置。
    """
    print("[planner_node] 开始制定执行策略...")

    # 优先用实际采集到的 sources 数量，无数据时用环境变量默认
    sources_count = len(state.get("sources", []))
    target_count = sources_count if sources_count > 0 else None

    plan = plan_strategy(target_count)

    print(f"[planner_node] 数据源数量: {sources_count if sources_count else '默认10'}")
    print(f"[planner_node] 策略名称: {plan['name']}")
    print(f"[planner_node] 最大迭代: {plan['max_iterations']}")
    print(f"[planner_node] 相关性阈值: {plan['relevance_threshold']}")
    print(f"[planner_node] 策略理由: {plan['rationale']}")

    return {"plan": plan}
