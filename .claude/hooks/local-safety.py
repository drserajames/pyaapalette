#!/usr/bin/env python3
"""PreToolUse hook: ask before LOCAL destructive operations.

Belt-and-braces with the literal-string `ask` patterns in settings.local.json:
fires on direct destructive verbs (`rm foo`) AND the bypass forms that ask
rules miss. When both hook and rule match, Claude surfaces the rule's pattern
in the UI; the hook still logs the match and serves as a backstop if a rule
is ever removed.

Does NOT fire on ssh/scp/rsync — remote-safety.py handles those.

Patterns caught:
  - direct: rm foo, mv foo bar, chmod ..., sudo ..., kill ..., etc.
  - find ... -delete
  - find ... -exec <destructive_verb>
  - find ... -execdir <destructive_verb>
  - xargs <destructive_verb>          (any flag ordering)
  - time/nice/nohup/env/ionice <destructive_verb>
  - compound: cmd ; rm ..., cmd && rm ..., cmd || rm ..., cmd | xargs rm ...
  - shell wrappers: bash -c "...", sh -c "...", zsh -c "..." (recursively
    checked, including direct destructive inside the wrapper)
  - git push --force / -f / --force-with-lease / -Xf-cluster
    (incl. behind global options: git -C path push -f, git --git-dir=x push -f)
  - downloader piped into a stdin-reading shell: curl ... | sh,
    wget -qO- ... | bash -s -- (remote-code execution)

Acceptable gaps (would need fuller shell parsing):
  - command substitution: $(rm foo), sh -c "$(curl ...)"
  - process substitution: <(rm foo), bash <(curl ...)
  - eval with constructed strings: V="rm foo"; eval $V
  - pipe-to-shell from a non-downloader source: cat script | sh

Failure posture: every exception path exits 0 with no JSON output, deferring
to normal permission flow. Hook bugs degrade safety but never block work.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

DESTRUCTIVE_LOCAL_VERBS = {
    "rm", "rmdir", "mv",
    "chmod", "chown",
    "sudo",
    "kill", "killall", "pkill",
    "dd", "mkfs",
    "shred", "srm",
    "eval", "source",
}

COMMAND_PREFIXES_TAKING_VERB = {"xargs", "time", "nice", "nohup", "ionice", "env"}

SHELL_WRAPPERS = {"bash", "sh", "zsh", "dash", "ksh"}

# downloaders whose output piped into a shell = remote-code execution
DOWNLOADERS = {"curl", "wget", "fetch"}
# shell options that consume the FOLLOWING token as their argument, so a bare
# token after them is that argument — not a script-file operand.
SHELL_OPTS_WITH_ARG = {"-o", "+o", "--rcfile", "--init-file"}

GIT_FORCE_PUSH_FLAGS = {"--force", "-f", "--force-with-lease"}
GIT_FORCE_SHORT_CLUSTER = re.compile(r"^-[A-Za-z]*f[A-Za-z]*$")

# git global options (before the subcommand) that consume the FOLLOWING token as
# their argument. Used to locate the real subcommand so `git -C path push --force`
# isn't mistaken for a non-push command. The `--opt=value` form carries its own
# argument and is handled separately.
GIT_GLOBAL_OPTS_WITH_ARG = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix",
}

SHELL_SEPARATORS = {";", "&&", "||", "|", "&"}

LOG_PATH = Path.home() / ".claude" / "local-safety-hook.log"


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


def bare(tok: str) -> str:
    return tok.rsplit("/", 1)[-1]


def tokenize_into_segments(cmd: str) -> list[list[str]]:
    """Tokenize cmd respecting quotes; split on shell separators.

    Returns list of per-segment token lists. Uses shlex.shlex with
    punctuation_chars so `;`, `|`, `&` become standalone tokens but stay
    inside quoted strings.
    """
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


def git_subcommand_index(tokens: list[str]) -> int | None:
    """Index of git's subcommand, skipping leading global options and their args.

    Handles `git -C path push`, `git --git-dir=x push`, `git -c k=v push`, etc.
    so the force-push detector can't be bypassed by inserting global options
    between `git` and `push`.
    """
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--":
            i += 1
            continue
        if tok.startswith("-"):
            if "=" in tok:            # --git-dir=x : arg is inline
                i += 1
            elif tok in GIT_GLOBAL_OPTS_WITH_ARG:
                i += 2                # skip the option AND its separate-token arg
            else:
                i += 1                # flag without an argument (-p, --bare, ...)
            continue
        return i                      # first non-option token = subcommand
    return None


def detect_git_force_push(tokens: list[str]) -> str | None:
    if not tokens or tokens[0] != "git":
        return None
    idx = git_subcommand_index(tokens)
    if idx is None or tokens[idx] != "push":
        return None
    for tok in tokens[idx + 1:]:
        if tok in GIT_FORCE_PUSH_FLAGS:
            return f"git push {tok} rewrites remote history — review before executing"
        if tok.startswith("--force"):
            return f"git push {tok} rewrites remote history — review before executing"
        if GIT_FORCE_SHORT_CLUSTER.match(tok) and not tok.startswith("--"):
            return f"git push {tok} contains -f flag — review before executing"
    return None


def shell_reads_stdin(args: list[str]) -> bool:
    """True if a shell invoked with `args` (tokens AFTER the shell name) takes
    its program from stdin rather than a script-file operand.

    `sh`, `sh -s`, `sh -`, `bash -s -- a b` read stdin; `sh script.sh` does not.
    `-c` is excluded — that's an inline string handled by detect_shell_wrapper.
    """
    if "-c" in args:
        return False
    for a in args:                       # explicit stdin modes
        if a in ("-", "-s"):
            return True
        if a.startswith("-") and not a.startswith("--") and "s" in a[1:]:
            return True                  # clustered short opts, e.g. -xs
    i = 0                                 # otherwise: stdin iff no script operand
    while i < len(args):
        a = args[i]
        if a == "--":
            return i + 1 >= len(args)     # token after -- would be the script
        if a in SHELL_OPTS_WITH_ARG:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return False                     # a bare operand = script file
    return True                          # nothing but options = bare `sh`


def detect_pipe_to_shell(segments: list[list[str]]) -> str | None:
    """Downloader feeding a stdin-reading shell: `curl … | sh`, `wget -qO- … | bash -s --`.

    Whole-command (cross-segment) check: requires a downloader segment followed
    by a shell segment that reads its program from stdin. `curl … | sudo sh` is
    already caught via the `sudo` verb.
    """
    downloader_idx = None
    for i, seg in enumerate(segments):
        if seg and bare(seg[0]) in DOWNLOADERS:
            downloader_idx = i
            break
    if downloader_idx is None:
        return None
    for seg in segments[downloader_idx + 1:]:
        if seg and bare(seg[0]) in SHELL_WRAPPERS and shell_reads_stdin(seg[1:]):
            return (f"'{bare(seg[0])}' executing a script piped from a downloader "
                    f"(curl/wget | shell) — review before executing")
    return None


def detect_find_destructive(tokens: list[str]) -> str | None:
    if not tokens or tokens[0] != "find":
        return None
    if "-delete" in tokens:
        return "find -delete removes files — review before executing"
    for i, tok in enumerate(tokens):
        if tok in ("-exec", "-execdir") and i + 1 < len(tokens):
            verb = bare(tokens[i + 1])
            if verb in DESTRUCTIVE_LOCAL_VERBS:
                return f"find {tok} invokes '{verb}' — review before executing"
    return None


def detect_command_prefix_destructive(tokens: list[str]) -> str | None:
    """xargs/time/nohup/env/etc. followed somewhere by a destructive verb.

    Scans all tokens after the prefix (not just the immediately-next one) so
    flag arguments like `xargs -I {} rm {}` are handled.
    """
    for i, tok in enumerate(tokens):
        if tok in COMMAND_PREFIXES_TAKING_VERB:
            for later in tokens[i + 1:]:
                verb = bare(later)
                if verb in DESTRUCTIVE_LOCAL_VERBS:
                    return f"{tok} invokes '{verb}' — review before executing"
            break  # only check the first prefix occurrence
    return None


def detect_shell_wrapper(tokens: list[str]) -> str | None:
    """bash -c "...", sh -c '...', etc. Recursively check inner."""
    for i, tok in enumerate(tokens):
        if tok in SHELL_WRAPPERS and i + 1 < len(tokens) and tokens[i + 1] == "-c":
            if i + 2 < len(tokens):
                inner = tokens[i + 2]
                inner_segments = tokenize_into_segments(inner)
                inner_reason = check_segments(inner_segments, in_wrapper=True)
                if inner_reason:
                    return f"{tok} -c wraps: {inner_reason}"
    return None


def check_segments(segments: list[list[str]], in_wrapper: bool = False) -> str | None:
    """Run all detectors across segments. Returns the first ASK reason.

    Fires on direct destructive verbs alongside the ask rules (belt-and-braces).
    When both hook and rule fire, Claude surfaces the rule's pattern in the UI,
    but the hook still logs the match — so the hook also serves as a backstop
    if a rule is ever removed.
    """
    pipe_reason = detect_pipe_to_shell(segments)
    if pipe_reason:
        return pipe_reason

    for i, seg in enumerate(segments):
        if not seg:
            continue

        # Skip remote-safety territory entirely
        if seg[0] in ("ssh", "scp", "rsync"):
            continue

        head = bare(seg[0])

        if head in DESTRUCTIVE_LOCAL_VERBS:
            if in_wrapper:
                return f"direct '{head}' inside shell wrapper — review before executing"
            if i > 0:
                return f"compound segment {i + 1} starts with '{head}' — review before executing"
            return f"direct '{head}' — review before executing"

        for detector in (
            detect_git_force_push,
            detect_find_destructive,
            detect_command_prefix_destructive,
            detect_shell_wrapper,
        ):
            result = detector(seg)
            if result:
                return result
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

    segments = tokenize_into_segments(cmd)
    if not segments:
        sys.exit(0)

    # Skip remote-safety territory at outer level
    if segments[0] and segments[0][0] in ("ssh", "scp", "rsync"):
        sys.exit(0)

    reason = check_segments(segments)
    if reason:
        log(f"ASK cmd={cmd!r} reason={reason}")
        emit_ask(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
