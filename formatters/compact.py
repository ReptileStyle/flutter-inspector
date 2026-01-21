#!/usr/bin/env python3
"""
Compact text formatter for Flutter UI semantics.
Produces human-readable, LLM-friendly output.
"""

from typing import List, Dict, Any, Optional


def format_compact(nodes: List[Dict], device_info: Optional[Dict] = None) -> str:
    """
    Format semantics nodes as compact text representation.

    Args:
        nodes: List of semantics node dicts
        device_info: Optional device/connection info

    Returns:
        Formatted string
    """
    lines = []

    # Header
    if device_info:
        if device_info.get('device'):
            lines.append(f"Device: {device_info['device']}")
        if device_info.get('uri'):
            lines.append(f"Connected: {device_info['uri']}")
        lines.append('')

    lines.append("UI Elements:")
    lines.append("-" * 40)

    # Format each node
    for node in nodes:
        line = _format_node(node)
        if line:
            lines.append(line)

    # Footer
    lines.append("-" * 40)
    lines.append(f"Total: {len(nodes)} elements")

    return '\n'.join(lines)


def _format_node(node: Dict) -> str:
    """Format a single node as a compact line."""
    parts = []

    # Indentation based on depth
    depth = node.get('depth', 0)
    indent = '  ' * min(depth, 4)  # Cap indent at 4 levels

    # Main content: label or value
    label = node.get('label', '')
    value = node.get('value', '')
    hint = node.get('hint', '')

    if label:
        parts.append(f'"{label}"')
    if value and value != label:
        parts.append(f'[{value}]')
    if hint:
        parts.append(f'({hint})')

    if not parts:
        return ''

    # Actions
    actions = node.get('actions', [])
    if actions:
        action_str = ', '.join(actions)
        parts.append(f'<{action_str}>')

    # Flags (only important ones)
    flags = node.get('flags', [])
    important_flags = _filter_important_flags(flags)
    if important_flags:
        flag_str = ', '.join(important_flags)
        parts.append(f'{{{flag_str}}}')

    return indent + ' '.join(parts)


def _filter_important_flags(flags: List[str]) -> List[str]:
    """Filter to keep only important flags for LLM context."""
    important = {
        'isButton',
        'isLink',
        'isHeader',
        'isTextField',
        'isSlider',
        'isChecked',
        'isSelected',
        'isEnabled',
        'isDisabled',
        'isFocused',
        'hasCheckedState',
        'hasSelectedState',
        'hasEnabledState',
        'isReadOnly',
        'isMultiline',
        'isHidden',
        'isImage',
        'isLiveRegion',
    }
    return [f for f in flags if f in important]


def format_tree(nodes: List[Dict], device_info: Optional[Dict] = None) -> str:
    """
    Format semantics as a tree structure with box-drawing characters.

    Args:
        nodes: List of semantics node dicts (flattened)
        device_info: Optional device/connection info

    Returns:
        Formatted tree string
    """
    lines = []

    # Header
    if device_info:
        if device_info.get('device'):
            lines.append(f"Device: {device_info['device']}")
        if device_info.get('uri'):
            lines.append(f"Connected: {device_info['uri']}")
        lines.append('')

    lines.append("UI Structure:")
    lines.append("")

    # Build tree representation
    prev_depth = -1
    for i, node in enumerate(nodes):
        depth = node.get('depth', 0)
        is_last = (i == len(nodes) - 1) or (i < len(nodes) - 1 and nodes[i + 1].get('depth', 0) <= depth)

        # Tree connectors
        if depth == 0:
            prefix = ''
        else:
            prefix = '│   ' * (depth - 1)
            if is_last:
                prefix += '└── '
            else:
                prefix += '├── '

        # Node content
        content = _format_node_content(node)
        if content:
            lines.append(prefix + content)

        prev_depth = depth

    lines.append('')
    lines.append(f"({len(nodes)} elements)")

    return '\n'.join(lines)


def _format_node_content(node: Dict) -> str:
    """Format node content for tree display."""
    label = node.get('label', '')
    value = node.get('value', '')
    actions = node.get('actions', [])

    parts = []

    if label:
        parts.append(f'"{label}"')
    elif value:
        parts.append(f'[{value}]')

    if actions:
        parts.append(f'<{", ".join(actions)}>')

    return ' '.join(parts) if parts else None


def format_minimal(nodes: List[Dict]) -> str:
    """
    Ultra-minimal format for maximum token efficiency.

    Output format:
    "Label" [actions]
    "Another label" [actions]
    """
    lines = []

    for node in nodes:
        label = node.get('label', '') or node.get('value', '')
        if not label:
            continue

        actions = node.get('actions', [])

        if actions:
            lines.append(f'"{label}" [{", ".join(actions)}]')
        else:
            lines.append(f'"{label}"')

    return '\n'.join(lines)


def estimate_tokens(text: str) -> int:
    """
    Rough estimate of token count.
    Assumes ~4 characters per token on average.
    """
    return len(text) // 4
