import { mediaImageUrl } from "@/lib/mediaLibrary";
import type { WebsiteStudioRenderedEvent } from "@/lib/websites";
import styles from "./WebsiteStudioEvents.module.css";

/** Same canonical event projection for authenticated preview and public visitors. */
export function WebsiteStudioEvents({ events, websiteId, language = "en", bannerOnly = false }: {
  events: WebsiteStudioRenderedEvent[]; websiteId: string; language?: "en" | "es"; bannerOnly?: boolean;
}) {
  const spanish = language === "es";
  if (!events.length) return null;
  if (bannerOnly) {
    const event = events[0];
    return <a className={styles.banner} href={`#event-${event.id}`} style={{ backgroundImage: `linear-gradient(90deg,#000b,#0004),url("${mediaImageUrl(event.banner_url)}")` }}>
      <strong>{spanish ? event.title_es : event.title}</strong>
      <span>{spanish ? event.summary_es : event.summary}</span>
      {(event.starts_on || event.ends_on) && <small>{[event.starts_on, event.ends_on].filter(Boolean).join(" — ")}</small>}
    </a>;
  }
  return <div className={styles.events}>{events.map(event => <section id={`event-${event.id}`} className={styles.event} key={event.id} style={{ background: event.background }}>
    <div className={styles.story}><div><span>{spanish ? "EN EL CONCESIONARIO" : "AT THE DEALERSHIP"}</span><h2>{spanish ? event.title_es : event.title}</h2><p>{spanish ? event.summary_es : event.summary}</p><small>{[event.starts_on, event.ends_on].filter(Boolean).join(" — ")}</small></div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={mediaImageUrl(event.image_url)} alt={spanish ? event.image_alt_es : event.image_alt} loading="lazy" /></div>
    {!!event.vehicles.length && <div className={styles.inventory}>{event.vehicles.map(vehicle => <a key={vehicle.id} className={styles.vehicle} href={`/site/${encodeURIComponent(websiteId)}/vehicle/${encodeURIComponent(vehicle.id)}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {vehicle.image_url ? <img src={vehicle.image_url} alt={[vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(" ")} loading="lazy" /> : <div className={styles.placeholder}>{spanish ? "Foto próximamente" : "Photo coming soon"}</div>}
      <div><strong>{[vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(" ")}</strong><span>{vehicle.location_name}</span><span>{spanish ? "Más información" : "More information"} ↗</span></div>
    </a>)}</div>}
    <p className={styles.terms}>{spanish ? event.terms_es : event.terms}</p>
  </section>)}</div>;
}
