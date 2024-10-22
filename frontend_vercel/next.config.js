/** @type {import('next').NextConfig} */
const nextConfig = {
    // rewrites: async () => {
    //   const backendUrl = process.env.NODE_ENV === 'development'
    //     ? 'https://dezcribe-gcp-cloud-781700989023.us-central1.run.app'
    //     : 'https://dezcribe-gcp-cloud-781700989023.us-central1.run.app';
  
    //   return [
    //     {
    //       source: "/:path*",
    //       destination: `${backendUrl}/:path*`,
    //     },
    //     {
    //       source: "/docs",
    //       destination: `${backendUrl}/docs`,
    //     },
    //     {
    //       source: "/openapi.json",
    //       destination: `${backendUrl}/openapi.json`,
    //     },
    //   ];
    // },
    env: {
      VIDDYSCRIBE_API_KEY: process.env.VIDDYSCRIBE_API_KEY,
    },
  };
  
  module.exports = nextConfig;