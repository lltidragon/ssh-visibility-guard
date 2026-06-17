#!/usr/bin/env bash
# ssh-visibility-guard.tmux — TPM entry point.
#
# Lets you install the STATUS-LINE integration as a tmux plugin:
#     set -g @plugin 'lltidragon/ssh-visibility-guard'
# then put the placeholder #{ssh_status} anywhere in status-left / status-right.
#
# IMPORTANT: this wires up ONLY the status line. The blocking hook
# (hooks/ssh-guard.py) is a Claude Code PreToolUse hook installed via
# ./install.sh — tmux cannot do the blocking (it never sees the agent's
# tool-call intent and has no "before command" hook).

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATUS_SCRIPT="$CURRENT_DIR/hooks/ssh-status"

# Standard TPM interpolation: replace the placeholder with a #(shell) call.
interpolation=("\#{ssh_status}")
commands=("#($STATUS_SCRIPT)")

do_interpolation() {
  local all="$1"
  local i
  for ((i = 0; i < ${#commands[@]}; i++)); do
    all="${all//${interpolation[$i]}/${commands[$i]}}"
  done
  echo "$all"
}

update_option() {
  local option="$1"
  local value
  value="$(tmux show-option -gqv "$option")"
  local new
  new="$(do_interpolation "$value")"
  tmux set-option -gq "$option" "$new"
}

main() {
  update_option "status-right"
  update_option "status-left"
}
main
