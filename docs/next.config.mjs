import { createMDX } from 'fumadocs-mdx/next';

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  trailingSlash: true,
  async rewrites() {
    return [
      {
        source: '/blogs/evolve-like-coral',
        destination: '/blogs/evolve-like-coral/index.html',
      },
    ];
  },
};

const withMDX = createMDX();

export default withMDX(config);
