#!/usr/bin/env python3
"""SessionStart hook: compare installed claude-config artifacts against source.

Checks whether hook scripts, settings.json, and the settings.local.json
allow/ask baseline match the source repo. Always emits a status line — silence
means this hook itself broke (cf. health-check.py).

  [OK]   Install drift: hooks N/N, settings.json ✓, settings.local.json ✓
  [WARN] Install drift: N issue(s) — <details>
  [--]   Install drift: no .claude/drift-source (not configured)

Source repo path is read from $CLAUDE_PROJECT_DIR/.claude/drift-source (one
line, absolute path to the claude-config clone). Written at bootstrap time by
the Safety hooks step. If absent, emits a configuration notice and exits 0.

Failure posture: every exception path exits 0 and emits a WARN rather than
crashing silently. A hook bug must never block the session from starting.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Must stay in sync with the HOOK_NAMES array in drift-check.sh.
HOOK_NAMES = [
    "remote-safety",
    "local-safety",
    "tmp-allow",
    "push-guard",
    "health-check",
    "drift-check",
]


def emit(msg: str, context: str) -> None:
    print(json.dumps({
        "systemMessage": msg,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        },
    }))


def missing_baseline(installed_path: Path, source_path: Path) -> list[str]:
    """Return baseline allow/ask entries absent from installed settings.local.json."""
    try:
        installed = json.loads(installed_path.read_text())
        source = json.loads(source_path.read_text())
    except Exception as exc:
        return [f"(unreadable: {exc})"]
    missing = []
    for key in ("allow", "ask"):
        src = set(source.get("permissions", {}).get(key, []))
        inst = set(installed.get("permissions", {}).get(key, []))
        for entry in sorted(src - inst):
            missing.append(f"{key}: {entry}")
    return missing


def main() -> None:
    try:
        sys.stdin.read()
    except Exception:
        pass

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    source_file = project_dir / ".claude" / "drift-source"

    if not source_file.exists():
        emit(
            "[--] Install drift: no .claude/drift-source (not configured)",
            "drift-check.py: .claude/drift-source not found. "
            "This file is written at bootstrap time with the absolute path to "
            "the claude-config repo. Re-run bootstrap or create it manually:\n"
            "  echo /path/to/claude-config > .claude/drift-source",
        )
        return

    source_repo = Path(source_file.read_text().strip())
    if not source_repo.is_dir():
        emit(
            f"[WARN] Install drift: source repo missing at {source_repo}",
            f"drift-check.py: path in .claude/drift-source ({source_repo}) "
            "does not exist or is not a directory. Re-run deploy.sh from the "
            "new clone location and re-bootstrap this project.",
        )
        return

    problems: list[str] = []
    hooks_dir = project_dir / ".claude" / "hooks"

    for name in HOOK_NAMES:
        src = source_repo / "hooks" / f"{name}.py"
        if not src.exists():
            continue  # source doesn't have this hook — not a drift problem
        inst = hooks_dir / f"{name}.py"
        if not inst.exists():
            problems.append(f"{name}.py MISSING")
        elif inst.read_bytes() != src.read_bytes():
            problems.append(f"{name}.py STALE")

    installed_settings = project_dir / ".claude" / "settings.json"
    source_settings = source_repo / "new-project-templates" / "settings.json"
    if not installed_settings.exists():
        problems.append("settings.json MISSING")
    elif source_settings.exists() and installed_settings.read_bytes() != source_settings.read_bytes():
        problems.append("settings.json STALE")

    installed_local = project_dir / ".claude" / "settings.local.json"
    source_local = source_repo / "new-project-templates" / "settings.local.json"
    if not installed_local.exists():
        problems.append("settings.local.json MISSING")
    elif source_local.exists():
        for entry in missing_baseline(installed_local, source_local):
            problems.append(f"settings.local.json missing {entry}")

    n_hooks = sum(
        1 for name in HOOK_NAMES
        if (source_repo / "hooks" / f"{name}.py").exists()
    )
    n_hooks_stale = sum(1 for p in problems if ".py" in p)
    n_hooks_ok = n_hooks - n_hooks_stale

    if not problems:
        msg = (
            f"[OK]  Install drift: hooks {n_hooks_ok}/{n_hooks}, "
            "settings.json ✓, settings.local.json ✓"
        )
        context = f"All claude-config artifacts match source at {source_repo}."
    else:
        detail = "; ".join(problems)
        msg = f"[WARN] Install drift: {len(problems)} issue(s) — {detail}"
        context = (
            f"drift-check.py found drift against {source_repo}.\n"
            f"Issues: {detail}\n"
            "See new-project-setup.md → 'Updating an existing install'."
        )

    emit(msg, context)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit(
            f"[WARN] Install drift: unexpected error — {exc}",
            f"drift-check.py raised an unexpected exception: "
            f"{type(exc).__name__}: {exc}",
        )
