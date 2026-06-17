# 安装指南

[English](INSTALL.md) | **简体中文**

从零开始的分步教程 —— 假设你还没装 tmux。

`ssh-visibility-guard` 有两部分：

- **拦截层**（`hooks/ssh-guard.py`）—— 一个 Claude Code hook，拦截裸 SSH。**必需**，通过 `./install.sh` 安装。
- **状态栏**（`hooks/ssh-status`）—— 可选，在 tmux 状态栏显示 SSH 分栏。可作为 tmux 插件装，也可手动配。

拦截部分**不是** tmux 插件（tmux 看不到智能体的工具调用意图，也没有「命令执行前」的 hook）。只有状态栏可以做成 tmux 插件。

---

## 1. 安装前置依赖：tmux、python3、jq

| 系统 | 命令 |
|----|---------|
| macOS（Homebrew）| `brew install tmux python jq` |
| Ubuntu / Debian / WSL | `sudo apt update && sudo apt install -y tmux python3 jq` |
| Fedora | `sudo dnf install -y tmux python3 jq` |
| Arch | `sudo pacman -S tmux python jq` |

验证：

```bash
tmux -V        # 需要 >= 3.0
python3 -V
jq --version
```

macOS 还没装 Homebrew？先装它：https://brew.sh

## 2. 拉取代码

```bash
git clone https://github.com/lltidragon/ssh-visibility-guard
cd ssh-visibility-guard
```

## 3. 安装拦截层（必需）

```bash
./install.sh
```

它会：
- 把 PreToolUse hook 注册进 `~/.claude/settings.json`
- 把 `ssh-pane` / `ssh-status` 复制到 `~/.claude/hooks/`
- 在 `~/.ssh-visibility-guard.json` 创建示例配置
- 打印状态栏片段

## 4. 验证

```bash
# hook 应当拦截裸 ssh：
echo '{"tool_name":"Bash","tool_input":{"command":"ssh example hostname"}}' \
  | python3 hooks/ssh-guard.py ; echo "exit=$?"
```

预期 `exit=2` 并附拦截信息（在 tmux 内）或一条告警（没有 tmux 时）。

跑测试套件：

```bash
./tests/run_tests.sh
```

## 5. 使用 —— 在 tmux 里

只有当你的智能体跑在 **tmux 内**时，拦截才生效。开一个会话，在里面启动 Claude Code：

```bash
tmux new -s main
# 在分栏里：
claude
```

之后智能体若想 `ssh host ...`，会被拦下并被告知改为开一个可见分栏。

## 6. 可选 —— 把 `ssh-pane` 加进 PATH

让智能体能直接调用它：

```bash
echo 'export PATH="$HOME/.claude/hooks:$PATH"' >> ~/.zshrc   # 或 ~/.bashrc
exec $SHELL
```

## 7. 可选 —— 状态栏

在 tmux 状态栏显示 `SSH: %87>gpu1 %91>wsl`。

### 方式 A —— 作为 tmux 插件（TPM）

如果你用 [TPM](https://github.com/tmux-plugins/tpm)，在 `~/.tmux.conf` 加：

```tmux
set -g @plugin 'lltidragon/ssh-visibility-guard'
set -g status-interval 5
set -g status-right '#{ssh_status} %H:%M'
```

然后按 `prefix + I` 安装。插件会把 `#{ssh_status}` 占位符替换成实时 SSH 分栏列表。

### 方式 B —— 手动（不用 TPM）

```tmux
set -g status-interval 5
set -g status-right '#(~/.claude/hooks/ssh-status)#{status-right}'
```

重载：`tmux source-file ~/.tmux.conf`

### 用了 `status-format` 的主题（catppuccin、powerline……）

这些主题覆盖了 `status-right`，所以上面两种方式都不生效。需要手动把片段嵌进你
`status-format[0]` 的右对齐区，并用**绝对路径**（`#(...)` 里 `~` 不会展开）：

```tmux
set -g status-interval 5
# ...#[align=right,...]#(/Users/你/.claude/hooks/ssh-status) <你的其它内容>
```

## 8. 配置例外（可选）

```bash
export SSH_GUARD_CONFIG=~/.ssh-visibility-guard.json
```

编辑该文件加 `allow_patterns`（正则白名单），或设 `"hard_block": false` 改为只告警。

## 卸载

```bash
./uninstall.sh
```

移除 hook（带备份）。辅助脚本和 tmux 配置改动保持不动。
