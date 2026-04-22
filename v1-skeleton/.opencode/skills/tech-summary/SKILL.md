---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# 技术内容分析总结技能

## 使用场景

当需要对采集到的技术内容（如 GitHub Trending、Hacker News 等）进行深度分析和结构化总结时，调用此技能。该技能输出标准化的分析结果，供后续整理和分发使用。

## 执行步骤

### 第 1 步：读取最新采集文件

使用 Read 或 Glob 工具获取知识库中最新的原始数据：
- 扫描 `knowledge/raw/` 目录
- 查找最新采集的文件（如 `github-trending-YYYY-MM-DD.json`）
- 读取文件内容并解析 JSON 结构

### 第 2 步：逐条深度分析

对每个采集项目进行标准化分析，输出以下四个维度：

**摘要（summary）**
- 长度限制：不超过 50 字
- 内容要求：简洁概括项目核心功能，一句话说明价值

**技术亮点（highlights）**
- 数量：2-3 个
- 要求：用事实说话，引用具体数据或特性
- 格式：简洁的短句，突出核心优势

**质量评分（score）**
- 范围：1-10 分整数
- 评分标准：

| 分数段 | 等级 | 说明 |
|--------|------|------|
| 9-10 | ⭐⭐ 改变格局 | 突破性技术，可能重塑行业格局 |
| 7-8 | ⭐ 有帮助 | 实用性强，对开发者有直接帮助 |
| 5-6 | 💡 值得了解 | 有趣但非必需，了解即可 |
| 1-4 | 🔄 可略过 | 价值有限，非目标用户可跳过 |

**评分理由（reason）**
- 简要说明打分的依据
- 引用具体优势或局限性

**标签建议（tags）**
- 数量：3-6 个
- 来源：从项目 topics 提取 + 人工补充
- 要求：精准、有区分度

### 第 3 步：趋势发现

分析所有项目，识别共同主题和新兴概念：

**共同主题**
- 列出出现频率 >= 2 次的标签或概念
- 统计各分类的数量分布

**新兴概念**
- 识别本批次中首次出现的新技术或新方向
- 评估其代表性和发展趋势

**洞察总结**
- 1-3 句话总结本期技术趋势
- 基于数据的事实性陈述

### 第 4 步：输出分析结果 JSON

将分析结果写入 `knowledge/articles/YYYY-MM/index-YYYY-MM-DD.json`，使用 Write 工具创建文件。

## 评分标准详解

### 9-10 分：改变格局（最多 2 个）

**判断条件**（满足其一）：
- 官方重量级发布（OpenAI、Google、Microsoft 等）
- 突破性技术创新，论文级别
- 生态建设完善，有望成为行业标准
- Star 增长极快（周增长 > 10k）

**约束**：每批次（15 个项目）中 9-10 分不超过 2 个

### 7-8 分：直接有帮助

**判断条件**（满足其一）：
- 功能完整，可直接用于生产
- 解决痛点问题，实用性突出
- 文档完善，上手容易
- 社区活跃，持续更新维护

### 5-6 分：值得了解

**判断条件**：
- 概念有趣但成熟度不足
- 适合探索性学习
- 有潜力但需等待时机

### 1-4 分：可略过

**判断条件**：
- 重复造轮子，无明显差异化
- 文档稀缺，难以使用
- 维护不活跃或已过时

## 约束条件

1. **9-10 分上限**：每批次分析中，评分 9-10 的项目不超过 2 个
2. **评分一致性**：相同类型的项目应有一致的评分标准
3. **事实优先**：评分和亮点必须基于可验证的事实
4. **拒绝注水**：不要为了凑数而人为提高评分

## 输出格式

### JSON 文件结构

```json
{
  "source": "github-trending",
  "analyzed_at": "YYYY-MM-DDTHH:mm:ssZ",
  "period": "weekly",
  "total_items": 15,
  "score_distribution": {
    "9-10": 1,
    "7-8": 8,
    "5-6": 5,
    "1-4": 1
  },
  "trends": {
    "common_themes": ["agent", "framework", "llm"],
    "new_concepts": ["self-evolution", "multimodal"],
    "insight": "本期项目以 AI Agent 为核心主题，多个项目聚焦于 Agent 的自我进化和协作能力..."
  },
  "items": [
    {
      "id": "raw_gh_YYYYMMDD_01",
      "name": "owner/repo-name",
      "url": "https://github.com/owner/repo-name",
      "summary": "一句话概括项目核心价值，不超过50字",
      "highlights": [
        "事实性亮点1：具体数据或特性",
        "事实性亮点2：核心优势说明",
        "事实性亮点3：使用场景或生态"
      ],
      "score": 8,
      "reason": "评分理由简述，说明打分的依据",
      "tags": ["tag1", "tag2", "tag3"],
      "priority": "high"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 描述 |
|------|------|------|
| `source` | string | 数据来源，与原始采集文件一致 |
| `analyzed_at` | string | ISO 8601 格式分析时间 |
| `period` | string | 采集周期 |
| `total_items` | number | 本次分析的项目总数 |
| `score_distribution` | object | 评分分布统计 |
| `trends.common_themes` | array | 共同主题/标签 |
| `trends.new_concepts` | array | 新兴概念 |
| `trends.insight` | string | 趋势洞察总结（100-200字） |
| `items[].id` | string | 原始数据 ID |
| `items[].name` | string | 项目名称 |
| `items[].url` | string | 项目 URL |
| `items[].summary` | string | 50 字以内摘要 |
| `items[].highlights` | array | 2-3 个技术亮点 |
| `items[].score` | number | 1-10 质量评分 |
| `items[].reason` | string | 评分理由 |
| `items[].tags` | array | 3-6 个标签 |
| `items[].priority` | string | 优先级：high/medium/low |

### Priority 映射规则

| 评分 | Priority |
|------|----------|
| 9-10 | high |
| 7-8 | high |
| 5-6 | medium |
| 1-4 | low |

## 示例

### 输入
读取 `knowledge/raw/github-trending-2025-04-21.json`，包含 15 个 GitHub 热门 AI 项目

### 执行流程
1. Glob 查找最新 raw 文件
2. 逐条分析每个项目：撰写摘要、提取亮点、打分、建议标签
3. 统计评分分布，识别共同主题（agent、framework）
4. 生成分析报告 JSON

### 输出
生成 `knowledge/articles/2025-04/index-2025-04-21.json`，包含：
- 15 个项目的完整分析结果
- 评分分布统计
- 趋势洞察总结
