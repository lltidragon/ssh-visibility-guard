#!/usr/bin/env python3
"""
tmux-context: Print current tmux layout for AI session startup.

Run this at the beginning of any session involving SSH/tmux
so the AI knows exactly what panes exist and can reuse them.

Usage:
  python3 ~/.claude/hooks/tmux-context.py
  python3 ~/.claude/hooks/tmux-context.py --json
"""

import json
import re
import subprocess
import sys


def tmux_run(*args, timeout=3) -> str:
    try:
        r = subprocess.run(
            ["tmux"] + list(args),
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip()
    except Exception:
        return ""


def get_active_window(session: str) -> str:
    """Return active window index for a session (#{client_window} is unreliable in some versions)."""
    raw = tmux_run("list-windows", "-t", session, "-F", "#{window_index} #{window_active}")
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "1":
            return parts[0]
    return "1"


def get_pane_ssh_host(pane_id: str) -> str:
    """Detect remote hostname for an SSH pane (best-effort)."""
    title = tmux_run("display-message", "-t", pane_id, "-p", "#{pane_title}")
    if title and title not in ("bash", "zsh", "sh", "fish", "tmux", ""):
        candidate = re.split(r'[\s:]', title)[0]
        if "@" in candidate or re.match(r'^[\w][\w.-]{2,}$', candidate):
            return candidate

    content = tmux_run("capture-pane", "-t", pane_id, "-p", "-S", "-8")
    lines = [l.rstrip() for l in content.splitlines() if l.strip()]
    for line in reversed(lines):
        m = re.search(r'([\w][\w.-]*@[\w][\w.-]+)', line)
        if m:
            return m.group(1)
        m = re.search(r'([\w]+@[\w-]+)\s+[A-Z]:\\', line)
        if m:
            return m.group(1)
    return ""


def get_context() -> dict:
    ctx = {"clients": [], "panes": [], "summary": {}}

    # Attached clients — use list-windows to get active window (#{client_window} unreliable)
    raw = tmux_run("list-clients", "-F", "#{client_name}|#{client_session}|#{client_termname}")
    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) < 2:
            continue
        session = parts[1]
        ctx["clients"].append({
            "name": parts[0],
            "session": session,
            "window": get_active_window(session),
            "term": parts[2] if len(parts) > 2 else "",
        })

    # All panes
    fmt = "|".join([
        "#{session_name}",
        "#{window_index}",
        "#{pane_index}",
        "#{pane_id}",
        "#{pane_current_command}",
        "#{pane_current_path}",
        "#{pane_width}",
        "#{pane_height}",
        "#{pane_active}",
        "#{alternate_on}",
        "#{pane_title}",
    ])
    raw = tmux_run("list-panes", "-a", "-F", fmt)

    ssh_panes = []
    local_panes = []

    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        pane = {
            "session": parts[0],
            "window": parts[1],
            "pane_index": parts[2],
            "id": parts[3],
            "cmd": parts[4],
            "path": parts[5] if len(parts) > 5 else "",
            "width": int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else 0,
            "height": int(parts[7]) if len(parts) > 7 and parts[7].isdigit() else 0,
            "active": parts[8] == "1" if len(parts) > 8 else False,
            "tui": parts[9] == "1" if len(parts) > 9 else False,
            "title": parts[10] if len(parts) > 10 else "",
            "host": "",
        }
        if pane["cmd"] == "ssh":
            pane["host"] = get_pane_ssh_host(pane["id"])
            ssh_panes.append(pane["id"])
        elif pane["cmd"] in ("zsh", "bash", "sh", "fish"):
            local_panes.append(pane["id"])
        ctx["panes"].append(pane)

    ctx["summary"] = {
        "ssh_panes": ssh_panes,
        "local_panes": local_panes,
        "total": len(ctx["panes"]),
    }

    return ctx


def print_human(ctx: dict):
    if not ctx["panes"]:
        print("No tmux session running.")
        return

    # User's current view
    if ctx["clients"]:
        print("━━ USER'S CURRENT VIEW ━━")
        for c in ctx["clients"]:
            win_target = f"{c['session']}:{c['window']}"
            print(f"  {c['name']}  session={c['session']} window={c['window']}  → target: {win_target}")
        print()

    # Pane table
    print("━━ CURRENT PANES ━━")
    print(f"  {'ID':<6}  {'LOC':<12}  {'CMD':<12}  {'SIZE':<10}  {'HOST/FLAGS'}")
    print(f"  {'─'*6}  {'─'*12}  {'─'*12}  {'─'*10}  {'─'*20}")

    for p in ctx["panes"]:
        loc = f"{p['session']}:{p['window']}.{p['pane_index']}"
        size = f"{p['width']}x{p['height']}"
        extras = []
        if p["active"]:
            extras.append("ACTIVE")
        if p["tui"]:
            extras.append("TUI")
        if p["cmd"] == "ssh" and p.get("host"):
            extras.append(f"→{p['host']}")
        elif p["cmd"] == "ssh":
            extras.append("SSH")
        print(f"  {p['id']:<6}  {loc:<12}  {p['cmd']:<12}  {size:<10}  {' '.join(extras)}")

    print()

    # Actionable summary
    s = ctx["summary"]
    print("━━ WHAT TO DO ━━")
    if s["ssh_panes"]:
        ids = " ".join(s["ssh_panes"])
        first = s["ssh_panes"][0]
        host_info = next((p["host"] for p in ctx["panes"] if p["id"] == first), "")
        host_tag = f" (connected to {host_info})" if host_info else ""
        print(f"  SSH panes: {ids}")
        print(f"  → reuse {first}{host_tag}: tmux send-keys -t {first} '<cmd>; echo DONE_$((7*7))' Enter")
        print(f"  → read:  tmux capture-pane -t {first} -p -S -200")
    else:
        print("  No SSH panes. To open one in the user's current window:")
        if ctx["clients"]:
            c = ctx["clients"][0]
            win_target = f"{c['session']}:{c['window']}"
            print(f"  → PANE=$(tmux split-window -h -t {win_target} -P -F '#{{pane_id}}' 'ssh <host>')")
            print(f"  → for i in $(seq 1 120); do tmux capture-pane -t \"$PANE\" -p | grep -qE '@|\\$|>' && break; done")
        else:
            print("  → tmux split-window -h 'ssh <host>'")

    if s["local_panes"]:
        print(f"  Local shell panes (safe to split from): {' '.join(s['local_panes'])}")


def main():
    as_json = "--json" in sys.argv

    if not tmux_run("list-sessions"):
        if as_json:
            print(json.dumps({"error": "tmux not running"}))
        else:
            print("[tmux-context] No tmux session found.")
        sys.exit(0)

    ctx = get_context()

    if as_json:
        print(json.dumps(ctx, indent=2))
    else:
        print_human(ctx)


if __name__ == "__main__":
    main()
