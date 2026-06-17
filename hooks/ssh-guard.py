#!/usr/bin/env python3
"""
ssh-guard: Claude Code PreToolUse hook
Blocks bare SSH commands, enforces tmux-routed visible SSH.

v2: SSH pane host detection, target-host matching, fixed client window display.
"""

import json
import re
import subprocess
import sys
import os
import shutil


def wrapper_cmd() -> str:
    """How to invoke ssh-pane in a RUNNABLE form, or '' if not installed.
    Prefer the bare name when it's on PATH; otherwise the explicit ~/.claude/hooks
    path — so the recommended command actually runs even if the user never added
    ~/.claude/hooks to PATH (a real gap: a subagent hit 'ssh-pane not found' and
    had to fall back to raw tmux)."""
    if shutil.which("ssh-pane"):
        return "ssh-pane"
    if os.access(os.path.expanduser("~/.claude/hooks/ssh-pane"), os.X_OK):
        return "~/.claude/hooks/ssh-pane"
    return ""

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_ENV = "SSH_GUARD_CONFIG"
DEFAULT_CONFIG = {
    "allow_patterns": [],
    "block_interactive": True,
    "hard_block": True,
}


def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    path = os.environ.get(CONFIG_ENV)
    if path and os.path.isfile(path):
        try:
            with open(path) as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def detect_tmux_mode() -> str:
    """
    'inside'   — $TMUX set (normal Claude session / workflow subagent inheriting env)
    'detached' — $TMUX unset but tmux server reachable (external script context)
    'none'     — no tmux at all
    'bypass'   — SSH_GUARD_BYPASS=1
    """
    if os.environ.get("SSH_GUARD_BYPASS", "").strip() == "1":
        return "bypass"
    if os.environ.get("TMUX", ""):
        return "inside"
    try:
        r = subprocess.run(["tmux", "list-sessions"], capture_output=True, timeout=2)
        if r.returncode == 0:
            return "detached"
    except Exception:
        pass
    return "none"


# ── SSH detection ─────────────────────────────────────────────────────────────

SSH_UTILITY_RE = re.compile(
    r'\b(ssh-keygen|ssh-copy-id|ssh-add|ssh-agent|ssh-keyscan)\b'
)
TMUX_ROUTE_RE = re.compile(
    r'\btmux\s+(send-keys|split-window|new-session|new-window|new-pane)\b'
)
# ssh must sit at a COMMAND position — line start, a shell separator, or after a
# known command wrapper (sudo/env/nohup/...). Catches `ssh`, `sudo ssh`,
# `env X=Y ssh`, `stdbuf -oL ssh`; does NOT fire on ssh-as-argument like
# `grep ssh log`, `man ssh`, `which ssh`.
_SSH_WRAP = r'(?:sudo|time|env|nohup|exec|setsid|stdbuf|nice|ionice|command)'
SSH_CMD_RE = re.compile(
    r'(?:^|[;&|(]|&&|\|\|)\s*'
    r'(?:' + _SSH_WRAP + r'\s+(?:-\S+\s+|\S+=\S+\s+)*)*'
    r'ssh\s+'
)


def _strip_noise(cmd: str) -> str:
    """
    Remove quoted spans and trailing comments so an 'ssh' mentioned inside an
    echo string, JSON payload, or comment is NOT treated as an executed ssh.
    Best-effort: a real `bash -c "ssh host"` (ssh inside quotes) is intentionally
    NOT caught — direct `ssh host` and prefixed `sudo ssh host` still are.
    """
    s = re.sub(r"'[^']*'", " ", cmd)
    s = re.sub(r'"[^"]*"', " ", s)
    s = re.sub(r'#[^\n]*', " ", s)
    return s


def is_violation(cmd: str, cfg: dict) -> bool:
    probe = _strip_noise(cmd)
    if not SSH_CMD_RE.search(probe):
        return False
    if SSH_UTILITY_RE.search(probe):
        return False
    if TMUX_ROUTE_RE.search(cmd):       # route commands aren't quoted; check full cmd
        return False
    for pattern in cfg.get("allow_patterns", []):
        try:
            if re.search(pattern, cmd):  # allow patterns may include quoted args
                return False
        except re.error:
            pass
    return True


# ssh short options that consume a following argument value (man ssh).
_SSH_VALUE_OPTS = set("BbcDEeFIiJLlmOopQRSWw")


def extract_host(cmd: str) -> str:
    """Pull the SSH target host from a command (best-effort, skips options)."""
    m = re.search(
        r'(?:^|[;&|(]|&&|\|\|)\s*'
        r'(?:' + _SSH_WRAP + r'\s+(?:-\S+\s+|\S+=\S+\s+)*)*'
        r'ssh\s+(.*)$', cmd)
    if not m:
        return ""
    tokens = m.group(1).split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("-"):
            if len(tok) == 2 and tok[1] in _SSH_VALUE_OPTS:
                i += 2          # "-p 2222": skip the option and its value
            else:
                i += 1          # "-v" or attached "-p2222": single token
            continue
        if tok in ("'", '"'):
            return ""
        return tok              # first non-option token is the host
    return ""


# ── tmux helpers ──────────────────────────────────────────────────────────────

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
    """Return active window index for a session (#{client_window} is unreliable)."""
    raw = tmux_run("list-windows", "-t", session, "-F", "#{window_index} #{window_active}")
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "1":
            return parts[0]
    return "1"


def get_self_location() -> dict:
    """
    Identify the window where THIS process (Claude, or a workflow subagent
    that inherited $TMUX_PANE) is running. This is the window the user is
    actually watching — split SSH panes HERE, not into some other session.
    """
    pane = os.environ.get("TMUX_PANE", "")
    if not pane:
        return {}
    info = tmux_run("display-message", "-t", pane, "-p",
                    "#{session_name}\t#{window_index}\t#{pane_id}")
    parts = info.split("\t")
    if len(parts) >= 3 and parts[0]:
        return {
            "session": parts[0],
            "window":  parts[1],
            "pane":    parts[2],
            "target":  f"{parts[0]}:{parts[1]}",
        }
    return {}


def get_client_views() -> list[dict]:
    """Return [{name, session, window}] for all attached clients (detached fallback only)."""
    raw = tmux_run("list-clients", "-F", "#{client_name}\t#{client_session}")
    views = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name, session = parts[0].strip(), parts[1].strip()
        win = get_active_window(session)
        views.append({"name": name, "session": session, "window": win,
                      "target": f"{session}:{win}"})
    return views


def get_pane_ssh_host(pane_id: str) -> str:
    """Remote host for an SSH pane — ONLY the deterministic @ssh_host that
    ssh-pane registers at connect time. We deliberately do NOT guess from the
    pane title or scrollback: those misfire (a leftover local hostname looks
    like a remote host) and would make the guard claim a host it isn't sure of.
    A pane opened without ssh-pane returns "" → shown as '?', same as ssh-status."""
    return tmux_run("display-message", "-t", pane_id, "-p", "#{@ssh_host}")


def get_all_panes() -> list[dict]:
    """Return all tmux panes with parsed metadata."""
    fmt = "\t".join([
        "#{pane_id}", "#{pane_current_command}",
        "#{session_name}", "#{window_index}", "#{pane_index}",
        "#{pane_width}", "#{pane_height}",
        "#{pane_active}", "#{alternate_on}",
    ])
    raw = tmux_run("list-panes", "-a", "-F", fmt)
    panes = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 9:
            continue
        pane = {
            "id":      parts[0],
            "cmd":     parts[1],
            "session": parts[2],
            "window":  parts[3],
            "pidx":    parts[4],
            "width":   parts[5],
            "height":  parts[6],
            "active":  parts[7] == "1",
            "tui":     parts[8] == "1",
            "host":    "",
        }
        pane["loc"] = f"{pane['session']}:{pane['window']}.{pane['pidx']}"
        panes.append(pane)
    return panes


# ── State snapshot ────────────────────────────────────────────────────────────

def _fmt_ssh_pane(p: dict) -> str:
    flag = "★" if p["active"] else " "
    tui  = " [TUI]" if p["tui"] else ""
    host = f"  → {p['host']}" if p.get("host") else "  → ?"
    return f"  {flag} {p['id']}  {p['loc']}  {p['width']}x{p['height']}{tui}{host}"


def build_state(target_host: str = "") -> str:
    lines = []

    # 1. Where Claude (or the subagent) is running — the window the user watches.
    self_loc = get_self_location()
    self_win = self_loc.get("target", "")

    if self_loc:
        lines.append(f"CLAUDE IS RUNNING HERE → {self_win}  (pane {self_loc['pane']})")
        lines.append(f"This is the window the user is watching. Put SSH panes HERE — not in any other session.")
        lines.append("")
        split_target = self_win
    else:
        # No $TMUX_PANE (true detached / external script): fall back to attached clients.
        views = get_client_views()
        if views:
            lines.append("ATTACHED WINDOWS (no $TMUX_PANE — pick the one running Claude):")
            for v in views:
                lines.append(f"  {v['name']}  → {v['target']}")
            lines.append("")
        split_target = views[0]["target"] if views else ""

    # 2. Panes — split into THIS window vs other windows.
    panes = get_all_panes()
    if not panes:
        lines.append("(no tmux panes found)")
        return "\n".join(lines)

    here_ssh, here_local, other_ssh = [], [], []
    for p in panes:
        p_win = f"{p['session']}:{p['window']}"
        in_self = bool(self_win) and (p_win == self_win)
        if p["cmd"] == "ssh":
            p["host"] = get_pane_ssh_host(p["id"])
            (here_ssh if in_self else other_ssh).append(p)
        elif p["cmd"] in ("zsh", "bash", "sh", "fish") and in_self:
            here_local.append(p)

    if here_ssh:
        lines.append(f"SSH PANES IN THIS WINDOW ({self_win}):")
        for p in here_ssh:
            lines.append(_fmt_ssh_pane(p))
        lines.append("")
    if here_local:
        ids = " ".join(p["id"] for p in here_local)
        lines.append(f"LOCAL shell panes in this window (can split from): {ids}")
        lines.append("")
    if other_ssh:
        lines.append("SSH panes in OTHER windows (user is NOT looking at these — avoid unless they ask):")
        for p in other_ssh:
            lines.append(_fmt_ssh_pane(p))
        lines.append("")

    # 3. Recommendation — prefer reusing a host-matched pane IN THIS window.
    match = _find_matching_pane(here_ssh, target_host)
    host_display = target_host if target_host else "<host>"

    # If the ssh-pane wrapper is installed, collapse everything to one line:
    # it finds/opens a visible pane in this window, registers the host, runs, returns output.
    wp = wrapper_cmd()
    if wp:
        lines.append("RECOMMENDED (ssh-pane installed — visible pane, host auto-registered):")
        lines.append(f"  {wp} run {host_display} '<your command>'")
        if match:
            lines.append(f"  # reuses pane {match['id']} (already on {match.get('host') or host_display}) in {split_target}")
        else:
            lines.append(f"  # opens a pane in {split_target or 'your window'}; {wp} open {host_display} to just watch")
        return "\n".join(lines)

    if match:
        pid = match["id"]
        host_info = f" (already connected to {match['host']})" if match.get("host") else ""
        lines.append(f"RECOMMENDED: reuse pane {pid}{host_info} — already visible to the user")
        lines.append(f"  tmux send-keys -t {pid} '<cmd>; echo DONE_$((7*7))' Enter")
        lines.append(f"  # poll:  for i in $(seq 1 300); do tmux capture-pane -t {pid} -p | grep -q DONE_49 && break; done")
        lines.append(f"  # read:  tmux capture-pane -t {pid} -p -S -200")
        if target_host and match.get("host") and target_host not in match["host"]:
            lines.append(f"  ⚠ pane {pid} is on '{match['host']}', not '{target_host}' — open a new pane if you need the other host")
    else:
        host_display = target_host if target_host else "<host>"
        # Note a host-matched pane elsewhere, but still recommend a visible one here.
        elsewhere = _find_matching_pane(other_ssh, target_host) if target_host else None
        if elsewhere:
            lines.append(f"(A pane on '{elsewhere['host']}' exists at {elsewhere['loc']} but it's in another window the user isn't watching.)")
        target_flag = f" -t {split_target}" if split_target else ""
        where = f"this window ({split_target})" if split_target else "the user's window"
        lines.append(f"RECOMMENDED: open a visible SSH pane for '{host_display}' in {where}:")
        lines.append(f"  PANE=$(tmux split-window -h{target_flag} -P -F '#{{pane_id}}' 'ssh {host_display}')")
        lines.append(f"  for i in $(seq 1 120); do tmux capture-pane -t \"$PANE\" -p | grep -qE '@|\\$|>' && break; done")
        lines.append(f"  tmux send-keys -t \"$PANE\" '<cmd>; echo DONE_$((7*7))' Enter")
        lines.append(f"  for i in $(seq 1 300); do tmux capture-pane -t \"$PANE\" -p | grep -q DONE_49 && break; done")
        lines.append(f"  tmux capture-pane -t \"$PANE\" -p -S -200")

    return "\n".join(lines)


def _find_matching_pane(ssh_panes: list, target_host: str) -> dict | None:
    """Find the best SSH pane for the given target host."""
    if not ssh_panes:
        return None
    if not target_host:
        return ssh_panes[0]  # no target info → return first

    # Exact or partial host match
    target_lower = target_host.lower()
    for p in ssh_panes:
        h = p.get("host", "").lower()
        if h and (target_lower in h or h in target_lower):
            return p

    # No host match — return None so caller opens a new pane for the right host
    return None


# ── Block messages ────────────────────────────────────────────────────────────

BLOCK_HEADER = """\
[SSH VISIBILITY GUARD] Bare SSH command blocked.
Route through a visible tmux pane so the user can see all SSH operations.

"""

BLOCK_FOOTER = """
━━━ Rules ━━━
• Open SSH panes in the window where Claude runs (CLAUDE IS RUNNING HERE above) — that is the user's view
• cmd=ssh panes ARE usable via send-keys — the command runs on the remote host
• Reuse only panes IN THIS window; panes in other windows are off-screen for the user
• Long-running jobs: keep tail -f <log> visible; use read-only capture-pane for completion
"""

NONE_WARNING = """\
[SSH VISIBILITY GUARD] ⚠ Bare SSH, no tmux server found.
Cannot enforce visibility (tmux not running). Allowing this time.
Set SSH_GUARD_BYPASS=1 to silence this warning in CI/automated contexts.
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    cmd = payload.get("tool_input", {}).get("command", "")
    if not cmd:
        sys.exit(0)

    mode = detect_tmux_mode()
    if mode == "bypass":
        sys.exit(0)

    cfg = load_config()
    if not is_violation(cmd, cfg):
        sys.exit(0)

    if mode == "none":
        print(NONE_WARNING, file=sys.stderr)
        sys.exit(0)

    # Build state with target-host awareness
    target = extract_host(cmd)
    state = build_state(target_host=target)

    if mode == "detached":
        header = (
            "[SSH VISIBILITY GUARD] Bare SSH blocked — running outside tmux.\n"
            "tmux server IS reachable. Open a visible pane in the user's window.\n\n"
        )
        print(header + state + BLOCK_FOOTER, file=sys.stderr)
        sys.exit(2)

    # mode == "inside"
    print(BLOCK_HEADER + state + BLOCK_FOOTER, file=sys.stderr)
    sys.exit(2 if cfg.get("hard_block", True) else 0)


if __name__ == "__main__":
    main()
