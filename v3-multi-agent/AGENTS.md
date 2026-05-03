# AI 知识库助手 - AGENTS.md

## 1. 项目概述

AI 知识库助手是一个自动化情报采集与分发系统：自动监控 GitHub Trending 和 Hacker News 获取 AI/LLM/Agent 领域最新技术动态，通过 AI 进行内容分析和结构化处理，最终输出到 Telegram 和飞书等多渠道。核心目标是帮助用户及时掌握 AI 领域前沿技术，减少信息筛选成本。

---

## 2. 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 运行环境 | Python 3.12 | 主开发语言 |
| AI 框架 | OpenCode + 国产大模型 | Agent 编排与 LLM 调用 |
| 工作流引擎 | LangGraph | 多 Agent 工作流定义 |
| 数据采集 | OpenClaw | 网页抓取与 API 集成 |
| 数据存储 | JSON 文件 | 知识条目持久化 |
| 分发渠道 | Telegram Bot / 飞书 Webhook | 消息推送 |

---

## 3. 编码规范

### 3.1 命名规范
- **变量/函数**：snake_case（如 `fetch_github_trending`）
- **类名**：PascalCase（如 `KnowledgeCollector`）
- **常量**：UPPER_SNAKE_CASE（如 `MAX_RETRY_COUNT`）
- **模块名**：snake_case（如 `data_fetcher.py`）

### 3.2 代码风格
- 严格遵循 PEP 8 规范
- 使用 4 空格缩进（禁用 Tab）
- 行长度限制 88 字符（Black 格式化标准）
- 文件末尾保留空行

### 3.3 文档规范
- 所有公共函数/类必须使用 Google 风格 docstring
- 复杂逻辑添加行内注释
- 模块顶部包含功能说明

```python
def analyze_content(content: str, max_summary: int = 200) -> dict:
    """分析内容并生成结构化摘要。

    Args:
        content: 原始文本内容
        max_summary: 摘要最大字数，默认 200

    Returns:
        包含摘要和标签的分析结果字典

    Raises:
        ValueError: 当内容为空时抛出
    """
    pass
```

### 3.4 日志规范（重要）
- **禁止裸 `print()` 输出**
- 统一使用标准 `logging` 模块
- 日志级别使用规范：DEBUG（开发调试）/ INFO（正常运行）/ WARNING（需要注意）/ ERROR（需处理错误）

```python
import logging

logger = logging.getLogger(__name__)

# 正确做法
logger.info("Successfully fetched %d items from GitHub", count)
logger.error("Failed to fetch data: %s", str(e))

# 禁止做法
print("Fetched data")  # ❌ 禁止
```

---

## 4. 项目结构

```
aiknowledge-base/
├── .opencode/              # OpenCode 配置目录
│   ├── agents/             # Agent 定义文件
│   │   ├── collector.yaml      # 采集 Agent
│   │   ├── analyzer.yaml       # 分析 Agent
│   │   └── organizer.yaml      # 整理 Agent
│   └── skills/             # Skill 工具库
│       ├── fetch/              # 数据获取技能
│       ├── parse/              # 内容解析技能
│       └── notify/             # 通知推送技能
├── knowledge/              # 知识库目录
│   ├── raw/                # 原始采集数据（未处理）
│   │   └── 2025-01/
│   │       └── github_trending_20250115.json
│   └── articles/           # 结构化文章（已处理）
│       └── 2025-01/
│           └── article_001.json
├── scripts/                # 独立脚本
├── tests/                  # 测试目录
├── AGENTS.md               # 本文件
└── requirements.txt        # 依赖清单
```

---

## 5. 知识条目 JSON 格式

### 5.1 原始数据格式（raw/）

```json
{
  "id": "github-20250115-001",
  "source": "github",
  "source_url": "https://github.com/username/repo",
  "title": "Awesome-LLM-Agents",
  "content": "...原始描述文本...",
  "metadata": {
    "stars": 1523,
    "language": "Python",
    "author": "username"
  },
  "collected_at": "2025-01-15T08:30:00Z",
  "raw_html": "...可选原始HTML..."
}
```

### 5.2 知识文章格式（articles/）

```json
{
  "id": "github-20250115-001",
  "title": "Awesome-LLM-Agents：LLM Agent 资源精选列表",
  "source_url": "https://github.com/username/repo",
  "source_type": "github",
  "summary": "一个精心整理的 LLM Agent 相关资源列表，包含论文、工具、框架...",
  "tags": ["agent", "llm", "awesome-list", "resources"],
  "category": "tools",
  "content_en": "English content...",
  "content_zh": "中文内容...",
  "status": "pending",
  "priority": "high",
  "collected_at": "2025-01-15T08:30:00Z",
  "processed_at": "2025-01-15T09:15:00Z",
  "published_at": null,
  "channels": ["telegram", "feishu"]
}
```

### 5.3 字段说明

| 字段 | 类型 | 说明 | 状态值 |
|------|------|------|--------|
| `id` | string | 唯一标识符 | - |
| `title` | string | 文章标题 | - |
| `source_url` | string | 原始链接 | - |
| `source_type` | string | 来源类型 | github / hackernews |
| `summary` | string | AI 生成摘要 | - |
| `tags` | array | AI 提取标签 | - |
| `category` | string | 分类 | paper / tool / framework / news |
| `status` | string | 处理状态 | pending / approved / rejected / published |
| `priority` | string | 优先级 | high / medium / low |
| `collected_at` | string | 采集时间（ISO 8601） | - |
| `processed_at` | string | 处理完成时间 | - |
| `published_at` | string | 发布时间 | - |
| `channels` | array | 目标分发渠道 | telegram / feishu |

---

## 6. Agent 角色概览

| Agent | 职责 | 输入 | 输出 | 触发方式 |
|-------|------|------|------|----------|
| **采集 Agent**<br>`collector` | 从 GitHub/HN 抓取原始数据 | - 时间调度<br>- 手动触发 | raw/*.json | 定时任务（每小时） |
| **分析 Agent**<br>`analyzer` | AI 分析内容、生成摘要标签 | raw/*.json | articles/*.json | 文件监听/新数据触发 |
| **整理 Agent**<br>`organizer` | 审核、去重、入分发队列 | articles/*.json | 更新 status | 人工审核后 |

### 6.1 Agent 工作流

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  采集 Agent  │ --> │  分析 Agent  │ --> │  整理 Agent  │ --> │  分发模块   │
│  Collector  │     │  Analyzer   │     │  Organizer  │     │  Distributor│
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                    │                   │                     │
      ▼                    ▼                   ▼                     ▼
   raw/*.json        articles/*.json      status=pending      Telegram/Feishu
```

---

## 7. 红线（绝对禁止操作）

以下操作**严禁执行**，违反可能导致数据丢失、安全风险或系统故障：

### 7.1 数据安全
- **禁止**直接删除 `knowledge/` 目录下任何 JSON 文件（如需删除必须通过整理 Agent 标记废弃）
- **禁止**修改知识条目的 `id` 字段（会破坏数据一致性）
- **禁止**在代码中硬编码 API Key、Token 等凭证（必须使用环境变量）
- **禁止**将原始采集的 HTML 数据提交到 Git（已配置 .gitignore）

### 7.2 代码规范
- **禁止**使用裸 `print()` 输出（统一使用 logging）
- **禁止**提交包含调试代码的文件（如 `if __name__ == "__main__":` 测试代码）
- **禁止**在没有 try-except 的情况下调用外部 API
- **禁止**使用全局变量存储状态（使用类或依赖注入）

### 7.3 运行安全
- **禁止**在主分支直接推送未经测试的代码
- **禁止**连续高频调用 API（必须实现指数退避重试）
- **禁止**在生产环境运行带有 `--debug` 标志的程序
- **禁止**手动修改 `knowledge/` 下的 JSON 文件状态字段（必须通过 Agent 接口）

### 7.4 合规要求
- **禁止**采集或存储个人信息（PII）
- **禁止**绕过目标网站的 robots.txt 限制
- **禁止**伪造 User-Agent 进行恶意爬取
- **禁止**将采集数据用于商业用途（遵循原始内容协议）

---

## 8. 快速开始

### 8.1 环境准备

```bash
# 创建虚拟环境
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate    # Windows

# 安装依赖
pip install -r requirements.txt
```

### 8.2 配置环境变量

```bash
export AIKB_LLM_API_KEY="your-api-key"
export AIKB_TELEGRAM_BOT_TOKEN="your-bot-token"
export AIKB_FEISHU_WEBHOOK_URL="your-webhook-url"
```

### 8.3 运行采集

```bash
# 手动触发采集
opencode run agent collector

# 手动触发分析
opencode run agent analyzer
```

---

## 9. 附录

### 9.1 相关文档
- [OpenCode Documentation](https://docs.opencode.ai)
- [LangGraph Concepts](https://langchain-ai.github.io/langgraph/concepts/)
- [PEP 8 Style Guide](https://pep8.org/)

### 9.2 更新日志
- 2025-01-15: 初始版本，定义核心架构和规范

---

**注意**：本文档由 OpenCode Agent 生成，人工修改时请保持格式一致性。
