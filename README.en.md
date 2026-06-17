# ssh-visibility-guard

[![tests](https://github.com/lltidragon/ssh-visibility-guard/actions/workflows/test.yml/badge.svg)](https://github.com/lltidragon/ssh-visibility-guard/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[简体中文](README.md) | **English**

> Force AI agents to route every SSH operation through a **visible tmux pane** —
> so you can see what the agent is doing on your remote machines, intervene at
> any point, and keep a natural audit trail.

## The problem

AI coding agents (Claude Code, Cursor, Windsurf, …) happily run:

```bash
ssh user@host 'rm -rf /scratch/run42 && ./solver'
```

It works — but the output vanishes the instant it runs. You can't see it, can't
intervene, and there's no trace. On a shared HPC cluster or a long simulation,
that's the difference between "I watched it" and "I hope it did the right thing."

## The solution

A Claude Code **PreToolUse hook** that blocks bare SSH and makes the agent run
it inside a real tmux pane you can watch:

```
AI wants:  ssh wsl 'nvidia-smi'
                 ↓  PreToolUse hook intercepts
        bare SSH detected → exit 2
                 ↓
   AI is told: open a pane in the window you're watching, run it there
                 ↓
   ssh-pane run wsl 'nvidia-smi'   (or a tmux send-keys equivalent)
                 ↓
        You see it happen, live ✓
```

Two layers, each doing a job the other can't — see [docs/architecture.md](docs/architecture.md):

1. **Interception** (`hooks/ssh-guard.py`, required) — the only layer that sees
   the agent's *intent* and can block before the command runs.
2. **Execution** (`hooks/ssh-pane` + `hooks/ssh-status`, optional) — a thin tmux
   wrapper that opens the pane, **registers** the host on it, and shows SSH panes
   in your status bar.

## Install

> 📖 **Full step-by-step guide** (from installing tmux, incl. TPM plugin setup): **[docs/INSTALL.md](docs/INSTALL.md)**.

```bash
git clone https://github.com/lltidragon/ssh-visibility-guard
cd ssh-visibility-guard
./install.sh
```

Requires `python3`, `jq`, `tmux`. The installer registers the hook in
`~/.claude/settings.json`, copies the optional helpers to `~/.claude/hooks/`, and
prints the status-line snippet to add to `~/.tmux.conf`.

## How blocking decides

The hook checks each `Bash` command:

| check | result |
|-------|--------|
| `SSH_GUARD_BYPASS=1` | allow (CI escape hatch) |
| `ssh` only inside a string / comment (`echo "… ssh …"`) | allow |
| `ssh` as an argument (`grep ssh log`, `man ssh`, `which ssh`) | allow |
| `ssh-keygen` / `ssh-copy-id` / `ssh-add` / … | allow |
| routed via `tmux send-keys` / `tmux split-window` | allow |
| matches a user `allow_pattern` | allow |
| **a real bare `ssh` / `sudo ssh` / `env X=Y ssh` at a command position** | **block** |

## Optional: ssh-pane wrapper + status line

See [docs/tmux-setup.md](docs/tmux-setup.md).

```bash
ssh-pane open <host>          # visible ssh pane in the window you're watching; registers @ssh_host
ssh-pane run  <host> '<cmd>'  # reuse/open the host's pane, run, return output
ssh-pane list                 # list registered ssh panes
```

When `ssh-pane` is on PATH, the block message collapses to one line:

```
RECOMMENDED (ssh-pane installed — visible pane, host auto-registered):
  ssh-pane run <host> '<your command>'
```

Status bar shows the live SSH topology: `SSH: %87>gpu1 %91>wsl`.

## Allowlist (exceptions)

Copy [`examples/ssh-visibility-guard.json`](examples/ssh-visibility-guard.json)
to `~/.ssh-visibility-guard.json`, then:

```bash
export SSH_GUARD_CONFIG=~/.ssh-visibility-guard.json
```

```json
{
  "hard_block": true,
  "allow_patterns": ["ssh win '", "ssh desktop '"]
}
```

`allow_patterns` are regexes matched against the full command. Set
`"hard_block": false` to warn instead of block (useful while evaluating).

## Tests

```bash
./tests/run_tests.sh        # or: python3 -m pytest tests/ -v
```

The suite (`tests/test_guard.py`) covers the pure logic — violation detection,
string/comment stripping, host extraction, allowlist, tmux-mode branches — and
needs no tmux. CI runs it on every push (`.github/workflows/test.yml`).

## Uninstall

```bash
./uninstall.sh
```

Removes the hook from `~/.claude/settings.json` (with a backup). Helpers and any
`~/.tmux.conf` edits are left in place.

## Philosophy

An AI agent doing SSH should be held to the same standard as a human operator:
**everything visible, nothing hidden.** Every command in a real pane, the user
able to intervene, a natural audit trail in tmux scrollback. This matters most
for long-running simulations, shared HPC clusters, and any destructive command.

## Related projects

- [mcp-ssh-interactive](https://github.com/qnxqnxqnx/mcp-ssh-interactive) — SSH via MCP tools + tmux backend
- [lox/tmux-mcp-server](https://github.com/lox/tmux-mcp-server) — MCP server exposing tmux primitives

## License

MIT — see [LICENSE](LICENSE).
