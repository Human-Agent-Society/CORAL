import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const blogSource = resolve(scriptDirectory, '../../blog');
const blogOutput = resolve(scriptDirectory, '../public/blog');

await rm(blogOutput, { force: true, recursive: true });
await mkdir(blogOutput, { recursive: true });
await cp(blogSource, blogOutput, { recursive: true });

const indexPath = resolve(blogOutput, 'index.html');
const indexHtml = await readFile(indexPath, 'utf8');
const htmlWithBasePath = indexHtml.replace('<head>', '<head>\n<base href="/blog/">');

await writeFile(indexPath, htmlWithBasePath);
