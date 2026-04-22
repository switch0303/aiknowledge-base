#!/usr/bin/env python3
"""
Knowledge entry quality scorer.

Usage:
    python check_quality.py <json_file> [json_file2 ...]
    python check_quality.py *.json
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

ID_PATTERN = re.compile(r"^[a-z]+-\d{8}-\d{3}$")

VALID_STATUSES = {"draft", "review", "published", "archived"}

TECH_KEYWORDS = {
    "api", "sdk", "cli", "rest", "graphql", "grpc", "json", "yaml", "xml",
    "python", "javascript", "typescript", "java", "go", "rust", "c++", "rust",
    "docker", "kubernetes", "k8s", "linux", "unix", "windows",
    "machine learning", "deep learning", "neural network", "transformer",
    "llm", "gpt", "bert", "rag", "fine-tuning", "embedding",
    "database", "sql", "nosql", "redis", "mongodb", "postgresql",
    "cache", "queue", "microservice", "serverless", "faas",
    "git", "ci/cd", "pipeline", "deployment", "container",
    "security", "encryption", "authentication", "oauth", "jwt",
    "http", "tcp", "udp", "websocket", "http2", "http3",
    "algorithm", "data structure", "distributed", "consensus",
    "blockchain", "web3", "defi", "nft",
    "frontend", "backend", "fullstack", "devops", "sre",
    "performance", "optimization", "benchmark", "profiling",
    "testing", "unit test", "integration test", "e2e",
    "cloud", "aws", "azure", "gcp", "serverless",
    "reactive", "async", "concurrency", "parallelism",
    "design pattern", "architecture", "microservices", "monolith",
}

BUZZWORD_CN = {
    "赋能", "抓手", "闭环", "打通", "全链路", "底层逻辑", "颗粒度",
    "对齐", "拉通", "沉淀", "强大的", "革命性的", "端到端", "矩阵式",
    "立体化", "多维度", "体系化", "系统化", "流程化", "规范化",
    "精细化", "差异化", "规模化", "产业化", "生态化", "平台化",
    "数字化", "智能化", "自动化", "可视化", "敏捷", "快速迭代",
}

BUZZWORD_EN = {
    "groundbreaking", "revolutionary", "game-changing", "cutting-edge",
    "next-generation", "best-in-class", "world-class", "state-of-the-art",
    "innovative", "disruptive", "paradigm shift", "leverage", "synergy",
    "holistic", "robust", "scalable", "seamless", "optimize", "streamline",
}

VALID_TAGS = {
    "ai", "ml", "deep-learning", "nlp", "computer-vision", "robotics",
    "blockchain", "web3", "defi", "nft", "crypto",
    "web", "frontend", "backend", "fullstack", "mobile", "desktop",
    "devops", "cloud", "security", "database", "infrastructure",
    "open-source", "framework", "library", "tool", "api", "protocol",
    "tutorial", "guide", "reference", "news", "research", "paper",
    "video", "podcast", "article", "blog", "documentation",
    "beginner", "intermediate", "advanced", "expert",
}


@dataclass
class DimensionScore:
    name: str
    score: float
    max_score: float
    detail: str


@dataclass
class QualityReport:
    file_path: Path
    summary_quality: DimensionScore
    tech_depth: DimensionScore
    format_compliance: DimensionScore
    tag_precision: DimensionScore
    buzzword_detection: DimensionScore
    total_score: float
    grade: str

    def print_report(self) -> None:
        print(f"\n{'=' * 60}")
        print(f"File: {self.file_path}")
        print(f"{'=' * 60}")
        self._print_dimension(self.summary_quality)
        self._print_dimension(self.tech_depth)
        self._print_dimension(self.format_compliance)
        self._print_dimension(self.tag_precision)
        self._print_dimension(self.buzzword_detection)
        print(f"{'-' * 60}")
        print(f"Total Score: {self.total_score:.1f}/100")
        print(f"Grade: {self.grade}")
        print(f"{'=' * 60}")

    def _print_dimension(self, dim: DimensionScore) -> None:
        bar_len = 20
        filled = int(bar_len * dim.score / dim.max_score)
        bar = "█" * filled + "░" * (bar_len - filled)
        pct = dim.score / dim.max_score * 100
        print(f"[{bar}] {dim.score:.1f}/{dim.max_score:.0f} ({pct:.0f}%) {dim.name}")
        print(f"  └─ {dim.detail}")


def expand_paths(paths: List[str]) -> List[Path]:
    result = []
    for path_str in paths:
        path = Path(path_str)
        if "*" in path_str:
            if path.parent != Path("."):
                result.extend(path.parent.glob(path.name))
            else:
                result.extend(Path(".").glob(path.name))
        else:
            result.append(path)
    return [p for p in result if p.is_file() and p.suffix == ".json"]


def check_summary_quality(data: dict) -> DimensionScore:
    summary = data.get("summary", "")
    length = len(summary)

    if length >= 50:
        base_score = 20.0
        detail = f"Excellent summary ({length} chars)"
    elif length >= 20:
        base_score = 12.0
        detail = f"Acceptable summary ({length} chars)"
    else:
        base_score = 0.0
        detail = f"Too short summary ({length} chars, need >= 20)"

    bonus = 0.0
    found_keywords = []
    summary_lower = summary.lower()
    for kw in TECH_KEYWORDS:
        if kw.lower() in summary_lower:
            found_keywords.append(kw)

    if found_keywords:
        bonus = min(5.0, 1.0 * len(found_keywords[:5]))
        detail += f", keywords: {', '.join(found_keywords[:3])}"

    return DimensionScore(
        name="Summary Quality",
        score=min(base_score + bonus, 25.0),
        max_score=25.0,
        detail=detail
    )


def check_tech_depth(data: dict) -> DimensionScore:
    score = data.get("score")
    if score is None:
        return DimensionScore(
            name="Technical Depth",
            score=0.0,
            max_score=25.0,
            detail="No score field, cannot assess depth"
        )

    try:
        score_val = float(score)
        if 1 <= score_val <= 10:
            mapped = (score_val - 1) / 9 * 25.0
            return DimensionScore(
                name="Technical Depth",
                score=mapped,
                max_score=25.0,
                detail=f"Score {score_val}/10 mapped to {mapped:.1f}/25"
            )
        else:
            return DimensionScore(
                name="Technical Depth",
                score=0.0,
                max_score=25.0,
                detail=f"Invalid score {score_val}, expected 1-10"
            )
    except (ValueError, TypeError):
        return DimensionScore(
            name="Technical Depth",
            score=0.0,
            max_score=25.0,
            detail=f"Invalid score type: {type(score).__name__}"
        )


def check_format_compliance(data: dict) -> DimensionScore:
    score = 0.0
    details = []

    if "id" in data and ID_PATTERN.match(str(data["id"])):
        score += 4.0
        details.append("id ✓")
    else:
        details.append("id ✗")

    if "title" in data and data["title"]:
        score += 4.0
        details.append("title ✓")
    else:
        details.append("title ✗")

    if "source_url" in data and str(data["source_url"]).startswith(("http://", "https://")):
        score += 4.0
        details.append("source_url ✓")
    else:
        details.append("source_url ✗")

    if "status" in data and data["status"] in VALID_STATUSES:
        score += 4.0
        details.append("status ✓")
    else:
        details.append("status ✗")

    has_timestamp = False
    entry_id = data.get("id", "")
    if len(entry_id) >= 9:
        ts_part = re.search(r"\d{8}", entry_id)
        if ts_part and len(ts_part.group()) == 8:
            has_timestamp = True
    if "created_at" in data or "updated_at" in data:
        has_timestamp = True

    if has_timestamp:
        score += 4.0
        details.append("timestamp ✓")
    else:
        details.append("timestamp ✗")

    return DimensionScore(
        name="Format Compliance",
        score=score,
        max_score=20.0,
        detail=", ".join(details)
    )


def check_tag_precision(data: dict) -> DimensionScore:
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        return DimensionScore(
            name="Tag Precision",
            score=0.0,
            max_score=15.0,
            detail="Tags must be a list"
        )

    tag_count = len(tags)
    if tag_count == 0:
        return DimensionScore(
            name="Tag Precision",
            score=0.0,
            max_score=15.0,
            detail="No tags provided"
        )

    valid_tags = [t for t in tags if t in VALID_TAGS]
    invalid_tags = [t for t in tags if t not in VALID_TAGS]

    if 1 <= tag_count <= 3:
        base_score = 10.0
        detail = f"{tag_count} tags (optimal range)"
    elif 4 <= tag_count <= 5:
        base_score = 6.0
        detail = f"{tag_count} tags (slightly too many)"
    else:
        base_score = 3.0
        detail = f"{tag_count} tags (too many, 1-3 optimal)"

    bonus = min(5.0, 2.5 * len(valid_tags))
    detail += f", {len(valid_tags)} valid"

    if invalid_tags:
        detail += f", invalid: {', '.join(invalid_tags[:2])}"

    return DimensionScore(
        name="Tag Precision",
        score=min(base_score + bonus, 15.0),
        max_score=15.0,
        detail=detail
    )


def check_buzzword_detection(data: dict) -> DimensionScore:
    text_parts = []

    if "title" in data:
        text_parts.append(str(data["title"]))
    if "summary" in data:
        text_parts.append(str(data["summary"]))
    if "tags" in data and isinstance(data["tags"], list):
        text_parts.extend([str(t) for t in data["tags"]])

    full_text = " ".join(text_parts).lower()

    found_buzzwords = []

    for bw in BUZZWORD_CN:
        if bw in full_text:
            found_buzzwords.append(bw)

    for bw in BUZZWORD_EN:
        if bw.lower() in full_text:
            found_buzzwords.append(bw)

    if not found_buzzwords:
        score = 15.0
        detail = "No buzzwords detected"
    else:
        score = max(0.0, 15.0 - 3.0 * len(found_buzzwords))
        detail = f"Found {len(found_buzzwords)} buzzwords: {', '.join(found_buzzwords[:3])}"

    return DimensionScore(
        name="Buzzword Detection",
        score=score,
        max_score=15.0,
        detail=detail
    )


def score_entry(file_path: Path) -> QualityReport:
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return QualityReport(
            file_path=file_path,
            summary_quality=DimensionScore("Summary Quality", 0, 25, "Invalid JSON"),
            tech_depth=DimensionScore("Technical Depth", 0, 25, "Invalid JSON"),
            format_compliance=DimensionScore("Format Compliance", 0, 20, "Invalid JSON"),
            tag_precision=DimensionScore("Tag Precision", 0, 15, "Invalid JSON"),
            buzzword_detection=DimensionScore("Buzzword Detection", 0, 15, "Invalid JSON"),
            total_score=0.0,
            grade="C"
        )

    summary_quality = check_summary_quality(data)
    tech_depth = check_tech_depth(data)
    format_compliance = check_format_compliance(data)
    tag_precision = check_tag_precision(data)
    buzzword_detection = check_buzzword_detection(data)

    total = summary_quality.score + tech_depth.score + format_compliance.score
    total += tag_precision.score + buzzword_detection.score

    if total >= 80:
        grade = "A"
    elif total >= 60:
        grade = "B"
    else:
        grade = "C"

    return QualityReport(
        file_path=file_path,
        summary_quality=summary_quality,
        tech_depth=tech_depth,
        format_compliance=format_compliance,
        tag_precision=tag_precision,
        buzzword_detection=buzzword_detection,
        total_score=total,
        grade=grade
    )


def print_progress_bar(current: int, total: int, prefix: str = "Progress") -> None:
    bar_len = 40
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    pct = current / total * 100 if total > 0 else 0
    sys.stdout.write(f"\r{prefix}: [{bar}] {current}/{total} ({pct:.0f}%)")
    sys.stdout.flush()


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python check_quality.py <json_file> [json_file2 ...]")
        sys.exit(1)

    files = expand_paths(sys.argv[1:])

    if not files:
        print("No JSON files found")
        sys.exit(1)

    total_files = len(files)
    reports: List[QualityReport] = []

    print(f"Scoring {total_files} file(s)...\n")

    for i, file_path in enumerate(sorted(files)):
        print_progress_bar(i, total_files)
        report = score_entry(file_path)
        reports.append(report)

    print_progress_bar(total_files, total_files)
    print()

    grade_counts = {"A": 0, "B": 0, "C": 0}

    for report in reports:
        report.print_report()
        grade_counts[report.grade] += 1

    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")
    print(f"Total: {total_files}")
    print(f"Grade A (>= 80): {grade_counts['A']}")
    print(f"Grade B (>= 60): {grade_counts['B']}")
    print(f"Grade C (< 60): {grade_counts['C']}")

    avg_score = sum(r.total_score for r in reports) / total_files
    print(f"Average Score: {avg_score:.1f}")

    if grade_counts["C"] > 0:
        print(f"\n⚠ {grade_counts['C']} file(s) below quality threshold (Grade C)")
        sys.exit(1)

    print("\n✓ All files passed quality check")
    sys.exit(0)


if __name__ == "__main__":
    main()
