---
name: agent-sessions-export
description: Export Claude Code and Codex CLI sessions to readable Markdown (one file per session, dialogue only, no tool noise) into any folder such as an Obsidian vault, and optionally keep exporting new sessions automatically via hooks. Use when the user says "export my sessions", "save my Claude/Codex chats to markdown", "back up agent sessions to Obsidian", "auto-export sessions", "выгрузи сессии", "сохрани сессии в vault", "выгружай сессии автоматически".
---

# Agent sessions export

Script: `scripts/export_sessions.py` (Python 3.9+, standard library only).

Reads local session logs:
- Claude Code: `~/.claude/projects/*/*.jsonl` (respects `CLAUDE_CONFIG_DIR`)
- Codex CLI: `~/.codex/sessions/**` and `~/.codex/archived_sessions/**` (respects `CODEX_HOME`)

Writes `YYYY-MM-DD <Agent> - <first prompt> [<id8>].md` with frontmatter (`session_id`, `agent`, `date`, `cwd`, `tags`) and the user/assistant messages. Tool calls, tool output, system reminders and injected AGENTS.md context are dropped. Re-running overwrites the same files, so it is safe to repeat.

## Steps

1. Ask where to save if the user did not say (an Obsidian vault subfolder works well). Ask whether to limit to one project folder (`--project`, substring of the session's working directory) and whether they want automatic export too.
2. Preview: `python3 scripts/export_sessions.py --out "<dir>" --dry-run [--source claude|codex] [--project X] [--since YYYY-MM-DD]`. Show the count and a few file names.
3. Export: same command without `--dry-run`.
4. Automatic export (if wanted): `python3 scripts/export_sessions.py --install --out "<dir>" [--project X]`.
   - Claude Code: adds a `Stop` hook to `settings.json`; each response updates the session file.
   - Codex: adds `notify` to `config.toml`. Codex allows only one notify program; if one exists the script leaves it alone and prints the command to chain - wrap both in a small shell script and tell the user.
   - Takes effect in new sessions. Running `--install` again replaces the previous hook. `--uninstall` removes it.
5. Report the folder, counts per agent, and whether hooks were installed.

Options: `--user-label "Me"` renames the user speaker (default "You"); `AGENT_SESSIONS_OUT` env var can replace `--out`.

Privacy: exports contain everything typed into the sessions, including pasted secrets. Do not put the output folder in a public repo or a shared cloud folder without checking.
