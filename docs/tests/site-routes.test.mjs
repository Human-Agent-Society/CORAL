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
