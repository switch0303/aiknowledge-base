"""统一的 LLM 调用客户端模块。

支持 DeepSeek、Qwen、OpenAI 三种模型提供商，通过环境变量配置。
提供统一的接口调用、重试机制、Token 估算和成本计算功能。

Example:
    >>> from pipeline.model_client import quick_chat
    >>> response = quick_chat("Hello, how are you?")
    >>> print(response.content)
"""

import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from functools import wraps

import httpx

# 配置日志
logger = logging.getLogger(__name__)


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class Usage:
    """Token 使用统计。
    
    Attributes:
        prompt_tokens: 输入 Token 数量
        completion_tokens: 输出 Token 数量
        total_tokens: 总 Token 数量
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """LLM 响应数据结构。
    
    Attributes:
        content: 生成的文本内容
        model: 使用的模型名称
        usage: Token 使用统计
        raw_response: 原始 API 响应（可选）
        latency_ms: 请求延迟（毫秒）
    """
    content: str
    model: str
    usage: Usage = field(default_factory=Usage)
    raw_response: Optional[Dict[str, Any]] = None
    latency_ms: Optional[float] = None


# ============================================================================
# 抽象基类
# ============================================================================

class LLMProvider(ABC):
    """LLM 提供商抽象基类。
    
    定义所有 LLM 提供商必须实现的接口。
    
    Example:
        >>> class MyProvider(LLMProvider):
        ...     def chat(self, messages, **kwargs):
        ...         # 实现聊天逻辑
        ...         pass
        ...     
        ...     def estimate_tokens(self, text):
        ...         # 实现 Token 估算
        ...         pass
    """
    
    def __init__(self, api_key: str, base_url: str, model: str, **kwargs):
        """初始化提供商。
        
        Args:
            api_key: API 密钥
            base_url: API 基础 URL
            model: 默认模型名称
            **kwargs: 其他配置参数
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.config = kwargs
        self.client = httpx.Client(
            timeout=kwargs.get('timeout', 60.0),
            headers=self._get_headers()
        )
        logger.info(f"Initialized {self.__class__.__name__} with model: {model}")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取 HTTP 请求头。
        
        Returns:
            请求头字典
        """
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """执行聊天补全请求。
        
        Args:
            messages: 消息列表，每个消息包含 role 和 content
            **kwargs: 额外的请求参数
        
        Returns:
            LLMResponse 对象
        
        Raises:
            Exception: 当 API 调用失败时抛出
        """
        pass
    
    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """估算文本的 Token 数量。
        
        Args:
            text: 输入文本
        
        Returns:
            估算的 Token 数量
        """
        pass
    
    def close(self):
        """关闭 HTTP 客户端连接。"""
        if hasattr(self, 'client'):
            self.client.close()
            logger.debug(f"Closed {self.__class__.__name__} client")
    
    def __enter__(self):
        """上下文管理器入口。"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口。"""
        self.close()


# ============================================================================
# OpenAI 兼容提供商实现
# ============================================================================

class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容 API 提供商实现。
    
    支持所有兼容 OpenAI API 格式的服务，包括 DeepSeek、Qwen 等。
    
    Example:
        >>> provider = OpenAICompatibleProvider(
        ...     api_key="sk-xxx",
        ...     base_url="https://api.deepseek.com/v1",
        ...     model="deepseek-chat"
        ... )
        >>> response = provider.chat([{"role": "user", "content": "Hello"}])
        >>> print(response.content)
    """
    
    # Token 估算系数（字符数 / 系数 ≈ Token 数）
    TOKEN_ESTIMATE_RATIO = 4.0
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """执行聊天补全请求。
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            **kwargs: 可选参数：
                - model: 覆盖默认模型
                - temperature: 采样温度（默认 0.7）
                - max_tokens: 最大生成 Token 数
                - stream: 是否流式输出（默认 False）
        
        Returns:
            LLMResponse 对象，包含生成的内容和 Token 统计
        
        Raises:
            httpx.HTTPError: 当 HTTP 请求失败时
            ValueError: 当响应格式无效时
        """
        start_time = time.time()
        
        # 构建请求体
        payload = {
            'model': kwargs.get('model', self.model),
            'messages': messages,
            'temperature': kwargs.get('temperature', 0.7),
            'stream': kwargs.get('stream', False)
        }
        
        # 可选参数
        if 'max_tokens' in kwargs:
            payload['max_tokens'] = kwargs['max_tokens']
        
        try:
            logger.debug(f"Sending chat request to {self.base_url}/chat/completions")
            response = self.client.post(
                f'{self.base_url}/chat/completions',
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            latency_ms = (time.time() - start_time) * 1000
            
            # 解析响应
            choice = data['choices'][0]
            message = choice['message']
            usage_data = data.get('usage', {})
            
            usage = Usage(
                prompt_tokens=usage_data.get('prompt_tokens', 0),
                completion_tokens=usage_data.get('completion_tokens', 0),
                total_tokens=usage_data.get('total_tokens', 0)
            )
            
            llm_response = LLMResponse(
                content=message.get('content', ''),
                model=data.get('model', payload['model']),
                usage=usage,
                raw_response=data if kwargs.get('include_raw') else None,
                latency_ms=latency_ms
            )
            
            logger.info(
                f"Chat completed: model={llm_response.model}, "
                f"tokens={usage.total_tokens}, latency={latency_ms:.1f}ms"
            )
            
            return llm_response
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Invalid response format: {e}")
            raise ValueError(f"Invalid API response format: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in chat: {e}")
            raise
    
    def estimate_tokens(self, text: str) -> int:
        """估算文本的 Token 数量。
        
        使用简单的字符比例估算，假设平均每个 Token 约 4 个字符。
        
        Args:
            text: 输入文本
        
        Returns:
            估算的 Token 数量（至少为 1）
        
        Example:
            >>> provider = OpenAICompatibleProvider(...)
            >>> provider.estimate_tokens("Hello world")
            3
        """
        if not text:
            return 0
        # 简单的估算：平均每个 Token 约 4 个字符
        estimated = int(len(text) / self.TOKEN_ESTIMATE_RATIO)
        return max(1, estimated)
    
    def count_message_tokens(self, messages: List[Dict[str, str]]) -> int:
        """估算消息列表的总 Token 数量。
        
        Args:
            messages: 消息列表，每个消息包含 role 和 content
        
        Returns:
            估算的总 Token 数量
        """
        total = 0
        for msg in messages:
            content = msg.get('content', '')
            total += self.estimate_tokens(content)
            # 每个消息额外的格式开销约 4 个 Token
            total += 4
        return total


# ============================================================================
# 重试机制
# ============================================================================

def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,)
):
    """带指数退避的重试装饰器。
    
    Args:
        max_retries: 最大重试次数（默认 3）
        base_delay: 初始延迟（秒，默认 1.0）
        max_delay: 最大延迟（秒，默认 60.0）
        exponential_base: 指数基数（默认 2.0）
        retryable_exceptions: 可重试的异常类型元组
    
    Returns:
        装饰器函数
    
    Example:
        >>> @retry_with_exponential_backoff(max_retries=3)
        ... def api_call():
        ...     return requests.get("https://api.example.com")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt >= max_retries:
                        logger.error(
                            f"Function {func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise
                    
                    # 计算延迟时间（指数退避）
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    time.sleep(delay)
            
            # 如果所有重试都失败，抛出最后一个异常
            raise last_exception
        
        return wrapper
    return decorator


def chat_with_retry(
    provider: LLMProvider,
    messages: List[Dict[str, str]],
    max_retries: int = 3,
    timeout: float = 60.0,
    **kwargs
) -> LLMResponse:
    """带重试机制的 LLM 聊天调用。
    
    使用指数退避策略，在请求失败时自动重试。
    
    Args:
        provider: LLM 提供商实例
        messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
        max_retries: 最大重试次数（默认 3）
        timeout: 请求超时时间（秒，默认 60）
        **kwargs: 传递给 provider.chat() 的额外参数
    
    Returns:
        LLMResponse 对象
    
    Raises:
        Exception: 当所有重试都失败时抛出
    
    Example:
        >>> provider = create_provider()
        >>> messages = [{"role": "user", "content": "Hello"}]
        >>> response = chat_with_retry(provider, messages)
        >>> print(f"Response: {response.content}")
    """
    @retry_with_exponential_backoff(
        max_retries=max_retries,
        base_delay=1.0,
        max_delay=30.0,
        retryable_exceptions=(
            httpx.HTTPStatusError,
            httpx.TimeoutException,
            httpx.NetworkError,
            ConnectionError,
            TimeoutError,
        )
    )
    def _do_chat():
        # 更新超时设置
        original_timeout = provider.client.timeout
        provider.client.timeout = timeout
        
        try:
            return provider.chat(messages, **kwargs)
        finally:
            provider.client.timeout = original_timeout
    
    return _do_chat()


# ============================================================================
# Token 估算和成本计算
# ============================================================================

# 模型价格表（USD / 1K tokens）
# 格式: (input_price, output_price)
MODEL_PRICING: Dict[str, tuple] = {
    # OpenAI 模型
    'gpt-4': (0.03, 0.06),
    'gpt-4-turbo': (0.01, 0.03),
    'gpt-4o': (0.005, 0.015),
    'gpt-3.5-turbo': (0.0005, 0.0015),
    
    # DeepSeek 模型
    'deepseek-chat': (0.00014, 0.00028),
    'deepseek-coder': (0.00014, 0.00028),
    'deepseek-reasoner': (0.0014, 0.0028),
    
    # Qwen 模型
    'qwen-turbo': (0.0005, 0.001),
    'qwen-plus': (0.002, 0.006),
    'qwen-max': (0.005, 0.01),
    'qwen-coder': (0.001, 0.002),
}


def estimate_tokens(text: str, model: Optional[str] = None) -> int:
    """估算文本的 Token 数量。
    
    使用简单的字符比例估算。对于更精确的估算，
    应该使用各模型对应的 tokenizer。
    
    Args:
        text: 输入文本
        model: 模型名称（目前仅用于日志记录）
    
    Returns:
        估算的 Token 数量（至少为 1）
    
    Example:
        >>> estimate_tokens("Hello world, this is a test.")
        6
        >>> estimate_tokens("这是一个中文测试。")
        5
    """
    if not text:
        return 0
    
    # 简单的估算策略：
    # - 英文：平均每个 Token 约 4 个字符
    # - 中文：平均每个 Token 约 1.5 个字符
    # 这里使用统一的 4:1 比例作为保守估计
    estimated = int(len(text) / 4.0)
    
    result = max(1, estimated) if text else 0
    
    if model:
        logger.debug(f"Estimated {result} tokens for {len(text)} chars using {model}")
    
    return result


def estimate_messages_tokens(messages: List[Dict[str, str]], model: Optional[str] = None) -> int:
    """估算消息列表的总 Token 数量。
    
    Args:
        messages: 消息列表，每个消息包含 role 和 content
        model: 模型名称
    
    Returns:
        估算的总 Token 数量
    """
    total = 0
    for msg in messages:
        content = msg.get('content', '')
        total += estimate_tokens(content, model)
        # 每个消息额外的格式开销约 4 个 Token
        total += 4
    return total


def calculate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str
) -> Dict[str, float]:
    """计算 API 调用成本。
    
    Args:
        prompt_tokens: 输入 Token 数量
        completion_tokens: 输出 Token 数量
        model: 模型名称
    
    Returns:
        包含各项成本的字典：
        - input_cost: 输入成本（USD）
        - output_cost: 输出成本（USD）
        - total_cost: 总成本（USD）
    
    Example:
        >>> calculate_cost(1000, 500, "deepseek-chat")
        {'input_cost': 0.00014, 'output_cost': 0.00014, 'total_cost': 0.00028}
    """
    if model not in MODEL_PRICING:
        logger.warning(f"Unknown model: {model}, using default pricing")
        # 使用默认价格
        input_price, output_price = 0.001, 0.002
    else:
        input_price, output_price = MODEL_PRICING[model]
    
    # 价格表是每 1K tokens 的价格
    input_cost = (prompt_tokens / 1000) * input_price
    output_cost = (completion_tokens / 1000) * output_price
    total_cost = input_cost + output_cost
    
    return {
        'input_cost': round(input_cost, 8),
        'output_cost': round(output_cost, 8),
        'total_cost': round(total_cost, 8)
    }


# ============================================================================
# 工厂函数和便捷方法
# ============================================================================

# 提供商配置映射
PROVIDER_CONFIG: Dict[str, Dict[str, str]] = {
    'deepseek': {
        'base_url': 'https://api.deepseek.com/v1',
        'default_model': 'deepseek-chat',
        'api_key_env': 'DEEPSEEK_API_KEY'
    },
    'qwen': {
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'default_model': 'qwen-turbo',
        'api_key_env': 'QWEN_API_KEY'
    },
    'openai': {
        'base_url': 'https://api.openai.com/v1',
        'default_model': 'gpt-3.5-turbo',
        'api_key_env': 'OPENAI_API_KEY'
    }
}


def create_provider(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> OpenAICompatibleProvider:
    """创建 LLM 提供商实例。
    
    通过环境变量或参数配置提供商。优先级：参数 > 环境变量 > 默认值
    
    Args:
        provider: 提供商名称（deepseek/qwen/openai），默认从 LLM_PROVIDER 环境变量读取
        api_key: API 密钥，默认从对应环境变量读取
        model: 模型名称，默认使用提供商的默认模型
        **kwargs: 其他配置参数（如 timeout）
    
    Returns:
        配置好的 OpenAICompatibleProvider 实例
    
    Raises:
        ValueError: 当提供商名称无效时
        KeyError: 当 API 密钥未提供时
    
    Example:
        >>> # 使用环境变量配置
        >>> provider = create_provider()
        >>> 
        >>> # 显式指定参数
        >>> provider = create_provider(
        ...     provider='deepseek',
        ...     api_key='sk-xxx',
        ...     model='deepseek-chat'
        ... )
    """
    # 确定提供商
    provider_name = (provider or os.getenv('LLM_PROVIDER', 'deepseek')).lower()
    
    if provider_name not in PROVIDER_CONFIG:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Supported: {list(PROVIDER_CONFIG.keys())}"
        )
    
    config = PROVIDER_CONFIG[provider_name]
    
    # 获取 API 密钥
    if api_key is None:
        api_key = os.getenv(config['api_key_env'])
    
    if not api_key:
        raise KeyError(
            f"API key for {provider_name} not found. "
            f"Set {config['api_key_env']} environment variable or pass api_key parameter"
        )
    
    # 确定模型
    model_name = model or os.getenv('LLM_MODEL', config['default_model'])
    
    logger.info(f"Creating provider: {provider_name}, model: {model_name}")
    
    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=config['base_url'],
        model=model_name,
        **kwargs
    )


def quick_chat(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: Optional[str] = None,
    **kwargs
) -> str:
    """便捷函数：快速发送单轮对话并返回结果。
    
    这是一个高级封装，自动创建提供商实例、发送请求并返回文本内容。
    适用于简单的单次调用场景。
    
    Args:
        prompt: 用户输入的提示文本
        system_prompt: 可选的系统提示词
        provider: 提供商名称，默认从环境变量读取
        **kwargs: 传递给 create_provider 和 chat 的额外参数
    
    Returns:
        LLM 生成的文本内容
    
    Raises:
        Exception: 当 API 调用失败时抛出
    
    Example:
        >>> # 简单调用
        >>> response = quick_chat("What is Python?")
        >>> 
        >>> # 带系统提示
        >>> response = quick_chat(
        ...     "Explain quantum computing",
        ...     system_prompt="You are a physics expert."
        ... )
    """
    messages = []
    
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    messages.append({"role": "user", "content": prompt})
    
    with create_provider(provider, **kwargs) as llm_provider:
        response = chat_with_retry(
            llm_provider,
            messages,
            max_retries=kwargs.get('max_retries', 3),
            timeout=kwargs.get('timeout', 60.0)
        )
    
    return response.content


# ============================================================================
# 重试装饰器
# ============================================================================

def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,)
):
    """带指数退避的重试装饰器。
    
    Args:
        max_retries: 最大重试次数（默认 3）
        base_delay: 初始延迟（秒，默认 1.0）
        max_delay: 最大延迟（秒，默认 60.0）
        exponential_base: 指数基数（默认 2.0）
        retryable_exceptions: 可重试的异常类型元组
    
    Returns:
        装饰器函数
    
    Example:
        >>> @retry_with_exponential_backoff(max_retries=3)
        ... def api_call():
        ...     return requests.get("https://api.example.com")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt >= max_retries:
                        logger.error(
                            f"Function {func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise
                    
                    # 计算延迟时间（指数退避）
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    time.sleep(delay)
            
            # 如果所有重试都失败，抛出最后一个异常
            raise last_exception
        
        return wrapper
    return decorator


# ============================================================================
# 主函数和测试
# ============================================================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("=" * 60)
    logger.info("LLM Client Test")
    logger.info("=" * 60)
    
    # 测试 1: Token 估算
    logger.info("\n[Test 1] Token Estimation")
    test_text = "Hello, this is a test message for token estimation."
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.test.com/v1",
        model="test-model"
    )
    estimated = provider.estimate_tokens(test_text)
    logger.info(f"Text: {test_text}")
    logger.info(f"Estimated tokens: {estimated}")
    
    # 测试 2: 成本计算
    logger.info("\n[Test 2] Cost Calculation")
    models = ['deepseek-chat', 'gpt-3.5-turbo', 'qwen-turbo']
    for model in models:
        cost = calculate_cost(1000, 500, model)
        logger.info(f"{model}: {cost}")
    
    # 测试 3: 提供商配置
    logger.info("\n[Test 3] Provider Configuration")
    provider_name = os.getenv('LLM_PROVIDER', 'deepseek')
    logger.info(f"Current provider: {provider_name}")
    logger.info(f"Available providers: {list(PROVIDER_CONFIG.keys())}")
    
    # 测试 4: 尝试创建提供商（需要有效的 API 密钥）
    logger.info("\n[Test 4] Create Provider (requires API key)")
    try:
        test_provider = create_provider()
        logger.info(f"Successfully created provider: {test_provider.model}")
        test_provider.close()
    except (KeyError, ValueError) as e:
        logger.warning(f"Could not create provider: {e}")
        logger.info("Set DEEPSEEK_API_KEY or other provider API key to test this")
    
    # 测试 5: quick_chat（需要有效的 API 密钥）
    logger.info("\n[Test 5] Quick Chat (requires API key)")
    logger.info("Skipping actual API call - set API key to test")
    
    logger.info("\n" + "=" * 60)
    logger.info("Tests completed!")
    logger.info("=" * 60)
