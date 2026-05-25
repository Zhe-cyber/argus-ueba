/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Required for the Docker multi-stage build — produces a self-contained
  // server bundle under .next/standalone that node server.js can serve.
  output: 'standalone',
  // Don't fail production builds on ESLint warnings/errors
  eslint: { ignoreDuringBuilds: true },
  // Don't fail on TypeScript errors either
  typescript: { ignoreBuildErrors: true },
}

module.exports = nextConfig
