---
paths:
  - "**/*.py"
  - "**/*.html"
  - "**/*.css"
  - "**/*.js"
---
# File Modification Standards & Error Recovery

## Tool Selection Guidelines
- For files under 200 lines: Always use `write_to_file` to write complete file contents.
- For files over 200 lines: Use `replace_in_file` with precise SEARCH/REPLACE blocks.

## Diff Edit Rules
- Include 2-3 lines of exact surrounding code in SEARCH blocks for anchor context.
- Ensure line indentation and whitespace match target content character-for-character.
- Order multiple SEARCH/REPLACE blocks sequentially from top to bottom of the file.

## Error Recovery Protocol
- If a `replace_in_file` call fails, invoke `read_file` with line numbers to re-verify target content.
- Never retry the exact same SEARCH block without re-reading the file first.
- If `replace_in_file` fails twice consecutively, switch to `write_to_file` and overwrite the entire file.