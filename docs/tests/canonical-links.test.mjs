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

test('public plugin instructions install CORAL from its source repository', async () => {
  const installationFiles = [
    'plugin/AGENTS.md',
    'plugin/hooks/session-start.py',
    'plugin/skills/coral-quickstart/SKILL.md',
  ];

  for (const relativePath of installationFiles) {
    const contents = await readFile(resolve(root, relativePath), 'utf8');
    assert.doesNotMatch(contents, /uv tool install coral(?:\s|[`'"]|$)/, relativePath);
    assert.match(
      contents,
      /uv tool install git\+https:\/\/github\.com\/Human-Agent-Society\/CORAL\.git/,
      relativePath,
    );
  }
});
