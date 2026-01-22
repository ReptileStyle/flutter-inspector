# Flutter UI Inspector

CLI tool for inspecting UI of a running Flutter app in debug mode. Designed for AI agents (Claude, GPT, etc.) to understand what's on screen.

## Installation

```bash
git clone https://github.com/user/flutter_ui_inspector.git
cd flutter_ui_inspector
python3 -m venv .venv
.venv/bin/pip install websocket-client

# Add to PATH (optional)
echo 'export PATH="$PATH:'$(pwd)'"' >> ~/.bashrc
source ~/.bashrc
```

## Quick Start

```bash
# Start your Flutter app in debug mode
flutter run

# In another terminal:
flutter-inspect --content    # What's on screen?
flutter-inspect --smart      # Widget structure
flutter-inspect --widgets    # Full widget tree
```

## For AI Agents

| Task | Command | Output |
|------|---------|--------|
| "What's on screen?" | `--content` | Text and icons with context (~300 lines) |
| "Widget structure" | `--smart` | Filtered widget tree (~1700 lines) |
| "Why this padding?" | `--trace "text"` | Path from root to element with constraints |
| "Full tree" | `--widgets` | Raw debugDumpApp (~4000 lines) |

**Important:**
- App must be in **debug mode** (not profile!) — otherwise widget tree is unavailable
- **Don't use `--raw`** — gives inconvenient output

### Processing `--widgets` output

Lines are long due to tree prefixes. Use these commands:

```bash
# Save and search
flutter-inspect --widgets > /tmp/widgets.txt
grep -n "Editor\|TableCell\|padding" /tmp/widgets.txt

# Clean tree prefixes for readability
sed -n '100,120p' /tmp/widgets.txt | sed 's/^.*│//' | sed 's/^[ │└├─]*//'
```

### Output Examples

**--content** (best for "what do you see on screen?"):
```
Row(start) > Expanded > Column(start)
  → "Today's task"
Row(start) > Flexible
  → "Apr 12 2019 / Main project" [gray]
  → Icon(U+0E018) [gray]
```

**--smart** (best for "what's the screen structure?"):
```
Scaffold
  Row(start/center)
    Expanded(flex:1)
      Column(start/center)
        [CardWithSwipes]
          Row(start/center)
            Padding(pad:0.0, 12.0, 15.0, 0.0)
              Text("Today's task")
```

**--trace "Apr 12"** (best for "where's this padding from?"):
```
# Layout Trace: 'Apr 12'

Scaffold
  Row (align:start/center)
    Expanded (flex:1)
      Column (align:start/start)
        Container (pad:0.0, 6.0, 0.0, 0.0)   ← here's the 6px top padding
          Padding (pad:0.0, 6.0, 0.0, 0.0)
            Row (align:start/center)
              Flexible (flex:1)
                Text ("Apr 12 2019 / Main project")
```

## How It Works

```
Flutter App (debug) → VM Service → flutter-inspect → Filtered Output
```

1. When you run `flutter run`, Flutter exposes a VM Service endpoint
2. **flutter-inspect** discovers the URI (from `/tmp/flutter_vm_service_uri` or by scanning ports)
3. Connects via WebSocket and calls `ext.flutter.debugDumpApp`
4. Filters and formats the output

## All Options

```bash
flutter-inspect --content              # Text and icons on screen
flutter-inspect --smart                # Filtered widget tree
flutter-inspect --trace "text"         # Trace path to element
flutter-inspect --widgets              # Full widget tree

# Additional
flutter-inspect --content --tokens     # Show token count
flutter-inspect --content -q           # Quiet mode (no connection status)
flutter-inspect --list                 # List debug sessions

# Manual URI
flutter-inspect --uri ws://127.0.0.1:12345/TOKEN=/ws --content
```

## Requirements

- Flutter app running via `flutter run` (user starts it, not the agent)
- Python 3.8+
- websocket-client

## Project Structure

```
flutter_ui_inspector/
├── flutter-inspect           # CLI wrapper script
├── inspector.py              # Main CLI entry point
├── discovery.py              # VM Service URI discovery
├── extractors/
│   └── semantics.py          # VM Service client
└── formatters/
    ├── widget_filter.py      # Smart filtering (content/smart/trace)
    ├── compact.py            # Legacy text formats
    └── json_output.py        # JSON formats
```

## Troubleshooting

**"PROFILE MODE" / empty output**
- App is running in profile mode — widget tree unavailable
- Restart with `flutter run` (without `--profile`)

**"No Flutter debug app found"**
- Make sure app is running via `flutter run`
- Check: `cat /tmp/flutter_vm_service_uri`

**"Connection refused"**
- App was closed or restarted
- Restart `flutter run`

**Output too large**
- Use `--content` instead of `--widgets`
- Add `--tokens` to see size

## License

MIT
