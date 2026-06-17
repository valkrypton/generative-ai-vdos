/** @type {import('next').NextConfig} */
const djangoOrigin = (process.env.DJANGO_ORIGIN ?? 'http://localhost:8000').replace(/\/$/, '')

const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${djangoOrigin}/api/:path*`,
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
