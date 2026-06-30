/** @type {import('next').NextConfig} */
const djangoOrigin = (process.env.DJANGO_ORIGIN ?? 'http://localhost:8000').replace(/\/$/, '')

const nextConfig = {
  async rewrites() {
    return [
      {
        // DRF router endpoints under /api/auth/keys/ need trailing slashes
        source: '/api/auth/keys/:path*',
        destination: `${djangoOrigin}/api/auth/keys/:path*/`,
      },
      {
        // other auth URLs have no trailing slash (login, callback, logout, me)
        source: '/api/auth/:path*',
        destination: `${djangoOrigin}/api/auth/:path*`,
      },
      {
        // all other API endpoints use trailing slashes (DRF router, health)
        // Next.js strips trailing slashes before rewrites fire, so we re-add here
        source: '/api/:path*',
        destination: `${djangoOrigin}/api/:path*/`,
      },
      {
        // Django serves local media files at /media/ in development;
        // the download endpoint redirects here, so the browser must reach Django.
        source: '/media/:path*',
        destination: `${djangoOrigin}/media/:path*`,
      },
    ]
  },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'nextjs.org',
        pathname: '/icons/**',
      },
    ],
  },
}

export default nextConfig
