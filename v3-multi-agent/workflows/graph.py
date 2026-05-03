import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END

from workflows.state import KBState
from workflows.nodes import collect_node, analyze_node, organize_node, save_node
from workflows.reviewer import review_node


def review_router(state: KBState) -> str:
    if state.get("review_passed", False):
        return "organize"
    return "analyze"


def build_graph():
    graph = StateGraph(KBState)

    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("review", review_node)
    graph.add_node("organize", organize_node)
    graph.add_node("save", save_node)

    graph.set_entry_point("collect")

    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "review")

    graph.add_conditional_edges(
        "review",
        review_router,
        {
            "organize": "organize",
            "analyze": "analyze",
        },
    )

    graph.add_edge("organize", "save")
    graph.add_edge("save", END)

    return graph.compile()


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
    }

    for output in app.stream(initial_state):
        for node_name, node_output in output.items():
            print(f"\n{'='*50}")
            print(f"节点: {node_name}")
            print(f"{'='*50}")

            if node_name == "collect":
                print(f"采集数量: {len(node_output.get('sources', []))}")
                if node_output.get("sources"):
                    print(f"首个来源: {node_output['sources'][0]['title']}")

            elif node_name == "analyze":
                print(f"分析数量: {len(node_output.get('analyses', []))}")
                cost = node_output.get("cost_tracker", {})
                print(f"累计 Token: {cost.get('total_tokens', 0)}")
                print(f"累计成本: ¥{cost.get('total_cost_cny', 0):.4f}")

            elif node_name == "organize":
                print(f"生成文章数: {len(node_output.get('articles', []))}")
                if node_output.get("articles"):
                    print(f"首篇文章: {node_output['articles'][0]['title']}")

            elif node_name == "review":
                passed = node_output.get("review_passed", False)
                feedback = node_output.get("review_feedback", "")
                iteration = node_output.get("iteration", 0)
                print(f"审核结果: {'通过' if passed else '不通过'}")
                print(f"审核意见: {feedback}")
                print(f"迭代次数: {iteration}")

            elif node_name == "save":
                print("文章已保存到 knowledge/articles/")

    print("\n" + "=" * 50)
    print("工作流执行完成")
    print("=" * 50)
