/** @type {import('next').NextConfig} */
const nextConfig = {
  rewrites: async () => {
    const isProd = process.env.NODE_ENV === 'production';
    const backendUrl = isProd ? 'https://app.viddyscribe.com' : 'http://127.0.0.1:8001';

    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/docs",
        destination: `${backendUrl}/docs`,
      },
      {
        source: "/openapi.json",
        destination: `${backendUrl}/openapi.json`,
      },
    ];
  },
  env: {
    VIDDYSCRIBE_API_KEY: process.env.VIDDYSCRIBE_API_KEY,
  },
};

module.exports = nextConfig;