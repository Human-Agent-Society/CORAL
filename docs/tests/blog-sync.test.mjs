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
