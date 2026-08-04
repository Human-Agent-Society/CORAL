import { source } from '@/lib/source';
import {
  DocsBody,
  DocsDescription,
  DocsPage,
  DocsTitle,
} from 'fumadocs-ui/page';
import { notFound } from 'next/navigation';
import { getMDXComponents } from '@/components/mdx';
import { createRelativeLink } from 'fumadocs-ui/mdx';
import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import {
  absoluteUrl,
  CORAL_DEFINITION,
  CORAL_DISAMBIGUATION,
  createPageMetadata,
  softwareApplicationJsonLd,
} from '@/lib/metadata';

interface PageProps {
  params: Promise<{ slug?: string[] }>;
}

// The page data includes MDX-specific fields (body, toc, full) at runtime,
// but the generic PageData type from fumadocs-core doesn't include them.
interface MDXPageData {
  title: string;
  description?: string;
  body: (props: { components?: Record<string, unknown> }) => ReactNode;
  toc: { depth: number; url: string; title: ReactNode }[];
  full?: boolean;
}

const coralIdentityJsonLd = {
  '@context': 'https://schema.org',
  '@graph': [
    softwareApplicationJsonLd,
    {
      '@type': 'AboutPage',
      '@id': absoluteUrl('/docs/what-is-coral/#page'),
      url: absoluteUrl('/docs/what-is-coral/'),
      name: 'What Is CORAL? The Open-Source Autoresearch Framework',
      description: CORAL_DEFINITION,
      mainEntity: { '@id': softwareApplicationJsonLd['@id'] },
    },
    {
      '@type': 'FAQPage',
      '@id': absoluteUrl('/docs/what-is-coral/#faq'),
      mainEntity: [
        {
          '@type': 'Question',
          name: 'What is CORAL?',
          acceptedAnswer: { '@type': 'Answer', text: CORAL_DEFINITION },
        },
        {
          '@type': 'Question',
          name: 'Is CORAL an AI agent?',
          acceptedAnswer: {
            '@type': 'Answer',
            text: 'Yes and no. Individual coding-agent processes running through CORAL can be called CORAL agents. The CORAL project itself is an autoresearch framework around those agents, not a single AI model.',
          },
        },
        {
          '@type': 'Question',
          name: 'Is CORAL related to Coral Protocol or CoralOS?',
          acceptedAnswer: { '@type': 'Answer', text: CORAL_DISAMBIGUATION },
        },
      ],
    },
  ],
};

export default async function Page(props: PageProps) {
  const params = await props.params;
  const page = source.getPage(params.slug);
  if (!page) notFound();

  const data = page.data as unknown as MDXPageData;
  const MDX = data.body;
  const isCoralIdentityPage = page.url === '/docs/what-is-coral';

  return (
    <>
      {isCoralIdentityPage ? (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(coralIdentityJsonLd) }}
        />
      ) : null}
      <DocsPage toc={data.toc} full={data.full} tableOfContent={{ single: false }}>
        <DocsTitle>{data.title}</DocsTitle>
        <DocsDescription>{data.description}</DocsDescription>
        <DocsBody>
          <MDX
            components={getMDXComponents({
              a: createRelativeLink(source, page),
            })}
          />
        </DocsBody>
      </DocsPage>
    </>
  );
}

export async function generateStaticParams() {
  return source.generateParams();
}

export async function generateMetadata(props: PageProps): Promise<Metadata> {
  const params = await props.params;
  const page = source.getPage(params.slug);
  if (!page) notFound();
  const data = page.data as unknown as MDXPageData;

  return createPageMetadata({
    title: data.title,
    description: data.description ?? 'Documentation for the CORAL autoresearch framework.',
    path: page.url.endsWith('/') ? page.url : `${page.url}/`,
  });
}
