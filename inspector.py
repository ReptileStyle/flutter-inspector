#!/usr/bin/env python3
"""
Flutter UI Inspector CLI

Automatically connects to a running Flutter debug app and outputs
a compact representation of the current UI for LLM context.

Usage:
    flutter-inspect --content       # What's on screen? (best for agents)
    flutter-inspect --smart         # Filtered widget tree
    flutter-inspect --trace "text"  # Why is this element here?
    flutter-inspect --widgets       # Raw widget tree (verbose)
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
from formatters.widget_filter import format_smart, format_content_only, format_layout_trace


QUICK_HELP = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                      FLUTTER-INSPECT: AI AGENT GUIDE                         ║
╚══════════════════════════════════════════════════════════════════════════════╝

WHAT IS THIS?
  Tool to see what's on screen in a running Flutter debug app.
  Prerequisite: Flutter app must be running via `flutter run` (debug mode).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RECOMMENDED WORKFLOW (for AI agents)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Step 1: Save full widget tree to temp file (DO THIS FIRST):

      flutter-inspect --widgets > /tmp/flutter_widgets.txt

  Step 2: Work with the saved file:

      grep -n "YourWidget\\|Text\\|padding" /tmp/flutter_widgets.txt
      head -100 /tmp/flutter_widgets.txt
      sed -n '50,100p' /tmp/flutter_widgets.txt

  Why? The raw output is 4000+ lines. Save once, grep many times.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUICK COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  flutter-inspect --content     "What text/icons are on screen?"  (~300 lines)
  flutter-inspect --smart       "What's the widget structure?"    (~1700 lines)
  flutter-inspect --widgets     "Give me everything"              (~4000 lines)
  flutter-inspect --trace "X"   "Why does X have this padding?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON ERRORS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  "No Flutter debug app found"  → Run `flutter run` first in the Flutter project
  Empty output / "PROFILE MODE" → App in profile mode, restart with `flutter run`
  "Connection refused"          → App was closed, restart it

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run with --help for all options.
"""


def main():
    parser = argparse.ArgumentParser(
        description='Inspect Flutter UI for LLM context',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Widget Tree Modes (recommended for agents):
  %(prog)s --content          What's on screen? Text, icons with context
  %(prog)s --smart            Filtered tree - layout widgets only
  %(prog)s --trace "text"     Layout path to specific text (debug spacing)
  %(prog)s --widgets          Raw widget tree (verbose, 4000+ lines)

Examples:
  %(prog)s --content          Best for "what do you see?"
  %(prog)s --smart            Best for "understand screen structure"
  %(prog)s --trace "Сегодня"  Best for "why is this here?"
  %(prog)s --list             List available debug services
'''
    )

    # Widget tree modes (main modes for agents)
    widget_group = parser.add_argument_group('Widget Tree Modes')
    widget_group.add_argument(
        '--content',
        action='store_true',
        help='Content summary: text, icons with layout context (best for agents)'
    )
    widget_group.add_argument(
        '--smart',
        action='store_true',
        help='Filtered widget tree: only layout-relevant widgets'
    )
    widget_group.add_argument(
        '--trace',
        metavar='TEXT',
        help='Layout trace: show path from root to TEXT with padding/constraints'
    )
    widget_group.add_argument(
        '--widgets',
        action='store_true',
        help='Raw widget tree from debugDumpApp (verbose)'
    )

    # Connection options
    conn_group = parser.add_argument_group('Connection')
    conn_group.add_argument(
        '--uri',
        help='VM Service WebSocket URI (e.g., ws://127.0.0.1:8181/ws)'
    )
    conn_group.add_argument(
        '--list',
        action='store_true',
        help='List all discovered Flutter debug services'
    )

    # Output options
    output_group = parser.add_argument_group('Output')
    output_group.add_argument(
        '--tokens',
        action='store_true',
        help='Show estimated token count'
    )
    output_group.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress connection info, output only UI data'
    )
    output_group.add_argument(
        '--watch', '-w',
        action='store_true',
        help='Watch for UI changes (Ctrl+C to stop)'
    )
    output_group.add_argument(
        '--interval',
        type=float,
        default=2.0,
        help='Watch interval in seconds (default: 2.0)'
    )

    # Legacy/semantics options (hidden, for backwards compat)
    parser.add_argument('--raw', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--format', '-f', default='compact', help=argparse.SUPPRESS)
    parser.add_argument('--json', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--minimal', action='store_true', help=argparse.SUPPRESS)

    args = parser.parse_args()

    # If no mode specified, show quick help for AI agents
    has_mode = any([
        args.content, args.smart, args.trace, args.widgets,
        args.list, args.raw, args.uri
    ])
    if not has_mode:
        print(QUICK_HELP)
        return 0

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
            # Widget tree modes (--content, --smart, --trace, --widgets)
            if args.content or args.smart or args.trace or args.widgets:
                return inspect_widget_tree(client, args)

            # Legacy: raw semantics dump
            if args.raw:
                raw = client.get_semantics_tree()
                print(raw)
                return 0

            # Legacy: try semantics first (requires TalkBack)
            nodes = get_compact_semantics(uri)

            if not nodes:
                if not args.quiet:
                    print("Semantics empty, using --content mode...", file=sys.stderr)
                args.content = True
                return inspect_widget_tree(client, args)

            # Format output (legacy semantics format)
            device_info = {'uri': uri} if not args.quiet else None
            output = format_output(nodes, args.format, device_info)

            print(output)

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
        raw_dump = client.get_widget_tree_text()

        if not raw_dump:
            print("Widget tree is empty", file=sys.stderr)
            return 1

        # Choose output format based on args
        if args.content:
            output = format_content_only(raw_dump)
        elif args.smart:
            output = format_smart(raw_dump)
        elif args.trace:
            output = format_layout_trace(raw_dump, args.trace)
        else:
            # Raw widget tree
            output = raw_dump

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
