/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Don't fail production builds on ESLint warnings/errors
  eslint: { ignoreDuringBuilds: true },
  // Don't fail on TypeScript errors either
  typescript: { ignoreBuildErrors: true },
  // Note: output: 'standalone' is only for Docker/self-hosted builds.
  // Vercel handles Next.js output natively — do not set it here.
}

module.exports = nextConfig
