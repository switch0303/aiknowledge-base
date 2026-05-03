"""Router 路由模式实现。

两层意图分类策略：
1. 关键词快速匹配（零成本，不调 LLM）
2. LLM 分类兜底（处理模糊意图）

支持三种意图：
- github_search: GitHub 仓库搜索
- knowledge_query: 本地知识库查询
- general_chat: 通用对话

Example:
    >>> from patterns.router import route
    >>> result = route("搜索 AI Agent 相关项目")
    >>> print(result)
"""

import json
import logging
import ssl
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

# 修复 SSL 证书问题
ssl._create_default_https_context = ssl._create_unverified_context

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
        logger.error(f"Failed to parse JSON response: {e}, text: {text}")
        return {"error": "JSON 解析失败", "raw_text": text}, usage


# ============================================================================
# 意图关键词配置
# ============================================================================

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "github_search": [
        "github", "搜索", "search", "仓库", "repo", "项目", "找",
        "github搜索", "github search", "查一下 github", "搜索项目"
    ],
    "knowledge_query": [
        "知识库", "knowledge", "检索", "查询", "查一下", "本地",
        "已存", "文章", "笔记", "知识库中", "之前的", "历史"
    ]
}


# ============================================================================
# 第一层：关键词快速匹配
# ============================================================================

def keyword_match(query: str) -> Optional[str]:
    """通过关键词快速匹配意图。

    Args:
        query: 用户输入查询

    Returns:
        匹配到的意图或 None
    """
    query_lower = query.lower()
    
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                logger.debug(f"Keyword matched: intent={intent}, keyword='{kw}'")
                return intent
    
    return None


# ============================================================================
# 第二层：LLM 意图分类
# ============================================================================

INTENT_CLASSIFICATION_PROMPT = """
请将用户输入分类到以下三种意图之一：

1. github_search: 用户想要搜索 GitHub 上的项目、仓库或代码
   - 关键词特征: "github", "搜索", "仓库", "repo", "项目", "找", "search"

2. knowledge_query: 用户想要查询本地知识库中的内容
   - 关键词特征: "知识库", "检索", "查询", "查一下", "本地", "已存", "文章", "之前的"

3. general_chat: 通用对话或无法归类到上述两种意图
   - 包括: 问候、闲聊、提问、请求帮助等

用户输入: {query}

请只输出意图名称（三个选择之一），不要添加任何其他内容:
"""


def llm_classify(query: str) -> str:
    """使用 LLM 进行意图分类兜底。

    Args:
        query: 用户输入查询

    Returns:
        分类结果: github_search / knowledge_query / general_chat
    """
    system_prompt = "你是一个专业的意图分类器。只输出意图名称，不要添加任何解释。"
    
    prompt = INTENT_CLASSIFICATION_PROMPT.format(query=query)
    
    try:
        result, usage = chat(prompt, system_prompt)
        result = result.strip().lower()
        
        # 验证分类结果
        if result in ["github_search", "knowledge_query", "general_chat"]:
            logger.info(f"LLM classified: intent={result}, tokens={usage.get('total_tokens', 0)}")
            return result
        else:
            logger.warning(f"Invalid LLM classification result: {result}, fallback to general_chat")
            return "general_chat"
            
    except Exception as e:
        logger.error(f"LLM classification failed: {e}, fallback to general_chat")
        return "general_chat"


# ============================================================================
# 意图分类主函数
# ============================================================================

def classify_intent(query: str) -> Tuple[str, str]:
    """两层意图分类策略。

    Args:
        query: 用户输入查询

    Returns:
        (intent, method) 元组，method 为 "keyword" 或 "llm"
    """
    # 第一层：关键词快速匹配
    intent = keyword_match(query)
    if intent:
        return intent, "keyword"
    
    # 第二层：LLM 兜底
    intent = llm_classify(query)
    return intent, "llm"


# ============================================================================
# 辅助函数：提取搜索关键词
# ============================================================================

def extract_search_terms(query: str, intent: str) -> str:
    """从查询中提取搜索关键词，去除意图相关词。

    Args:
        query: 原始查询
        intent: 意图类型

    Returns:
        提取后的搜索关键词
    """
    search_terms = query.lower()
    
    # 去除意图关键词
    for kw in INTENT_KEYWORDS.get(intent, []):
        search_terms = search_terms.replace(kw.lower(), "")
    
    # 去除常见的停用词和标点
    stop_words = [
        "的", "了", "吗", "呢", "吧", "啊", "哦", "嗯", "有", "是", "什么", "怎么", "如何",
        "关于", "相关", "内容", "中", "一下", "上", "好", "哪些", "哪个", "什么", "多少",
        "几", "文章", "项目", "仓库", "repo", "找", "帮我", "我想", "请", "请问", "可以",
        "里", "里面", "里边", "内", "里面有", "中有", "里有", "库里", "中有", "关于",
        "什么", "怎么", "如何", "哪些", "哪个", "多少", "几", "有什么", "有没有", "有关"
    ]
    for sw in stop_words:
        search_terms = search_terms.replace(sw, " ")
    
    # 清理多余空格
    while "  " in search_terms:
        search_terms = search_terms.replace("  ", " ")
    
    search_terms = search_terms.strip()
    
    # 如果提取结果为空，使用默认关键词
    if not search_terms:
        search_terms = "AI agent" if intent == "github_search" else "AI"
    
    logger.debug(f"Extracted search terms: '{search_terms}' from '{query}'")
    return search_terms


# ============================================================================
# 处理器：GitHub 搜索
# ============================================================================

def handle_github_search(query: str) -> str:
    """处理 GitHub 搜索意图。

    Args:
        query: 用户输入查询

    Returns:
        搜索结果字符串
    """
    logger.info(f"Handling GitHub search: {query}")
    
    # 提取搜索关键词（去除意图相关词）
    search_terms = extract_search_terms(query, "github_search")
    
    # URL 编码（处理中文和空格）
    encoded_query = urllib.parse.quote(search_terms)
    
    try:
        # 调用 GitHub Search API
        url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&per_page=5"
        
        headers = {
            "User-Agent": "aiknowledge-base/1.0",
            "Accept": "application/vnd.github.v3+json"
        }
        
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        # 格式化结果
        items = data.get("items", [])
        if not items:
            return f"未找到与 '{search_terms}' 相关的 GitHub 项目。"
        
        result_lines = [f"🔍 GitHub 搜索结果（共 {data.get('total_count', 0)} 个结果，展示前 5 个）:\n"]
        
        for i, item in enumerate(items[:5], 1):
            result_lines.append(
                f"{i}. {item['name']} ⭐ {item['stargazers_count']}\n"
                f"   描述: {item.get('description', '无描述')}\n"
                f"   语言: {item.get('language', '未知')}\n"
                f"   链接: {item['html_url']}\n"
            )
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"GitHub search failed: {e}")
        return f"GitHub 搜索失败: {str(e)}"


# ============================================================================
# 处理器：知识库查询
# ============================================================================

KNOWLEDGE_INDEX_PATH = "knowledge/articles"


def handle_knowledge_query(query: str) -> str:
    """处理本地知识库查询意图。

    Args:
        query: 用户输入查询

    Returns:
        查询结果字符串
    """
    logger.info(f"Handling knowledge query: {query}")
    
    import os
    import glob
    
    # 提取搜索关键词
    search_terms = extract_search_terms(query, "knowledge_query")
    query_lower = search_terms.lower()
    results = []
    
    # 查找所有 JSON 文件
    json_files = glob.glob(f"{KNOWLEDGE_INDEX_PATH}/**/*.json", recursive=True)
    
    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 简单的相似度匹配
            title = data.get("title", "").lower()
            summary = data.get("summary", "").lower()
            tags = [t.lower() for t in data.get("tags", [])]
            
            score = 0
            if query_lower in title:
                score += 5
            if query_lower in summary:
                score += 3
            for tag in tags:
                if query_lower in tag:
                    score += 2
            
            if score > 0:
                results.append((score, data))
                
        except Exception as e:
            logger.warning(f"Failed to parse {json_file}: {e}")
    
    # 按得分排序
    results.sort(key=lambda x: -x[0])
    
    if not results:
        return f"知识库中未找到与 '{query}' 相关的内容。"
    
    result_lines = [f"📚 知识库检索结果（找到 {len(results)} 条相关内容，展示前 5 条）:\n"]
    
    for i, (score, item) in enumerate(results[:5], 1):
        tags = ", ".join(item.get("tags", []))
        result_lines.append(
            f"{i}. {item['title']} (匹配度: {score})\n"
            f"   摘要: {item.get('summary', '无摘要')[:100]}...\n"
            f"   标签: {tags}\n"
            f"   分类: {item.get('category', '未知')}\n"
            f"   来源: {item.get('source_url', '无链接')}\n"
        )
    
    return "\n".join(result_lines)


# ============================================================================
# 处理器：通用对话
# ============================================================================

def handle_general_chat(query: str) -> str:
    """处理通用对话意图。

    Args:
        query: 用户输入查询

    Returns:
        LLM 生成的回复
    """
    logger.info(f"Handling general chat: {query}")
    
    system_prompt = "你是一个友好的 AI 助手，专业领域是 AI 技术、编程和软件工程。请用中文简洁、准确地回答问题。"
    
    response, usage = chat(query, system_prompt)
    
    logger.debug(f"General chat completed, tokens: {usage.get('total_tokens', 0)}")
    
    return response


# ============================================================================
# 路由映射
# ============================================================================

INTENT_HANDLERS = {
    "github_search": handle_github_search,
    "knowledge_query": handle_knowledge_query,
    "general_chat": handle_general_chat
}


# ============================================================================
# 统一入口
# ============================================================================

def route(query: str) -> str:
    """统一路由入口函数。

    两层意图分类策略：
    1. 关键词快速匹配（零成本）
    2. LLM 分类兜底（处理模糊意图）

    Args:
        query: 用户输入查询

    Returns:
        处理结果字符串

    Example:
        >>> route("搜索 AI Agent 相关项目")
        >>> route("查一下知识库中有什么关于 LangChain 的内容")
        >>> route("你好，介绍一下自己")
    """
    logger.info(f"Routing query: {query}")
    
    # 意图分类
    intent, method = classify_intent(query)
    
    logger.info(f"Classified intent: {intent} (method: {method})")
    
    # 调用对应的处理器
    handler = INTENT_HANDLERS.get(intent)
    if handler:
        result = handler(query)
        return result
    else:
        logger.warning(f"No handler found for intent: {intent}, fallback to general_chat")
        return handle_general_chat(query)


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 如果有命令行参数，使用参数作为查询
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"Query: {query}")
        print("-" * 60)
        result = route(query)
        print(result)
        sys.exit(0)
    
    # 否则运行默认测试
    print("=" * 60)
    print("Router 路由模式测试")
    print("=" * 60)
    
    test_queries = [
        "搜索 AI Agent 相关的 GitHub 项目",
        "查一下知识库中有什么关于 LangChain 的内容",
        "你好，介绍一下什么是大语言模型",
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n[测试 {i}] Query: {query}")
        print("-" * 40)
        result = route(query)
        print(result)
        print("-" * 40)
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
