import type { MetadataRoute } from 'next';
import { absoluteUrl, SITE_ORIGIN } from '@/lib/metadata';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
    },
    sitemap: absoluteUrl('/sitemap.xml'),
    host: SITE_ORIGIN,
  };
}
