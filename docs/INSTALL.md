# Installation guide

**English** | [简体中文](INSTALL.zh.md)

Step-by-step, starting from zero — assuming you don't have tmux yet.

`ssh-visibility-guard` has two parts:

- **the guard** (`hooks/ssh-guard.py`) — a Claude Code hook that blocks bare
  SSH. **Required.** Installed via `./install.sh`.
- **the status line** (`hooks/ssh-status`) — optional, shows SSH panes in your
  tmux bar. Installable as a tmux plugin or by hand.

The blocking part is **not** a tmux plugin (tmux never sees the agent's
tool-call intent and has no "before command" hook). Only the status line can be
a tmux plugin.

---

## 1. Install prerequisites: tmux, python3, jq

| OS | command |
|----|---------|
| macOS (Homebrew) | `brew install tmux python jq` |
| Ubuntu / Debian / WSL | `sudo apt update && sudo apt install -y tmux python3 jq` |
| Fedora | `sudo dnf install -y tmux python3 jq` |
| Arch | `sudo pacman -S tmux python jq` |

Verify:

```bash
tmux -V        # need >= 3.0
python3 -V
jq --version
```

No Homebrew on macOS yet? Install it first: https://brew.sh

## 2. Get the code

```bash
git clone https://github.com/lltidragon/ssh-visibility-guard
cd ssh-visibility-guard
```

## 3. Install the guard (required)

```bash
./install.sh
```

This:
- registers the PreToolUse hook in `~/.claude/settings.json`
- copies `ssh-pane` / `ssh-status` to `~/.claude/hooks/`
- creates an example config at `~/.ssh-visibility-guard.json`
- prints the status-line snippet

## 4. Verify

```bash
# the hook should block a bare ssh:
echo '{"tool_name":"Bash","tool_input":{"command":"ssh example hostname"}}' \
  | python3 hooks/ssh-guard.py ; echo "exit=$?"
```

Expect `exit=2` with a block message (inside tmux) or a warning (no tmux).

Run the test suite:

```bash
./tests/run_tests.sh
```

## 5. Use it — inside tmux

The guard enforces visibility only when your agent runs **inside tmux**. Start a
session, then launch Claude Code in it:

```bash
tmux new -s main
# inside the pane:
claude
```

Now if the agent tries `ssh host ...`, it's blocked and told to open a visible
pane instead.

## 6. Optional — put `ssh-pane` on PATH

So the agent can call it directly:

```bash
echo 'export PATH="$HOME/.claude/hooks:$PATH"' >> ~/.zshrc   # or ~/.bashrc
exec $SHELL
```

## 7. Optional — the status line

Shows `SSH: %87>gpu1 %91>wsl` in your tmux status bar.

### Option A — as a tmux plugin (TPM)

If you use [TPM](https://github.com/tmux-plugins/tpm), add to `~/.tmux.conf`:

```tmux
set -g @plugin 'lltidragon/ssh-visibility-guard'
set -g status-interval 5
set -g status-right '#{ssh_status} %H:%M'
```

Then press `prefix + I` to install. The plugin replaces the `#{ssh_status}`
placeholder with the live SSH-pane list.

### Option B — manual (no TPM)

```tmux
set -g status-interval 5
set -g status-right '#(~/.claude/hooks/ssh-status)#{status-right}'
```

Reload: `tmux source-file ~/.tmux.conf`

### Themes that set `status-format` (catppuccin, powerline, …)

These override `status-right`, so both options above are ignored. Embed the
snippet inside your `status-format[0]` right-aligned section by hand, using an
**absolute path** (`~` isn't expanded inside `#(...)`):

```tmux
set -g status-interval 5
# ...#[align=right,...]#(/Users/you/.claude/hooks/ssh-status) <your items>
```

## 8. Configure exceptions (optional)

```bash
export SSH_GUARD_CONFIG=~/.ssh-visibility-guard.json
```

Edit that file to add `allow_patterns` (a regex allowlist) or set
`"hard_block": false` to warn instead of block.

## Uninstall

```bash
./uninstall.sh
```

Removes the hook (with a backup). Helpers and tmux edits are left in place.
