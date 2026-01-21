#!/usr/bin/env python3
"""
JSON formatter for Flutter UI semantics.
Produces structured JSON output for parsing.
"""

import json
from typing import List, Dict, Any, Optional


def format_json(
    nodes: List[Dict],
    device_info: Optional[Dict] = None,
    indent: Optional[int] = 2,
    ensure_ascii: bool = False
) -> str:
    """
    Format semantics nodes as JSON.

    Args:
        nodes: List of semantics node dicts
        device_info: Optional device/connection info
        indent: JSON indentation (None for compact)
        ensure_ascii: Whether to escape non-ASCII characters

    Returns:
        JSON string
    """
    output = {
        'elements': nodes,
        'count': len(nodes)
    }

    if device_info:
        output['device'] = device_info

    return json.dumps(output, indent=indent, ensure_ascii=ensure_ascii)


def format_json_lines(nodes: List[Dict]) -> str:
    """
    Format as JSON Lines (one JSON object per line).
    Useful for streaming or line-by-line processing.

    Args:
        nodes: List of semantics node dicts

    Returns:
        JSON Lines string
    """
    lines = []
    for node in nodes:
        lines.append(json.dumps(node, ensure_ascii=False))
    return '\n'.join(lines)


def format_compact_json(nodes: List[Dict]) -> str:
    """
    Format as single-line compact JSON.
    Maximum token efficiency for LLM context.

    Args:
        nodes: List of semantics node dicts

    Returns:
        Compact JSON string
    """
    # Simplify nodes for maximum compactness
    simplified = []
    for node in nodes:
        simple = {}

        label = node.get('label', '')
        value = node.get('value', '')
        actions = node.get('actions', [])

        if label:
            simple['l'] = label  # Short key
        if value and value != label:
            simple['v'] = value
        if actions:
            simple['a'] = actions

        if simple:
            simplified.append(simple)

    return json.dumps(simplified, ensure_ascii=False, separators=(',', ':'))


def to_dict(
    nodes: List[Dict],
    device_info: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Convert to dictionary (for further processing).

    Args:
        nodes: List of semantics node dicts
        device_info: Optional device/connection info

    Returns:
        Dictionary with full data
    """
    output = {
        'elements': nodes,
        'count': len(nodes)
    }

    if device_info:
        output['device'] = device_info

    return output
