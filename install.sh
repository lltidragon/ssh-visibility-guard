#!/usr/bin/env bash
# install.sh — Install ssh-visibility-guard into Claude Code

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD_SCRIPT="$SCRIPT_DIR/hooks/ssh-guard.py"
SETTINGS_FILE="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"

# ── Preflight ─────────────────────────────────────────────────────────────────

echo "ssh-visibility-guard installer"
echo "================================"
echo "Guard script : $GUARD_SCRIPT"
echo "Settings file: $SETTINGS_FILE"
echo ""

if [ ! -f "$GUARD_SCRIPT" ]; then
  echo "ERROR: Guard script not found at $GUARD_SCRIPT" >&2
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 required" >&2
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq required (brew install jq / apt install jq)" >&2
  exit 1
fi

chmod +x "$GUARD_SCRIPT"

# ── Optional execution-layer helpers ──────────────────────────────────────────
# ssh-pane (visible-pane wrapper, registers #{@ssh_host}) + ssh-status (status line).
# Installed to ~/.claude/hooks so the guard's wrapper_path() finds ssh-pane and
# can collapse its block message to a single `ssh-pane run` line.
HOOKS_DST="$HOME/.claude/hooks"
mkdir -p "$HOOKS_DST"
for f in ssh-pane ssh-status; do
  if [ -f "$SCRIPT_DIR/hooks/$f" ]; then
    install -m 0755 "$SCRIPT_DIR/hooks/$f" "$HOOKS_DST/$f"
    echo "Installed $HOOKS_DST/$f"
  fi
done

# ── Patch settings.json ───────────────────────────────────────────────────────

mkdir -p "$(dirname "$SETTINGS_FILE")"

if [ ! -f "$SETTINGS_FILE" ]; then
  echo "{}" > "$SETTINGS_FILE"
fi

# Check if hook already registered
if jq -e '.hooks.PreToolUse[]?.hooks[]?.command' "$SETTINGS_FILE" 2>/dev/null \
   | grep -q "ssh-guard"; then
  echo "Hook already installed. Skipping."
  exit 0
fi

# Backup
cp "$SETTINGS_FILE" "${SETTINGS_FILE}.bak"
echo "Backed up settings to ${SETTINGS_FILE}.bak"

# Inject hook using jq
HOOK_ENTRY=$(cat <<EOF
{
  "matcher": "Bash",
  "hooks": [
    {
      "type": "command",
      "command": "python3 $GUARD_SCRIPT"
    }
  ]
}
EOF
)

jq --argjson hook "$HOOK_ENTRY" '
  .hooks //= {} |
  .hooks.PreToolUse //= [] |
  .hooks.PreToolUse += [$hook]
' "$SETTINGS_FILE" > "${SETTINGS_FILE}.tmp" && mv "${SETTINGS_FILE}.tmp" "$SETTINGS_FILE"

echo "Hook installed successfully."
echo ""
echo "Test: run 'echo {\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"ssh wsl hostname\"}} | python3 $GUARD_SCRIPT'"
echo "Expected: exit code 2 + block message"

# ── Optional: create example config ──────────────────────────────────────────

CONFIG_EXAMPLE="$HOME/.ssh-visibility-guard.json"
if [ ! -f "$CONFIG_EXAMPLE" ]; then
  cat > "$CONFIG_EXAMPLE" <<'EOF'
{
  "_comment": "ssh-visibility-guard user config. Set SSH_GUARD_CONFIG to this path.",
  "hard_block": true,
  "block_interactive": true,
  "allow_patterns": [
    "ssh win '",
    "ssh desktop '"
  ]
}
EOF
  echo ""
  echo "Example config created at $CONFIG_EXAMPLE"
  echo "To activate: export SSH_GUARD_CONFIG=$CONFIG_EXAMPLE"
  echo "Or add to your shell profile: echo 'export SSH_GUARD_CONFIG=$CONFIG_EXAMPLE' >> ~/.zshrc"
fi

# ── Optional: enable wrapper + status line ────────────────────────────────────
echo ""
echo "── Optional: visible-pane wrapper + status line ──"
echo "1) Put ssh-pane on PATH so the AI can call it:"
echo "     echo 'export PATH=\"\$HOME/.claude/hooks:\$PATH\"' >> ~/.zshrc"
echo "2) Show SSH panes in your tmux status bar. Add to ~/.tmux.conf:"
echo "     set -g status-interval 5"
echo "     set -g status-right '#($HOOKS_DST/ssh-status)#{status-right}'"
echo "   If a theme sets status-format (e.g. catppuccin), instead embed"
echo "     #($HOOKS_DST/ssh-status)"
echo "   inside your status-format[0] right-aligned section."
echo "   Then reload: tmux source-file ~/.tmux.conf"
