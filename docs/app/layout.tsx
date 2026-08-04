import { RootProvider } from 'fumadocs-ui/provider/next';
import { Analytics } from '@vercel/analytics/next';
import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import {
  createPageMetadata,
  DEFAULT_DESCRIPTION,
  DEFAULT_TITLE,
  SITE_ORIGIN,
} from '@/lib/metadata';
import './global.css';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_ORIGIN),
  ...createPageMetadata({
    title: DEFAULT_TITLE,
    description: DEFAULT_DESCRIPTION,
    path: '/',
  }),
  title: {
    default: DEFAULT_TITLE,
    template: '%s | CORAL',
  },
  applicationName: 'CORAL',
  authors: [{ name: 'Human-Agent-Society', url: 'https://github.com/Human-Agent-Society' }],
  creator: 'Human-Agent-Society',
  publisher: 'Human-Agent-Society',
  category: 'technology',
  keywords: [
    'autoresearch',
    'autonomous coding agents',
    'multi-agent systems',
    'coding agent infrastructure',
    'self-evolving agents',
    'Claude Code',
    'Codex',
  ],
};

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,200..900;1,8..60,200..900&family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=DM+Mono:wght@300;400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body
        className="flex min-h-screen flex-col"
        style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}
      >
        <RootProvider>{children}</RootProvider>
        <Analytics />
      </body>
    </html>
  );
}
