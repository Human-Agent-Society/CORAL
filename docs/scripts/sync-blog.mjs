import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const blogSource = resolve(scriptDirectory, '../../blog');
const blogOutput = resolve(scriptDirectory, '../public/blogs/evolve-like-coral');

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

await syncBlog();
