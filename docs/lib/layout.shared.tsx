import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { type ReactNode } from 'react';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <>
          <img
            src="/coral_logo.png"
            alt="CORAL"
            style={{ width: 28, height: 28, objectFit: 'contain' }}
          />
          <span style={{ fontWeight: 700, fontSize: 17, letterSpacing: '0.02em' }}>
            CORAL
          </span>
        </>
      ) as ReactNode,
    },
    links: [
      {
        text: 'Blog',
        url: 'https://human-agent-society.github.io/CORAL/',
      },
    ],
    githubUrl: 'https://github.com/Human-Agent-Society/CORAL',
  };
}
