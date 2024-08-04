/** @type {import('next').NextConfig} */
const nextConfig = {
  rewrites: async () => {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8001/api/:path*",
      },
      {
        source: "/docs",
        destination: "http://127.0.0.1:8001/docs",
      },
      {
        source: "/openapi.json",
        destination: "http://127.0.0.1:8001/openapi.json",
      },
    ];
  },
  env: {
    VIDDYSCRIBE_API_KEY: process.env.VIDDYSCRIBE_API_KEY,
  },
};

module.exports = nextConfig;