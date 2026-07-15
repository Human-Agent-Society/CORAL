# Unified CORAL Site Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make coral.compounding-intelligence.ai the single official CORAL site, with a Fumadocs-styled home page, /docs/ documentation, /blogs/ listing, and the existing article at /blogs/evolve-like-coral/, while retaining GitHub Pages only as an unlinked default-URL copy.

**Architecture:** Extend the existing docs/ Next.js/Fumadocs application into the official site. A shared Fumadocs shell serves Home and the blog listing; the existing standalone article remains sourced from blog/ and is copied into a canonical public article directory at build time. GitHub Pages continues deploying blog/ independently but no longer owns the custom domain.

**Tech Stack:** Next.js 15, React 19, Fumadocs Core/UI/MDX, Tailwind CSS 4, Node.js built-in test runner, GitHub Actions Pages deployment, Vercel custom-domain hosting.

## Global Constraints

- All PRs target dev, never main, except maintainer release-promotion PRs.
- coral.compounding-intelligence.ai is the only official website origin.
- Canonical routes are /, /docs/, /blogs/, and /blogs/evolve-like-coral/.
- Do not add redirects for docs.coral.compounding-intelligence.ai, /blog/, or former root-level docs paths.
- Preserve the current Fumadocs visual system for Home and Docs.
- Preserve the existing standalone article HTML/CSS design.
- Keep .github/workflows/deploy-blog.yml and the default GitHub Pages copy.
- Official repository links must not point to the default GitHub Pages URL.
- Do not add a CMS, database, pagination, tags system, or new runtime dependency.
- A human author must review every changed line before any PR is opened.

## File Map

Create:

- docs/app/(site)/layout.tsx
- docs/app/(site)/page.tsx
- docs/app/(site)/blogs/page.tsx
- docs/lib/blogs.ts
- docs/tests/site-routes.test.mjs
- docs/tests/blog-sync.test.mjs
- docs/tests/canonical-links.test.mjs

Move:

- docs/app/[[...slug]]/page.tsx to docs/app/docs/[[...slug]]/page.tsx
- docs/app/[[...slug]]/layout.tsx to docs/app/docs/[[...slug]]/layout.tsx

Modify:

- docs/lib/layout.shared.tsx, docs/lib/source.ts, docs/next.config.mjs
- docs/scripts/sync-blog.mjs, docs/package.json
- absolute docs links in docs/content/**/*.mdx
- README.md, README_CN.md, install.sh, blog/index.html
- plugin/AGENTS.md, plugin/hooks/session-start.py, and the listed plugin skills

---

### Task 1: Establish the failing canonical-route contract

**Files:** Create docs/tests/site-routes.test.mjs; modify docs/package.json.

**Interfaces:** The test consumes a production server at SITE_URL (default
http://127.0.0.1:3000) and produces npm run test:routes for later tasks.

- [ ] Step 1: Add the failing route test.

~~~js
import assert from 'node:assert/strict';
import test from 'node:test';

const base = new URL(process.env.SITE_URL ?? 'http://127.0.0.1:3000');
async function get(path) {
  const response = await fetch(new URL(path, base));
  return { response, body: await response.text() };
}

test('canonical pages stay on the same origin', async () => {
  const pages = [
    ['/', 'autonomous'],
    ['/docs/', 'Documentation'],
    ['/blogs/', 'Blogs'],
    ['/blogs/evolve-like-coral/', 'Evolve Like Coral'],
  ];
  for (const [path, marker] of pages) {
    const { response, body } = await get(path);
    assert.equal(response.status, 200, path);
    assert.equal(new URL(response.url).origin, base.origin, path);
    assert.match(body, new RegExp(marker, 'i'), path);
  }
});

test('the article serves an asset below its canonical prefix', async () => {
  const { response } = await get(
    '/blogs/evolve-like-coral/coral_logo.png',
  );
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type') ?? '', /^image\//);
});

test('retired root-level docs are not canonical', async () => {
  const { response } = await get('/getting-started/installation');
  assert.equal(response.status, 404);
});
~~~

- [ ] Step 2: Add the package script.

~~~json
{
  "scripts": {
    "test:routes": "node --test tests/site-routes.test.mjs"
  }
}
~~~

Keep the existing predev, prebuild, build, postinstall, and start scripts.

- [ ] Step 3: Run the red test against the current app.

~~~bash
cd docs
npm ci
npm run build
PORT=3100 npm start > /tmp/coral-docs-route-test.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID"' EXIT
SITE_URL=http://127.0.0.1:3100 npm run test:routes
~~~

Expected: FAIL because /docs/, /blogs/, and the canonical article do not
exist.

- [ ] Step 4: Commit the contract.

~~~bash
git add docs/package.json docs/tests/site-routes.test.mjs
git commit -m "test(docs): define unified site routes"
~~~

---

### Task 2: Add the Fumadocs shell, landing page, docs prefix, and listing

**Files:** Create docs/app/(site)/layout.tsx, docs/app/(site)/page.tsx,
docs/app/(site)/blogs/page.tsx, docs/lib/blogs.ts. Move both existing
catch-all files below docs/app/docs/. Modify docs/lib/layout.shared.tsx,
docs/lib/source.ts, and absolute links in docs/content/**/*.mdx.

**Interfaces:** Consumes baseOptions(), source, and Task 1's route contract.
Produces Home at /, Docs below /docs/, and typed blogPosts metadata.

- [ ] Step 1: Move the two catch-all files to docs/app/docs/ and change
  docs/lib/source.ts to:

~~~ts
export const source = loader({
  baseUrl: '/docs',
  source: { files: resolveFiles({ docs: docs.docs, meta: docs.meta }) },
});
~~~

- [ ] Step 2: Prefix maintained absolute MDX links. For example, change
  [Quick Start](/getting-started/quickstart) to
  [Quick Start](/docs/getting-started/quickstart). Update exact matches in
  docs/content/docs/ and leave code examples, external URLs, and raw/blog/
  fixture references unchanged.

- [ ] Step 3: Create docs/lib/blogs.ts:

~~~ts
export interface BlogPost {
  slug: string;
  title: string;
  summary: string;
  date: string;
  category: string;
  href: string;
}

export const blogPosts: readonly BlogPost[] = [
  {
    slug: 'evolve-like-coral',
    title: 'Evolve Like Coral: Towards Autonomous Multi-Agent Evolution',
    summary:
      'CORAL experiments on autonomous multi-agent evolution, collaboration, and open-ended discovery.',
    date: '2026-03-18',
    category: 'Research',
    href: '/blogs/evolve-like-coral/',
  },
];
~~~

- [ ] Step 4: Update docs/lib/layout.shared.tsx while preserving its current
  logo JSX, dimensions, and palette. Its links must be:

~~~ts
links: [
  { text: 'Home', url: '/' },
  { text: 'Docs', url: '/docs/' },
  { text: 'Blogs', url: '/blogs/' },
  { type: 'button', text: 'Get started', url: '/docs/getting-started/' },
],
~~~

Keep the existing GitHub URL.

- [ ] Step 5: Create docs/app/(site)/layout.tsx:

~~~tsx
import { HomeLayout } from 'fumadocs-ui/layouts/home';
import type { ReactNode } from 'react';
import { baseOptions } from '@/lib/layout.shared';

export default function SiteLayout({ children }: { children: ReactNode }) {
  return <HomeLayout {...baseOptions()}>{children}</HomeLayout>;
}
~~~

- [ ] Step 6: Create the root page with existing Fumadocs/Tailwind classes and
  global color variables. Render, in order: positioning hero; three capability
  cards; architecture explanation; Quick Start linked to
  /docs/getting-started/; supported agents/examples; research and latest-blog
  links. Create the Blogs page with H1 Blogs, short description, and one card
  per blogPosts entry; it must not include a docs sidebar.

- [ ] Step 7: Run the production server from Task 1 and run the focused
  Home/Docs/Blogs test with
  `node --test tests/site-routes.test.mjs --test-name-pattern="canonical pages"`.
  The article and asset assertions intentionally remain deferred to Task 3,
  which owns article synchronization. Commit:

~~~bash
git add docs/app docs/lib docs/content
git commit -m "feat(docs): unify home docs and blogs routes"
~~~

---

### Task 3: Move the existing article to its canonical slug without redesigning it

**Files:** Create docs/tests/blog-sync.test.mjs. Modify
docs/scripts/sync-blog.mjs and docs/next.config.mjs. blog/index.html is
modified for links in Task 4.

**Interfaces:** Consumes blog/ as the source. Produces syncBlog({ sourceDir,
outputDir, baseHref }), generated output at
docs/public/blogs/evolve-like-coral/, and a non-catch-all rewrite.

- [ ] Step 1: Add the isolated sync test:

~~~js
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { syncBlog } from '../scripts/sync-blog.mjs';

test('syncBlog copies the article and scopes assets', async () => {
  const root = await mkdtemp(join(tmpdir(), 'coral-blog-'));
  const sourceDir = join(root, 'source');
  const outputDir = join(root, 'output');
  await mkdir(sourceDir);
  await writeFile(join(sourceDir, 'index.html'), '<html><head></head></html>');
  await writeFile(join(sourceDir, 'coral_logo.png'), 'asset');
  await syncBlog({
    sourceDir,
    outputDir,
    baseHref: '/blogs/evolve-like-coral/',
  });
  const html = await readFile(join(outputDir, 'index.html'), 'utf8');
  assert.match(html, /<base href="\/blogs\/evolve-like-coral\/">/);
  assert.equal(await readFile(join(outputDir, 'coral_logo.png'), 'utf8'), 'asset');
});
~~~

- [ ] Step 2: Run node --test tests/blog-sync.test.mjs and record the red
  state because syncBlog is not exported.

- [ ] Step 3: Export syncBlog with defaults for the real source/output:

~~~js
export async function syncBlog({
  sourceDir = blogSource,
  outputDir = blogOutput,
  baseHref = '/blogs/evolve-like-coral/',
} = {}) {
  await rm(outputDir, { force: true, recursive: true });
  await mkdir(outputDir, { recursive: true });
  await cp(sourceDir, outputDir, { recursive: true });
  const indexPath = resolve(outputDir, 'index.html');
  const indexHtml = await readFile(indexPath, 'utf8');
  const htmlWithBasePath = indexHtml.replace(
    '<head>',
    '<head>\n<base href="' + baseHref + '">',
  );
  await writeFile(indexPath, htmlWithBasePath);
}
~~~

Keep the default syncBlog() invocation for predev and prebuild.

- [ ] Step 4: Run the sync test and expect 1 passing test. Replace the old
  /blog rewrite with:

~~~js
{
  source: '/blogs/evolve-like-coral',
  destination: '/blogs/evolve-like-coral/index.html',
}
~~~

Retain reactStrictMode and createMDX; cover the trailing-slash request without
using a catch-all that intercepts article assets.

- [ ] Step 5: Run the route test and:

~~~bash
curl -I http://127.0.0.1:3100/blogs/evolve-like-coral/coral_logo.png
~~~

Expected: article and image are HTTP 200 and the image content type starts
with image/.

- [ ] Step 6: Commit:

~~~bash
git add docs/scripts/sync-blog.mjs docs/next.config.mjs docs/tests/blog-sync.test.mjs
git commit -m "feat(docs): serve blog article at canonical slug"
~~~

---

### Task 4: Migrate all maintained public links

**Files:** Create docs/tests/canonical-links.test.mjs. Modify README.md,
README_CN.md, install.sh, blog/index.html, docs/lib/layout.shared.tsx,
plugin/AGENTS.md, plugin/hooks/session-start.py, and the listed plugin
skill/reference files found by the repository search.

**Interfaces:** Consumes the canonical route table and produces no maintained
reference to the retired docs origin, default Pages URL, or old /blog path.

- [ ] Step 1: Add a Node test that reads the maintained file list and asserts
  neither docs.coral.compounding-intelligence.ai nor
  human-agent-society.github.io/CORAL occurs. Also assert docs/content/docs/index.mdx
  contains ](/docs/getting-started/installation) and no ](/getting-started/,
  ](/guides/, ](/cli/, ](/api/, or ](/concepts/ links.

- [ ] Step 2: Run node --test tests/canonical-links.test.mjs and record the
  red state.

- [ ] Step 3: Rewrite official destinations exactly:

- Documentation: https://coral.compounding-intelligence.ai/docs/<path>
- Blog list: https://coral.compounding-intelligence.ai/blogs/
- Existing article: https://coral.compounding-intelligence.ai/blogs/evolve-like-coral/
- In-application links: equivalent root-relative paths.

In blog/index.html set the logo to the official root, Docs to /docs/, Blog to
/blogs/, and Documentation to /docs/. Use absolute canonical-origin URLs there
so the default Pages copy does not resolve links against /CORAL/.

- [ ] Step 4: Run the link test and:

~~~bash
rg -n -i 'docs\.coral\.compounding-intelligence\.ai|human-agent-society\.github\.io/CORAL' \
  README.md README_CN.md install.sh blog docs/content docs/lib plugin
~~~

Expected: the test passes and rg returns no maintained official references.
Leave unrelated fixture prose such as raw/blog/<file> unchanged.

- [ ] Step 5: Commit:

~~~bash
git add README.md README_CN.md install.sh blog docs plugin
git commit -m "docs: point public links to unified site"
~~~

---

### Task 5: Build, smoke-test, and review the complete code change

**Files:** Test docs/tests/site-routes.test.mjs, docs/tests/blog-sync.test.mjs,
docs/tests/canonical-links.test.mjs; verify unchanged
.github/workflows/deploy-blog.yml.

- [ ] Step 1: Run:

~~~bash
cd docs
npm run test:routes
node --test tests/blog-sync.test.mjs tests/canonical-links.test.mjs
npm run build
~~~

Expected: all tests pass and Next/Fumadocs build exits 0 with
public/blogs/evolve-like-coral/index.html generated.

- [ ] Step 2: Start npm start on port 3100 and rerun the route test plus curl
  checks for /docs/, /blogs/, the article, and its image. Inspect Home, Docs,
  Blogs, and the article at desktop/mobile widths. Confirm Fumadocs palette,
  fonts, sidebar, mobile menu, article layout, images, and same-origin Navbar.

- [ ] Step 3: Confirm:

~~~bash
git diff origin/dev...HEAD -- .github/workflows/deploy-blog.yml
git status --short
~~~

Expected: workflow diff is empty and only intentional site files are changed.
Do not create an empty commit; attach the fresh build and smoke-test output to
the Preview/PR Test plan.

---

### Task 6: Deploy Preview and perform the controlled domain cutover

**Files:** No repository files; Vercel, GitHub Pages settings, and DNS.

**Interfaces:** Consumes a deployable implementation branch with Tasks 1–5
passing. Produces Vercel as sole official origin and GitHub Pages as an
unlinked default-URL compatibility copy.

- [ ] Step 1: Deploy a Vercel Preview and run every route, asset, link, and
  visual check before changing production DNS.

- [ ] Step 2: In repository Settings → Pages, remove
  coral.compounding-intelligence.ai from Custom domain. Keep the workflow and
  verify https://human-agent-society.github.io/CORAL/ still serves the article.

- [ ] Step 3: In the existing coral-docs Vercel project, add
  coral.compounding-intelligence.ai and apply the exact DNS target Vercel
  provides. Never guess the target or leave both services claiming the name.

- [ ] Step 4: Verify:

~~~bash
dig @1.1.1.1 +short coral.compounding-intelligence.ai CNAME
curl -fsSI https://coral.compounding-intelligence.ai/
curl -fsS https://coral.compounding-intelligence.ai/docs/ >/dev/null
curl -fsS https://coral.compounding-intelligence.ai/blogs/ >/dev/null
curl -fsS https://coral.compounding-intelligence.ai/blogs/evolve-like-coral/ >/dev/null
openssl s_client -connect coral.compounding-intelligence.ai:443 \
  -servername coral.compounding-intelligence.ai </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -ext subjectAltName
~~~

Expected: Vercel DNS, HTTPS enforcement, HTTP 200 canonical routes, and a
certificate SAN containing coral.compounding-intelligence.ai.

- [ ] Step 5: Only after the main domain is healthy, remove
  docs.coral.compounding-intelligence.ai from Vercel and delete its DNS record.
  Do not add a redirect.

- [ ] Step 6: Record Pages default URL, Vercel domain status, DNS answer, TLS
  SAN, and smoke output in the PR Test plan. Do not claim cutover success
  without fresh successful output.

## Self-Review Checklist

- Tasks cover Home, all docs namespaces, Blogs listing, article slug/assets,
  retired paths, same-origin navigation, and the Fumadocs visual contract.
- Sync task keeps blog/ as the one source and uses a non-catch-all rewrite.
- Link task covers README, installer, blog, docs, plugin docs, hooks, and
  Skills while excluding unrelated fixture paths.
- Deployment keeps GitHub Pages, removes only its custom-domain binding,
  attaches Vercel, verifies TLS, and retires docs subdomain last.
- No task adds compatibility redirects, a CMS, or a second article source.
- Every implementation task has an executable test or verification command and
  a commit boundary.
