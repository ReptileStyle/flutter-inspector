#!/usr/bin/env python3
"""
Flutter UI Inspector CLI

Automatically connects to a running Flutter debug app and outputs
a compact representation of the current UI for LLM context.

Usage:
    flutter-inspect              # Auto-discover and inspect
    flutter-inspect --json       # Output as JSON
    flutter-inspect --watch      # Watch for changes
    flutter-inspect --uri <uri>  # Connect to specific VM service
"""

import argparse
import sys
import time
import signal
from typing import Optional

from discovery import discover_vm_service, list_vm_services
from extractors.semantics import get_compact_semantics, VMServiceClient
from formatters.compact import format_compact, format_tree, format_minimal, estimate_tokens
from formatters.json_output import format_json, format_compact_json


def main():
    parser = argparse.ArgumentParser(
        description='Inspect Flutter UI for LLM context',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                    Auto-discover and inspect
  %(prog)s --json             Output as JSON
  %(prog)s --minimal          Ultra-compact output
  %(prog)s --watch            Watch for UI changes
  %(prog)s --uri ws://...     Connect to specific service
  %(prog)s --list             List available services
'''
    )

    parser.add_argument(
        '--uri',
        help='VM Service WebSocket URI (e.g., ws://127.0.0.1:8181/ws)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all discovered Flutter debug services'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['compact', 'tree', 'minimal', 'json', 'json-compact'],
        default='compact',
        help='Output format (default: compact)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Shortcut for --format json'
    )
    parser.add_argument(
        '--minimal',
        action='store_true',
        help='Shortcut for --format minimal'
    )
    parser.add_argument(
        '--watch', '-w',
        action='store_true',
        help='Watch for UI changes (Ctrl+C to stop)'
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=2.0,
        help='Watch interval in seconds (default: 2.0)'
    )
    parser.add_argument(
        '--raw',
        action='store_true',
        help='Output raw semantics dump from Flutter'
    )
    parser.add_argument(
        '--widgets',
        action='store_true',
        help='Use widget tree instead of semantics (no TalkBack needed)'
    )
    parser.add_argument(
        '--tokens',
        action='store_true',
        help='Show estimated token count'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress connection info, output only UI data'
    )

    args = parser.parse_args()

    # Handle format shortcuts
    if args.json:
        args.format = 'json'
    if args.minimal:
        args.format = 'minimal'

    # List mode
    if args.list:
        list_services()
        return 0

    # Discover or use provided URI
    uri = args.uri
    if not uri:
        if not args.quiet:
            print("Searching for Flutter debug apps...", file=sys.stderr)
        uri = discover_vm_service()

    if not uri:
        print("Error: No Flutter debug app found.", file=sys.stderr)
        print("Make sure you have a Flutter app running in debug mode.", file=sys.stderr)
        print("Tip: Run 'flutter run' in your Flutter project.", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Connecting to: {uri}", file=sys.stderr)

    # Watch mode
    if args.watch:
        return watch_mode(uri, args)

    # Single inspection
    return inspect_once(uri, args)


def list_services():
    """List all discovered VM services."""
    print("Searching for Flutter debug services...")
    services = list_vm_services()

    if not services:
        print("No Flutter debug apps found.")
        return

    print(f"\nFound {len(services)} service(s):\n")
    for i, svc in enumerate(services):
        print(f"  [{i}] {svc['uri']}")
        if svc['pid']:
            print(f"      PID: {svc['pid']}")
        if svc['app_name']:
            print(f"      App: {svc['app_name']}")
        print()


def inspect_once(uri: str, args) -> int:
    """Perform single UI inspection."""
    try:
        with VMServiceClient(uri) as client:
            if args.raw:
                # Raw dump mode
                raw = client.get_semantics_tree()
                print(raw)
                return 0

            if args.widgets:
                # Widget tree mode
                return inspect_widget_tree(client, args)

            # Try semantics first
            nodes = get_compact_semantics(uri)

            if not nodes:
                if not args.quiet:
                    print("Semantics empty, falling back to widget tree...", file=sys.stderr)
                return inspect_widget_tree(client, args)

            # Format output
            device_info = {'uri': uri} if not args.quiet else None
            output = format_output(nodes, args.format, device_info)

            print(output)

            # Show token estimate
            if args.tokens:
                tokens = estimate_tokens(output)
                print(f"\n[Estimated tokens: ~{tokens}]", file=sys.stderr)

            return 0

    except ConnectionRefusedError:
        print(f"Error: Connection refused to {uri}", file=sys.stderr)
        print("The Flutter app may have been closed.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def inspect_widget_tree(client: VMServiceClient, args) -> int:
    """Inspect using widget tree (debugDumpApp)."""
    try:
        output = client.get_widget_tree_text()

        if not output:
            print("Widget tree is empty", file=sys.stderr)
            return 1

        print(output)

        if args.tokens:
            tokens = estimate_tokens(output)
            print(f"\n[Estimated tokens: ~{tokens}]", file=sys.stderr)

        return 0
    except Exception as e:
        print(f"Error getting widget tree: {e}", file=sys.stderr)
        return 1


def watch_mode(uri: str, args) -> int:
    """Watch for UI changes."""
    print(f"Watching UI changes (interval: {args.interval}s, Ctrl+C to stop)...\n", file=sys.stderr)

    # Handle Ctrl+C gracefully
    stop = False

    def signal_handler(sig, frame):
        nonlocal stop
        stop = True
        print("\nStopping watch...", file=sys.stderr)

    signal.signal(signal.SIGINT, signal_handler)

    last_output = None
    iteration = 0

    while not stop:
        try:
            nodes = get_compact_semantics(uri)
            output = format_output(nodes, args.format, None)

            # Only print if changed
            if output != last_output:
                iteration += 1
                if not args.quiet:
                    print(f"\n--- Update #{iteration} ---", file=sys.stderr)
                print(output)
                last_output = output

            time.sleep(args.interval)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            time.sleep(args.interval)

    return 0


def format_output(nodes, format_type: str, device_info: Optional[dict]) -> str:
    """Format nodes according to specified format."""
    if format_type == 'json':
        return format_json(nodes, device_info)
    elif format_type == 'json-compact':
        return format_compact_json(nodes)
    elif format_type == 'tree':
        return format_tree(nodes, device_info)
    elif format_type == 'minimal':
        return format_minimal(nodes)
    else:  # compact
        return format_compact(nodes, device_info)


if __name__ == '__main__':
    sys.exit(main())
