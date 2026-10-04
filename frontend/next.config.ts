import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Do not advertise the framework version in responses.
  poweredByHeader: false,
  // Compress text responses (HTML/CSS/JS/JSON) at the edge of the server.
  compress: true,
  // The API lives on another origin; keep images/fonts self-hosted by default.
  reactStrictMode: true,
};

export default nextConfig;
