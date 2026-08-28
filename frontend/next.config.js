/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // Backend mounts every router under /api (backend/app/main.py); only
    // /health is served bare. The old rule stripped the /api prefix, so any
    // relative fetch through this proxy 404'd. Specific rule first — Next
    // matches in order.
    return [
      {
        source: '/api/health',
        destination: 'http://localhost:8000/health',
      },
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ]
  },
}

module.exports = nextConfig
