#!/usr/bin/env python3
"""
Semantics Tree extractor for Flutter applications.
Uses Dart VM Service protocol over WebSocket.
"""

import json
import threading
from typing import Optional, Dict, List, Any, Callable
from websocket import create_connection, WebSocket


class VMServiceClient:
    """Client for Dart VM Service protocol."""

    def __init__(self, uri: str):
        """
        Initialize VM Service client.

        Args:
            uri: WebSocket URI (e.g., ws://127.0.0.1:8181/ws)
        """
        self.uri = uri
        self._ws: Optional[WebSocket] = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._isolate_id: Optional[str] = None

    def connect(self) -> None:
        """Establish WebSocket connection."""
        self._ws = create_connection(self.uri, timeout=10)

    def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    def _next_id(self) -> str:
        with self._lock:
            self._request_id += 1
            return str(self._request_id)

    def _call(self, method: str, params: Optional[Dict] = None) -> Dict:
        """
        Make a JSON-RPC call to VM Service.

        Args:
            method: Method name
            params: Method parameters

        Returns:
            Response result dict
        """
        if not self._ws:
            raise RuntimeError("Not connected")

        request_id = self._next_id()
        request = {
            'jsonrpc': '2.0',
            'id': request_id,
            'method': method,
            'params': params or {}
        }

        self._ws.send(json.dumps(request))

        while True:
            response_text = self._ws.recv()
            response = json.loads(response_text)

            # Skip stream notifications
            if response.get('id') == request_id:
                if 'error' in response:
                    error = response['error']
                    raise RuntimeError(f"VM Service error: {error.get('message', error)}")
                return response.get('result', {})

    def get_vm(self) -> Dict:
        """Get VM information."""
        return self._call('getVM')

    def get_flutter_isolate(self) -> Optional[str]:
        """
        Find the main Flutter isolate ID.

        Returns:
            Isolate ID string or None
        """
        vm = self.get_vm()
        isolates = vm.get('isolates', [])

        for isolate in isolates:
            isolate_id = isolate.get('id')
            name = isolate.get('name', '')

            # Flutter main isolate is typically named 'main'
            if 'main' in name.lower():
                return isolate_id

        # Fallback: return first isolate
        if isolates:
            return isolates[0].get('id')

        return None

    def _ensure_isolate(self) -> str:
        """Ensure we have an isolate ID."""
        if not self._isolate_id:
            self._isolate_id = self.get_flutter_isolate()
            if not self._isolate_id:
                raise RuntimeError("No Flutter isolate found")
        return self._isolate_id

    def call_service_extension(self, extension: str, args: Optional[Dict] = None) -> Dict:
        """
        Call a Flutter service extension.

        Args:
            extension: Extension name (e.g., 'ext.flutter.debugDumpSemanticsTreeInTraversalOrder')
            args: Extension arguments

        Returns:
            Extension response
        """
        isolate_id = self._ensure_isolate()

        params = {
            'isolateId': isolate_id,
        }
        if args:
            params.update(args)

        return self._call(extension, params)

    def get_semantics_tree(self, traversal_order: bool = True) -> str:
        """
        Get the semantics tree dump.

        Args:
            traversal_order: If True, use traversal order; otherwise use inverse hit test order

        Returns:
            Semantics tree as formatted string
        """
        if traversal_order:
            ext = 'ext.flutter.debugDumpSemanticsTreeInTraversalOrder'
        else:
            ext = 'ext.flutter.debugDumpSemanticsTreeInInverseHitTestOrder'

        result = self.call_service_extension(ext)
        return result.get('data', '')

    def get_render_tree(self) -> str:
        """Get the render tree dump."""
        result = self.call_service_extension('ext.flutter.debugDumpRenderTree')
        return result.get('data', '')

    def get_layer_tree(self) -> str:
        """Get the layer tree dump."""
        result = self.call_service_extension('ext.flutter.debugDumpLayerTree')
        return result.get('data', '')

    def get_widget_tree(self) -> Dict:
        """Get the widget summary tree."""
        result = self.call_service_extension(
            'ext.flutter.inspector.getRootWidgetSummaryTree',
            {'groupName': 'flutter-inspect'}
        )
        return result

    def get_widget_tree_text(self) -> str:
        """Get widget tree as text dump."""
        result = self.call_service_extension('ext.flutter.debugDumpApp')
        return result.get('data', '')


class SemanticsNode:
    """Parsed semantics node."""

    def __init__(self):
        self.id: Optional[int] = None
        self.label: str = ''
        self.hint: str = ''
        self.value: str = ''
        self.flags: List[str] = []
        self.actions: List[str] = []
        self.rect: Optional[Dict] = None
        self.children: List['SemanticsNode'] = []
        self.raw_line: str = ''

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        result = {}

        if self.id is not None:
            result['id'] = self.id
        if self.label:
            result['label'] = self.label
        if self.hint:
            result['hint'] = self.hint
        if self.value:
            result['value'] = self.value
        if self.flags:
            result['flags'] = self.flags
        if self.actions:
            result['actions'] = self.actions
        if self.children:
            result['children'] = [c.to_dict() for c in self.children]

        return result


def parse_semantics_dump(dump: str) -> List[SemanticsNode]:
    """
    Parse semantics tree dump into structured nodes.

    The dump format looks like:
    SemanticsNode#1
     │ Rect.fromLTRB(0.0, 0.0, 800.0, 600.0)
     │ actions: tap
     │ label: "Button text"
     │
     └─SemanticsNode#2
        ...

    Args:
        dump: Raw semantics dump string

    Returns:
        List of root SemanticsNode objects
    """
    if not dump:
        return []

    lines = dump.strip().split('\n')
    nodes = []
    node_stack: List[tuple] = []  # (indent_level, node)

    current_node: Optional[SemanticsNode] = None
    current_indent = 0

    for line in lines:
        stripped = line.lstrip(' │├└─')
        original_len = len(line)
        stripped_len = len(stripped)
        indent = original_len - stripped_len

        # New node starts with "SemanticsNode#"
        if stripped.startswith('SemanticsNode#'):
            node = SemanticsNode()
            node.raw_line = stripped

            # Extract node ID
            try:
                id_part = stripped.split('#')[1].split()[0].split('(')[0]
                node.id = int(id_part)
            except (IndexError, ValueError):
                pass

            # Determine parent based on indentation
            while node_stack and node_stack[-1][0] >= indent:
                node_stack.pop()

            if node_stack:
                parent_node = node_stack[-1][1]
                parent_node.children.append(node)
            else:
                nodes.append(node)

            node_stack.append((indent, node))
            current_node = node
            current_indent = indent

        elif current_node and stripped:
            # Parse node properties
            _parse_semantics_property(current_node, stripped)

    return nodes


def _parse_semantics_property(node: SemanticsNode, line: str) -> None:
    """Parse a property line and update the node."""
    line = line.strip()

    if line.startswith('label:'):
        # label: "Some text"
        value = line[6:].strip().strip('"')
        node.label = value

    elif line.startswith('hint:'):
        value = line[5:].strip().strip('"')
        node.hint = value

    elif line.startswith('value:'):
        value = line[6:].strip().strip('"')
        node.value = value

    elif line.startswith('actions:'):
        # actions: tap, longPress, scrollUp
        actions_str = line[8:].strip()
        node.actions = [a.strip() for a in actions_str.split(',')]

    elif line.startswith('flags:'):
        flags_str = line[6:].strip()
        node.flags = [f.strip() for f in flags_str.split(',')]

    elif line.startswith('Rect.'):
        # Rect.fromLTRB(x, y, w, h)
        try:
            import re
            match = re.search(r'Rect\.fromLTRB\(([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\)', line)
            if match:
                node.rect = {
                    'left': float(match.group(1)),
                    'top': float(match.group(2)),
                    'right': float(match.group(3)),
                    'bottom': float(match.group(4))
                }
        except Exception:
            pass


def extract_semantics(uri: str) -> Dict[str, Any]:
    """
    Extract semantics information from a Flutter app.

    Args:
        uri: VM Service WebSocket URI

    Returns:
        Dictionary with semantics data
    """
    with VMServiceClient(uri) as client:
        # Get raw semantics dump
        raw_dump = client.get_semantics_tree(traversal_order=True)

        # Parse into structured format
        nodes = parse_semantics_dump(raw_dump)

        # Get VM info for context
        vm_info = client.get_vm()

        return {
            'vm_version': vm_info.get('version', 'unknown'),
            'raw_dump': raw_dump,
            'nodes': [n.to_dict() for n in nodes],
            'node_count': _count_nodes(nodes)
        }


def _count_nodes(nodes: List[SemanticsNode]) -> int:
    """Count total nodes including children."""
    count = len(nodes)
    for node in nodes:
        count += _count_nodes(node.children)
    return count


def get_compact_semantics(uri: str) -> List[Dict]:
    """
    Get a compact representation of semantics for LLM context.

    Filters out nodes without meaningful content and flattens structure.

    Args:
        uri: VM Service WebSocket URI

    Returns:
        List of compact node representations
    """
    data = extract_semantics(uri)
    nodes = data.get('nodes', [])

    compact = []
    _flatten_meaningful_nodes(nodes, compact)
    return compact


def _flatten_meaningful_nodes(nodes: List[SemanticsNode], result: List[Dict], depth: int = 0) -> None:
    """Recursively extract meaningful nodes."""
    for node in nodes:
        # Include node if it has label, value, or actions
        if node.label or node.value or node.actions:
            entry = {}

            if node.label:
                entry['label'] = node.label
            if node.value:
                entry['value'] = node.value
            if node.hint:
                entry['hint'] = node.hint
            if node.actions:
                entry['actions'] = node.actions
            if node.flags:
                entry['flags'] = node.flags

            entry['depth'] = depth
            result.append(entry)

        # Process children
        if node.children:
            _flatten_meaningful_nodes(node.children, result, depth + 1)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python semantics.py <vm_service_uri>")
        print("Example: python semantics.py ws://127.0.0.1:8181/ws")
        sys.exit(1)

    uri = sys.argv[1]

    print(f"Connecting to {uri}...")
    try:
        data = extract_semantics(uri)
        print(f"\nVM Version: {data['vm_version']}")
        print(f"Total nodes: {data['node_count']}")
        print("\n--- Raw Dump ---")
        print(data['raw_dump'][:2000] if len(data['raw_dump']) > 2000 else data['raw_dump'])

        print("\n--- Compact Semantics ---")
        compact = get_compact_semantics(uri)
        print(json.dumps(compact, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
