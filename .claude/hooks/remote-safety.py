#!/usr/bin/env python3
"""PreToolUse hook: ask before destructive operations against any remote host.

Token-based detection (via shlex) of Bash commands that ssh-execute
destructive verbs on a remote host, or that scp/rsync data TO a remote host.
Fires `permissionDecision: ask` when detected; otherwise exits with no
decision (deferring to normal permission flow).

Host-agnostic: any ssh/scp/rsync target counts. Catches the bypass forms
that literal-string `ask` patterns in settings.local.json miss:

  ssh HOST "rm foo"              (double quotes)
  ssh HOST rm foo                (no quotes)
  ssh -t HOST 'rm foo'           (extra flag before host)
  ssh HOST 'sleep 0; rm foo'     (leading sub-command)
  scp -v -O -r src HOST:dest     (any flag order)

Acceptable gaps (would need fuller shell parsing to catch):
  bash -c "ssh HOST 'rm foo'"    (wrapped in another shell)
  $(ssh HOST rm foo)             (command substitution)

Failure posture: every exception path exits 0 with no JSON output, deferring
to normal permission flow. Hook bugs degrade safety but never block work.
"""

from __future__ import annotations

import json
import shlex
import sys
from datetime import datetime
from pathlib import Path

DESTRUCTIVE_REMOTE_VERBS = {
    "rm", "rmdir", "mv", "cp",
    "mkdir", "chmod", "chown",
    "python", "python3", "pip", "pip3",
    "dd", "truncate", "tee",
}

LOG_PATH = Path.home() / ".claude" / "remote-safety-hook.log"


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


def emit_ask(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def looks_like_remote_dest(tok: str) -> bool:
    """Match host:path or user@host:path; reject local paths with colons."""
    if ":" not in tok:
        return False
    if tok.startswith(("/", "./", "../", "~")):
        return False
    prefix, _, _ = tok.partition(":")
    if not prefix or "/" in prefix:
        return False
    return True


def detect_ssh_destructive(tokens: list[str]) -> str | None:
    """Any ssh ... containing a destructive verb token → ask.

    Doesn't try to identify the host token. Re-splits quoted command bodies
    (so `ssh HOST 'sleep 0; rm foo'` is seen as ['sleep', '0;', 'rm', 'foo'])
    and matches any token whose basename equals a destructive verb.
    """
    if not tokens or tokens[0] != "ssh":
        return None
    candidates: list[str] = []
    for tok in tokens[1:]:
        if any(c in tok for c in (" ", ";", "|", "&")):
            try:
                candidates.extend(shlex.split(tok, posix=True))
            except ValueError:
                candidates.extend(tok.split())
        else:
            candidates.append(tok)
    for tok in candidates:
        bare = tok.rsplit("/", 1)[-1]
        if bare in DESTRUCTIVE_REMOTE_VERBS:
            return f"ssh remote command invokes '{bare}' — review before executing"
    return None


def detect_remote_write(tokens: list[str]) -> str | None:
    """scp/rsync with a host:path last positional → ask."""
    if not tokens or tokens[0] not in ("scp", "rsync"):
        return None
    positionals = [t for t in tokens[1:] if not t.startswith("-")]
    if not positionals:
        return None
    dest = positionals[-1]
    if looks_like_remote_dest(dest):
        return f"{tokens[0]} writes to {dest} — review before executing"
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
    if not cmd:
        sys.exit(0)

    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError as e:
        log(f"shlex_error cmd={cmd!r} err={e}")
        sys.exit(0)

    reason = (
        detect_ssh_destructive(tokens)
        or detect_remote_write(tokens)
    )
    if reason:
        log(f"ASK cmd={cmd!r} reason={reason}")
        emit_ask(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
