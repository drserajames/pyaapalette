#!/usr/bin/env python3
"""PreToolUse hook: restrict `git push` to an allowlist of GitHub owners.

Generic and OPT-IN per project. Enforcement is active only when the file

    $CLAUDE_PROJECT_DIR/.claude/push-allowed-owners

exists. Each non-empty, non-comment line is an allowed GitHub owner (user or
org), case-insensitive. If the file is ABSENT, this hook defers on every
command — so a project with no GitHub repo, or one that simply hasn't opted
in, is never affected. If the file exists but is empty, every GitHub push is
denied (a deliberate full lockdown).

On a `git push` the hook resolves the destination repository to a URL:
  - an explicit URL argument            -> that URL
  - a named remote argument             -> `git remote get-url <name>`
  - no repository argument (bare push)  -> the branch's push/upstream remote
Then, if the URL is on github.com and its owner is NOT in the allowlist, it
DENIES. Non-github destinations, unresolvable ones, and non-push commands all
defer (the host-level control for non-github exfil is the sandbox allowlist).

Because hooks hot-reload and the allowlist file is read fresh on every call,
adding an owner to the file takes effect immediately — no restart needed.

Resolution honors a `git -C <dir>` / `--git-dir=<dir>` in the command, else
$CLAUDE_PROJECT_DIR, else the process cwd. Detection covers compound commands
(`a && git push …`) and `bash -c "git push …"` wrappers.

Acceptable gaps (would need fuller shell parsing): command/process
substitution (`$(…)`, `<(…)`) and `eval` of constructed strings.

Failure posture: every exception path exits 0 with no output (defer). A guard
bug must never block legitimate work.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SHELL_WRAPPERS = {"bash", "sh", "zsh", "dash", "ksh"}
SHELL_SEPARATORS = {";", "&&", "||", "|", "&"}

# git global options (before the subcommand) that consume the following token.
GIT_GLOBAL_OPTS_WITH_ARG = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix",
}
# `git push` options that consume the following token as their argument.
PUSH_OPTS_WITH_ARG = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}

# github.com immediately followed by ':' (scp form) or '/' (url form), then owner.
GITHUB_OWNER_RE = re.compile(r"github\.com[:/]+([^/]+)/", re.IGNORECASE)

LOG_PATH = Path.home() / ".claude" / "push-guard-hook.log"


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


def emit_deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def bare(tok: str) -> str:
    return tok.rsplit("/", 1)[-1]


def project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def allowed_owners() -> set[str] | None:
    """Allowed owners (lowercased), or None if the project hasn't opted in."""
    path = Path(project_dir()) / ".claude" / "push-allowed-owners"
    try:
        text = path.read_text()
    except Exception:
        return None  # file absent/unreadable -> no enforcement
    owners: set[str] = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            owners.add(line.lower())
    return owners  # may be empty -> deny all github pushes


def tokenize_into_segments(cmd: str) -> list[list[str]]:
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";|&")
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        try:
            return [shlex.split(cmd, posix=True)]
        except ValueError:
            return [cmd.split()]
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok in SHELL_SEPARATORS:
            if segments[-1]:
                segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def git_subcommand(tokens: list[str]) -> tuple[int | None, str | None]:
    """Return (index of git subcommand, -C/--git-dir work dir) skipping globals."""
    work_dir = None
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--":
            i += 1
            continue
        if tok.startswith("-"):
            if tok == "-C" and i + 1 < len(tokens):
                work_dir = tokens[i + 1]
                i += 2
                continue
            if tok.startswith("--git-dir="):
                work_dir = tok.split("=", 1)[1]
                i += 1
                continue
            if "=" in tok:
                i += 1
                continue
            if tok in GIT_GLOBAL_OPTS_WITH_ARG:
                i += 2
                continue
            i += 1
            continue
        return i, work_dir
    return None, work_dir


def push_repository(tokens: list[str], sub_idx: int) -> str | None:
    """The <repository> argument of `git push` (remote name or URL), or None."""
    i = sub_idx + 1
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--":
            return tokens[i + 1] if i + 1 < len(tokens) else None
        if tok == "--repo" and i + 1 < len(tokens):
            return tokens[i + 1]
        if tok.startswith("--repo="):
            return tok.split("=", 1)[1]
        if tok.startswith("-"):
            if tok in PUSH_OPTS_WITH_ARG and i + 1 < len(tokens):
                i += 2
                continue
            i += 1
            continue
        return tok  # first bare token is the repository
    return None


def looks_like_url(s: str) -> bool:
    return "://" in s or ":" in s or "/" in s


def git_output(args: list[str]) -> str | None:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    return out or None


def resolve_url(repo: str | None, work_dir: str | None) -> str | None:
    cwd = work_dir or project_dir()
    if repo and looks_like_url(repo):
        return repo
    if repo:  # a named remote
        return git_output(["-C", cwd, "remote", "get-url", repo])
    # bare `git push`: find the branch's effective push remote
    branch = git_output(["-C", cwd, "symbolic-ref", "--short", "HEAD"])
    remote = None
    if branch:
        remote = git_output(["-C", cwd, "config", f"branch.{branch}.pushRemote"])
    remote = (remote
              or git_output(["-C", cwd, "config", "remote.pushDefault"])
              or (git_output(["-C", cwd, "config", f"branch.{branch}.remote"]) if branch else None)
              or "origin")
    return git_output(["-C", cwd, "remote", "get-url", remote])


def github_owner(url: str) -> str | None:
    m = GITHUB_OWNER_RE.search(url)
    return m.group(1).lower() if m else None


def check_segment(seg: list[str], owners: set[str]) -> str | None:
    if not seg:
        return None
    head = bare(seg[0])
    if head in SHELL_WRAPPERS:
        for i, tok in enumerate(seg):
            if tok == "-c" and i + 1 < len(seg):
                inner = check_command(seg[i + 1], owners)
                if inner:
                    return inner
        return None
    if head != "git":
        return None
    sub_idx, work_dir = git_subcommand(seg)
    if sub_idx is None or seg[sub_idx] != "push":
        return None
    url = resolve_url(push_repository(seg, sub_idx), work_dir)
    if not url:
        return None  # unresolvable -> defer
    owner = github_owner(url)
    if owner is None:
        return None  # non-github -> defer (sandbox handles host allowlisting)
    if owner not in owners:
        allowed = ", ".join(sorted(owners)) or "(none allowed)"
        return (f"git push targets GitHub owner '{owner}', which is not in this "
                f"project's push allowlist [{allowed}] — blocked. To allow it, add "
                f"'{owner}' to .claude/push-allowed-owners.")
    return None


def check_command(cmd: str, owners: set[str]) -> str | None:
    for seg in tokenize_into_segments(cmd):
        reason = check_segment(seg, owners)
        if reason:
            return reason
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        log(f"parse_error {e}")
        sys.exit(0)
    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = payload.get("tool_input", {}).get("command", "")
    if not cmd or "push" not in cmd:
        sys.exit(0)  # fast path: only git push is relevant
    owners = allowed_owners()
    if owners is None:
        sys.exit(0)  # project hasn't opted in

    try:
        reason = check_command(cmd, owners)
    except Exception as e:
        log(f"check_error cmd={cmd!r} err={e}")
        sys.exit(0)  # fail open
    if reason:
        log(f"DENY cmd={cmd!r} reason={reason}")
        emit_deny(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
