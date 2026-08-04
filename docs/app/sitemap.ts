import type { MetadataRoute } from 'next';
import { source } from '@/lib/source';
import { absoluteUrl } from '@/lib/metadata';

function withTrailingSlash(path: string): string {
  return path.endsWith('/') ? path : `${path}/`;
}

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = new Set([
    '/',
    '/blogs/',
    '/blogs/evolve-like-coral/',
    ...source.getPages().map((page) => withTrailingSlash(page.url)),
  ]);

  return [...routes].map((path) => ({
    url: absoluteUrl(path),
    changeFrequency: path === '/' ? 'weekly' : 'monthly',
    priority: path === '/' ? 1 : path === '/docs/' ? 0.9 : 0.7,
  }));
}
