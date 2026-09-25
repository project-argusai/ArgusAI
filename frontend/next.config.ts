import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker deployment (Story P10-2.2)
  // Creates a minimal production bundle that includes only necessary files
  output: 'standalone',
  images: {
    // Disable image optimization for self-hosted deployments
    // This allows images from any hostname (localhost, IP, custom domain)
    unoptimized: true,
    dangerouslyAllowSVG: true,
  },
  // Proxy API requests to the backend so the browser stays on the frontend origin.
  // HTTP requests, including those handled by server.js (HTTPS), are passed to
  // Next's request handler, which applies this rewrite. server.js only
  // intercepts WebSocket upgrades. Leave NEXT_PUBLIC_API_URL empty so the
  // browser uses these same-origin URLs (required for SameSite=lax cookies).
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
