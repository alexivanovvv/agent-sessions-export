# agent-sessions-export

Export your **Claude Code** and **Codex CLI** sessions to clean Markdown: one file per session, only the dialogue, no tool noise. Works great with Obsidian. It can also keep exporting new sessions automatically.

Works as a standalone script or as an agent skill (Claude Code, Codex, any tool that reads `SKILL.md`). Python 3.9+, no dependencies.

## Install as a skill

```bash
git clone https://github.com/alexivanovvv/agent-sessions-export.git
cp -r agent-sessions-export/agent-sessions-export ~/.claude/skills/   # Claude Code
cp -r agent-sessions-export/agent-sessions-export ~/.codex/skills/    # Codex
```

Then just ask: "export my sessions to ~/Obsidian/Vault/AI Sessions and keep them updated".

## Use the script directly

```bash
S=agent-sessions-export/scripts/export_sessions.py

python3 $S --out ~/notes/sessions --dry-run          # preview
python3 $S --out ~/notes/sessions                    # export everything
python3 $S --out ~/notes/sessions --source codex --since 2026-01-01
python3 $S --out ~/notes/sessions --project my-app   # only sessions run inside .../my-app

python3 $S --install --out ~/notes/sessions          # auto-export new sessions
python3 $S --uninstall
```

`--install` adds a `Stop` hook to `~/.claude/settings.json` and `notify` to `~/.codex/config.toml`. If Codex already has a `notify` program, it is left untouched and the script prints the command to chain.

## Output

```markdown
---
session_id: 1f36647b-aa71-443f-aa46-70bee90339d8
agent: claude
date: 2026-10-15
cwd: "/Users/me/code/my-app"
tags: [claude-session]
---

# Fix the login redirect

**You:** Fix the login redirect...

**Claude:** The redirect loops because...
```

File name: `2026-10-15 Claude - Fix the login redirect [1f36647b].md`. Re-running overwrites the same file.

## Privacy

Exports contain everything you typed, including pasted keys and tokens. Keep the output folder private.

## License

MIT
