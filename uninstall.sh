#!/usr/bin/env bash
# uninstall.sh — remove the ssh-visibility-guard hook from Claude Code.
set -euo pipefail

SETTINGS_FILE="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"

if [ ! -f "$SETTINGS_FILE" ]; then
  echo "No settings file at $SETTINGS_FILE — nothing to do."
  exit 0
fi

if ! command -v jq &>/dev/null; then
  echo "jq required. Remove the entry containing 'ssh-guard.py' from $SETTINGS_FILE manually." >&2
  exit 1
fi

cp "$SETTINGS_FILE" "${SETTINGS_FILE}.bak"

# Drop any PreToolUse entry whose hooks reference ssh-guard.
jq '
  (.hooks.PreToolUse // []) |= map(
    select(([.hooks[]?.command // ""] | any(test("ssh-guard"))) | not)
  )
' "$SETTINGS_FILE" > "${SETTINGS_FILE}.tmp" && mv "${SETTINGS_FILE}.tmp" "$SETTINGS_FILE"

echo "Removed ssh-guard hook from $SETTINGS_FILE (backup: ${SETTINGS_FILE}.bak)"
echo "Helpers at ~/.claude/hooks/ (ssh-pane, ssh-status) were left in place — delete manually if unwanted."
echo "Status-line edits in ~/.tmux.conf (if any) were NOT touched."
