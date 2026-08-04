import type { Metadata } from 'next';

export const SITE_ORIGIN = 'https://coral.compounding-intelligence.ai';
export const SITE_NAME = 'CORAL';
export const DEFAULT_TITLE = 'CORAL: Open-Source Autoresearch Powered by Autonomous Coding Agents';
export const DEFAULT_DESCRIPTION =
  'Run Claude Code, Codex, Cursor, Kiro, and OpenCode as a self-improving multi-agent team with isolated worktrees, continuous grading, and shared memory.';
const SOCIAL_IMAGE_PATH = '/opengraph-image/';
const SOCIAL_IMAGE_ALT = 'CORAL: open-source autoresearch powered by autonomous coding agents';

export function absoluteUrl(path: string): string {
  return new URL(path, SITE_ORIGIN).toString();
}

export function createPageMetadata({
  title,
  description,
  path,
}: {
  title: string;
  description: string;
  path: string;
}): Metadata {
  const canonical = absoluteUrl(path);

  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      type: 'website',
      locale: 'en_US',
      url: canonical,
      siteName: SITE_NAME,
      title,
      description,
      images: [
        {
          url: absoluteUrl(SOCIAL_IMAGE_PATH),
          width: 1200,
          height: 630,
          alt: SOCIAL_IMAGE_ALT,
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [{ url: absoluteUrl(SOCIAL_IMAGE_PATH), alt: SOCIAL_IMAGE_ALT }],
    },
  };
}
