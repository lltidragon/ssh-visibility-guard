# ssh-visibility-guard

[![tests](https://github.com/lltidragon/ssh-visibility-guard/actions/workflows/test.yml/badge.svg)](https://github.com/lltidragon/ssh-visibility-guard/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**简体中文** | [English](README.en.md)

> 强制 AI 智能体把每一次 SSH 操作都走**可见的 tmux 分栏** —— 让你能看到智能体在远程机器上做什么、随时介入、并在 tmux 滚动历史里留下天然的审计记录。

## 问题

AI 编程智能体（Claude Code、Cursor、Windsurf……）会很自然地跑：

```bash
ssh user@host 'rm -rf /scratch/run42 && ./solver'
```

能跑通——但输出在执行的瞬间就消失了。你看不到、无法介入、不留痕迹。在共享 HPC 集群或长时间仿真上，这就是「我盯着它跑完」和「但愿它做对了」的区别。

## 方案

一个 Claude Code **PreToolUse hook**：拦截裸 SSH，让智能体在你能看见的 tmux 分栏里执行。

```
AI 想跑:  ssh wsl 'nvidia-smi'
                 ↓  PreToolUse hook 拦截
        检测到裸 SSH → exit 2
                 ↓
   告诉 AI: 在你正看着的窗口开一个分栏，在那里跑
                 ↓
   ssh-pane run wsl 'nvidia-smi'   (或等价的 tmux send-keys)
                 ↓
        你实时看到它发生 ✓
```

两层设计，各做对方做不到的事 —— 详见 [docs/architecture.md](docs/architecture.md)：

1. **拦截层**（`hooks/ssh-guard.py`，必需）—— 唯一能看到智能体「意图」、能在命令执行前拦下的层。
2. **执行层**（`hooks/ssh-pane` + `hooks/ssh-status`，可选）—— 轻量 tmux 封装：开分栏、把目标主机**登记**到分栏上、并在状态栏显示 SSH 拓扑。

### 为什么 tmux 插件替代不了拦截层

tmux 没有「命令执行前」的 hook（只有 `after-*` 事后事件），也看不到智能体的工具调用 —— 等裸 SSH 到达分栏时它已经跑了。所以拦截必须在工具调用层（PreToolUse hook），tmux 插件做不到。tmux 能帮的只有执行层（开分栏、登记主机、状态栏）。

## 安装

```bash
git clone https://github.com/lltidragon/ssh-visibility-guard
cd ssh-visibility-guard
./install.sh
```

需要 `python3`、`jq`、`tmux`。安装脚本会把 hook 注册进 `~/.claude/settings.json`，把可选辅助脚本复制到 `~/.claude/hooks/`，并打印需要加到 `~/.tmux.conf` 的状态栏片段。

## 拦截如何判定

hook 检查每条 `Bash` 命令：

| 检查 | 结果 |
|---|---|
| `SSH_GUARD_BYPASS=1` | 放行（CI 逃生通道）|
| `ssh` 只出现在字符串/注释里（`echo "… ssh …"`）| 放行 |
| `ssh` 作为参数（`grep ssh log`、`man ssh`、`which ssh`）| 放行 |
| `ssh-keygen` / `ssh-copy-id` / `ssh-add` / … | 放行（ssh 工具）|
| 经 `tmux send-keys` / `tmux split-window` 路由 | 放行（已可见）|
| 命中用户 `allow_pattern` | 放行（白名单）|
| **命令位置上真正的裸 `ssh` / `sudo ssh` / `env X=Y ssh`** | **拦截** |

## 可选：ssh-pane 封装 + 状态栏

详见 [docs/tmux-setup.md](docs/tmux-setup.md)。

```bash
ssh-pane open <host>          # 在你正看着的窗口开可视 ssh 分栏，登记 @ssh_host
ssh-pane run  <host> '<cmd>'  # 复用/开该主机的分栏，跑命令，回显输出
ssh-pane list                 # 列出已登记的 ssh 分栏
```

装了 `ssh-pane` 后，拦截信息会塌缩成一行：

```
RECOMMENDED (ssh-pane installed — visible pane, host auto-registered):
  ssh-pane run <host> '<your command>'
```

状态栏实时显示 SSH 拓扑：`SSH: %87>gpu1 %91>wsl`。

## 白名单（例外）

把 [`examples/ssh-visibility-guard.json`](examples/ssh-visibility-guard.json) 复制到 `~/.ssh-visibility-guard.json`，然后：

```bash
export SSH_GUARD_CONFIG=~/.ssh-visibility-guard.json
```

```json
{
  "hard_block": true,
  "allow_patterns": ["ssh win '", "ssh desktop '"]
}
```

`allow_patterns` 是对整条命令做匹配的正则，命中即放行。设 `"hard_block": false` 改为只告警不拦截（评估期有用）。

## 测试

```bash
./tests/run_tests.sh        # 或: python3 -m pytest tests/ -v
```

测试套件（`tests/test_guard.py`）覆盖纯逻辑 —— 违规检测、字符串/注释剥离、主机提取、白名单、tmux 模式分支 —— 无需 tmux。CI 每次 push 都会跑（`.github/workflows/test.yml`）。

## 卸载

```bash
./uninstall.sh
```

从 `~/.claude/settings.json` 移除 hook（带备份）。辅助脚本和 `~/.tmux.conf` 的改动保持不动。

## 理念

做 SSH 操作的 AI 智能体，应该和人类操作员守同一条标准：**一切可见，毫不隐藏。** 每条命令都在真实分栏里、用户随时能介入、tmux 滚动历史里留下天然审计。这对长时间仿真、共享 HPC 集群、以及任何破坏性命令尤其重要。

## 相关项目

- [mcp-ssh-interactive](https://github.com/qnxqnxqnx/mcp-ssh-interactive) — 通过 MCP 工具 + tmux 后端做 SSH
- [lox/tmux-mcp-server](https://github.com/lox/tmux-mcp-server) — 暴露 tmux 原语的 MCP server

## License

MIT —— 见 [LICENSE](LICENSE)。
