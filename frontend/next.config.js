/** @type {import('next').NextConfig} */
const nextConfig = {
  // API proxy is handled by server.js (http-proxy-middleware) to avoid
  // the Next.js rewrites() `duplex` error on POST bodies.
}

module.exports = nextConfig