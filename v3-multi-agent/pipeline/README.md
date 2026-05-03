# LLM Client 模块

统一的 LLM 调用客户端，支持 DeepSeek、Qwen、OpenAI 三种提供商。

## 快速开始

### 1. 环境配置

```bash
# 设置提供商（deepseek/qwen/openai，默认 deepseek）
export LLM_PROVIDER=deepseek

# 设置对应提供商的 API Key
export DEEPSEEK_API_KEY=your-key
export QWEN_API_KEY=your-key
export OPENAI_API_KEY=your-key

# 可选：覆盖默认模型
export LLM_MODEL=deepseek-chat
```

### 2. 基本使用

```python
from pipeline.model_client import quick_chat, create_provider

# 最简单的方式 - 一句话调用
response = quick_chat("你好，请介绍一下 Python")
print(response)

# 带系统提示
response = quick_chat(
    "解释量子计算",
    system_prompt="你是一位物理学专家，请用通俗易懂的语言解释。"
)
```

### 3. 高级用法

```python
from pipeline.model_client import (
    create_provider, chat_with_retry, 
    calculate_cost, estimate_tokens
)

# 创建提供商实例
provider = create_provider(
    provider='deepseek',
    model='deepseek-chat',
    timeout=60.0
)

# 发送消息
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is Python?"}
]

response = chat_with_retry(
    provider,
    messages,
    max_retries=3,
    timeout=60.0,
    temperature=0.7
)

print(f"Response: {response.content}")
print(f"Tokens used: {response.usage.total_tokens}")
print(f"Latency: {response.latency_ms:.1f}ms")

# 计算成本
cost = calculate_cost(
    response.usage.prompt_tokens,
    response.usage.completion_tokens,
    response.model
)
print(f"Cost: ${cost['total_cost']:.8f} USD")

# 估算 Token
estimated = estimate_tokens("Hello, this is a test.")
print(f"Estimated tokens: {estimated}")

# 关闭连接
provider.close()
```

## API 参考

### 核心类

- `LLMProvider`: 抽象基类，定义 LLM 提供商接口
- `OpenAICompatibleProvider`: OpenAI 兼容 API 实现
- `LLMResponse`: 响应数据结构
- `Usage`: Token 使用统计

### 便捷函数

- `create_provider()`: 创建提供商实例
- `quick_chat()`: 一句话调用 LLM
- `chat_with_retry()`: 带重试的聊天调用

### 工具函数

- `estimate_tokens()`: 估算 Token 数量
- `calculate_cost()`: 计算 API 调用成本
- `retry_with_exponential_backoff()`: 指数退避重试装饰器

## 支持的模型

| 提供商 | 模型 | 输入价格 | 输出价格 |
|--------|------|----------|----------|
| DeepSeek | deepseek-chat | $0.00014/1K | $0.00028/1K |
| Qwen | qwen-turbo | $0.0005/1K | $0.001/1K |
| OpenAI | gpt-3.5-turbo | $0.0005/1K | $0.0015/1K |

更多模型详见 `MODEL_PRICING` 字典。

## 错误处理

```python
from pipeline.model_client import create_provider, chat_with_retry
import httpx

try:
    provider = create_provider()
    response = chat_with_retry(provider, messages)
except KeyError as e:
    print(f"API key not found: {e}")
except httpx.HTTPStatusError as e:
    print(f"HTTP error: {e.response.status_code}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## 测试

```bash
# 运行测试
python pipeline/model_client.py
```

这会运行模块的内置测试，包括：
- Token 估算测试
- 成本计算测试
- 提供商配置测试
- 连接测试（需要 API key）
