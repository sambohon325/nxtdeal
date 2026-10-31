// Inventory department's "Merchandising" item -- digital inventory
// presentation (Inventory rebuild, sixth slice). Backend:
// core/merchandising.py / _api.py. A deliberate mix: photo upload,
// description, and featured flag are REAL (internal capabilities nobody
// had built); VDP Health Score and Feed Sync Status are SIMULATED (a
// genuine external gap -- no real VDP-analytics platform or third-party
// listing feed is connected anywhere in this system), clearly labeled via
// basis/disclaimer fields.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type FeedStatusValue = "synced" | "pending" | "error";

export type MerchandisingCatalog = { feed_platforms: string[] };

export type VehicleImage = { id: string; url: string; caption: string };

export type VehicleBrief = {
  vehicle_id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | null;
  make: string | null;
  model: string | null;
  price: number | null;
};

export type VdpHealth = {
  vehicle_id: string;
  has_photos: boolean;
  has_description: boolean;
  is_featured: boolean;
  simulated_page_views: number;
  simulated_lead_conversion_rate: number;
  health_score: number;
  health_score_max: number;
  basis: string;
  disclaimer: string;
};

export type FeedStatusEntry = { platform: string; status: FeedStatusValue };

export type FeedStatus = {
  vehicle_id: string;
  feeds: FeedStatusEntry[];
  basis: string;
  disclaimer: string;
};

export type FeedPublishEntry = { platform: string; published_by: string; published_at: string; simulated: boolean };

export type MerchandisingView = {
  vehicle: VehicleBrief;
  images: VehicleImage[];
  description: string;
  featured: boolean;
  vdp_health: VdpHealth;
  feed_status: FeedStatus;
  feed_publish_log: FeedPublishEntry[];
};

export type MerchandisingQueueEntry = VehicleBrief & { vdp_health: VdpHealth };

export type MerchandisingQueue = { total: number; offset: number; count: number; vehicles: MerchandisingQueueEntry[] };

export type FeaturedVehicles = { count: number; vehicles: VehicleBrief[] };

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

export function getMerchandisingCatalog(): Promise<MerchandisingCatalog> {
  return get("/merchandising/catalog");
}

export function getMerchandisingQueue(limit = 25, offset = 0): Promise<MerchandisingQueue> {
  return get(`/merchandising/queue?limit=${limit}&offset=${offset}`);
}

export function getFeaturedVehicles(): Promise<FeaturedVehicles> {
  return get("/merchandising/featured");
}

export function getMerchandisingView(vehicleId: string): Promise<MerchandisingView> {
  return get(`/merchandising/${encodeURIComponent(vehicleId)}`);
}

export function addVehicleImage(vehicleId: string, imageUrl: string, caption = ""): Promise<{ vehicle_id: string; image: VehicleImage }> {
  return post(`/merchandising/${encodeURIComponent(vehicleId)}/images`, { image_url: imageUrl, caption });
}

export function updateDescription(vehicleId: string, description: string): Promise<{ vehicle_id: string; description: string }> {
  return post(`/merchandising/${encodeURIComponent(vehicleId)}/description`, { description });
}

export function setFeatured(vehicleId: string, featured: boolean): Promise<{ vehicle_id: string; featured: boolean }> {
  return post(`/merchandising/${encodeURIComponent(vehicleId)}/featured`, { featured });
}

export function publishToFeed(vehicleId: string, platform: string): Promise<{ vehicle_id: string; entry: FeedPublishEntry; basis: string; disclaimer: string }> {
  return post(`/merchandising/${encodeURIComponent(vehicleId)}/feed-status/publish`, { platform });
}
