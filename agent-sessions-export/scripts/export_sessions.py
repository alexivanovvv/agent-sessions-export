#!/usr/bin/env python3
"""Export Claude Code and Codex CLI sessions to readable Markdown files.

One .md per session: YAML frontmatter + the user/assistant dialogue, without
tool calls, tool output or injected system context. Re-running is safe: files
are named by session id and overwritten in place.

Batch:  export_sessions.py --out ~/notes/sessions [--source claude|codex|all]
                           [--project SUBSTR] [--since YYYY-MM-DD] [--dry-run]
Auto:   export_sessions.py --install --out DIR [--project SUBSTR]   (adds hooks)
        export_sessions.py --uninstall
Hook:   export_sessions.py --hook claude|codex --out DIR   (called by the hooks)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

CLAUDE_ROOT = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
CODEX_ROOTS = [CODEX_HOME / "sessions", CODEX_HOME / "archived_sessions"]


def read_jsonl(path: Path):
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r'[\\/:*?"<>|#^\[\]]', "-", text)
    return text[:80].rstrip(" .-") or "Untitled session"


def local_date(timestamp: str | None, fallback: Path) -> str:
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except (AttributeError, ValueError):
        return datetime.fromtimestamp(fallback.stat().st_mtime).strftime("%Y-%m-%d")


# --- Claude Code: ~/.claude/projects/<project>/<session-id>.jsonl ---------------

def claude_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n\n".join(
            b.get("text", "").strip()
            for b in content
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()
        )
    return ""


def parse_claude(path: Path) -> dict | None:
    messages, cwd, first_ts = [], "", None
    for entry in read_jsonl(path):
        if entry.get("type") not in ("user", "assistant") or entry.get("isMeta") or entry.get("isSidechain"):
            continue
        text = claude_text(entry.get("message", {}).get("content", ""))
        # Slash-command wrappers, hook output and system reminders start with a tag.
        if not text or text.startswith("<"):
            continue
        cwd = cwd or entry.get("cwd", "")
        first_ts = first_ts or entry.get("timestamp")
        messages.append(("user" if entry["type"] == "user" else "assistant", text))
    if not messages:
        return None
    return {"agent": "Claude", "id": path.stem, "cwd": cwd, "date": local_date(first_ts, path), "messages": messages}


# --- Codex CLI: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl --------------------

def codex_text(content: object, kind: str) -> str:
    if not isinstance(content, list):
        return ""
    return "\n\n".join(
        i["text"].strip()
        for i in content
        if isinstance(i, dict) and i.get("type") == kind and isinstance(i.get("text"), str) and i["text"].strip()
    )


def parse_codex(path: Path) -> dict | None:
    meta, messages, seen = {}, [], set()
    for record in read_jsonl(path):
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if record.get("type") == "session_meta" and not meta:
            meta = payload
            continue
        if record.get("type") != "response_item":
            continue
        role = payload.get("role")
        if role == "user":
            text = codex_text(payload.get("content"), "input_text")
        elif role == "assistant":
            text = codex_text(payload.get("content"), "output_text")
        else:
            continue
        # Codex injects AGENTS.md and environment context as user items.
        if not text or text.startswith(("<", "# AGENTS.md instructions")) or (role, text) in seen:
            continue
        seen.add((role, text))
        messages.append((role, text))
    if not messages:
        return None
    session_id = meta.get("id") or meta.get("session_id") or path.stem.rsplit("-", 5)[-1]
    return {"agent": "Codex", "id": session_id, "cwd": meta.get("cwd", ""),
            "date": local_date(meta.get("timestamp"), path), "messages": messages}


# --- Output ---------------------------------------------------------------------

def render(session: dict, user_label: str) -> str:
    title = clean_title(next((t for r, t in session["messages"] if r == "user"), "session").splitlines()[0])
    lines = [
        "---",
        f"session_id: {session['id']}",
        f"agent: {session['agent'].lower()}",
        f"date: {session['date']}",
        f"cwd: {json.dumps(session['cwd'], ensure_ascii=False)}",
        f"tags: [{session['agent'].lower()}-session]",
        "---",
        "",
        f"# {title}",
        "",
    ]
    for role, text in session["messages"]:
        lines += [f"**{user_label if role == 'user' else session['agent']}:** {text}", ""]
    return "\n".join(lines)


def write(session: dict, out: Path, user_label: str, dry_run: bool) -> Path:
    short = session["id"][:8]
    title = clean_title(next((t for r, t in session["messages"] if r == "user"), "session").splitlines()[0])
    target = out / f"{session['date']} {session['agent']} - {title[:50].rstrip(' .-')} [{short}].md"
    if not dry_run:
        out.mkdir(parents=True, exist_ok=True)
        # Drop an older copy of the same session saved under a different title.
        for old in out.glob(f"* {session['agent']} - * [[]{short}[]].md"):
            if old != target:
                old.unlink()
        target.write_text(render(session, user_label), encoding="utf-8")
    return target


def sources(which: str):
    if which in ("claude", "all"):
        for path in CLAUDE_ROOT.glob("*/*.jsonl"):
            yield parse_claude, path
    if which in ("codex", "all"):
        for root in CODEX_ROOTS:
            for path in root.rglob("*.jsonl"):
                yield parse_codex, path


def run_hook(agent: str, args) -> int:
    payload = {}
    if agent == "claude" and not sys.stdin.isatty():
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            pass
    if agent == "claude":
        path = Path(payload.get("transcript_path", ""))
        session = parse_claude(path) if path.is_file() else None
    else:
        # Codex `notify` passes the event as argv JSON; fall back to the newest rollout.
        event = {}
        for value in sys.argv[1:]:
            if value.startswith("{"):
                try:
                    event = json.loads(value)
                except json.JSONDecodeError:
                    pass
        sid = event.get("thread-id") or event.get("session_id") or payload.get("session_id") or ""
        files = [p for root in CODEX_ROOTS for p in root.rglob("*.jsonl")]
        matches = [p for p in files if sid and sid in p.name] or files
        session = parse_codex(max(matches, key=lambda p: p.stat().st_mtime)) if matches else None
    if session and (not args.project or args.project in session["cwd"]):
        write(session, args.out, args.user_label, False)
    return 0


# --- Automatic export: Claude Code Stop hook + Codex notify ---------------------

MARKER = "export_sessions.py"
CLAUDE_SETTINGS = CLAUDE_ROOT.parent / "settings.json"
CODEX_CONFIG = CODEX_HOME / "config.toml"


def hook_command(agent: str, args) -> list[str]:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--hook", agent, "--out", str(args.out)]
    if args.project:
        cmd += ["--project", args.project]
    if args.user_label != "You":
        cmd += ["--user-label", args.user_label]
    return cmd


def strip_claude_hook(settings: dict) -> None:
    groups = settings.get("hooks", {}).get("Stop", [])
    for group in groups:
        group["hooks"] = [h for h in group.get("hooks", []) if MARKER not in h.get("command", "")]
    groups[:] = [g for g in groups if g.get("hooks")]
    if "hooks" in settings and not groups:
        settings["hooks"].pop("Stop", None)


def install(args) -> int:
    import shlex

    # Claude Code: a Stop hook fires after every response with the transcript path.
    if CLAUDE_SETTINGS.parent.is_dir():
        settings = json.loads(CLAUDE_SETTINGS.read_text()) if CLAUDE_SETTINGS.exists() else {}
        strip_claude_hook(settings)
        settings.setdefault("hooks", {}).setdefault("Stop", []).append(
            {"hooks": [{"type": "command", "command": shlex.join(hook_command("claude", args))}]})
        CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
        print(f"Claude Code: Stop hook added to {CLAUDE_SETTINGS}")

    # Codex: `notify` runs a program at the end of every turn. Only one is allowed.
    if CODEX_HOME.is_dir():
        text = CODEX_CONFIG.read_text() if CODEX_CONFIG.exists() else ""
        line = "notify = " + json.dumps(hook_command("codex", args))
        if re.search(r"^notify\s*=", text, re.M) and MARKER not in text:
            print(f"Codex: {CODEX_CONFIG} already has a notify program, left untouched.\n"
                  f"  Make it also run:  {shlex.join(hook_command('codex', args))}")
        else:
            text = re.sub(r"^notify\s*=.*\n?", "", text, flags=re.M)
            CODEX_CONFIG.write_text(line + "\n" + text)
            print(f"Codex: notify added to {CODEX_CONFIG}")
    print(f"New sessions will be exported to {args.out}")
    return 0


def uninstall() -> int:
    if CLAUDE_SETTINGS.exists():
        settings = json.loads(CLAUDE_SETTINGS.read_text())
        strip_claude_hook(settings)
        CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
        print(f"Claude Code: hook removed from {CLAUDE_SETTINGS}")
    if CODEX_CONFIG.exists() and MARKER in CODEX_CONFIG.read_text():
        CODEX_CONFIG.write_text(re.sub(r"^notify\s*=.*%s.*\n?" % re.escape(MARKER), "",
                                       CODEX_CONFIG.read_text(), flags=re.M))
        print(f"Codex: notify removed from {CODEX_CONFIG}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=os.environ.get("AGENT_SESSIONS_OUT"),
                        help="output folder (or env AGENT_SESSIONS_OUT)")
    parser.add_argument("--source", choices=["claude", "codex", "all"], default="all")
    parser.add_argument("--project", help="only sessions whose working directory contains this substring")
    parser.add_argument("--since", help="only sessions started on/after YYYY-MM-DD")
    parser.add_argument("--user-label", default="You", help='label for your messages (default "You")')
    parser.add_argument("--hook", choices=["claude", "codex"], help="export the session from a hook payload")
    parser.add_argument("--install", action="store_true", help="export new sessions automatically via hooks")
    parser.add_argument("--uninstall", action="store_true", help="remove the hooks added by --install")
    parser.add_argument("--dry-run", action="store_true", help="list what would be written")
    args, _ = parser.parse_known_args()
    if args.uninstall:
        return uninstall()
    if not args.out:
        parser.error("--out is required (or set AGENT_SESSIONS_OUT)")
    args.out = Path(args.out).expanduser()

    if args.install:
        return install(args)
    if args.hook:
        try:
            return run_hook(args.hook, args)
        except Exception:
            return 0  # never break the agent because of an export problem

    counts: dict[str, int] = {}
    for parse, path in sources(args.source):
        session = parse(path)
        if not session:
            continue
        if args.project and args.project not in session["cwd"]:
            continue
        if args.since and session["date"] < args.since:
            continue
        target = write(session, args.out, args.user_label, args.dry_run)
        counts[session["agent"]] = counts.get(session["agent"], 0) + 1
        if args.dry_run:
            print(target.name)
    total = sum(counts.values())
    summary = ", ".join(f"{k}: {v}" for k, v in counts.items()) or "nothing found"
    print(f"{'Would export' if args.dry_run else 'Exported'} {total} sessions to {args.out} ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
