#!/usr/bin/env python3
"""MCP Server for AI Knowledge Base.

Provides tools to search and query local knowledge base articles.
Uses JSON-RPC 2.0 over stdio protocol.
"""

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, List, Dict


KNOWLEDGE_DIR = Path(__file__).parent / "knowledge" / "articles"


def load_articles() -> List[Dict]:
    """Load all articles from knowledge/articles directory."""
    articles = []
    if not KNOWLEDGE_DIR.exists():
        return articles
    
    for json_file in KNOWLEDGE_DIR.rglob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    articles.append(data)
                elif isinstance(data, list):
                    articles.extend(data)
        except (json.JSONDecodeError, IOError):
            continue
    return articles


def search_articles(keyword: str, limit: int = 5) -> Dict:
    """Search articles by keyword in title and summary."""
    articles = load_articles()
    keyword_lower = keyword.lower()
    
    results = []
    for article in articles:
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()
        if keyword_lower in title or keyword_lower in summary:
            results.append({
                "id": article.get("id"),
                "title": article.get("title"),
                "source": article.get("source"),
                "summary": article.get("summary"),
                "score": article.get("score", 0),
                "tags": article.get("tags", [])
            })
    
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"results": results[:limit], "total": len(results)}


def get_article(article_id: str) -> Dict:
    """Get article by ID."""
    articles = load_articles()
    for article in articles:
        if article.get("id") == article_id:
            return {"article": article}
    return {"error": "Article not found", "article_id": article_id}


def knowledge_stats() -> Dict:
    """Return knowledge base statistics."""
    articles = load_articles()
    
    source_dist = Counter()
    all_tags = []
    
    for article in articles:
        source_dist[article.get("source", "unknown")] += 1
        all_tags.extend(article.get("tags", []))
    
    tag_counts = Counter(all_tags)
    top_tags = tag_counts.most_common(10)
    
    return {
        "total_articles": len(articles),
        "source_distribution": dict(source_dist),
        "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags]
    }


TOOL_HANDLERS = {
    "search_articles": search_articles,
    "get_article": get_article,
    "knowledge_stats": knowledge_stats
}


TOOLS = [
    {
        "name": "search_articles",
        "description": "Search articles by keyword in title and summary",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Search keyword"},
                "limit": {"type": "number", "description": "Max results", "default": 5}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "get_article",
        "description": "Get article full content by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {"type": "string", "description": "Article ID"}
            },
            "required": ["article_id"]
        }
    },
    {
        "name": "knowledge_stats",
        "description": "Get knowledge base statistics",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


def send_response(data: Dict) -> None:
    """Send JSON-RPC response."""
    print(json.dumps(data, ensure_ascii=False), flush=True)


def handle_request(request: Dict) -> Dict:
    """Handle JSON-RPC request."""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "knowledge-server", "version": "1.0.0"}
            }
        }
    
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS}
        }
    
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name not in TOOL_HANDLERS:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
            }
        
        try:
            result = TOOL_HANDLERS[tool_name](**arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(e)}
            }
    
    elif method == "notifications/initialized":
        return None
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"}
        }


def main() -> None:
    """Main server loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        
        response = handle_request(request)
        if response is not None:
            send_response(response)


if __name__ == "__main__":
    main()
