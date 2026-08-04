import type { Metadata } from 'next';

export const SITE_ORIGIN = 'https://coral.compounding-intelligence.ai';
export const SITE_NAME = 'CORAL';
export const DEFAULT_TITLE = 'CORAL: Open-Source Autoresearch Powered by Autonomous Coding Agents';
export const CORAL_DEFINITION =
  'CORAL is an open-source autoresearch framework powered by autonomous coding agents. It runs long-lived agents in isolated Git worktrees, continuously grades experiments, and shares knowledge through persistent memory.';
export const CORAL_DISAMBIGUATION =
  'CORAL is not affiliated with Coral Protocol or CoralOS; those are separate projects.';
export const DEFAULT_DESCRIPTION = CORAL_DEFINITION;
export const GITHUB_REPOSITORY_URL = 'https://github.com/Human-Agent-Society/CORAL';
export const PAPER_URL = 'https://arxiv.org/abs/2604.01658';
const SOCIAL_IMAGE_PATH = '/opengraph-image/';
const SOCIAL_IMAGE_ALT = 'CORAL: open-source autoresearch powered by autonomous coding agents';

export function absoluteUrl(path: string): string {
  return new URL(path, SITE_ORIGIN).toString();
}

export const softwareApplicationJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  '@id': `${SITE_ORIGIN}/#software`,
  name: 'CORAL',
  alternateName: [
    'CORAL autoresearch framework',
    'CORAL autonomous coding agents framework',
  ],
  applicationCategory: 'DeveloperApplication',
  operatingSystem: 'Linux, macOS',
  description: CORAL_DEFINITION,
  disambiguatingDescription: CORAL_DISAMBIGUATION,
  url: SITE_ORIGIN,
  mainEntityOfPage: absoluteUrl('/docs/what-is-coral/'),
  codeRepository: GITHUB_REPOSITORY_URL,
  license: 'https://www.apache.org/licenses/LICENSE-2.0',
  softwareRequirements: 'Python 3.11 or later and Git',
  keywords: [
    'autoresearch',
    'autonomous coding agents',
    'multi-agent systems',
    'agent orchestration',
    'shared memory',
  ],
  offers: {
    '@type': 'Offer',
    price: '0',
    priceCurrency: 'USD',
  },
  sameAs: [GITHUB_REPOSITORY_URL, PAPER_URL],
};

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
