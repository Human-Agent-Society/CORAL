# Source Types — Deep Research

`SKILL.md` step 3 says "save raw sources" but the canonical example is a web article. Real research draws on heterogeneous sources. For each type below: **how to capture**, **what to extract**, **frontmatter that matters**, **pitfalls**.

The frontmatter convention is uniform across all source types:

```yaml
---
title: "Source: <title>"
source_url: <original URL or local path>
source_type: <web|paper|repo|video|thread|docs|blog|conversation>
captured: <ISO timestamp>
captured_by: <agent_id>
truncated: false        # set true if the original was clipped to fit
original_chars: 12345   # only when truncated: true
---
```

Treat `raw/` files as immutable after capture. If a source updates, capture a new file with a date suffix (`paper-name-2026-04.md`), don't overwrite.

---

## Web article (canonical case)

**How:** `WebFetch` → write the cleaned markdown to `raw/<slug>.md`. SKILL.md step 3 covers this.

**What to extract:** full article body, author, publication date.

**Pitfalls:** SPA pages return JS shells; comment sections are usually noise; cookie banners and navigation chrome can leak in if the markdown converter is naive — strip them.

---

## Academic paper (PDF)

**How:**
1. Download the PDF (`curl` or your environment's fetch). Save the binary to `raw/papers/<slug>.pdf` if you'll re-read it; don't commit large PDFs to a notes directory you sync widely.
2. Extract text. If `pdftotext` is available: `pdftotext -layout paper.pdf raw/papers/<slug>.md`. Otherwise use a Python `pdfplumber` / `pypdf` one-liner.
3. The text version goes in `raw/papers/<slug>.md`.

**What to extract:** abstract, methods, results tables (often the highest-value section), limitations/threats-to-validity (often where the actual caveats hide), references list (lets you trace one citation hop).

**Frontmatter additions:**
```yaml
authors: ["Last, First", ...]
venue: "NeurIPS 2024" | "arXiv 2401.12345"
doi: "10.xxxx/yyyy"
```

**Pitfalls:**
- Two-column PDFs — `-layout` flag matters or text comes out interleaved.
- Equations and figures don't extract; note them as `[FIGURE: caption]` placeholders so they're not silently lost.
- The abstract can disagree with the actual results. Always read past the abstract.

---

## GitHub repository / code

**How:**
1. Don't `git clone` into `raw/` — capture the README and key files individually.
2. `gh repo view <owner>/<repo> --json description,homepageUrl,stargazerCount,latestRelease > raw/repos/<slug>.json`.
3. Save the README: `gh api repos/<owner>/<repo>/readme --jq '.content' | base64 -d > raw/repos/<slug>-README.md`.
4. If a specific file is the meat (e.g. `train.py`, `model.py`), save that too with full path preserved in the filename.

**What to extract:** README, license, last commit date, any `BENCHMARKS.md` / `PERFORMANCE.md`, the entry-point file.

**Frontmatter additions:**
```yaml
repo: "owner/name"
commit: <sha at capture time>
license: <MIT|Apache-2.0|...>
stars: <count>
```

**Pitfalls:** stars are not a quality signal; README claims often don't match code; check the issue tracker for "doesn't work" reports before treating a repo as a recommended solution.

---

## Video (YouTube, conference talk)

**How:**
1. Use `yt-dlp --write-auto-sub --skip-download <url>` to grab the auto-generated captions.
2. Convert the `.vtt` to plain text (strip timestamps and HTML tags) and save to `raw/videos/<slug>.md`.
3. For talks with slides, grab a slides PDF if linked from the description.

**What to extract:** the transcript. Note speaker turns if multiple presenters.

**Frontmatter additions:**
```yaml
duration_seconds: <int>
speaker: <name>
transcript_source: "auto" | "human"   # auto-captions are noisy
```

**Pitfalls:** auto-captions mangle technical terms; treat any specific number, name, or formula as needing verification against a written source.

---

## Twitter/X thread

**How:** save as a single markdown file with each tweet as a paragraph. If the thread links to a primary source (paper, blog), capture that *too* and treat the thread as commentary, not the primary source.

**Frontmatter additions:**
```yaml
thread_url: <root tweet URL>
author_handle: "@..."
thread_length: <tweet count>
```

**Pitfalls:** threads compress aggressively and lose nuance; never cite a thread as the only evidence for a quantitative claim — find the underlying source.

---

## Documentation site (official docs, framework references)

**How:** identify the canonical URL (e.g. `docs.python.org/3/library/asyncio.html`), capture with `WebFetch`. For multi-page topics, capture each page as a separate `raw/` file under a subdirectory: `raw/docs/asyncio/<page-slug>.md`.

**What to extract:** signatures, parameters, examples, version-introduced markers, deprecation notices.

**Frontmatter additions:**
```yaml
doc_version: "Python 3.12" | "React 18"
section: "asyncio" | "hooks"
```

**Pitfalls:** version drift — a doc page captured today may not match the version in your project. Always record `doc_version`.

---

## Blog post / personal site

**How:** `WebFetch` as for web articles, but record the author and any institutional affiliation.

**Frontmatter additions:**
```yaml
author: <name>
author_credibility: <one-line note — researcher at X, practitioner with Y experience, anonymous>
```

**Pitfalls:** author credibility matters more than for institutional sources. A blog claim from a domain expert is often the best available source; from an anonymous commentator, it's weak.

---

## Conversation log (Slack/Discord/internal chat)

**How:** export the relevant message range as JSON if the platform supports it, otherwise paste as markdown. Strip personal handles → roles (`@alice` → `engineer-A`) if the notes will be shared more broadly than the original chat.

**Frontmatter additions:**
```yaml
platform: slack | discord | other
channel: <name>
date_range: "2026-04-01..2026-04-03"
participant_count: <int>
```

**Pitfalls:** chat logs encode unstated context. Note what wasn't said, not just what was. Verify any factual claims against a primary source — chat is for "who decided what when", not for citing technical truths.

---

## Choosing the right capture method

When in doubt:

1. Prefer the **most primary** source available — paper > blog summary of paper > tweet about blog.
2. Prefer the **most stable** location — arxiv URL > author homepage > random mirror.
3. Capture **enough context to re-locate** the source later, even if the URL rots — author + title + venue + date.
