"""Supervisor 监督模式实现。

Worker Agent 执行任务并输出 JSON 分析报告，
Supervisor Agent 对输出进行质量审核，
不通过则带反馈重做，最多 3 轮。

Example:
    >>> from patterns.supervisor import supervisor
    >>> result = supervisor("分析 AI Agent 领域的发展趋势")
    >>> print(result)
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional

# 将项目根目录添加到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.model_client import create_provider, chat_with_retry

logger = logging.getLogger(__name__)


# ============================================================================
# 辅助函数：chat 和 chat_json
# ============================================================================

def chat(prompt: str, system_prompt: Optional[str] = None) -> Tuple[str, Dict]:
    """调用 LLM 并返回 (text, usage) 元组。

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词

    Returns:
        (response_text, usage_dict) 元组
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        with create_provider() as llm_provider:
            response = chat_with_retry(llm_provider, messages, max_retries=2)
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            return response.content, usage
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return f"调用 LLM 失败: {str(e)}", {}


def chat_json(prompt: str, system_prompt: Optional[str] = None) -> Tuple[Dict, Dict]:
    """调用 LLM 并解析 JSON 响应。

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词

    Returns:
        (parsed_json, usage_dict) 元组
    """
    if system_prompt is None:
        system_prompt = "你是一个 JSON 输出助手。只输出合法的 JSON，不要添加任何解释或 markdown 标记。"
    
    text, usage = chat(prompt, system_prompt)
    
    try:
        return json.loads(text), usage
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}, text: {text[:200]}")
        return {"error": "JSON 解析失败", "raw_text": text}, usage


# ============================================================================
# Worker Agent
# ============================================================================

WORKER_SYSTEM_PROMPT = """
你是一个专业的分析专家。请根据用户的任务要求，输出一份结构化的分析报告。

要求：
1. 输出必须是严格的 JSON 格式，不要添加任何额外文字说明
2. 必须包含以下字段：
   - summary: 简短的摘要
   - key_points: 关键要点列表（数组）
   - analysis: 详细分析内容
   - conclusion: 结论
   - recommendations: 建议列表（数组）
3. 内容要准确、深入，有深度
4. 语言使用中文

输出

JSON 格式示例：
{
  "summary": "摘要内容",
  "key_points": ["要点1", "要点2", "要点3"],
  "analysis": "详细分析...",
  "conclusion": "结论...",
  "recommendations": ["建议1", "建议2"]
}
"""


def worker_agent(task: str, feedback: str = "") -> Dict:
    """Worker Agent：接收任务，输出 JSON 格式的分析报告。

    Args:
        task: 任务描述
        feedback: 上一轮的反馈意见（如果有）

    Returns:
        分析报告字典
    """
    prompt = f"任务：{task}"
    
    if feedback:
        prompt += f"\n\n上一轮的审核反馈意见，请根据反馈改进你的输出：\n{feedback}"
    
    prompt += "\n\n请输出 JSON 格式的分析报告。"
    
    logger.info(f"Worker executing task: {task[:50]}...")
    
    result, usage = chat_json(prompt, WORKER_SYSTEM_PROMPT)
    
    logger.info(f"Worker completed, tokens: {usage.get('total_tokens', 0)}")
    
    return result


# ============================================================================
# Supervisor Agent
# ============================================================================

SUPERVISOR_SYSTEM_PROMPT = """
你是一个严格的质量审核员。请对分析报告进行质量审核。

审核维度（每项 1-10 分）：
1. 准确性：内容是否准确、可靠
2. 深度：分析是否深入、有见地
3. 格式：JSON 格式是否完整、符合要求

输出必须是严格的 JSON 格式，包含以下字段：
- passed: 布尔值，是否通过审核（总分 >= 7 则通过）
- score: 总分（0-10）
- feedback: 详细的反馈意见，说明优点和改进建议

只输出 JSON，不要添加任何其他内容。

JSON 格式示例：
{
  "passed": true,
  "score": 8,
  "feedback": "分析准确，内容深入，格式完整。建议增加更多数据支撑。"
}
"""


def supervisor_agent(report: Dict) -> Dict:
    """Supervisor Agent：对 Worker 的输出进行质量审核。

    Args:
        report: Worker 输出的分析报告

    Returns:
        审核结果字典: {"passed": bool, "score": int, "feedback": str}
    """
    prompt = f"请审核以下分析报告：\n\n{json.dumps(report, ensure_ascii=False, indent=2)}"
    
    logger.info("Supervisor reviewing report...")
    
    result, usage = chat_json(prompt, SUPERVISOR_SYSTEM_PROMPT)
    
    # 确保字段存在
    if "passed" not in result:
        result["passed"] = result.get("score", 0) >= 7
    if "score" not in result:
        result["score"] = 0
    if "feedback" not in result:
        result["feedback"] = "审核结果格式异常"
    
    logger.info(f"Supervisor review: score={result['score']}, passed={result['passed']}")
    
    return result


# ============================================================================
# Supervisor 主函数
# ============================================================================

def supervisor(task: str, max_retries: int = 3) -> Dict:
    """Supervisor 监督模式主函数。

    审核循环：
    - 通过（score >= 7）→ 返回结果
    - 不通过 → 带反馈重做（最多 max_retries 轮）
    - 超过最大重试次数 → 强制返回 + 警告

    Args:
        task: 任务描述
        max_retries: 最大重试次数（包括第一次尝试

    Returns:
        结果字典，包含：
        - output: 最终的分析报告
        - attempts: 尝试次数
        - final_score: 最终得分
        - warning: 警告信息（可选）
        - history: 每轮的历史记录
    """
    logger.info(f"Starting supervisor task: {task[:50]}..., max_retries={max_retries}")
    
    history = []
    feedback = ""
    final_output = None
    final_score = 0
    warning = None
    
    for attempt in range(1, max_retries + 1):
        logger.info(f"Attempt {attempt}/{max_retries}")
        
        # Worker 执行任务
        worker_output = worker_agent(task, feedback)
        history.append({
            "attempt": attempt,
            "output": worker_output,
            "feedback_given": feedback
        })
        
        # Supervisor 审核
        review = supervisor_agent(worker_output)
        history[-1]["review"] = review
        
        final_output = worker_output
        final_score = review.get("score", 0)
        feedback = review.get("feedback", "")
        
        # 检查是否通过
        if review.get("passed", False) and final_score >= 7:
            logger.info(f"Task passed on attempt {attempt}, score={final_score}")
            break
        
        logger.warning(f"Task failed on attempt {attempt}, score={final_score}, feedback: {feedback[:100]}...")
        
        # 如果不是最后一轮，继续重试
        if attempt < max_retries:
            continue
        
        # 最后一轮仍不通过
        if attempt == max_retries:
            warning = f"警告：经过 {max_retries} 轮审核后仍未达到质量要求，强制返回结果。最终得分：{final_score}"
            logger.warning(warning)
    
    result = {
        "output": final_output,
        "attempts": len(history),
        "final_score": final_score,
        "history": history
    }
    
    if warning:
        result["warning"] = warning
    
    logger.info(f"Supervisor task completed: attempts={result['attempts']}, final_score={final_score}")
    
    return result


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 如果有命令行参数，使用参数作为任务
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        print(f"任务: {task}")
        print("=" * 60)
        result = supervisor(task, max_retries=3)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)
    
    # 否则运行默认测试
    print("=" * 60)
    print("Supervisor 监督模式测试")
    print("=" * 60)
    
    test_task = "分析 AI Agent 领域的发展趋势和未来方向"
    
    print(f"\n测试任务: {test_task}")
    print("-" * 60)
    
    result = supervisor(test_task, max_retries=3)
    
    print("\n" + "=" * 60)
    print("最终结果")
    print("=" * 60)
    print(f"尝试次数: {result['attempts']}")
    print(f"最终得分: {result['final_score']}")
    if "warning" in result:
        print(f"警告: {result['warning']}")
    print("\n分析报告:")
    print(json.dumps(result["output"], ensure_ascii=False, indent=2))
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
