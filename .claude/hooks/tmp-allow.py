#!/usr/bin/env python3
"""PreToolUse hook: auto-allow Read/Edit/Write to /tmp/ paths.

Works around a macOS-specific behavior: /tmp is a symlink to /private/tmp.
Claude Code's symlink-intersection rule requires a single allow rule to
match BOTH the symlink path AND the resolved path. Rule syntax can't
express "matches either form," so even with `Read(//tmp/**)` AND
`Read(//private/tmp/**)` separately, neither rule alone covers both paths,
and the intersection check falls back to prompting.

This hook returns permissionDecision='allow' for any Read/Edit/Write where
the file path is in /tmp/ or /private/tmp/, bypassing rule matching
entirely (hook decisions are authoritative over rules).

Note: auto-allowing /tmp is a personal-Mac convenience. On a shared
workstation or server where /tmp may contain other users' files, review
before deploying.

Failure posture: every exception path exits 0 with no JSON output, deferring
to normal permission flow. Hook bugs make /tmp writes start prompting again;
they don't block work.
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("tool_name") not in ("Read", "Edit", "Write"):
        sys.exit(0)

    path = payload.get("tool_input", {}).get("file_path", "")
    if not path:
        sys.exit(0)

    if path.startswith("/tmp/") or path.startswith("/private/tmp/"):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": f"/tmp path pre-approved by hook ({path})",
            }
        }))
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
