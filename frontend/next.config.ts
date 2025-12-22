import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Disable image optimization for self-hosted deployments
    // This allows images from any hostname (localhost, IP, custom domain)
    unoptimized: true,
    dangerouslyAllowSVG: true,
  },
  // Proxy API requests to backend to avoid CORS issues
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
