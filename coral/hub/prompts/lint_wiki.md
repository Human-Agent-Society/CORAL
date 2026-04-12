## Heartbeat: Wiki Lint

Health-check the shared notes. Read `{shared_dir}/notes/index.md` and scan the notes directory.

### Check for:
- **Contradictions** — do any notes claim opposite things? Update or flag them.
- **Stale info** — research notes that your experiments have disproven. Update with actual results.
- **Orphan pages** — notes not listed in `index.md`. Add them.
- **Missing cross-references** — related notes that don't link to each other.
- **Gaps** — techniques mentioned but never researched, or researched but never tried.

### Fix what you can:
- Update `index.md` to reflect current state
- Merge duplicate notes
- Add experiment results to research notes that lack them
- Flag open questions in `index.md`

### If you find knowledge gaps:
Do a quick web search to fill them. Save raw sources to `{shared_dir}/notes/raw/`, update research notes.

After linting, continue optimizing.
