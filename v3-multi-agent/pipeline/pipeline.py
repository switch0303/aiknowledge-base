#!/usr/bin/env python3
"""知识库自动化流水线。

四步流水线：采集 -> 分析 -> 整理 -> 保存
支持从 GitHub Search API 和 RSS 源采集 AI 相关内容。

Usage:
    python pipeline/pipeline.py --sources github,rss --limit 20
    python pipeline/pipeline.py --sources github --limit 5 --verbose
    python pipeline/pipeline.py --sources rss --limit 10 --dry-run
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Tuple, Tuple
from urllib.parse import urljoin, urlparse

import httpx

# 导入 model_client
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model_client import create_provider, chat_with_retry, tracker

# ============================================================================
# 配置和常量
# ============================================================================

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
RAW_DIR = KNOWLEDGE_DIR / "raw"
ARTICLES_DIR = KNOWLEDGE_DIR / "articles"

# GitHub Search API 配置
GITHUB_API_URL = "https://api.github.com/search/repositories"
GITHUB_API_VERSION = "2022-11-28"

# 默认 AI/LLM 相关搜索关键词 (简化版，避免 422 错误)
DEFAULT_GITHUB_QUERY = "AI LLM machine-learning stars:>100"

# RSS 源配置
DEFAULT_RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://www.reddit.com/r/MachineLearning/.rss",
    "https://blog.google.com/technology/ai/rss/",
]

# 日期格式
ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# ============================================================================
# 日志配置
# ============================================================================

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """配置日志级别和格式。

    Args:
        verbose: 是否启用详细日志（DEBUG 级别）
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


# ============================================================================
# Step 1: 采集 (Collect)
# ============================================================================

class DataCollector:
    """数据采集器，支持 GitHub Search API 和 RSS 源。"""

    def __init__(self, github_token: Optional[str] = None, limit: int = 20, dry_run: bool = False):
        """初始化采集器。

        Args:
            github_token: GitHub API Token（可选，用于提高速率限制）
            limit: 每个源的最大采集数量
            dry_run: 是否为干跑模式
        """
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.limit = limit
        self.dry_run = dry_run
        self.httpx_client = httpx.Client(
            timeout=30.0,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            }
        )

        if self.github_token:
            self.httpx_client.headers["Authorization"] = f"Bearer {self.github_token}"

        logger.info("DataCollector initialized (GitHub token: %s)",
                   "available" if self.github_token else "not available")

    def collect_github(self, query: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """从 GitHub Search API 采集仓库信息。

        Args:
            query: 搜索查询字符串，默认使用 AI/LLM 相关关键词
            limit: 最多采集数量

        Returns:
            采集的仓库信息列表
        """
        search_query = query or DEFAULT_GITHUB_QUERY
        logger.info("Collecting from GitHub: query='%s...', limit=%d", search_query[:50], limit)

        items = []
        page = 1
        per_page = min(limit, 100)

        try:
            while len(items) < limit:
                params = {
                    "q": search_query,
                    "sort": "updated",
                    "order": "desc",
                    "per_page": per_page,
                    "page": page,
                }

                response = self.httpx_client.get(GITHUB_API_URL, params=params)
                response.raise_for_status()

                data = response.json()
                repositories = data.get("items", [])

                if not repositories:
                    break

                for repo in repositories:
                    if len(items) >= limit:
                        break

                    item = {
                        "id": f"github-{repo['id']}",
                        "source": "github",
                        "source_url": repo["html_url"],
                        "title": repo["name"],
                        "content": repo.get("description") or "No description",
                        "metadata": {
                            "stars": repo.get("stargazers_count", 0),
                            "language": repo.get("language") or "Unknown",
                            "author": repo.get("owner", {}).get("login", "unknown"),
                            "created_at": repo.get("created_at"),
                            "updated_at": repo.get("updated_at"),
                        },
                        "collected_at": datetime.now(timezone.utc).strftime(ISO_FORMAT),
                    }
                    items.append(item)

                logger.debug("Collected %d items from page %d", len(repositories), page)
                page += 1

                if len(repositories) < per_page:
                    break

        except httpx.HTTPError as e:
            logger.error("GitHub API request failed: %s", e)
        except Exception as e:
            logger.error("Unexpected error collecting from GitHub: %s", e)

        logger.info("Collected %d items from GitHub", len(items))
        return items

    def collect_rss(self, feeds: Optional[List[str]] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """从 RSS 源采集内容。

        使用简易正则解析 RSS XML 内容。

        Args:
            feeds: RSS 源 URL 列表，默认使用内置列表
            limit: 每个源最多采集数量

        Returns:
            采集的 RSS 条目列表
        """
        rss_feeds = feeds or DEFAULT_RSS_FEEDS
        logger.info("Collecting from %d RSS feeds, limit=%d per feed", len(rss_feeds), limit)

        items = []

        # RSS item 正则模式
        item_pattern = re.compile(
            r'<item[^>]*>.*?<title[^>]*>(.*?)</title>.*?'
            r'<link[^>]*>(.*?)</link>.*?(?:<description[^>]*>(.*?)</description>)?.*?'
            r'(?:<pubDate[^>]*>(.*?)</pubDate>)?.*?</item>',
            re.DOTALL | re.IGNORECASE
        )

        # 清理 HTML 标签的简单函数
        def clean_html(text: str) -> str:
            if not text:
                return ""
            # 移除 HTML 标签
            text = re.sub(r'<[^>]+>', '', text)
            # 解码 HTML 实体
            text = text.replace('&lt;', '<').replace('&gt;', '>')
            text = text.replace('&quot;', '"').replace('&amp;', '&')
            text = text.replace('&#39;', "'")
            return text.strip()

        for feed_url in rss_feeds:
            try:
                logger.debug("Fetching RSS feed: %s", feed_url)
                response = self.httpx_client.get(feed_url)
                response.raise_for_status()

                content = response.text
                matches = item_pattern.findall(content)

                feed_items = 0
                for i, match in enumerate(matches):
                    if i >= limit:
                        break

                    title, link, desc, pub_date = match

                    item = {
                        "id": f"rss-{hashlib.md5(link.encode()).hexdigest()[:12]}",
                        "source": "rss",
                        "source_url": link.strip(),
                        "title": clean_html(title.strip()),
                        "content": clean_html(desc) if desc else "No description",
                        "metadata": {
                            "feed_url": feed_url,
                            "published_at": pub_date.strip() if pub_date else None,
                        },
                        "collected_at": datetime.now(timezone.utc).strftime(ISO_FORMAT),
                    }
                    items.append(item)
                    feed_items += 1

                logger.debug("Collected %d items from %s", feed_items, feed_url)

            except httpx.HTTPError as e:
                logger.error("RSS feed request failed for %s: %s", feed_url, e)
            except Exception as e:
                logger.error("Unexpected error collecting from %s: %s", feed_url, e)

        logger.info("Collected %d items from RSS feeds", len(items))
        return items

    def close(self):
        """关闭 HTTP 客户端。"""
        if hasattr(self, 'httpx_client'):
            self.httpx_client.close()
            logger.debug("DataCollector HTTP client closed")

    def __enter__(self):
        """上下文管理器入口。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口。"""
        self.close()


# ============================================================================
# Step 2: 分析 (Analyze)
# ============================================================================

class ContentAnalyzer:
    """内容分析器，使用 LLM 对内容进行摘要、评分和标签提取。"""

    # 分析提示词模板
    ANALYSIS_PROMPT = """你是一个专业的 AI 技术内容分析助手。请分析以下技术内容，并提供结构化分析结果。

【内容标题】: {title}
【内容来源】: {source}
【原始内容】: {content}

请按以下 JSON 格式返回分析结果：

{{
    "summary": "内容的详细摘要（200-300字）",
    "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
    "category": "类别（paper/tool/framework/news/resource）",
    "quality_score": 质量评分（1-10分）,
    "relevance_score": AI相关度评分（1-10分）,
    "language": "内容语言（zh/en/mixed）"
}}

要求：
1. 标签应该涵盖技术领域、内容类型、应用场景等维度
2. 类别必须是：paper（论文）、tool（工具）、framework（框架）、news（新闻）、resource（资源）之一
3. 质量评分考虑内容深度、技术价值、原创性等因素
4. 只返回纯 JSON 格式，不要添加任何其他文字说明"""

    def __init__(self, provider_name: Optional[str] = None):
        """初始化分析器。

        Args:
            provider_name: LLM 提供商名称，默认从环境变量读取
        """
        self.provider_name = provider_name or os.getenv("LLM_PROVIDER", "deepseek")
        self.provider = None
        logger.info("ContentAnalyzer initialized with provider: %s", self.provider_name)

    def _get_provider(self):
        """延迟初始化 LLM 提供商。"""
        if self.provider is None:
            self.provider = create_provider(self.provider_name)
        return self.provider

    def analyze(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """分析单个内容条目。

        Args:
            item: 原始内容条目

        Returns:
            包含分析结果的文章字典
        """
        logger.info("Analyzing content: %s", item.get("title", "Unknown"))

        try:
            # 构建提示词
            prompt = self.ANALYSIS_PROMPT.format(
                title=item.get("title", ""),
                source=item.get("source", ""),
                content=item.get("content", "")
            )

            messages = [
                {"role": "user", "content": prompt}
            ]

            # 调用 LLM
            provider = self._get_provider()
            response = chat_with_retry(
                provider,
                messages,
                max_retries=3,
                timeout=60.0,
                temperature=0.3
            )

            # 解析 JSON 响应
            analysis = self._parse_analysis_response(response.content)

            # 构建文章数据
            article = {
                "id": item.get("id"),
                "title": item.get("title"),
                "source_url": item.get("source_url"),
                "source_type": item.get("source"),
                "summary": analysis.get("summary", ""),
                "tags": analysis.get("tags", []),
                "category": analysis.get("category", "resource"),
                "content_en": item.get("content", "") if analysis.get("language") == "en" else "",
                "content_zh": item.get("content", "") if analysis.get("language") in ["zh", "mixed"] else "",
                "status": "pending",
                "priority": self._calculate_priority(
                    analysis.get("quality_score", 5),
                    analysis.get("relevance_score", 5)
                ),
                "collected_at": item.get("collected_at"),
                "processed_at": datetime.now(timezone.utc).strftime(ISO_FORMAT),
                "published_at": None,
                "channels": ["telegram", "feishu"],
                "_raw_metadata": item.get("metadata", {}),
                "_analysis": {
                    "quality_score": analysis.get("quality_score", 0),
                    "relevance_score": analysis.get("relevance_score", 0),
                    "language": analysis.get("language", "unknown"),
                }
            }

            logger.info("Successfully analyzed: %s (quality=%d, relevance=%d)",
                       article["title"][:50],
                       analysis.get("quality_score", 0),
                       analysis.get("relevance_score", 0))

            return article

        except Exception as e:
            logger.error("Failed to analyze content %s: %s", item.get("id"), e)
            return {
                "id": item.get("id"),
                "title": item.get("title"),
                "source_url": item.get("source_url"),
                "source_type": item.get("source"),
                "error": str(e),
                "status": "failed",
            }

    def _parse_analysis_response(self, content: str) -> Dict[str, Any]:
        """解析 LLM 的 JSON 响应。"""
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

        try:
            result = json.loads(content)
            defaults = {
                "summary": "",
                "tags": [],
                "category": "resource",
                "quality_score": 5,
                "relevance_score": 5,
                "language": "unknown"
            }
            defaults.update(result)
            return defaults
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse JSON response: %s", e)
            return {
                "summary": content[:500] if content else "",
                "tags": [],
                "category": "resource",
                "quality_score": 5,
                "relevance_score": 5,
                "language": "unknown"
            }

    def _calculate_priority(self, quality_score: int, relevance_score: int) -> str:
        """根据质量和相关度计算优先级。"""
        avg_score = (quality_score + relevance_score) / 2
        if avg_score >= 8:
            return "high"
        elif avg_score >= 5:
            return "medium"
        return "low"

    def close(self):
        """关闭 LLM 提供商连接。"""
        if self.provider:
            self.provider.close()
            logger.debug("ContentAnalyzer LLM provider closed")



# ============================================================================
# Step 3: 整理 (Organize)
# ============================================================================

class ContentOrganizer:
    """内容整理器，负责去重、格式标准化和校验。"""

    def __init__(self, raw_dir: Path = RAW_DIR, articles_dir: Path = ARTICLES_DIR):
        """初始化整理器。

        Args:
            raw_dir: 原始数据目录
            articles_dir: 文章输出目录
        """
        self.raw_dir = raw_dir
        self.articles_dir = articles_dir
        self.existing_urls: Set[str] = set()
        self._load_existing_urls()
        logger.info("ContentOrganizer initialized, found %d existing URLs", len(self.existing_urls))

    def _load_existing_urls(self):
        """加载已存在的文章 URL，用于去重。"""
        if not self.articles_dir.exists():
            return

        for subdir in self.articles_dir.iterdir():
            if subdir.is_dir():
                for json_file in subdir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            url = data.get('source_url')
                            if url:
                                self.existing_urls.add(url)
                    except Exception as e:
                        logger.warning("Failed to load %s: %s", json_file, e)

    def is_duplicate(self, url: str) -> bool:
        """检查 URL 是否已存在。

        Args:
            url: 要检查的 URL

        Returns:
            如果 URL 已存在返回 True
        """
        return url in self.existing_urls

    def validate_article(self, article: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """校验文章数据的有效性。

        Args:
            article: 文章数据字典

        Returns:
            (是否有效, 错误信息)
        """
        required_fields = ['id', 'title', 'source_url', 'source_type']

        for field in required_fields:
            if not article.get(field):
                return False, f"Missing required field: {field}"

        # 校验 URL 格式
        url = article.get('source_url', '')
        if not url.startswith(('http://', 'https://')):
            return False, f"Invalid URL format: {url}"

        # 校验评分范围
        if '_analysis' in article:
            analysis = article['_analysis']
            for score_field in ['quality_score', 'relevance_score']:
                score = analysis.get(score_field, 5)
                if not (1 <= score <= 10):
                    return False, f"Invalid {score_field}: {score}"

        return True, None

    def standardize_format(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """标准化文章数据格式。

        Args:
            article: 原始文章数据

        Returns:
            标准化后的文章数据
        """
        standardized = {
            # 必填字段
            'id': article.get('id'),
            'title': article.get('title', '').strip(),
            'source_url': article.get('source_url', ''),
            'source_type': article.get('source_type', 'unknown'),

            # 内容相关
            'summary': article.get('summary', ''),
            'tags': article.get('tags', []),
            'category': article.get('category', 'resource'),
            'content_en': article.get('content_en', ''),
            'content_zh': article.get('content_zh', ''),

            # 状态和时间
            'status': article.get('status', 'pending'),
            'priority': article.get('priority', 'medium'),
            'collected_at': article.get('collected_at'),
            'processed_at': article.get('processed_at'),
            'published_at': article.get('published_at'),

            # 其他
            'channels': article.get('channels', ['telegram', 'feishu']),
            '_raw_metadata': article.get('_raw_metadata', {}),
            '_analysis': article.get('_analysis', {}),
        }

        # 确保 tags 是列表
        if not isinstance(standardized['tags'], list):
            standardized['tags'] = []

        # 去重 tags
        standardized['tags'] = list(set(standardized['tags']))

        return standardized

    def organize(self, articles: List[Dict[str, Any]], dry_run: bool = False) -> Dict[str, Any]:
        """整理文章列表，执行去重、校验和标准化。

        Args:
            articles: 原始文章列表
            dry_run: 是否为干跑模式

        Returns:
            包含整理结果的字典
        """
        logger.info("Organizing %d articles...", len(articles))

        results = {
            'total': len(articles),
            'duplicates': 0,
            'invalid': 0,
            'accepted': 0,
            'articles': []
        }

        for article in articles:
            url = article.get('source_url', '')

            # 去重检查
            if self.is_duplicate(url):
                logger.debug("Duplicate article skipped: %s", url)
                results['duplicates'] += 1
                continue

            # 校验
            is_valid, error_msg = self.validate_article(article)
            if not is_valid:
                logger.warning("Invalid article rejected: %s - %s", url, error_msg)
                results['invalid'] += 1
                continue

            # 标准化格式
            standardized = self.standardize_format(article)

            if not dry_run:
                # 添加到已存在 URL 集合
                self.existing_urls.add(url)

            results['accepted'] += 1
            results['articles'].append(standardized)

        logger.info("Organizing complete: %d accepted, %d duplicates, %d invalid",
                   results['accepted'], results['duplicates'], results['invalid'])

        return results


# ============================================================================
# Step 4: 保存 (Save) 和主流水线
# ============================================================================

class Pipeline:
    """知识库自动化流水线，协调四步流程。"""

    def __init__(
        self,
        sources: List[str],
        limit: int = 20,
        dry_run: bool = False,
        verbose: bool = False
    ):
        """初始化流水线。

        Args:
            sources: 数据源列表 (github, rss)
            limit: 每个源的最大采集数量
            dry_run: 是否为干跑模式
            verbose: 是否启用详细日志
        """
        self.sources = sources
        self.limit = limit
        self.dry_run = dry_run
        self.verbose = verbose

        # 初始化组件
        self.collector = DataCollector()
        self.analyzer = ContentAnalyzer()
        self.organizer = ContentOrganizer()

        # 统计信息
        self.stats = {
            'collected': 0,
            'analyzed': 0,
            'accepted': 0,
            'saved': 0,
        }

        logger.info("Pipeline initialized: sources=%s, limit=%d, dry_run=%s",
                   sources, limit, dry_run)

    def _save_raw_data(self, items: List[Dict[str, Any]], source: str) -> Path:
        """保存原始采集数据。

        Args:
            items: 采集的原始数据项列表
            source: 数据源名称

        Returns:
            保存的文件路径
        """
        # 创建日期目录
        today = datetime.now(timezone.utc).strftime("%Y-%m")
        save_dir = RAW_DIR / today
        save_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{source}_{timestamp}.json"
        filepath = save_dir / filename

        # 保存数据
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'source': source,
                'collected_at': datetime.now(timezone.utc).strftime(ISO_FORMAT),
                'items': items
            }, f, ensure_ascii=False, indent=2)

        logger.info("Saved raw data to %s (%d items)", filepath, len(items))
        return filepath

    def _save_article(self, article: Dict[str, Any]) -> Path:
        """保存单个文章。

        Args:
            article: 文章数据字典

        Returns:
            保存的文件路径
        """
        # 创建日期目录
        today = datetime.now(timezone.utc).strftime("%Y-%m")
        save_dir = ARTICLES_DIR / today
        save_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        article_id = article.get('id', 'unknown')
        # 清理 ID 用于文件名
        safe_id = re.sub(r'[^\w\-]', '_', str(article_id))[:50]
        filename = f"{safe_id}.json"
        filepath = save_dir / filename

        # 保存数据
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

        logger.debug("Saved article to %s", filepath)
        return filepath

    def run(self) -> Dict[str, Any]:
        """执行完整的流水线。

        Returns:
            包含执行结果的字典
        """
        logger.info("=" * 60)
        logger.info("Starting pipeline execution")
        logger.info("=" * 60)

        all_items = []

        # ========================================================================
        # Step 1: 采集 (Collect)
        # ========================================================================
        logger.info("\n[Step 1/4] Collecting data from sources...")

        if 'github' in self.sources:
            logger.info("Collecting from GitHub...")
            github_items = self.collector.collect_github(limit=self.limit)
            all_items.extend(github_items)
            self.stats['collected'] += len(github_items)

            # 保存原始数据
            if github_items and not self.dry_run:
                self._save_raw_data(github_items, 'github')

        if 'rss' in self.sources:
            logger.info("Collecting from RSS feeds...")
            rss_items = self.collector.collect_rss(limit=self.limit)
            all_items.extend(rss_items)
            self.stats['collected'] += len(rss_items)

            # 保存原始数据（即使在干跑模式下也保存，以便测试）
            if rss_items:
                self._save_raw_data(rss_items, 'rss')

        logger.info("Total items collected: %d", len(all_items))

        if not all_items:
            logger.warning("No items collected, pipeline finished early")
            return {'success': True, 'stats': self.stats, 'articles': []}

        # ========================================================================
        # Step 2: 分析 (Analyze)
        # ========================================================================
        logger.info("\n[Step 2/4] Analyzing content with LLM...")

        analyzed_articles = []

        if self.dry_run:
            logger.info("[DRY RUN] Skipping LLM analysis")
            # 模拟分析结果
            for item in all_items[:3]:  # 只模拟前3个
                analyzed_articles.append({
                    'id': item['id'],
                    'title': item['title'],
                    'source_url': item['source_url'],
                    'source_type': item['source'],
                    'summary': '[DRY RUN] Simulated summary',
                    'tags': ['ai', 'dry-run', 'test'],
                    'category': 'resource',
                    'status': 'pending',
                    'priority': 'medium',
                })
        else:
            for item in all_items:
                try:
                    article = self.analyzer.analyze(item)
                    if article and 'error' not in article:
                        analyzed_articles.append(article)
                        self.stats['analyzed'] += 1
                    else:
                        logger.warning("Analysis failed for %s", item.get('id'))
                except Exception as e:
                    logger.error("Error analyzing %s: %s", item.get('id'), e)

        logger.info("Analyzed %d articles", len(analyzed_articles))

        # ========================================================================
        # Step 3: 整理 (Organize)
        # ========================================================================
        logger.info("\n[Step 3/4] Organizing articles (dedup & validate)...")

        organize_result = self.organizer.organize(analyzed_articles, dry_run=self.dry_run)
        accepted_articles = organize_result['articles']
        self.stats['accepted'] = organize_result['accepted']

        logger.info("Organizing complete: %d accepted, %d duplicates, %d invalid",
                   organize_result['accepted'], organize_result['duplicates'], organize_result['invalid'])

        # ========================================================================
        # Step 4: 保存 (Save)
        # ========================================================================
        logger.info("\n[Step 4/4] Saving articles to JSON files...")

        saved_paths = []

        if self.dry_run:
            logger.info("[DRY RUN] Would save %d articles to %s", len(accepted_articles), ARTICLES_DIR)
            for article in accepted_articles[:3]:  # 只显示前3个
                logger.info("[DRY RUN] Would save: %s", article.get('title', 'Unknown')[:50])
        else:
            for article in accepted_articles:
                try:
                    filepath = self._save_article(article)
                    saved_paths.append(filepath)
                    self.stats['saved'] += 1
                except Exception as e:
                    logger.error("Failed to save article %s: %s", article.get('id'), e)

        logger.info("Saved %d articles to %s", len(saved_paths), ARTICLES_DIR)

        # ========================================================================
        # 完成
        # ========================================================================
        logger.info("\n" + "=" * 60)
        logger.info("Pipeline execution completed")
        logger.info("=" * 60)
        logger.info("Statistics:")
        logger.info("  - Collected: %d", self.stats['collected'])
        logger.info("  - Analyzed:  %d", self.stats['analyzed'])
        logger.info("  - Accepted:  %d", self.stats['accepted'])
        logger.info("  - Saved:     %d", self.stats['saved'])

        # LLM 成本报告
        if not self.dry_run:
            tracker.report()

        return {
            'success': True,
            'stats': self.stats,
            'articles': accepted_articles,
            'saved_paths': saved_paths if not self.dry_run else []
        }



# ============================================================================
# CLI 入口
# ============================================================================

def main() -> int:
    """CLI 入口函数。

    Returns:
        退出码 (0 表示成功)
    """
    parser = argparse.ArgumentParser(
        description='知识库自动化流水线 - 四步流程：采集、分析、整理、保存',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --sources github,rss --limit 20           # 完整流水线
  %(prog)s --sources github --limit 5              # 只采集 GitHub
  %(prog)s --sources rss --limit 10                # 只采集 RSS
  %(prog)s --sources github --limit 5 --dry-run    # 干跑模式
  %(prog)s --verbose                               # 详细日志
        """
    )

    parser.add_argument(
        '--sources',
        type=str,
        default='github,rss',
        help='数据源列表，逗号分隔 (github,rss)，默认: github,rss'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='每个源的最大采集数量，默认: 20'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='干跑模式（不调用 LLM，不保存文件）'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='启用详细日志（DEBUG 级别）'
    )

    args = parser.parse_args()

    # 配置日志
    setup_logging(verbose=args.verbose)

    # 解析数据源
    sources = [s.strip().lower() for s in args.sources.split(',')]
    valid_sources = {'github', 'rss'}
    invalid_sources = set(sources) - valid_sources
    if invalid_sources:
        logger.error("Invalid sources: %s. Valid options: %s",
                    invalid_sources, valid_sources)
        return 1

    # 确保目录存在
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    # 创建并运行流水线
    try:
        pipeline = Pipeline(
            sources=sources,
            limit=args.limit,
            dry_run=args.dry_run,
            verbose=args.verbose
        )

        result = pipeline.run()

        if result.get('success'):
            logger.info("Pipeline completed successfully")
            return 0
        else:
            logger.error("Pipeline failed")
            return 1

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        return 130
    except Exception as e:
        logger.exception("Pipeline failed with error: %s", e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
