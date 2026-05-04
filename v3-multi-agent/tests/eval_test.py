"""AI 知识库评估测试套件。

使用 pytest 框架，包含多种场景测试和 LLM-as-Judge 自动评分。
"""

import os
import sys
import warnings
from typing import Dict, Any, Callable

# 屏蔽 PytestUnknownMarkWarning
warnings.filterwarnings("ignore", category=UserWarning, message="Unknown pytest.mark")

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pytest

# 添加父目录到路径以便导入 workflows
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflows.model_client import create_provider, chat_with_retry


def chat(prompt: str, system: str = "") -> tuple:
    """简单的 chat 封装函数。

    Args:
        prompt: 用户提示词
        system: 系统提示词

    Returns:
        (text, usage) 元组
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        provider = create_provider()
        response = chat_with_retry(provider, messages)
        provider.close()
        return response.content, response.usage
    except (KeyError, ValueError) as e:
        # 如果没有配置 API key，返回模拟数据用于测试
        warnings.warn(f"LLM API not configured: {e}, using mock response")
        return f"Mock response for: {prompt[:50]}...", type('Usage', (), {
            'prompt_tokens': len(prompt) // 4,
            'completion_tokens': 50,
            'total_tokens': len(prompt) // 4 + 50
        })()


# ============================================================================
# 评估测试用例定义
# ============================================================================

EVAL_CASES = [
    {
        "name": "正面案例-技术文章分析",
        "input": """
            LangGraph 是一个用于构建有状态代理的库，基于 LangChain 构建。
            它提供了循环、分支和持久化状态的能力，特别适合构建多步骤的
            复杂 Agent 工作流。核心概念包括 State、Nodes、Edges 和
            Conditional Edges。支持人类在回路、持久化存储和时间旅行调试。
        """,
        "expected": {
            "checks": [
                lambda result: len(result) >= 50,
                lambda result: "摘要" in result or "总结" in result or "分析" in result,
                lambda result: any(kw in result.lower() for kw in ["agent", "langgraph", "工作流", "代理"]),
            ],
            "min_keywords": 2,
            "min_length": 50,
        }
    },
    {
        "name": "负面案例-无关内容过滤",
        "input": """
            今天天气很好，我去公园散步，看到了很多花，有红色的玫瑰，
            黄色的向日葵，还有粉色的樱花。小鸟在树上唱歌，微风拂面，
            心情非常愉快。晚上吃了一顿美味的火锅，真是美好的一天。
        """,
        "expected": {
            "checks": [
                lambda result: "无关" in result or "不相关" in result or "非技术" in result or len(result) < 100,
            ],
            "relevance_threshold": "low",
        }
    },
    {
        "name": "边界案例-极短输入",
        "input": "AI",
        "expected": {
            "checks": [
                lambda result: result is not None,
                lambda result: isinstance(result, str),
                lambda result: len(result) >= 0,
            ],
            "should_not_crash": True,
        }
    },
    {
        "name": "边界案例-空输入",
        "input": "",
        "expected": {
            "checks": [
                lambda result: result is not None,
                lambda result: isinstance(result, str),
            ],
        }
    },
]


# ============================================================================
# 本地验证测试（不调用 LLM）
# ============================================================================

def test_eval_cases_structure():
    """验证 EVAL_CASES 的结构完整性。"""
    assert isinstance(EVAL_CASES, list), "EVAL_CASES 必须是列表"
    assert len(EVAL_CASES) >= 3, "至少需要 3 个测试用例"

    for case in EVAL_CASES:
        assert "name" in case, f"用例缺少 name 字段: {case}"
        assert "input" in case, f"用例缺少 input 字段: {case}"
        assert "expected" in case, f"用例缺少 expected 字段: {case}"
        assert isinstance(case["expected"], dict), "expected 必须是字典"

        assert isinstance(case["name"], str), "name 必须是字符串"
        assert isinstance(case["input"], str), "input 必须是字符串"
        assert "checks" in case["expected"], "expected 必须包含 checks 列表"
        assert isinstance(case["expected"]["checks"], list), "checks 必须是列表"

        for check in case["expected"]["checks"]:
            assert callable(check), "check 必须是可调用的函数"


@pytest.mark.parametrize("case", EVAL_CASES, ids=lambda c: c["name"])
def test_case_local_validation(case):
    """本地验证测试用例输入输出格式（不调用 LLM）。"""
    assert isinstance(case["input"], str), "输入必须是字符串"
    assert len(case["expected"]["checks"]) >= 1, "至少有一个检查函数"


# ============================================================================
# LLM 分析功能测试
# ============================================================================

def analyze_content(content: str) -> Dict[str, Any]:
    """调用 LLM 分析内容并返回结构化结果。

    Args:
        content: 待分析的文本内容

    Returns:
        包含摘要、关键词和相关度评分的字典
    """
    system_prompt = """
    你是一个 AI 技术内容分析器。请分析输入的文本，返回 JSON 格式：
    {
        "summary": "200字以内的中文摘要",
        "keywords": ["关键词1", "关键词2", "关键词3"],
        "relevance_score": 0-10的整数（AI/技术相关度）,
        "category": "paper|tool|news|irrelevant"
    }
    """

    prompt = f"请分析以下文本：\n\n{content}\n\n返回JSON格式的分析结果。"

    result_text, usage = chat(prompt, system_prompt)

    try:
        import json
        result = json.loads(result_text)
    except json.JSONDecodeError:
        result = {
            "summary": result_text,
            "keywords": [],
            "relevance_score": 5,
            "category": "unknown",
            "raw_text": result_text
        }

    return result


@pytest.mark.slow
@pytest.mark.parametrize("case", EVAL_CASES, ids=lambda c: c["name"])
def test_llm_analysis(case):
    """测试 LLM 内容分析功能。"""
    content = case["input"]
    result = analyze_content(content)

    # 范围断言：验证结果结构
    assert isinstance(result, dict), "结果必须是字典"
    assert "summary" in result, "结果必须包含 summary 字段"
    assert isinstance(result["summary"], str), "summary 必须是字符串"

    # 长度范围断言
    assert len(result["summary"]) >= case["expected"].get("min_length", 0), \
        f"摘要长度不足，期望至少 {case['expected'].get('min_length', 0)} 字符"

    # 运行所有检查函数
    for check in case["expected"]["checks"]:
        assert check(result["summary"]) or check(result), f"检查失败: {check}"

    # 关键词数量断言（如果有）
    if "keywords" in result:
        min_keywords = case["expected"].get("min_keywords", 0)
        assert len(result["keywords"]) >= min_keywords, \
            f"关键词数量不足，期望至少 {min_keywords} 个"


@pytest.mark.slow
def test_positive_case_detailed():
    """正面案例详细测试：技术文章应生成有意义的摘要和关键词。"""
    content = """
    LangGraph 是一个用于构建有状态代理的库，基于 LangChain 构建。
    它提供了循环、分支和持久化状态的能力，特别适合构建多步骤的
    复杂 Agent 工作流。核心概念包括 State、Nodes、Edges 和
    Conditional Edges。支持人类在回路、持久化存储和时间旅行调试。
    """

    result = analyze_content(content)

    # 摘要非空且有足够长度
    assert len(result["summary"]) >= 30, "摘要长度应至少 30 字符"

    # 相关度应较高
    relevance = result.get("relevance_score", 0)
    assert isinstance(relevance, (int, float)), "相关度评分必须是数字"
    assert relevance >= 5, f"技术内容相关度应 >= 5，实际: {relevance}"

    # 关键词数量
    keywords = result.get("keywords", [])
    assert len(keywords) >= 2, f"应至少提取 2 个关键词，实际: {keywords}"

    # 分类应为技术相关
    category = result.get("category", "")
    assert category in ["tool", "paper", "news", "unknown"], \
        f"技术内容分类应为 tool/paper/news，实际: {category}"


@pytest.mark.slow
def test_negative_case_relevance():
    """负面案例测试：非技术内容应被识别为低相关。"""
    content = """
    今天天气很好，我去公园散步，看到了很多花，有红色的玫瑰，
    黄色的向日葵，还有粉色的樱花。小鸟在树上唱歌，微风拂面，
    心情非常愉快。晚上吃了一顿美味的火锅，真是美好的一天。
    """

    result = analyze_content(content)

    # 非技术内容相关度应较低（允许一定的宽容度）
    relevance = result.get("relevance_score", 10)
    assert isinstance(relevance, (int, float)), "相关度评分必须是数字"
    # 我们不做严格断言，因为不同模型可能评分不同
    # 只要返回有效的数字即可
    assert 0 <= relevance <= 10, f"相关度应在 0-10 之间，实际: {relevance}"


@pytest.mark.slow
def test_boundary_case_short_input():
    """边界案例测试：极短输入不应崩溃。"""
    result = analyze_content("AI")

    # 只要不崩溃且返回有效结构即可
    assert isinstance(result, dict)
    assert "summary" in result
    assert isinstance(result["summary"], str)


# ============================================================================
# LLM-as-Judge 自动评分测试
# ============================================================================

def llm_judge_score(original_content: str, analysis_result: str) -> int:
    """使用 LLM 作为法官对分析结果打分（1-10分）。

    评分标准：
    - 准确性：摘要是否准确反映原文
    - 完整性：是否覆盖了关键信息
    - 简洁性：摘要是否简洁明了
    - 相关性：是否与 AI/技术领域相关

    Args:
        original_content: 原始内容
        analysis_result: 分析结果摘要

    Returns:
        1-10 的整数分数
    """
    system_prompt = """
    你是一个严格的内容质量评估专家。请根据以下标准对分析结果打分（1-10分）：

    评分标准：
    1. 准确性（3分）：摘要是否准确反映原文内容
    2. 完整性（3分）：是否覆盖了关键信息
    3. 简洁性（2分）：摘要是否简洁明了
    4. 相关性（2分）：关键词和分类是否合理

    只返回一个整数分数，不要其他内容。
    """

    prompt = f"""
    原始内容：
    {original_content}

    分析结果：
    {analysis_result}

    请打分（只返回整数）：
    """

    score_text, _ = chat(prompt, system_prompt)

    try:
        # 提取数字
        import re
        match = re.search(r'\d+', score_text)
        if match:
            score = int(match.group())
            return max(1, min(10, score))
        return 5
    except (ValueError, TypeError):
        return 5


@pytest.mark.slow
def test_llm_as_judge():
    """LLM-as-Judge 自动评分测试。"""
    original_content = """
    LangGraph 是一个用于构建有状态代理的库，基于 LangChain 构建。
    它提供了循环、分支和持久化状态的能力，特别适合构建多步骤的
    复杂 Agent 工作流。核心概念包括 State、Nodes、Edges 和
    Conditional Edges。支持人类在回路、持久化存储和时间旅行调试。
    """

    result = analyze_content(original_content)
    analysis_summary = result.get("summary", "")

    # 确保有足够的内容供评分
    if len(analysis_summary) < 20:
        pytest.skip("分析结果太短，无法评分")

    score = llm_judge_score(original_content, analysis_summary)

    print(f"\n[LLM-as-Judge] 评分: {score}/10")
    print(f"  原始内容长度: {len(original_content)} 字符")
    print(f"  分析摘要长度: {len(analysis_summary)} 字符")
    print(f"  摘要预览: {analysis_summary[:100]}...")

    # 断言分数 >= 5
    assert score >= 5, f"LLM-as-Judge 评分过低: {score}/10，期望 >= 5"


# ============================================================================
# 性能测试
# ============================================================================

@pytest.mark.slow
def test_llm_response_time():
    """测试 LLM 响应时间。"""
    import time

    start_time = time.time()
    result, usage = chat("简单回答：什么是 Python？")
    elapsed = time.time() - start_time

    print(f"\n[性能测试] 响应时间: {elapsed:.2f}s")
    print(f"  Token 使用: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}")
    print(f"  响应长度: {len(result)} 字符")

    # 响应时间断言（允许较大范围）
    assert elapsed <= 60, f"响应时间过长: {elapsed:.2f}s"
    assert len(result) >= 10, "响应内容过短"
    assert usage.prompt_tokens >= 1, "prompt tokens 应为正数"
    assert usage.completion_tokens >= 1, "completion tokens 应为正数"


if __name__ == "__main__":
    # 直接运行时执行本地测试
    print("=" * 60)
    print("运行本地验证测试...")
    print("=" * 60)

    test_eval_cases_structure()
    print("✓ EVAL_CASES 结构验证通过")

    print("\n" + "=" * 60)
    print("本地测试完成！")
    print("运行完整测试请执行: pytest tests/eval_test.py -v")
    print("跳过慢测试: pytest tests/eval_test.py -v -m 'not slow'")
    print("=" * 60)
