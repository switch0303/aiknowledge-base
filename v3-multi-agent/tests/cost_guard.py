"""多 Agent 预算守卫模块。

提供 LLM 调用成本追踪、预算监控和报告生成功能，
支持三重保护机制：预警、超限检测、按节点统计。
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """预算超出异常。

    当 LLM 调用总成本超出预算时抛出。
    """
    pass


@dataclass
class CostRecord:
    """单次 LLM 调用成本记录。"""

    timestamp: str
    """调用时间戳，ISO 8601 格式。"""

    node_name: str
    """调用节点名称，标识哪个 Agent 产生的调用。"""

    prompt_tokens: int
    """输入 Token 数量。"""

    completion_tokens: int
    """输出 Token 数量。"""

    cost_yuan: float
    """本次调用成本（人民币元）。"""

    model: str
    """使用的模型名称。"""


class CostGuard:
    """多 Agent 预算守卫。

    实现三重保护机制：
    1. 成本追踪：记录每次 LLM 调用的 Token 用量和成本
    2. 预算监控：接近预算时预警，超出时抛出异常
    3. 报告生成：按节点分组统计成本，生成详细报告
    """

    def __init__(
        self,
        budget_yuan: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
    ) -> None:
        """初始化预算守卫。

        Args:
            budget_yuan: 总预算（人民币元），默认 1.0 元
            alert_threshold: 预警阈值（0-1），默认 0.8（80%）
            input_price_per_million: 输入 Token 单价（元/百万），默认 1.0
            output_price_per_million: 输出 Token 单价（元/百万），默认 2.0
        """
        self.budget_yuan = budget_yuan
        self.alert_threshold = alert_threshold
        self.input_price_per_million = input_price_per_million
        self.output_price_per_million = output_price_per_million

        self._records: List[CostRecord] = []
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_cost_yuan: float = 0.0

    def record(
        self,
        node_name: str,
        usage: Dict[str, int],
        model: str = "",
    ) -> None:
        """记录一次 LLM 调用的 Token 用量。

        Args:
            node_name: 调用节点名称
            usage: Token 用量字典，格式 {"prompt_tokens": int, "completion_tokens": int}
            model: 使用的模型名称，默认为空
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        input_cost = (prompt_tokens / 1_000_000) * self.input_price_per_million
        output_cost = (completion_tokens / 1_000_000) * self.output_price_per_million
        cost_yuan = input_cost + output_cost

        record = CostRecord(
            timestamp=datetime.utcnow().isoformat() + "Z",
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost_yuan,
            model=model,
        )

        self._records.append(record)
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens
        self._total_cost_yuan += cost_yuan

        logger.debug(
            "Recorded LLM call: node=%s, prompt=%d, completion=%d, cost=%.6f yuan",
            node_name,
            prompt_tokens,
            completion_tokens,
            cost_yuan,
        )

    def check(self) -> Dict:
        """检查预算状态。

        Returns:
            包含预算状态的字典

        Raises:
            BudgetExceededError: 当总成本超出预算时抛出
        """
        usage_ratio = self._total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 0.0

        if self._total_cost_yuan >= self.budget_yuan:
            message = f"Budget exceeded: used {self._total_cost_yuan:.4f} yuan, budget {self.budget_yuan:.4f} yuan"
            logger.error(message)
            raise BudgetExceededError(message)

        if usage_ratio >= self.alert_threshold:
            status = "warning"
            message = f"Approaching budget limit: {usage_ratio*100:.1f}% used"
            logger.warning(message)
        else:
            status = "ok"
            message = "Budget usage within limit"

        return {
            "status": status,
            "total_cost": self._total_cost_yuan,
            "budget": self.budget_yuan,
            "usage_ratio": usage_ratio,
            "message": message,
        }

    def get_report(self) -> Dict:
        """生成成本报告（按节点分组统计。

        Returns:
            包含总成本、总Token统计的报告字典
        """
        node_stats: Dict[str, Dict] = defaultdict(
            lambda: {
                "call_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_yuan": 0.0,
            }
        )

        for record in self._records:
            stats = node_stats[record.node_name]
            stats["call_count"] += 1
            stats["prompt_tokens"] += record.prompt_tokens
            stats["completion_tokens"] += record.completion_tokens
            stats["cost_yuan"] += record.cost_yuan

        usage_ratio = self._total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 0.0

        return {
            "summary": {
                "total_calls": len(self._records),
                "total_prompt_tokens": self._total_prompt_tokens,
                "total_completion_tokens": self._total_completion_tokens,
                "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
                "total_cost_yuan": self._total_cost_yuan,
                "budget_yuan": self.budget_yuan,
                "usage_ratio": usage_ratio,
                "alert_threshold": self.alert_threshold,
            },
            "by_node": dict(node_stats),
            "records": [asdict(r) for r in self._records],
        }

    def save_report(self, path: Optional[str] = None) -> str:
        """保存成本报告到 JSON 文件。

        Args:
            path: 保存路径，默认为 "cost_report_YYYYMMDD_HHMMSS.json

        Returns:
            实际保存的文件路径
        """
        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"cost_report_{timestamp}.json"

        report = self.get_report()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info("Cost report saved to %s", path)
        return path

    @property
    def total_prompt_tokens(self) -> int:
        """总输入 Token 数量。"""
        return self._total_prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        """总输出 Token 数量。"""
        return self._total_completion_tokens

    @property
    def total_cost_yuan(self) -> float:
        """总成本（人民币元）。"""
        return self._total_cost_yuan


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("CostGuard 测试套件")
    print("=" * 60)

    print("\n【测试 1】成本追踪正确")
    print("-" * 40)
    guard = CostGuard(budget_yuan=1.0)
    guard.record(
        "analyzer",
        {"prompt_tokens": 100000, "completion_tokens": 50000},
        "gpt-4",
    )
    expected_cost = (100000 / 1e6) * 1.0 + (50000 / 1e6) * 2.0
    print(f"  预期成本: {expected_cost:.4f} 元")
    print(f"  实际成本: {guard.total_cost_yuan:.4f} 元")
    print(f"  总输入 Token: {guard.total_prompt_tokens}")
    print(f"  总输出 Token: {guard.total_completion_tokens}")
    assert abs(guard.total_cost_yuan - expected_cost) < 0.0001
    assert guard.total_prompt_tokens == 100000
    assert guard.total_completion_tokens == 50000
    print("  ✓ 成本追踪测试通过")

    print("\n【测试 2】预警阈值触发")
    print("-" * 40)
    guard2 = CostGuard(budget_yuan=1.0, alert_threshold=0.5)
    guard2.record(
        "collector",
        {"prompt_tokens": 400000, "completion_tokens": 100000},
    )
    result = guard2.check()
    print(f"  预算使用: {result['usage_ratio']*100:.1f}%")
    print(f"  状态: {result['status']}")
    print(f"  消息: {result['message']}")
    assert result["status"] == "warning"
    print("  ✓ 预警阈值测试通过")

    print("\n【测试 3】预算超限检测")
    print("-" * 40)
    guard3 = CostGuard(budget_yuan=0.1)
    guard3.record(
        "organizer",
        {"prompt_tokens": 200000, "completion_tokens": 100000},
    )
    try:
        guard3.check()
        print("  ✗ 未抛出 BudgetExceededError 异常")
        assert False
    except BudgetExceededError as e:
        print(f"  正确抛出异常: {e}")
        print("  ✓ 预算超限测试通过")

    print("\n【测试 4】按节点统计报告")
    print("-" * 40)
    guard4 = CostGuard(budget_yuan=10.0)
    guard4.record("analyzer", {"prompt_tokens": 10000, "completion_tokens": 5000})
    guard4.record("collector", {"prompt_tokens": 5000, "completion_tokens": 2000})
    guard4.record("analyzer", {"prompt_tokens": 8000, "completion_tokens": 4000})
    report = guard4.get_report()
    print(f"  总调用次数: {report['summary']['total_calls']}")
    print(f"  节点列表: {list(report['by_node'].keys())}")
    print(f"  analyzer 调用次数: {report['by_node']['analyzer']['call_count']}")
    assert report["summary"]["total_calls"] == 3
    assert "analyzer" in report["by_node"]
    assert report["by_node"]["analyzer"]["call_count"] == 2
    print("  ✓ 节点统计测试通过")

    print("\n【测试 5】报告保存")
    print("-" * 40)
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_path = f.name
    saved_path = guard4.save_report(temp_path)
    assert os.path.exists(saved_path)
    with open(saved_path, "r", encoding="utf-8") as f:
        loaded_report = json.load(f)
    assert loaded_report["summary"]["total_calls"] == 3
    os.unlink(saved_path)
    print(f"  报告保存路径: {saved_path}")
    print("  ✓ 报告保存测试通过")

    print("\n" + "=" * 60)
    print("所有测试通过! ✓")
    print("=" * 60)
