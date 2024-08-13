/** @type {import('next').NextConfig} */
const nextConfig = {
  rewrites: async () => {
    const backendUrl =  'http://127.0.0.1:8000';

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