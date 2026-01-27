# Changelog

All notable changes to this project.

- 2026-01-26: refactor: unify Solve, Analyze, Audio, and Text inputs through a single session flow
- 2026-01-26: feat: add session reset button (R) to floating toolbar
- 2026-01-26: feat: add F8 hotkey for text input from clipboard with session memory
- 2026-01-26: fix: use pyperclip for reliable clipboard persistence on Windows
- 2026-01-26: feat: update interview prompt to enforce verbal-friendly, code-free responses
- 2026-01-26: fix: resolve encoding issues in context.txt and update overlay UI for manual control
- 2026-01-26: fix: ensure clipboard copy works from overlay and disable auto-silence detection
- 2026-01-26: fix: add hotkey cheatsheet footer to overlay
- 2026-01-26: feat: transition to spec-driven implementation workflow
- 2026-01-26: feat: add interview recovery features (retry, cancel, transcript display)
- 2026-01-26: fix: implement async Claude streaming and error recovery in ClaudeProvider
- 2026-01-26: docs: ignore .conductor directory in git
