/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Required for the Docker multi-stage build — produces a self-contained
  // server bundle under .next/standalone that node server.js can serve.
  output: 'standalone',
}

module.exports = nextConfig
