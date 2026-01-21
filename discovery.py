#!/usr/bin/env python3
"""
VM Service URI discovery for Flutter debug applications.
Linux-specific implementation using /proc and lsof.
"""

import os
import re
import subprocess
import socket
import json
from pathlib import Path
from typing import Optional, List, Tuple


VM_SERVICE_PROXY_FILE = Path('/tmp/flutter_vm_service_uri')


def find_dart_vm_services() -> List[Tuple[str, int, Optional[str]]]:
    """
    Find all running Dart VM services.
    Returns list of (uri, pid, app_name) tuples.
    """
    results = []

    # Method 0: Read from flutter proxy file (most reliable)
    proxy_result = _find_via_proxy_file()
    if proxy_result:
        results.append(proxy_result)
        return results  # This is the most reliable, use it directly

    # Method 1: Parse /proc for Dart processes with VM service
    proc_results = _find_via_proc()
    results.extend(proc_results)

    # Method 2: Use lsof to find Dart listening ports
    if not results:
        lsof_results = _find_via_lsof()
        results.extend(lsof_results)

    # Method 3: Scan common ports
    if not results:
        scan_results = _find_via_port_scan()
        results.extend(scan_results)

    return results


def _find_via_proxy_file() -> Optional[Tuple[str, int, Optional[str]]]:
    """Read VM Service URI from flutter proxy file."""
    try:
        if not VM_SERVICE_PROXY_FILE.exists():
            return None

        uri = VM_SERVICE_PROXY_FILE.read_text().strip()
        if not uri:
            return None

        # Extract VM Service URI from DevTools URL if needed
        # Format: http://127.0.0.1:9101?uri=http://127.0.0.1:43535/TOKEN=/
        if '?uri=' in uri:
            uri = uri.split('?uri=')[1]

        # Convert http:// to ws:// if needed
        ws_uri = uri
        if uri.startswith('http://'):
            ws_uri = 'ws://' + uri[7:]
        if not ws_uri.endswith('/ws'):
            ws_uri = ws_uri.rstrip('/') + '/ws'

        # Verify the URI is reachable
        if _is_uri_reachable(ws_uri):
            return (ws_uri, 0, 'flutter-proxy')

    except Exception:
        pass

    return None


def _is_uri_reachable(ws_uri: str) -> bool:
    """Check if WebSocket URI is reachable."""
    try:
        # Extract host and port from ws://host:port/path
        match = re.match(r'ws://([^:]+):(\d+)', ws_uri)
        if not match:
            return False

        host = match.group(1)
        port = int(match.group(2))

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _find_via_proc() -> List[Tuple[str, int, Optional[str]]]:
    """Find VM services by parsing /proc filesystem."""
    results = []

    try:
        for pid_dir in Path('/proc').iterdir():
            if not pid_dir.name.isdigit():
                continue

            pid = int(pid_dir.name)
            cmdline_path = pid_dir / 'cmdline'

            try:
                cmdline = cmdline_path.read_text().replace('\x00', ' ')

                # Check if it's a Dart/Flutter process
                if 'dart' not in cmdline.lower() and 'flutter' not in cmdline.lower():
                    continue

                # Look for VM service URI in cmdline or environment
                # Try to find the observatory/vm service port from fd or net
                uri = _extract_vm_service_uri_for_pid(pid)
                if uri:
                    app_name = _extract_app_name(cmdline)
                    results.append((uri, pid, app_name))

            except (PermissionError, FileNotFoundError, ProcessLookupError):
                continue

    except Exception:
        pass

    return results


def _extract_vm_service_uri_for_pid(pid: int) -> Optional[str]:
    """Extract VM service URI for a specific PID by checking listening ports."""
    try:
        # Read /proc/net/tcp to find listening ports for this process
        # Then verify which one is the VM service

        # Get file descriptors for this process
        fd_path = Path(f'/proc/{pid}/fd')
        socket_inodes = set()

        for fd in fd_path.iterdir():
            try:
                link = os.readlink(str(fd))
                if link.startswith('socket:['):
                    inode = link[8:-1]
                    socket_inodes.add(inode)
            except (PermissionError, FileNotFoundError, OSError):
                continue

        if not socket_inodes:
            return None

        # Parse /proc/net/tcp to find listening sockets
        listening_ports = []
        try:
            with open('/proc/net/tcp', 'r') as f:
                for line in f.readlines()[1:]:  # Skip header
                    parts = line.split()
                    if len(parts) < 10:
                        continue

                    # State 0A = LISTEN
                    if parts[3] != '0A':
                        continue

                    inode = parts[9]
                    if inode in socket_inodes:
                        # Parse local address
                        local_addr = parts[1]
                        port_hex = local_addr.split(':')[1]
                        port = int(port_hex, 16)
                        listening_ports.append(port)
        except Exception:
            pass

        # Check which port responds to VM service
        for port in listening_ports:
            if _is_vm_service_port(port):
                return f'ws://127.0.0.1:{port}/ws'

    except Exception:
        pass

    return None


def _find_via_lsof() -> List[Tuple[str, int, Optional[str]]]:
    """Find VM services using lsof command."""
    results = []

    try:
        output = subprocess.check_output(
            ['lsof', '-i', '-P', '-n'],
            stderr=subprocess.DEVNULL,
            text=True
        )

        for line in output.splitlines():
            if 'dart' not in line.lower():
                continue
            if 'LISTEN' not in line:
                continue

            parts = line.split()
            if len(parts) < 9:
                continue

            pid = int(parts[1])

            # Extract port from address like *:8181 or 127.0.0.1:8181
            addr_part = parts[8]
            match = re.search(r':(\d+)', addr_part)
            if match:
                port = int(match.group(1))
                if _is_vm_service_port(port):
                    uri = f'ws://127.0.0.1:{port}/ws'
                    app_name = _get_app_name_for_pid(pid)
                    results.append((uri, pid, app_name))

    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return results


def _find_via_port_scan() -> List[Tuple[str, int, Optional[str]]]:
    """Find VM services by scanning common ports."""
    results = []

    # Flutter typically uses ports in this range
    common_ports = list(range(8181, 8200)) + list(range(9100, 9110))

    for port in common_ports:
        if _is_vm_service_port(port):
            uri = f'ws://127.0.0.1:{port}/ws'
            results.append((uri, 0, None))

    return results


def _is_vm_service_port(port: int) -> bool:
    """Check if port is a Dart VM service by making a test request."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()

        if result != 0:
            return False

        # Try HTTP request to verify it's a VM service
        import http.client
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
        try:
            conn.request('GET', '/getVM')
            response = conn.getresponse()
            data = response.read().decode('utf-8', errors='ignore')
            conn.close()

            # VM service responds with JSON containing 'vm' key
            if 'vm' in data.lower() or 'isolate' in data.lower():
                return True

        except Exception:
            conn.close()

        # Also try the JSONRPC endpoint
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
        try:
            conn.request('GET', '/')
            response = conn.getresponse()
            data = response.read().decode('utf-8', errors='ignore')
            conn.close()

            if 'dart' in data.lower() or 'vm' in data.lower():
                return True

        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    except Exception:
        pass

    return False


def _extract_app_name(cmdline: str) -> Optional[str]:
    """Extract Flutter app name from command line."""
    # Look for common patterns
    patterns = [
        r'--dart-entrypoint-args=([^\s]+)',
        r'/([^/]+)\.dart',
        r'package:([^/]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, cmdline)
        if match:
            return match.group(1)

    return None


def _get_app_name_for_pid(pid: int) -> Optional[str]:
    """Get app name for a specific PID."""
    try:
        cmdline = Path(f'/proc/{pid}/cmdline').read_text().replace('\x00', ' ')
        return _extract_app_name(cmdline)
    except Exception:
        return None


def discover_vm_service(prefer_index: int = 0) -> Optional[str]:
    """
    Discover and return a single VM service URI.

    Args:
        prefer_index: If multiple services found, return this index (0-based)

    Returns:
        WebSocket URI string or None if not found
    """
    services = find_dart_vm_services()

    if not services:
        return None

    if prefer_index < len(services):
        return services[prefer_index][0]

    return services[0][0]


def list_vm_services() -> List[dict]:
    """
    List all discovered VM services with details.

    Returns:
        List of dicts with 'uri', 'pid', 'app_name' keys
    """
    services = find_dart_vm_services()

    return [
        {
            'uri': uri,
            'pid': pid,
            'app_name': app_name
        }
        for uri, pid, app_name in services
    ]


if __name__ == '__main__':
    print("Searching for Flutter VM services...")
    services = list_vm_services()

    if not services:
        print("No Flutter debug apps found.")
    else:
        print(f"Found {len(services)} service(s):")
        for i, svc in enumerate(services):
            print(f"  [{i}] {svc['uri']}")
            if svc['pid']:
                print(f"      PID: {svc['pid']}")
            if svc['app_name']:
                print(f"      App: {svc['app_name']}")
