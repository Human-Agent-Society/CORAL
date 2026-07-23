export interface BlogPost {
  slug: string;
  title: string;
  summary: string;
  date: string;
  category: string;
  href: string;
}

export const blogPosts: readonly BlogPost[] = [
  {
    slug: 'agents-need-institutions',
    title: 'Multi-agent Societies, Institutions, and Incentives',
    summary:
      'Why evolving agent societies need judges, multi-island city-states, provenance-aware archives, and enforced privacy.',
    date: '2026-07-10',
    category: 'Release Notes',
    href: '/blogs/agents-need-institutions/',
  },
  {
    slug: 'evolve-like-coral',
    title: 'Evolve Like Coral: Towards Autonomous Multi-Agent Evolution',
    summary:
      'CORAL experiments on autonomous multi-agent evolution, collaboration, and open-ended discovery.',
    date: '2026-03-18',
    category: 'Research',
    href: '/blogs/evolve-like-coral/',
  },
];
