# Architecture

ssh-visibility-guard has two layers that do different jobs. Keeping them
separate is deliberate — one **cannot** do the other's job.

## Layer 1 — Interception (the guard, required)

`hooks/ssh-guard.py` is a Claude Code **PreToolUse hook** on every `Bash` tool
call. It is the only layer that sees the AI's *intent to run a command* before
it runs, so it decides allow vs block.

**Why this can't be a tmux plugin:** tmux has no "before a command runs" hook
(only `after-*` events), and it never sees the AI's tool call — by the time a
bare `ssh` reaches a pane it has already run. Interception must live at the
tool-call layer.

### Decision flow

```
Bash tool call
  → SSH_GUARD_BYPASS=1 ?            → allow (CI / automation escape hatch)
  → is it a violation?
      strip quoted spans + comments
      ssh at a command position?    (^ | ; | && | || | ( | sudo/env/... wrapper)
        no  → allow                 (e.g. `grep ssh log`, `man ssh`)
      ssh-keygen / ssh-copy-id / …? → allow (ssh utilities)
      tmux send-keys / split-window?→ allow (already routed)
      matches an allow_pattern?     → allow (user allowlist)
        else → VIOLATION
  → tmux mode?
      none      → warn only (exit 0)        — no tmux to route to
      detached  → block (exit 2) + how to open a pane in the user's window
      inside    → block (exit 2) + live snapshot of THIS window
```

### tmux modes

| mode | when | behavior |
|------|------|----------|
| `inside` | `$TMUX` set (normal session, or a subagent that inherited it) | hard block + snapshot of the window Claude runs in |
| `detached` | `$TMUX` empty but a tmux server is reachable | hard block + instructions to open a pane in the user's attached window |
| `none` | no tmux at all | warn only — nothing to route to |
| `bypass` | `SSH_GUARD_BYPASS=1` | skip entirely (CI pipelines) |

### Self-window targeting

The block message is built around `$TMUX_PANE` → the window where Claude (or a
subagent) is actually running, i.e. the window the user is watching. SSH panes
are recommended **there**, not in some other session. This fixes "a new session
or subagent is blind to existing panes and drives the wrong window."

## Layer 2 — Execution (ssh-pane + ssh-status, optional)

tmux *can* make the execution layer more stable, as a thin wrapper:

- **`hooks/ssh-pane`** opens a visible pane in Claude's window, stamps the host
  onto the pane as `#{@ssh_host}`, and runs commands via marker polling. The
  host is **registered, not guessed**.
- **`hooks/ssh-status`** renders which panes are SSH and where they connect.

When `ssh-pane` is installed, the guard's block message collapses to a single
`ssh-pane run <host> '<cmd>'` line.

## Why host registration matters

The host shown for an SSH pane comes **only** from `#{@ssh_host}`, which
`ssh-pane` sets at connect time. Both the guard and the status line read it back
deterministically, so they always agree. A pane opened **without** `ssh-pane`
shows `?` — we deliberately do NOT guess from the pane title or scrollback,
because that misfires (a leftover local hostname looks like a remote host) and
would make the guard claim a host it isn't sure of. The cure is to open panes
with `ssh-pane`, which registers the host for certain.

## Files

| file | role |
|------|------|
| `hooks/ssh-guard.py` | PreToolUse interception hook (layer 1) |
| `hooks/ssh-pane` | visible-pane wrapper, registers `@ssh_host` (layer 2) |
| `hooks/ssh-status` | status-line snippet (layer 2) |
| `hooks/tmux-context.py` | standalone session-startup snapshot of current panes |
