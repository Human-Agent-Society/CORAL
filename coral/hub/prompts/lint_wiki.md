## Heartbeat: Wiki Lint

Spawn the **librarian** subagent to health-check and organize the shared notes.

```
Use the Agent tool with subagent_type="librarian" to:
- Scan the notes directory and index.md for contradictions, stale info, orphan pages, and gaps
- Find and merge duplicate notes
- Reorganize cluttered directories
- Regenerate index.md
- Extract reusable patterns into skills
```

Pass it context about what you've been working on so it can prioritize relevant areas.

After the librarian finishes, review its summary and continue optimizing.
