import { createMDX } from 'fumadocs-mdx/next';

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/blog',
        destination: '/blog/index.html',
      },
    ];
  },
};

const withMDX = createMDX();

export default withMDX(config);
