#!/usr/bin/env python3
"""
Knowledge entry JSON validator.

Usage:
    python validate_json.py <json_file> [json_file2 ...]
    python validate_json.py *.json
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REQUIRED_FIELDS: Dict[str, type] = {
    "id": str,
    "title": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

ID_PATTERN = re.compile(r"^[a-z]+-\d{8}-\d{3}$")

VALID_STATUSES = {"draft", "review", "published", "archived"}

URL_PATTERN = re.compile(r"^https?://")

VALID_AUDIENCES = {"beginner", "intermediate", "advanced"}


def validate_id(value: str) -> List[str]:
    errors = []
    if not ID_PATTERN.match(value):
        errors.append(
            f"ID '{value}' does not match format {{source}}-{{YYYYMMDD}}-{{NNN}}"
        )
    return errors


def validate_url(value: str) -> List[str]:
    errors = []
    if not URL_PATTERN.match(value):
        errors.append(f"URL '{value}' does not start with http:// or https://")
    return errors


def validate_summary(value: str) -> List[str]:
    errors = []
    if len(value) < 20:
        errors.append(f"Summary must be at least 20 characters, got {len(value)}")
    return errors


def validate_tags(value: List) -> List[str]:
    errors = []
    if len(value) < 1:
        errors.append("Tags must contain at least 1 item")
    return errors


def validate_status(value: str) -> List[str]:
    errors = []
    if value not in VALID_STATUSES:
        errors.append(
            f"Status '{value}' must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )
    return errors


def validate_score(value) -> List[str]:
    errors = []
    if not isinstance(value, (int, float)):
        errors.append(f"Score must be a number, got {type(value).__name__}")
    elif value < 1 or value > 10:
        errors.append(f"Score must be between 1 and 10, got {value}")
    return errors


def validate_audience(value: str) -> List[str]:
    errors = []
    if value not in VALID_AUDIENCES:
        errors.append(
            f"Audience '{value}' must be one of: {', '.join(sorted(VALID_AUDIENCES))}"
        )
    return errors


def validate_entry(file_path: Path) -> Tuple[bool, List[str]]:
    errors = []

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"JSON parse error: {e}"]

    if not isinstance(data, dict):
        return False, ["Root must be a JSON object"]

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"Missing required field: '{field}'")
        elif not isinstance(data[field], expected_type):
            errors.append(
                f"Field '{field}' must be {expected_type.__name__}, "
                f"got {type(data[field]).__name__}"
            )

    if "id" in data and isinstance(data["id"], str):
        errors.extend(validate_id(data["id"]))

    if "source_url" in data and isinstance(data["source_url"], str):
        errors.extend(validate_url(data["source_url"]))

    if "summary" in data and isinstance(data["summary"], str):
        errors.extend(validate_summary(data["summary"]))

    if "tags" in data and isinstance(data["tags"], list):
        errors.extend(validate_tags(data["tags"]))

    if "status" in data and isinstance(data["status"], str):
        errors.extend(validate_status(data["status"]))

    if "score" in data:
        errors.extend(validate_score(data["score"]))

    if "audience" in data and isinstance(data["audience"], str):
        errors.extend(validate_audience(data["audience"]))

    return len(errors) == 0, errors


def expand_paths(paths: List[str]) -> List[Path]:
    result = []
    for path_str in paths:
        path = Path(path_str)
        if "*" in path_str:
            result.extend(path.parent.glob(path.name) if path.parent != Path(".") else Path(".").glob(path.name))
        else:
            result.append(path)
    return [p for p in result if p.is_file() and p.suffix == ".json"]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python validate_json.py <json_file> [json_file2 ...]")
        sys.exit(1)

    files = expand_paths(sys.argv[1:])

    if not files:
        print("No JSON files found")
        sys.exit(1)

    total_files = len(files)
    passed = 0
    failed = 0

    all_errors: Dict[Path, List[str]] = {}

    for file_path in sorted(files):
        valid, errors = validate_entry(file_path)
        if valid:
            passed += 1
            print(f"✓ {file_path}")
        else:
            failed += 1
            all_errors[file_path] = errors
            print(f"✗ {file_path}")

    print()
    print(f"Total: {total_files}, Passed: {passed}, Failed: {failed}")

    if failed > 0:
        print()
        for file_path, errors in all_errors.items():
            print(f"Errors in {file_path}:")
            for error in errors:
                print(f"  - {error}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
