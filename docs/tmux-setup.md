# tmux setup: ssh-pane + status line

Optional. The guard works without these; they make the execution layer
deterministic and visible.

## Put ssh-pane on PATH

So the AI can call `ssh-pane` directly:

```bash
echo 'export PATH="$HOME/.claude/hooks:$PATH"' >> ~/.zshrc   # or ~/.bashrc
```

`install.sh` copies `ssh-pane` and `ssh-status` to `~/.claude/hooks/`.

## Usage

```bash
ssh-pane open <host>          # open a visible ssh pane in Claude's window, register the host
ssh-pane run  <host> '<cmd>'  # reuse/open the host's pane, run, print output
ssh-pane list                 # list registered ssh panes
```

`<host>` is anything ssh understands — an alias from `~/.ssh/config`, or `user@host`.

## Status line

Show SSH panes in your tmux status bar.

### Simple case — you set `status-right` yourself

```tmux
set -g status-interval 5
set -g status-right '#(~/.claude/hooks/ssh-status)#{status-right}'
```

### Theme case — catppuccin / anything that sets `status-format`

If a theme drives `status-format`, `status-right` is ignored. Embed the snippet
inside your right-aligned section instead:

```tmux
set -g status-interval 5
# inside status-format[0], at the start of the align=right section:
#   ...#[align=right,...]#(/absolute/path/to/ssh-status) <your existing items>
```

Use an **absolute path** inside `#(...)` — `~` is not reliably expanded there.

Reload: `tmux source-file ~/.tmux.conf`

## What you see

```
SSH: %87>gpu1 %91>wsl
```

- `%87>gpu1` — opened with `ssh-pane` (host registered via `#{@ssh_host}`)
- `%64>?` — opened by hand (host unknown; open it with `ssh-pane` to get a real name)
