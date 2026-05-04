import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END

from workflows.state import KBState
from workflows.collector import collect_node
from workflows.analyzer import analyze_node
from workflows.organizer import organize_node
from workflows.saver import save_node
from workflows.planner import planner_node
from workflows.reviewer import review_node
from workflows.reviser import revise_node
from workflows.human_flag import human_flag_node

# 导入安全监控模块
from tests.security import get_pii_stats, reset_pii_stats
from workflows.model_client import get_cost_guard


def route_after_review(state: KBState) -> str:
    """审核后的 3 路条件路由（读取 Planner 动态配置）。"""
    if state.get("review_passed", False):
        return "organize"
    
    # 从 plan 读取动态配置，默认值 3
    max_iterations = state.get("plan", {}).get("max_iterations", 3)
    if state.get("iteration", 0) < max_iterations:
        return "revise"
    return "human_flag"


def build_graph():
    graph = StateGraph(KBState)

    graph.add_node("collect", collect_node)
    graph.add_node("planner", planner_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("review", review_node)
    graph.add_node("revise", revise_node)
    graph.add_node("human_flag", human_flag_node)
    graph.add_node("organize", organize_node)
    graph.add_node("save", save_node)

    graph.set_entry_point("collect")

    graph.add_edge("collect", "planner")
    graph.add_edge("planner", "analyze")
    graph.add_edge("analyze", "review")

    graph.add_conditional_edges(
        "review",
        route_after_review,
        {
            "organize": "organize",
            "revise": "revise",
            "human_flag": "human_flag",
        },
    )

    graph.add_edge("revise", "review")
    graph.add_edge("human_flag", END)
    graph.add_edge("organize", "save")
    graph.add_edge("save", END)

    return graph.compile()


def print_cost_summary():
    """打印 CostGuard 成本汇总。"""
    cg = get_cost_guard()
    report = cg.get_report()
    
    total_calls = report['summary']['total_calls']
    total_cost = report['summary']['total_cost_yuan']
    
    print(f"\n[CostGuard] 总调用 {total_calls} 次 · 总成本 ¥{total_cost:.4f}")
    
    # 按节点统计
    if report['by_node']:
        node_costs = {}
        for node, stats in report['by_node'].items():
            cost = stats.get('cost_yuan', 0)
            if cost > 0:
                # 简化节点名称
                short_name = node.replace('_node', '')
                node_costs[short_name] = round(cost, 4)
        print(f"[CostGuard] 按节点：{node_costs}")


def print_security_summary():
    """打印 Security 安全监控汇总。"""
    pii_stats = get_pii_stats()
    total_pii = sum(pii_stats.values())
    
    if total_pii > 0:
        for node, count in pii_stats.items():
            short_name = node.replace('_node', '')
            print(f"[Security] {short_name} 阶段共掩码 {count} 处 PII")


if __name__ == "__main__":
    app = build_graph()

    initial_state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {},
        "needs_human_review": False,
        "human_review_file": "",
        "plan": {},
    }

    # 重置 PII 统计
    reset_pii_stats()

    for output in app.stream(initial_state):
        for node_name, node_output in output.items():
            if node_name == "collect":
                count = len(node_output.get("sources", []))
                print(f"[Collector] 采集到 {count} 条原始数据")

            elif node_name == "planner":
                plan = node_output.get("plan", {})
                strategy = plan.get("name", "default")
                per_source = plan.get("per_source_limit", 10)
                max_iter = plan.get("max_iterations", 3)
                print(f"[Planner] 策略：{strategy} · 每源限 {per_source} 条 · 最大迭代 {max_iter}")

            elif node_name == "analyze":
                count = len(node_output.get("analyses", []))
                print(f"[Analyzer] 完成 {count} 条分析")

            elif node_name == "review":
                passed = node_output.get("review_passed", False)
                iteration = node_output.get("iteration", 0)
                feedback = node_output.get("review_feedback", "")
                # 提取分数
                score = "N/A"
                if "加权总分" in feedback:
                    import re
                    match = re.search(r"加权总分\s*([\d.]+)", feedback)
                    if match:
                        score = match.group(1)
                print(f"[Reviewer] 加权总分: {score}/10, 通过: {passed} (第 {iteration} 次审核)")

            elif node_name == "revise":
                improved_count = len(node_output.get("analyses", []))
                print(f"[Reviser] 修正完成 {improved_count} 条")

            elif node_name == "organize":
                count = len(node_output.get("articles", []))
                print(f"[Organizer] 整理出 {count} 条知识条目")

            elif node_name == "human_flag":
                print(f"[HumanFlag] 已标记人工审核")

            elif node_name == "save":
                print(f"[Saver] 已保存到知识库")

    # 打印汇总
    print("\n=== 工作流完成 ===")
    print_security_summary()
    print_cost_summary()
