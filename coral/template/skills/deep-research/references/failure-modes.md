# Failure Modes — Deep Research

What to do when the happy path breaks. Each entry: **symptom** → **diagnosis** → **action** → **don't**.

---

## WebFetch returns an error or empty body

**Symptom:** `WebFetch` errors with 403/404/timeout, or the returned content is empty / a JS shell / a paywall page.

**Diagnosis:**
- 403/Cloudflare → bot-blocking
- 404 → URL changed or moved
- Empty body / "Please enable JavaScript" → SPA that renders client-side
- Login wall / paywall → content gated

**Action:**
1. Try the URL through a search engine cache or `web.archive.org/web/<URL>` — works for ~70% of dead/blocked pages.
2. Search for the document title directly; the original may be mirrored elsewhere (arXiv, author's homepage, blog cross-post).
3. For SPAs, look for an RSS/JSON feed or an API endpoint the page hits — those return real content.
4. For paywalled academic papers, search the title + author + "pdf" — preprints are almost always free.
5. If the source is genuinely unrecoverable, **don't fabricate it** — note in research/ that the citation is unreachable and downgrade evidence weight accordingly.

**Don't:** retry the same URL three times and give up. Use a different access path before abandoning.

---

## Search returns nothing useful

**Symptom:** Three queries in, every result is irrelevant or low-quality blog spam.

**Diagnosis:** wrong vocabulary. The community calls the thing something different from your initial guess.

**Action:**
1. Find one good source by any means (textbook index, Wikipedia, Stack Overflow). Read its terminology.
2. Re-search using the *vocabulary from that source*, not your original phrasing.
3. Try adversarial queries: `"why X doesn't work"`, `"X failure case"`, `"X is wrong"` — surfaces critique papers that sit one citation hop from the canonical work.
4. Try the academic angle: `site:arxiv.org`, `site:scholar.google.com`, `"survey" OR "review"` + topic.

**Don't:** keep rephrasing your original guess. The terminology is wrong, not the wording.

---

## Sources contradict each other

**Symptom:** Source A says technique X works; source B says it doesn't.

**Diagnosis:** Almost always a scope mismatch (different dataset, scale, hyperparameters, or definition of "works").

**Action:**
1. Read the methods sections of both, not just the abstracts. Find the scope difference.
2. Document the contradiction in the research note: *"X works at scale > N (source A), fails below it (source B)."* Specificity beats picking a winner.
3. If you genuinely can't reconcile them, note both with the contradiction explicit, set `contradictedBy: [other-note-slug]` in frontmatter, and add to `_open-questions.md`.

**Don't:** silently pick the source you read first, or the one that confirms your prior. The contradiction itself is signal.

---

## An existing note is stale

**Symptom:** You're researching topic X and find `research/x.md` already exists, but its references are broken / its claims contradict newer sources / its `creator` is from a prior session.

**Diagnosis:** prior research that hasn't kept up.

**Action:**
1. **Don't delete or rewrite from scratch.** Read it carefully — old notes contain context (failed approaches, dead ends) that is itself valuable.
2. Update incrementally: add new sources to References, mark superseded claims with `~~strikethrough~~`, append an "Update <date>" section explaining what changed and why.
3. If a claim is fully refuted, set `superseded: true` in frontmatter rather than deleting the file. Future agents may rediscover the topic and benefit from the audit trail.

**Don't:** create `research/x-v2.md`. Forking notes fragments the index.

---

## Topic is genuinely underexplored

**Symptom:** After a real search, only 1–2 mediocre sources exist on the topic.

**Diagnosis:** either novel research area, or you're framing it too narrowly.

**Action:**
1. Broaden one level: search the parent class of the problem. Underexplored *intersections* often have rich coverage of each component separately.
2. Check adjacent fields — often the same idea exists under a different name in a neighbouring discipline (ML/statistics, biology/chemistry, etc.).
3. If genuinely novel, write the research note with explicit `confidence: low` and document what's *missing* — that's also useful future input.

**Don't:** pretend mediocre sources are strong because nothing better exists. Mark evidence as weak honestly.

---

## Source contains code you can't run

**Symptom:** Found a GitHub repo or paper with code, but environment is incompatible / dataset is private / training takes 3 days.

**Action:**
1. Read the README, `__main__`, and the test files (if any) — these usually expose the API and intended usage without needing to run.
2. Look for a published model/result file in the repo releases — sometimes you can verify outputs without re-running training.
3. Note in the research note: *"Verified by code reading, not execution"* — distinguishes "I read it" from "I ran it."

**Don't:** silently treat unrun code the same as run-and-verified code.

---

## You found a duplicate of an existing research note

**Symptom:** You've written most of `research/foo.md` and notice `research/foo-similar.md` already exists.

**Action:** stop, read the existing one, decide:
- **Same topic, different angle** → fold your new content into the existing note as a new section, then delete your draft.
- **Same topic, same angle** → discard your draft. Update the existing note's References with anything new you found.
- **Different topic, similar name** → rename one of them more specifically and add `aliases` to disambiguate.

**Don't:** keep both. The index becomes misleading.
