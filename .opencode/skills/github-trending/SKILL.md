---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# GitHub Trending 采集技能

## 使用场景

当用户要求采集 GitHub 热门开源项目时，调用此技能。该技能专注于 AI/LLM/Agent 领域的技术动态采集，帮助用户及时掌握前沿技术动态。

## 执行步骤

### 第 1 步：搜索热门仓库

使用 GitHub API 或 WebFetch 工具获取 GitHub Trending 页面数据：
- 访问 `https://github.com/trending` 获取本周热门
- 访问 `https://github.com/trending/python` 获取 Python 语言热门
- 可选：使用 GitHub API `https://api.github.com/search/repositories?q=...&sort=stars`

### 第 2 步：提取项目信息

解析 HTML/API 响应，提取每个项目的关键信息：
- `name`: 项目名称（owner/repo 格式）
- `url`: 项目完整 URL
- `description`: 项目描述
- `stars`: Star 数量
- `language`: 编程语言
- `topics`: 项目主题标签数组

### 第 3 步：过滤筛选

**纳入条件**（满足任一即可）：
- 标题或描述包含 AI 相关关键词：AI, LLM, Agent, GPT, Claude, Gemini, Neural, Deep Learning, Machine Learning
- 属于 AI/LLM 相关主题标签：machine-learning, artificial-intelligence, llm, gpt, agent, chatbot, langchain, etc.

**排除条件**（满足任一则排除）：
- Awesome 列表类项目（标题含 "awesome-"）
- 纯教程/学习资源类（不含实际代码）
- Star 数量低于 100 的项目

### 第 4 步：去重检查

对候选项目执行去重：
- URL 去重：相同 GitHub URL 只保留一个
- 相似度去重：名称相似度 > 80% 的项目只保留一个
- 优先保留 Star 数量更高的项目

### 第 5 步：撰写中文摘要

对每个通过筛选的项目撰写中文摘要，采用以下公式：

```
[项目名称]：由 [作者/组织] 开发的 [项目类型]，主要功能是 [核心功能描述]。该项目[技术亮点/创新点]，适合用于 [典型使用场景]。值得关注的理由：[为什么值得关注，1-2句话]。
```

摘要要求：
- 长度：80-150 字
- 语言：简体中文
- 必须包含：项目名、核心功能、亮点、使用场景

### 第 6 步：排序取 Top 15

按以下规则排序并取前 15 名：
1. 主要排序键：`stars`（Star 数量，降序）
2. 次要排序键：项目完整性（优先有详细 README 的项目）
3. 最终筛选：取排名前 15 的项目

### 第 7 步：输出 JSON 文件

将结果写入 `knowledge/raw/github-trending-YYYY-MM-DD.json`，使用 Write 工具创建文件。

## 注意事项

1. **遵守 robots.txt**：优先使用 GitHub API，避免高频抓取页面
2. **数据时效性**：采集完成后记录 `collected_at` 时间戳
3. **质量优先**：Star 数量高不代表质量高，需结合描述判断是否为有效项目
4. **避免 Awesome 列表**：Awesome 列表属于资源合集，不计入独立项目统计
5. **中文摘要准确性**：基于项目 README 和描述撰写，不要编造功能
6. **工具限制**：本技能仅允许使用 Read, Grep, Glob, WebFetch 工具

## 输出格式

### JSON 文件结构

```json
{
  "source": "github-trending",
  "skill": "github-trending",
  "collected_at": "YYYY-MM-DDTHH:mm:ssZ",
  "period": "weekly",
  "total_count": 15,
  "items": [
    {
      "id": "raw_gh_YYYYMMDD_01",
      "name": "owner/repo-name",
      "url": "https://github.com/owner/repo-name",
      "summary": "中文摘要内容...",
      "stars": 12345,
      "language": "Python",
      "topics": ["agent", "llm", "framework"],
      "author": "owner"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 描述 |
|------|------|------|
| `source` | string | 数据来源，固定为 "github-trending" |
| `skill` | string | 使用的技能名，固定为 "github-trending" |
| `collected_at` | string | ISO 8601 格式采集时间 |
| `period` | string | 采集周期，"daily" 或 "weekly" |
| `total_count` | number | 本次采集的项目总数 |
| `items` | array | 项目数组，最多 15 个元素 |
| `items[].id` | string | 唯一标识符，格式：raw_gh_YYYYMMDD_序号 |
| `items[].name` | string | 项目名称（owner/repo 格式） |
| `items[].url` | string | 项目 GitHub URL |
| `items[].summary` | string | 中文摘要，80-150 字 |
| `items[].stars` | number | Star 总数 |
| `items[].language` | string | 主要编程语言 |
| `items[].topics` | array | GitHub Topics 标签数组 |
| `items[].author` | string | 项目所有者/组织 |

## 示例

### 输入
用户：搜集本周 AI 领域的 GitHub 热门开源项目 Top 10

### 执行流程
1. WebFetch 获取 GitHub Trending 周榜
2. 解析提取 25+ 个项目信息
3. 过滤出 AI/LLM/Agent 相关项目（约 18 个）
4. 去重后保留 15 个候选项目
5. 撰写中文摘要
6. 按 Star 排序取 Top 15
7. 输出 JSON 文件

### 输出
生成 `knowledge/raw/github-trending-2025-04-21.json`，包含 15 个 AI 领域热门项目及完整元数据。
