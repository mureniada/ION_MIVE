# Claude Code Automation Workflow

**Status:** Automation-bootstrap phase ("Phase B"), recovered after `/ion-diagnose` proved unusable in this environment.

## What changed and why

The original Phase B design implemented the read-only workspace diagnostic as a custom Claude Code skill (`/ion-diagnose`), gated to manual invocation only. In practice, this environment only registers a newly created `.claude/skills/` directory at process start. `/reload-skills` confirmed it does not pick up a brand-new top-level skills directory mid-session ("23 skills available (no changes)"), and this environment's `/exit` command is unavailable, so there was no in-session way to trigger the restart that would have made it invocable. The skill file was correct and present on disk but never became usable, and chasing it turned the operator into a step-by-step relay — restart, reload, retry — instead of a tool doing the work. It has been removed as no longer useful.

## Current workflow — no custom command required

The same read-only diagnostic `/ion-diagnose` was meant to perform is now just a described procedure. Ask for it directly, in ordinary conversation (for example: "run the workspace diagnostic" or "check ION MIVE status"), and it is carried out inline with ordinary read-only tools — no skill file, slash command, or session restart required:

1. Read `ION_MIVE_HANDOVER_INDEX.md` first; report its current stated status for M8.1 / R-001 / E1 verbatim, not from memory of an earlier session.
2. Report workspace root, branch, HEAD, and Git status.
3. Report Claude Code configuration inventory (`.claude/settings.json`, `.claude/settings.local.json`, and presence/absence of `commands/`, `skills/`, `agents/`, `hooks/`).
4. Re-check known risks by re-reading the current files (frontend/`ui/` vs. target-tree mismatch; stale planning docs; unchecked acceptance criteria) rather than repeating a cached conclusion.
5. End with exactly one operator decision.

The same constraints apply every time this is asked for, stated directly rather than enforced by a skill definition: read-only, no Docker, no network/provider calls, no tests, no file edits, no subagents.

## Guardrails that remain (unaffected by this change)

`.claude/settings.json` continues to enforce, at the project-permission level, independent of any skill: Manual (`default`) mode, with Auto mode and `bypassPermissions` mode explicitly disabled (`disableAutoMode` / `disableBypassPermissionsMode`); `ask` rules on Git mutation, Docker, tests, builds/installs, and network calls; `deny` rules on destructive Git/Docker operations and secret-file access. These apply to every command in every session and never depended on a skill being loaded.

## Configuration and permission boundaries

- **`.claude/settings.json` is the tracked project guardrail.** It is committed to the repository (added by `356bc05`) and is the authoritative permission model for every session. It is not a local file and is not gitignored.
- **`.claude/settings.local.json` is local-only.** It must remain ignored and must never be committed. It must not contain secrets, and it must not weaken any project protection — it may only narrow scope or add trivially safe read-only allowances. Project `deny` rules always take precedence and cannot be overridden locally.
- **Secret files are denied outright**, at both repository root and nested paths: `.env`, `.env.*`, `**/secrets/**`, `**/*.key`, `**/*.pem`. Reading a secret value is never an authorized step in any phase.
- **Railway and deployment actions require explicit operator approval.** `railway` is covered by `ask` in both the Bash and PowerShell rule families. Deploys, redeploys, variable changes, and domain changes are operator decisions, never autonomous ones.
- **The canonical bootstrap is exactly three tracked paths:** `CLAUDE.md`, `.claude/settings.json`, and this document. Documents named `01_ION_MIVE_CONFIRMED_STATE_EN.md`, `03_CLAUDE_CODE_AUTOMATION_BOOTSTRAP_EN.md`, and `04_OPERATOR_WORKING_PROTOCOL_RU.md` have never existed in this repository. They were erroneous mission assumptions, are **not** part of the canonical workflow, and must not be created, stubbed, or referenced as required reading.

## Planned — not implemented

Four further capabilities remain planned only, described here as future ideas rather than committed slash commands — so that if one is ever built, it isn't forced into the same restart-dependent shape, and can use whatever mechanism actually works reliably at that time. Each still requires its own future proposal, review, and explicit operator approval before any code is written:

- **Resume** — start a new session by confirming the project root, reading `ION_MIVE_HANDOVER_INDEX.md`, and reporting branch, HEAD, working-tree state, current phase, and open questions, ending with exactly one operator decision. Must not start Docker, must not read `.env`, and must not continue product work autonomously.
- **Status** — report branch, HEAD, clean/dirty working-tree state, changed files, unpushed commits, active phase, and read-only Docker service status only when that inspection is explicitly permitted. Must not change Docker state.
- **Verify** — verify only the currently approved phase, scoped to what it actually touched: inspect the allowed diff and required wording for a documentation change; run only explicitly selected tests for a code change (never the full suite by default); perform only explicitly approved health checks for a runtime claim. Must not automatically run the full test suite, rebuild Docker, or make provider calls.
- **Close** — capture final Git state, stop only explicitly authorised Docker services after operator approval, preserve all volumes, report unpushed commits, and produce a concise resume block. Must never use `docker compose down -v` (or `--volumes`), must never commit or push, must never delete volumes, and must never independently close R-001, E1, or any other project issue.
