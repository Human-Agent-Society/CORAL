import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import test from 'node:test';

const root = resolve(import.meta.dirname, '../..');
const maintainedFiles = [
  'README.md',
  'README_CN.md',
  'install.sh',
  'blog/index.html',
  'blog/agents-need-institutions.html',
  'docs/lib/layout.shared.tsx',
  'plugin/AGENTS.md',
  'plugin/hooks/session-start.py',
  'plugin/skills/coral-quickstart/SKILL.md',
  'plugin/skills/creating-a-coral-task/SKILL.md',
  'plugin/skills/creating-a-coral-task/references/rubric-judges.md',
  'plugin/skills/creating-a-coral-task/references/task-yaml.md',
  'plugin/skills/running-coral-experiments/SKILL.md',
  'plugin/skills/running-coral-experiments/references/scaling-and-ops.md',
  'plugin/skills/setting-up-coral/SKILL.md',
  'docs/content/docs/index.mdx',
];

test('maintained public links use the unified site origin', async () => {
  const forbidden = [
    'docs.coralxyz.com',
    'docs.coral.compounding-intelligence.ai',
    'human-agent-society.github.io/CORAL',
  ];

  for (const relativePath of maintainedFiles) {
    const contents = await readFile(resolve(root, relativePath), 'utf8');
    for (const origin of forbidden) {
      assert.doesNotMatch(contents, new RegExp(origin.replaceAll('.', '\\.'), 'i'), relativePath);
    }
  }
});

test('docs index links stay under the canonical docs prefix', async () => {
  const contents = await readFile(resolve(root, 'docs/content/docs/index.mdx'), 'utf8');
  assert.match(contents, /\]\(\/docs\/getting-started\/installation\)/);
  for (const route of ['getting-started', 'guides', 'cli', 'api', 'concepts']) {
    assert.doesNotMatch(contents, new RegExp(`\\]\\(/${route}\\/`), route);
  }
});

test('blog articles declare their canonical unified-site URLs', async () => {
  const expected = {
    'blog/index.html': 'https://coral.compounding-intelligence.ai/blogs/evolve-like-coral/',
    'blog/agents-need-institutions.html': 'https://coral.compounding-intelligence.ai/blogs/agents-need-institutions/',
  };

  for (const [relativePath, url] of Object.entries(expected)) {
    const contents = await readFile(resolve(root, relativePath), 'utf8');
    assert.match(contents, new RegExp(`<link rel="canonical" href="${url.replaceAll('.', '\\.')}">?`), relativePath);
    assert.match(contents, new RegExp(`<meta property="og:url" content="${url.replaceAll('.', '\\.')}">?`), relativePath);
  }
});
