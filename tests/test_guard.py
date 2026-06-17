"""Unit tests for ssh-guard.py — pure logic, no tmux required."""
import importlib.util
import pathlib
import pytest

# Load the hyphenated module file by path.
_GUARD_PATH = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "ssh-guard.py"
_spec = importlib.util.spec_from_file_location("ssh_guard", _GUARD_PATH)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

CFG = {"allow_patterns": [], "hard_block": True}


# ── Blocked: real bare ssh at a command position ──────────────────────────────

@pytest.mark.parametrize("cmd", [
    "ssh gpu1 hostname",
    "ssh user@host 'nvidia-smi'",
    "ssh -p 2222 user@host",
    "sudo ssh box uptime",
    "time ssh host ls",
    "env FOO=1 ssh host ls",
    "stdbuf -oL ssh host cmd",
    "nohup ssh host long-job",
    "a && ssh host",
    "make build; ssh host deploy",
    "(ssh host status)",
])
def test_bare_ssh_is_blocked(cmd):
    assert guard.is_violation(cmd, CFG) is True


# ── Allowed: ssh as an ARGUMENT, not a command ────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "grep ssh /etc/hosts",
    "man ssh",
    "which ssh",
    "type ssh",
    "cat ~/.ssh/config",
    "ls -la ~/.ssh",
])
def test_ssh_as_argument_is_allowed(cmd):
    assert guard.is_violation(cmd, CFG) is False


# ── Allowed: ssh inside strings / comments ────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    'echo "use ssh to connect"',
    "echo 'remember to ssh in'",
    "# ssh notes: ssh host then run",
    'echo \'{"command": "ssh localhost ls"}\'',
])
def test_ssh_in_strings_or_comments_is_allowed(cmd):
    assert guard.is_violation(cmd, CFG) is False


# ── Allowed: ssh utilities, wrapper, tmux routing ─────────────────────────────

@pytest.mark.parametrize("cmd", [
    "ssh-keygen -t ed25519",
    "ssh-copy-id user@host",
    "ssh-add ~/.ssh/id_ed25519",
    "ssh-agent bash",
    "ssh-keyscan host",
    "ssh-pane open gpu1",
    "ssh-pane run wsl 'nvidia-smi'",
    "tmux send-keys -t %5 'ssh host cmd' Enter",
    "tmux split-window -h 'ssh host'",
])
def test_utilities_wrapper_and_routing_allowed(cmd):
    assert guard.is_violation(cmd, CFG) is False


# ── Allowlist patterns ────────────────────────────────────────────────────────

def test_allowlist_pattern_permits_match():
    cfg = {"allow_patterns": [r"ssh win '"], "hard_block": True}
    assert guard.is_violation("ssh win 'hostname'", cfg) is False

def test_allowlist_does_not_leak_to_other_hosts():
    cfg = {"allow_patterns": [r"ssh win '"], "hard_block": True}
    assert guard.is_violation("ssh other 'hostname'", cfg) is True

def test_bad_regex_in_allowlist_is_ignored():
    cfg = {"allow_patterns": ["[unclosed"], "hard_block": True}
    assert guard.is_violation("ssh host ls", cfg) is True


# ── _strip_noise ──────────────────────────────────────────────────────────────

def test_strip_noise_removes_quotes_and_comments():
    assert "ssh" not in guard._strip_noise("echo 'ssh x'")
    assert "ssh" not in guard._strip_noise('echo "ssh x"')
    assert "ssh" not in guard._strip_noise("ls  # ssh x")

def test_strip_noise_keeps_bare_ssh():
    assert "ssh" in guard._strip_noise("ssh host ls")


# ── extract_host ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cmd,host", [
    ("ssh gpu1 hostname", "gpu1"),
    ("ssh -p 2222 user@host ls", "user@host"),
    ("sudo ssh box uptime", "box"),
])
def test_extract_host(cmd, host):
    assert guard.extract_host(cmd) == host


# ── detect_tmux_mode (env-driven branches, no tmux needed) ────────────────────

def test_bypass_env(monkeypatch):
    monkeypatch.setenv("SSH_GUARD_BYPASS", "1")
    assert guard.detect_tmux_mode() == "bypass"

def test_inside_when_tmux_set(monkeypatch):
    monkeypatch.delenv("SSH_GUARD_BYPASS", raising=False)
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,123,0")
    assert guard.detect_tmux_mode() == "inside"
