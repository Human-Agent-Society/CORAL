# Unified CORAL Site Design

**Date:** 2026-07-15
**Status:** Design approved; pending written-spec review

## Summary

CORAL will use `https://coral.compounding-intelligence.ai` as its only
official website origin. The root path will become a product landing page,
documentation will live below `/docs/`, and the blog will live below
`/blogs/`. Home, Docs, and Blogs will share same-origin navigation.

The existing Vercel documentation application will become the unified site.
The existing GitHub Pages workflow will remain as an unlinked compatibility
copy of the original article at the repository's default Pages URL, but it
will no longer own the custom domain or appear in official repository links.

## Goals

- Give CORAL one official website origin.
- Make Home, Docs, and Blogs distinct, predictable path namespaces.
- Keep navigation between those sections on the same origin.
- Preserve the current Fumadocs visual system for the landing page and docs.
- Preserve the existing article's HTML/CSS visual design.
- Establish `/blogs/` as a list that can hold multiple future posts.
- Keep the GitHub Pages deployment as a low-maintenance compatibility copy.
- Replace official links in the repository in one coordinated change.

## Non-goals

- Redesigning the documentation site or the existing article.
- Building a CMS, feed, tags system, pagination, or authoring pipeline.
- Redirecting the retired docs subdomain or old application paths.
- Publishing new blog content as part of this change.
- Removing the existing GitHub Pages workflow.

## Current State

- `coral.compounding-intelligence.ai` is attached to GitHub Pages and serves
  `blog/index.html` as the root page.
- `docs.coral.compounding-intelligence.ai` is attached to the Vercel
  `coral-docs` project and serves the Fumadocs application.
- The docs build copies `blog/` to `docs/public/blog/` and rewrites `/blog` to
  the copied static article.
- Repository documentation and bundled plugin material link to both origins.

## Canonical Information Architecture

| Canonical route | Purpose |
| --- | --- |
| `/` | CORAL product landing page |
| `/docs/` | Documentation home |
| `/docs/getting-started/...` | Getting-started documentation |
| `/docs/concepts/...` | Concept documentation |
| `/docs/guides/...` | Guides |
| `/docs/examples/...` | Examples |
| `/docs/cli/...` | CLI documentation |
| `/docs/api/...` | API documentation |
| `/blogs/` | Blog listing |
| `/blogs/evolve-like-coral/` | Existing launch/research article |

`/blogs/` is plural by design because it is a collection. Future posts use
`/blogs/<slug>/` without changing the listing route.

The following locations are not canonical and receive no new redirects:

- `docs.coral.compounding-intelligence.ai`
- `/blog` and `/blog/`
- former root-level docs paths such as `/guides/...`

## Visual and Navigation Design

### Landing page

The root page uses the existing Docs/Fumadocs visual language: current colors,
typography, spacing, dark-mode behavior, and compatible UI components. It does
not introduce a separate marketing theme.

Its content order is:

1. CORAL positioning and primary calls to action.
2. Core capabilities: isolated workspaces, continuous grading, and shared
   knowledge.
3. A concise explanation of how CORAL works.
4. Quick-start commands leading into the documentation.
5. Supported agent runtimes and representative examples.
6. Research/paper results and the latest blog entry.

### Global navigation

The Fumadocs site shell exposes:

- Logo/Home → `/`
- Docs → `/docs/`
- Blogs → `/blogs/`
- Get started → `/docs/getting-started/`
- GitHub → the external repository

Docs retain their existing sidebar and docs-scoped search below the global
navigation. Blog listing pages do not show the docs sidebar.

The existing article keeps its current standalone visual design and navbar
styling. Its Home, Docs, and Blogs links are changed to the canonical paths on
`coral.compounding-intelligence.ai`. External GitHub and paper links may still
leave the origin.

## Application Structure

The existing `docs/` Next.js application is the sole official application.

### Routes

- Add a root landing page at `docs/app/page.tsx` using the existing Fumadocs
  theme and layout primitives.
- Move the current optional catch-all docs route beneath
  `docs/app/docs/[[...slug]]/`.
- Configure the Fumadocs source base URL as `/docs` so generated page URLs,
  navigation, breadcrumbs, and search results include the prefix.
- Add a Fumadocs-styled blog listing at `docs/app/blogs/page.tsx`.

### Existing article

`blog/` remains the single source for the existing standalone article and its
assets. The docs prebuild sync performs these transformations only in the
generated copy:

1. Copy `blog/` into
   `docs/public/blogs/evolve-like-coral/`.
2. Insert `<base href="/blogs/evolve-like-coral/">` so relative images and
   assets resolve under the canonical article path.
3. Add an explicit Next.js rewrite from `/blogs/evolve-like-coral` (including
   the normalized trailing-slash form) to the copied `index.html`.

The source `blog/index.html` receives canonical same-origin Navbar links so the
Vercel copy and default GitHub Pages copy both lead users back to the official
site. The copy step does not create a second hand-edited article source.

### Blog listing data

This change needs only one article, so the listing may use a small typed local
metadata collection containing slug, title, summary, date, and category. It
must be structured so a future post is added as one metadata entry plus its
content directory. A CMS, dynamic database, and pagination are intentionally
out of scope.

## Link Migration

All maintained repository references to the public website are updated in the
same change. This includes at least:

- `README.md` and `README_CN.md`
- `install.sh`
- `blog/index.html`
- docs navigation and content
- plugin guidance, hooks, and bundled skills

Documentation links gain the `/docs/` prefix. Blog links use `/blogs/` or the
existing article's canonical slug. Official repository content must not link
to `docs.coral.compounding-intelligence.ai` or the default GitHub Pages URL.

## Deployment Topology

### Official site

- Vercel project: existing `coral-docs` project
- Official domain: `coral.compounding-intelligence.ai`
- Content: landing page, docs, blog listing, and article copy

### Compatibility copy

- Deployment: existing GitHub Pages workflow deploying `blog/`
- Address: default project Pages URL,
  `https://human-agent-society.github.io/CORAL/`
- Role: unlinked compatibility copy only
- Custom domain: none

The compatibility deployment remains independent so a Vercel problem does not
remove the old article, but it is not treated as a second official site.

## Migration Sequence

1. Implement routes, content sync, navigation, and repository link changes.
2. Build and deploy a Vercel Preview while production DNS remains unchanged.
3. Verify all canonical routes, assets, navigation, search, themes, and mobile
   behavior on the Preview.
4. Remove `coral.compounding-intelligence.ai` from GitHub Pages custom-domain
   settings. Do not remove the Pages workflow.
5. Add `coral.compounding-intelligence.ai` to the Vercel `coral-docs` project
   and change its DNS record to the Vercel-provided target.
6. Verify DNS propagation, Vercel domain verification, TLS issuance, HTTP to
   HTTPS behavior, and canonical production routes.
7. Remove `docs.coral.compounding-intelligence.ai` from Vercel and remove its
   DNS record only after the main domain is healthy.
8. Confirm the default GitHub Pages URL still serves the compatibility copy.

This order keeps the old production site available until the Preview has been
validated and delays retirement of the docs subdomain until the unified site
is confirmed healthy.

## Failure Handling and Rollback

- If Preview validation fails, production DNS and both existing custom domains
  remain unchanged.
- If Vercel cannot verify or provision TLS for the main domain, restore the
  previous GitHub Pages DNS/custom-domain binding and investigate before
  retiring the docs subdomain.
- If the article route or assets fail, revert the Vercel deployment; the
  GitHub Pages compatibility copy remains available throughout.
- Do not remove `docs.coral.compounding-intelligence.ai` until all main-domain
  checks pass, so it acts as a temporary operational fallback during cutover.

## Verification

### Local and Preview checks

- `npm run build` succeeds in `docs/`.
- A production-mode local server returns successful responses for:
  - `/`
  - `/docs/`
  - `/docs/getting-started/installation`
  - `/blogs/`
  - `/blogs/evolve-like-coral/`
  - representative article images
- Docs sidebar links, breadcrumbs, and search results stay below `/docs/`.
- Home, Docs, Blogs, and Get started use same-origin canonical routes.
- Light/dark themes and mobile navigation work on landing and docs pages.
- The existing article retains its current visual layout at desktop and mobile
  sizes.

### Repository checks

- Search maintained files for `docs.coral.compounding-intelligence.ai`; expect
  no official references.
- Search maintained files for official links to
  `human-agent-society.github.io/CORAL`; expect none.
- Search maintained files for canonical uses of `/blog`; replace them with
  `/blogs/` routes while ignoring unrelated prose and fixture paths.
- Confirm the GitHub Pages workflow still deploys `blog/`.

### Production checks

- DNS resolves the main domain to the Vercel target.
- The main domain presents a valid certificate containing
  `coral.compounding-intelligence.ai` and enforces HTTPS.
- Every canonical route returns the intended page without changing origins.
- GitHub Pages serves the default project URL without a custom domain.
- The retired docs subdomain is no longer advertised or configured.

## Acceptance Criteria

- A user entering `coral.compounding-intelligence.ai` can browse Home, Docs,
  and Blogs without changing origins.
- Documentation canonical URLs all begin with `/docs/`.
- The blog list is `/blogs/`; the existing article is
  `/blogs/evolve-like-coral/`.
- The landing page and docs use the existing Fumadocs design.
- The existing article retains its original design.
- Maintained repository content uses only the new official URLs.
- Vercel is the sole official application and domain owner.
- GitHub Pages remains available only at its default project URL as an
  unlinked compatibility copy.
