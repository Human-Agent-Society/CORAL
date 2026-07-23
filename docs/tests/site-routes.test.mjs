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
    ['/blogs/agents-need-institutions/', 'Multi-agent Societies'],
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
  for (const prefix of ['evolve-like-coral', 'agents-need-institutions']) {
    const { response } = await get(`/blogs/${prefix}/coral_logo.png`);
    assert.equal(response.status, 200, prefix);
    assert.match(response.headers.get('content-type') ?? '', /^image\//, prefix);
  }
});

test('the blogs index lists the new institutions post', async () => {
  const { body } = await get('/blogs/');
  assert.match(body, /href="\/blogs\/agents-need-institutions\/"/);
});

test('home presents the institutions post as the latest article', async () => {
  const { body } = await get('/');
  assert.match(body, /href="\/blogs\/agents-need-institutions\/"/);
  assert.match(body, /Multi-agent Societies, Institutions, and Incentives/);
});

test('the article keeps the global navigation and blog active state', async () => {
  for (const path of ['/blogs/evolve-like-coral/', '/blogs/agents-need-institutions/']) {
    const { body } = await get(path);
    const navbar = body.match(/<nav class="nav">[\s\S]*?<\/nav>/)?.[0];

    assert.ok(navbar, `${path} article navigation`);
    for (const href of ['/', '/docs/', '/blogs/']) {
      assert.match(navbar, new RegExp(`href="${href}"`), `${path} ${href}`);
    }
    assert.match(navbar, /href="\/blogs\/"[^>]*aria-current="page"/, `${path} active blog`);
    assert.match(navbar, /class="nav-logo"/, `${path} logo`);
    assert.match(navbar, /class="nav-links"/, `${path} desktop links`);
    assert.match(navbar, /class="nav-actions"/, `${path} desktop actions`);
    assert.match(navbar, /<details class="nav-menu">/, `${path} mobile menu`);
    assert.match(navbar, /summary aria-label="Toggle Menu"/, `${path} menu toggle`);
    assert.match(navbar, /href="https:\/\/github\.com\/Human-Agent-Society\/CORAL" class="gh-link" aria-label="GitHub"/, `${path} GitHub link`);
    assert.equal((navbar.match(/data-theme-toggle/g) ?? []).length, 2, `${path} theme toggles`);
  }
});

test('docs and blogs share the global top navigation', async () => {
  for (const path of ['/docs/', '/blogs/']) {
    const { body } = await get(path);
    const navbar = body.match(/<header id="nd-nav"[\s\S]*?<\/header>/)?.[0];

    assert.ok(navbar, `${path} top navigation`);
    for (const href of ['/', '/docs/', '/blogs/']) {
      assert.match(navbar, new RegExp(`href="${href}"`), `${path} ${href}`);
    }
    assert.doesNotMatch(navbar, /href="\/docs\/getting-started\/"/);
  }

  const { body } = await get('/docs/');
  const sidebar = body.match(/<aside id="nd-sidebar"[\s\S]*?<\/aside>/)?.[0];

  assert.ok(sidebar, 'docs sidebar');
  assert.doesNotMatch(sidebar, /href="\/blogs\/"/);
  assert.doesNotMatch(sidebar, /href="\/docs\/getting-started\/"/);
});

test('the current global navigation item is the only active item', async () => {
  const pages = [
    ['/', ['/']],
    ['/docs/', ['/docs/']],
    ['/blogs/', ['/blogs/']],
    ['/docs/getting-started/', ['/docs/']],
  ];

  for (const [path, expectedHrefs] of pages) {
    const { body } = await get(path);
    const navbar = body.match(/<header id="nd-nav"[\s\S]*?<\/header>/)?.[0];
    const activeLinks = [...(navbar?.matchAll(/<a\b[^>]*data-active="true"[^>]*>/g) ?? [])]
      .map(([tag]) => tag.match(/href="([^"]+)"/)?.[1])
      .filter(Boolean);

    assert.deepEqual([...new Set(activeLinks)], expectedHrefs, path);
  }
});

test('theme controls include the interactive theme bootstrap', async () => {
  for (const path of ['/', '/docs/', '/blogs/', '/blogs/evolve-like-coral/', '/blogs/agents-need-institutions/']) {
    const { body } = await get(path);

    assert.match(body, /data-theme-toggle/, `${path} theme control`);
    assert.match(body, /localStorage/, `${path} theme bootstrap`);
    assert.doesNotMatch(body, /<html[^>]*class="light"/, `${path} forced light theme`);
  }
});

test('retired root-level docs are not canonical', async () => {
  const { response } = await get('/getting-started/installation');
  assert.equal(response.status, 404);
});
