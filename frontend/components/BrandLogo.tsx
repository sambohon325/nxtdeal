import Image from "next/image";
import logo from "@/public/brand/nxtdeal-logo-transparent.png";

/** Transparent official artwork, framed to remove its unused outer margin. */
export function BrandLogo({ large = false }: { large?: boolean }) {
  return (
    <span className={large ? "nxt-entry-logo relative block shrink-0 overflow-hidden" : "relative block h-14 w-60 shrink-0 overflow-hidden"}>
      <Image src={logo} alt="NXTDeal | Powered by Chrono" priority sizes={large ? "(max-width: 760px) 300px, 520px" : "240px"}
        className="absolute left-0 top-1/2 h-auto w-full -translate-y-1/2" />
    </span>
  );
}
