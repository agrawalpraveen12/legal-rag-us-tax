import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a fully static site into ui/out so FastAPI can serve it on one port.
  // Required for single-container deployment (HuggingFace Spaces / any host).
  output: "export",

  // next/image optimization needs a server; static export has none.
  images: { unoptimized: true },

  // Emit /path/index.html so static hosts resolve routes without a server.
  trailingSlash: true,
};

export default nextConfig;
