# The Meta-Skill — Admission Standards for the Shared Skill Library

Read this before drafting any new skill. It defines what deserves to enter
the shared library, what belongs elsewhere, and the consistency standards
every skill must meet.

**Why a gate exists at birth.** Every skill's description is loaded into
*every* agent's context for trigger-matching, permanently. A weak skill is
not neutral: it dilutes triggering for every good skill, adds a
near-duplicate for future dedup work, and burdens the librarian's
retirement pass. Research on self-evolving skill libraries finds that
ungoverned LLM-authored skills contribute roughly nothing on their own —
the value comes from curation: strict admission plus evidence-based
retirement. Cheap prevention here beats expensive cleanup later.

## Admission gate

All five must hold before you draft. If any fails, write a note instead
(or update an existing skill) — a rejected skill is a good outcome.

1. **Recurrence evidence.** The pattern appeared at least 3 times in real
   work — across your own attempts, or independently in 2+ agents (check
   notes and attempt history). A clever trick used once is a note, not a
   skill.
2. **Outcome link.** The pattern is tied to results: attempts using it
   scored better, or it repeatedly saved substantial time or avoided a
   recurring failure. "Seems useful" without an attempt or note to point
   at does not pass. Record the evidence — you will cite it in the spec.
3. **Beyond base-model competence.** Would a fresh agent without this
   skill plausibly fail or waste real time? If the model already does it
   fine when asked, packaging it adds context cost and zero capability.
4. **No existing home.** Run `coral skills` and read the frontmatter of
   anything adjacent. At 70%+ overlap, update that skill instead. If an
   adjacent skill exists but is never used (check the librarian's usage
   scan, or run `.claude/skills/scan-usage/scripts/scan_usage.py`), fix
   its description — don't birth a sibling that will split the trigger.
5. **Generalizes past this task-state.** The skill must be phrased in
   terms of the *kind* of problem, not the current file names, dataset,
   or attempt. If it only works for the exact situation you're in now,
   it's a note about that situation.

## Skill vs note

| Content | Home |
|---|---|
| A finding, measurement, comparison, or dead end | Note |
| Config values, magic constants, environment quirks | Note |
| A repeatable procedure with steps and/or scripts | Skill |
| A workflow 2+ agents keep reinventing | Skill |
| An insight about *this* codebase's structure | Note (skills outlive context) |

The same principles govern the note side — placement over duplication,
update-vs-new, discoverability — via the "Before You Write" check in the
`create-notes` skill. Route note-shaped content there, not to a thinner
gate.

## Scope and granularity

- **One workflow per skill.** If the SKILL.md needs "Part A / Part B" for
  unrelated procedures, that's two skills — or one skill and one rejection.
- **Deterministic steps become `scripts/`**, not prose. Prose instructions
  drift; scripts don't.
- **Kebab-case name that says what it does** (`profile-kernel`, not
  `helper-v2` or `agent3-tricks`).
- Keep SKILL.md focused (the writing guide's 500-line ceiling); push
  depth into `references/`.

## Description standards

The frontmatter description is the skill's entire trigger surface:

- State what it does AND the concrete situations that should trigger it.
- Include the vocabulary a *different* agent would use when hitting the
  problem — not just your own phrasing. A description only its author can
  trigger produces a skill only its author uses.
- Name the situations where it should NOT trigger if near-misses are
  likely.

## Consistency with the library

- Match the structure and tone of the bundled skills (imperative voice,
  explain *why* over ALWAYS/NEVER walls, progressive disclosure).
- Stamp `creator:` in the frontmatter (see SKILL.md "Frontmatter
  discipline") — unattributed skills are excluded from provenance and
  migration flows.

## Lifecycle expectations

Admission is not tenure. The librarian periodically runs a usage scan over
agent logs; skills that go unused get their descriptions rewritten and are
eventually archived. Design for discovery (description quality), and when
you improve a workflow, update the existing skill in place — history lives
in the checkpoint repo, so edits are safe and forks are clutter.
