---
paths:
  - "**/*"
---
# Architectural Core Rules

## Execution Discipline
- Execute exactly one tool call per turn and wait for system feedback before proceeding.
- Never assume command success; verify every tool output explicitly.
- Keep response text concise and objective. Eliminate conversational filler and greetings.
- Run only non-interactive terminal commands that terminate automatically (e.g., `pytest tests/ -v`, no hanging watch processes).

## Modal Workflow Enforcements
- **In PLAN MODE**: Use only read-only analysis tools (`read_file`, `list_files`, `search_files`). Formulate a detailed, numbered implementation plan before asking to switch to **ACT MODE**.
- **In ACT MODE**: Execute file changes and commands strictly according to the approved plan.