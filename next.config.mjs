/** NIMUS OS web. In development /api goes to the local FastAPI (npm run api); on Vercel, vercel.json sends it to api/index.py. */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return process.env.NODE_ENV === 'development'
      ? [{ source: '/api/:path*', destination: 'http://127.0.0.1:8000/api/:path*' }]
      : [];
  },
};

export default nextConfig;
