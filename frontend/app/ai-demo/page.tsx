import { redirect } from "next/navigation";

// Retain old links while retiring the canned dedicated-assistant preview.
// The platform overview retains external-agent integration information.
export default function LegacyAiDemoPage() {
  redirect("/solutions");
}
