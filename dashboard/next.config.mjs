/** @type {import('next').NextConfig} */
// Production builds are a static export (dashboard/out) that the FastAPI
// app serves at "/", so the whole system runs from one `uvicorn` command.
// In development the API runs separately on :8000 (see lib/api.ts).
const nextConfig = {
  output: process.env.NODE_ENV === "production" ? "export" : undefined,
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};
export default nextConfig;
