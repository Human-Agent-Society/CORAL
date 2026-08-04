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

test('public pages expose canonical and social metadata', async () => {
  const pages = [
    ['/', '/'],
    ['/docs/', '/docs/'],
    ['/blogs/', '/blogs/'],
    ['/blogs/evolve-like-coral/', '/blogs/evolve-like-coral/'],
  ];

  for (const [path, canonicalPath] of pages) {
    const { body } = await get(path);
    const canonical = new URL(canonicalPath, 'https://coral.compounding-intelligence.ai');

    assert.match(body, /<meta name="description" content="[^"]+"/, `${path} description`);
    assert.match(
      body,
      new RegExp(`<link rel="canonical" href="${canonical.toString()}"`),
      `${path} canonical`,
    );
    assert.match(body, /<meta property="og:title" content="[^"]+"/, `${path} Open Graph`);
    assert.match(body, /<meta property="og:image" content="[^"]+"/, `${path} social image`);
    assert.match(body, /<meta name="twitter:card" content="summary_large_image"/, `${path} Twitter`);
  }
});

test('the homepage describes CORAL as a software application', async () => {
  const { body } = await get('/');
  assert.match(body, /<script type="application\/ld\+json">/);
  assert.match(body, /"@type":"SoftwareApplication"/);
  assert.match(body, /"codeRepository":"https:\/\/github\.com\/Human-Agent-Society\/CORAL"/);
});

test('robots and sitemap expose canonical site routes', async () => {
  const robots = await get('/robots.txt');
  assert.equal(robots.response.status, 200);
  assert.match(robots.body, /Allow: \//);
  assert.match(
    robots.body,
    /Sitemap: https:\/\/coral\.compounding-intelligence\.ai\/sitemap\.xml/,
  );

  const sitemap = await get('/sitemap.xml');
  assert.equal(sitemap.response.status, 200);
  assert.match(sitemap.response.headers.get('content-type') ?? '', /application\/xml/);
  for (const path of ['/', '/docs/', '/blogs/', '/blogs/evolve-like-coral/']) {
    assert.match(
      sitemap.body,
      new RegExp(`https://coral\\.compounding-intelligence\\.ai${path.replaceAll('/', '\\/')}`),
      path,
    );
  }
});

test('llms.txt provides canonical project and documentation entry points', async () => {
  const { response, body } = await get('/llms.txt');
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type') ?? '', /^text\/plain/);
  assert.match(body, /^# CORAL$/m);
  assert.match(body, /open-source autoresearch powered by autonomous coding agents/i);
  assert.match(body, /https:\/\/coral\.compounding-intelligence\.ai\/docs\/getting-started\/quickstart\//);
  assert.match(body, /https:\/\/github\.com\/Human-Agent-Society\/CORAL/);
  assert.doesNotMatch(body, /uv tool install coral(?:\s|[`'"]|$)/);
});

test('the article serves an asset below its canonical prefix', async () => {
  const { response } = await get(
    '/blogs/evolve-like-coral/coral_logo.png',
  );
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type') ?? '', /^image\//);
});

test('the article keeps the global navigation and blog active state', async () => {
  const { body } = await get('/blogs/evolve-like-coral/');
  const navbar = body.match(/<nav class="nav">[\s\S]*?<\/nav>/)?.[0];

  assert.ok(navbar, 'article navigation');
  for (const href of ['/', '/docs/', '/blogs/']) {
    assert.match(navbar, new RegExp(`href="${href}"`), href);
  }
  assert.match(navbar, /href="\/blogs\/"[^>]*aria-current="page"/);
  assert.match(navbar, /data-theme-toggle/);
  assert.match(navbar, /aria-label="GitHub"/);
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
  for (const path of ['/', '/docs/', '/blogs/', '/blogs/evolve-like-coral/']) {
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
