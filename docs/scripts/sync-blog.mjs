import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const blogSource = resolve(scriptDirectory, '../../blog');
const blogOutput = resolve(scriptDirectory, '../public/blogs/evolve-like-coral');
const institutionsOutput = resolve(scriptDirectory, '../public/blogs/agents-need-institutions');

export async function syncBlog({
  sourceDir = blogSource,
  outputDir = blogOutput,
  baseHref = '/blogs/evolve-like-coral/',
  sourceFile = 'index.html',
} = {}) {
  await rm(outputDir, { force: true, recursive: true });
  await mkdir(outputDir, { recursive: true });
  const entries = await readdir(sourceDir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isFile() && entry.name.endsWith('.html') && entry.name !== sourceFile) {
      continue;
    }
    await cp(
      resolve(sourceDir, entry.name),
      resolve(outputDir, entry.name),
      { recursive: true },
    );
  }

  const sourcePath = resolve(outputDir, sourceFile);
  const indexPath = resolve(outputDir, 'index.html');
  const indexHtml = await readFile(sourcePath, 'utf8');
  const htmlWithBasePath = indexHtml.replace(
    '<head>',
    '<head>\n<base href="' + baseHref + '">',
  );
  await writeFile(indexPath, htmlWithBasePath);
  if (sourcePath !== indexPath) {
    await rm(sourcePath);
  }
}

await syncBlog();
await syncBlog({
  outputDir: institutionsOutput,
  baseHref: '/blogs/agents-need-institutions/',
  sourceFile: 'agents-need-institutions.html',
});
