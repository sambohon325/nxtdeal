import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  const base = process.env.DEALEROS_BASE_PATH || "";
  return {
    name: "NXTDeal | Powered by Chrono",
    short_name: "NXTDeal",
    start_url: `${base}/`,
    scope: `${base}/`,
    display: "standalone",
    background_color: "#090909",
    theme_color: "#090909",
    icons: [192, 512].map(size => ({
      src: `${base}/brand/icon-${size}.png`,
      sizes: `${size}x${size}`,
      type: "image/png",
      purpose: "any" as const,
    })),
  };
}
