## Heartbeat: Wiki Lint

Spawn the **librarian** subagent to health-check and organize the shared notes.
It must follow the `{notes_skill}` skill
(`{shared_dir}/skills/{notes_skill}/SKILL.md`) for task-specific note structure.

```
Use the Agent tool with subagent_type="librarian" to:
- Scan the notes for contradictions, stale information, orphan pages, and gaps
- Find and merge duplicate notes
- Reorganize cluttered directories
- Restore any navigation required by the configured notes workflow
- Extract reusable patterns into skills
```

Pass it context about what you've been working on so it can prioritize relevant areas.

After the librarian finishes, review its summary and continue optimizing.
