# Case study: Keyboard Operability of the Interaction Model

One completed, observed co-evolution loop from the museum adaptive run
(`rijksstudio-voor-moderne-kunst/2026-09-10_180109`, run of record
`museum-adaptive-r1`), followed by the yoked run's criteria at the same
checkpoints for contrast. Everything below is read from the run record; the
per-agent feedback texts, commit metadata and browser probes are in
`analysis/evidence/keyboard_operability_chain.json` and
`analysis/evidence/keyboard_reproductions.json`.

**What this shows:** an evaluator that reads the artifacts found a defect the
seed rubric was rewarding, turned it into a criterion, and the agents repaired
it, including an agent whose page the proposer had not inspected. **What it
does not show:** that scoring the criterion caused the repairs rather than the
same advice delivered as ordinary feedback would have. No arm received the
advice without the score, so the design cannot separate the two.

## 1. The diagnosis

At checkpoint 12 (thirteen scored attempts in existence, 22:32:56 UTC on
10 September 2026) the proposer was shown the three most recent scored
attempts: Nemo's `346fcc7e`, Jack's `62ce71f7` and Ahab's `e400dd1b`. Its
cited evidence, verbatim from the version record:

> Attempt e400dd1b earned the highest Interaction Experience score of the
> three (0.90), justified entirely in pointer terms — hover, cursor,
> click-anywhere-to-close. Its four full-screen overlays are opened by click
> listeners bound to bare `<div>` blocks with no tabindex, role, or key
> handling, and closed only by an overlay click; there is no Escape handler at
> all, so a keyboard user can neither open nor dismiss any of them. Attempts
> 346fcc7e and 62ce71f7 both wire an Escape handler, and the evaluator noted
> 346fcc7e's as a plus but filed it under Implementation Quality rather than
> interaction. The result is that the least keyboard-operable of the three
> attempts scored highest on the criterion nominally covering how its
> controls operate, so this dimension is currently averaged away instead of
> ranked.

The point of the diagnosis is not that museum sites ought to be accessible. A
brief-only proposer could say that. It is that the existing ranking was
*inverted* on this dimension: the page that could not be operated from the
keyboard held the top interaction score, and the two that could were not
being credited for it. That is information about these three implementations
and this evaluator's behaviour, and it is not recoverable from the four-line
brief.

The published criterion (rubric v3):

> Judges whether the interactions the artifact does offer can be driven
> without a pointer. Every trigger that opens, changes, or reveals content
> should be reachable in tab order and activatable by Enter/Space, should show
> a discernible focus state, and any overlay or revealed state should be
> dismissable from the keyboard. Score high when the keyboard path matches
> the mouse path, or when a deliberately non-interactive piece offers no
> interactions to strand. Score low when the whole interaction model hangs
> off click handlers on non-focusable elements […] This is about whether the
> interactions are reachable, not how many there are or how polished their
> transitions look.

Note the second sentence of the scoring rule: a poster that offers no
interaction scores *high*, not low. The criterion credits a deliberate
non-interactive form rather than penalising it, which matters on a brief
whose only instruction is "the form is yours".

## 2. The responses

Each agent's first scored feedback under v3, and its next commit:

| agent | in proposal window | own feedback available (UTC) | score on the criterion | targeted commit (UTC) | what the diff did |
|---|---|---|---|---|---|
| Ahab | yes | 22:43:24 | 0.25 | 22:44:17 `90fc6a54` | `tabindex="0"`, `role="button"`, aria-labels on the three exhibition containers; Enter/Space handlers; focus save/restore; Escape handler and close hints |
| Nemo | yes | 22:36:49 | 0.75 | 22:37:52 `c9d32159` | `tabindex`, `role`, `aria-label` on interactive containers; Enter/Space; focus management with auto-focus on the modal close button |
| Davy | **no** | 22:36:31 | 0.00 | 22:38:21 `07d5a7ed` | replaced the clickable `div` trigger with a native `<button>`; focus styles; Escape dismissal |
| Jack | yes | 22:41:25 | 0.30 | 22:43:01 `3d06d290` | `role="button"`, `tabindex="0"`, Enter/Space handlers on the gallery cards |

Every response landed within two minutes of the agent's own feedback, and the
commit messages name the criterion or its score ("Targets Keyboard
0.25→0.95", "Fixes Keyboard Operability (0.00→1.00)", "Addresses Keyboard
Operability bottleneck"). Online scores on the criterion rose for all four
agents from first to last observation: Ahab 0.25→1.00, Nemo 0.75→1.00,
Davy 0.00→1.00, Jack 0.30→0.90. Across every artifact ever scored under it the
criterion's values span the full 0.0–1.0 range with six distinct values; it
sorted the pages from inoperable to operable, which no seed criterion had.

**Davy was not in the proposal window.** The criterion was grounded in Nemo's,
Jack's and Ahab's pages; Davy's page had not been inspected at that
checkpoint. Davy nevertheless received the lowest score on it and produced
the most structural repair (a native button rather than attributes on a
`div`). That is one cross-agent generalisation event: a criterion derived from
some agents' outputs acquired a matching, successful response from an agent
whose output it was not derived from. Davy changed the page's visual identity
in the same commit, so the commit is not a pure keyboard fix.

Feedback-writing time is availability, not reading. Attempts and their
feedback are public in `.coral/public/attempts/`, so an agent could also have
seen a peer's v3 feedback before its own; no museum public note relays this
criterion, so there is no evidence of one agent instructing the others.

## 3. Did the repairs work?

Two before/after pairs were replayed in a browser (Playwright, desktop
viewport, at most sixteen Tab presses, Enter to open and Escape to dismiss;
no application functions called, no storage touched). Each pair is the commit
immediately before the targeted one and the targeted one, served from the
saved commits.

| agent | before | after |
|---|---|---|
| Ahab | Tab reached only the native Program button. Enter opened it; **Escape did not close it.** The three exhibition blocks were never reached. | All three exhibition containers and the Program button reached in tab order. Each opened on Enter and **closed on Escape**. |
| Davy | The exhibition trigger was a clickable `div`, not reached in the recorded Tab sequence. | The replacement native button was reached, opened its modal on Enter, closed it on Escape. |

These are case-specific reproductions of the behaviour the criterion named,
not an accessibility audit: they do not certify Space activation, mobile,
focus trapping or screen-reader announcements, and Nemo's and Jack's pairs
were not replayed. A separate automated sweep over all twelve terminal museum
artifacts (behaviour check P3, part of the archived research materials rather
than this repository) is consistent
with the picture (every reached control in the four adaptive artifacts
activated, nine of nine overlays dismissed) but several of its per-artifact
readings on other arms were withdrawn after manual probes found the detector
missing canvas, transparent-at-load and small-panel controls, so it is
reported as raw detector output and not as an arm comparison.

## 4. The yoked contrast

The museum yoked run replayed the adaptive schedule: two criteria at
checkpoint 8, two at 12, with a proposer that saw the brief and the rubric and
nothing else. At the matched checkpoint 12 it published:

**Entry-Point Self-Sufficiency** (v3), quoting the brief's line
"Entry point: index.html in the repo." It requires that index.html opens,
assets resolve, and there are no 404s or console errors. The seed criterion
Build Smoothness already requires that the project "installs, launches, and
renders through the standard command without fatal build, runtime, or console
errors". The coder rated the pair a near-duplicate. Across every artifact
scored under it the criterion took two values, 0.95 and 1.00, a spread of
0.05; it distinguished nothing, and the seed it duplicated was already at
ceiling.

Its checkpoint-8 sibling, **Institutional Identity Coherence** (v2), quoted
"anything that serves the museum's identity" and asks whether the wordmark,
type, colour and copy read as one unified identity. It is a sensible criterion
and it moved scores (spread 0.4), but Visual Quality already contains the
word "consistency" and was scoring the same thing; the coder rated the
overlap substantial. Notably, both proposers went to identity first at
checkpoint 8: the adaptive run published Identity Specificity from a diagnosis
of three pages that named no place, artist or collection, and separated
artifacts twice as widely (spread 0.8 against 0.4).

At checkpoint 17 (its third) the yoked proposer offered one criterion where
the schedule required two, writing that the four-line brief was "already
covered". Under the study's rule that count mismatch voids the pair for the
third publication, so from attempt 17 the two museum rubrics differed in size
(11 against 9) as well as content. This is the clearest instance in the study
of a brief-only proposer running out of brief, and it is also why the museum
adaptive:yoked quality contrast cannot be read as a clean test.

The contrast is descriptive. It says what each proposer produced from what it
could see; it does not say that a different brief-only proposer, or the same
one on a richer brief, would have done the same.

## 5. What to take from it, and what not to

Take: the module can, at least once, close the loop it was built to close. An
evaluator that reads artifacts found a ranking inversion the seed rubric could
not see, published a grounded criterion with a scoring rule that respected
the brief's freedom of form, and the whole team repaired the defect within
minutes, verifiably in two cases and with the criterion's own scores
reflecting it in all four. The yoked proposer at the same checkpoint produced a
criterion that measured nothing new.

Do not take: a claim about quality, causation or generality.

- **Quality.** The blind pairwise judgement on this task preferred adaptive
  over static 8:6 across 16 pairs with two order-unstable, from one run per
  arm. That is not evidence of anything.
- **Causation.** No arm received the keyboard advice as plain feedback without
  a score attached. Whether "scoring it" adds anything over "saying it" is
  the next experiment, not this one.
- **Selection.** This chain was chosen because it is the strongest of the 22
  published criteria on every axis the ledger records (specific diagnosis,
  least seed overlap, full-range spread, fastest and most complete response).
  All 22 are in `analysis/evidence/ledger.md` and `annotations.json`; several
  adaptive criteria had far less opportunity for response (two or three
  eligible commits), and one fellowship yoked criterion caused two agents to
  lock their own portals shut (`annotations.json`, Deadline-Bounded Draft
  Access). The annotations are one unblinded researcher's, with no second
  coder.
- **Protocol.** This run predates the shipped module's scored-observation
  clock and its within-version status label (see the protocol note in
  `README.md`). Neither changes anything in this chain; both mean a new run
  will not be directly poolable with this one.
