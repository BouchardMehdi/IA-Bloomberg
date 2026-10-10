import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/api/v1/:path*` }];
  },
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
