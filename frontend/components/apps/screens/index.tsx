"use client";

// Wired-screen registry (2026-07-24).
//
// Maps "<appSlug>:<screenKey>" → a live React screen. The dynamic route (app/apps/[slug]) looks
// up the active app+tab here: a hit renders the wired screen (live NXTDeal data), a miss renders
// the static AppScreenView shell. This keeps the suite data-driven while deep-wiring proceeds one
// screen at a time — adding a wired screen is a single entry here plus its component.

import { type ComponentType } from "react";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { KioskCheckin } from "./KioskCheckin";
import { KioskLobby } from "./KioskLobby";
import { SalesToday } from "./SalesToday";
import { SalesCustomers } from "./SalesCustomers";
import { InventoryScreen } from "./InventoryScreen";
import { ReceptionAppointments } from "./ReceptionAppointments";
import { ReceptionDirectory } from "./ReceptionDirectory";
import { ServiceRoBoard } from "./ServiceRoBoard";
import { ServiceManager } from "./ServiceManager";
import { ServiceTechs } from "./ServiceTechs";
import { ShowroomDeal } from "./ShowroomDeal";
import { CustomerUnavailable } from "./CustomerUnavailable";
import { SalesUps } from "./SalesUps";
import { Messages } from "./Messages";
import { SalesCoach } from "./SalesCoach";
import { SalesRewards } from "./SalesRewards";
import { SalesMoney } from "./SalesMoney";
import { ReceptionCheckin } from "./ReceptionCheckin";
import { ReceptionAway } from "./ReceptionAway";
import { ReceptionDesk } from "./ReceptionDesk";
import { ReceptionTeamChat } from "./ReceptionTeamChat";
import { DeskScreen } from "./DeskScreen";
import { InspectionsScreen } from "./InspectionsScreen";
import { MyGarageOffers } from "./MyGarageOffers";
import { MyGarageVehicles } from "./MyGarageVehicles";
import { MyGarageRewards } from "./MyGarageRewards";
import { MySalesAiConfig } from "./MySalesAiConfig";
import { AiConfig } from "./AiConfig";
import { MyGarageApprovals } from "./MyGarageApprovals";
import { MyGarageStatus } from "./MyGarageStatus";
import { CustomerMessages } from "./CustomerMessages";
import { VehicleShowroom } from "./VehicleShowroom";
import { SalesBrand } from "./SalesBrand";
import { DashboardScreen } from "./DashboardScreen";
import { ItemsScreen } from "./ItemsScreen";

export type WiredScreenComponent = ComponentType<{ app: AppDef; screen: AppScreen }>;

const WIRED: Record<string, WiredScreenComponent> = {
  "kiosk:checkin": KioskCheckin,
  "kiosk:queue": KioskCheckin,
  "kiosk:amenities": KioskLobby,
  // Sales Pro
  "mysales:today": SalesToday,
  "mysales:brand": SalesBrand,
  "mysales:customers": SalesCustomers,
  "mysales:inventory": InventoryScreen,
  "mysales:coach": SalesCoach,
  "mysales:aiconfig": MySalesAiConfig,
  // Generalized AI model selector for all companion apps (2026-10-24)
  "salesapp:aiconfig": AiConfig,
  "reception:aiconfig": AiConfig,
  "serviceops:aiconfig": AiConfig,
  "showroom:aiconfig": AiConfig,
  "mygarage:aiconfig": AiConfig,
  "kiosk:aiconfig": AiConfig,
  "mysales:rewards": SalesRewards,
  "mysales:money": SalesMoney,
  // Sales (dealer)
  "salesapp:pipeline": SalesToday,
  "salesapp:ups": SalesUps,
  "salesapp:inventory": InventoryScreen,
  "salesapp:desking": DeskScreen,
  "salesapp:messages": Messages,
  // Receptionist
  "reception:checkin": ReceptionCheckin,
  "reception:desk": ReceptionDesk,
  "reception:team": ReceptionTeamChat,
  "reception:appointments": ReceptionAppointments,
  "reception:directory": ReceptionDirectory,
  "reception:away": ReceptionAway,
  // Service Operations
  "serviceops:roboard": ServiceRoBoard,
  "serviceops:inspections": InspectionsScreen,
  "serviceops:techs": ServiceTechs,
  "serviceops:manager": ServiceManager,
  // Customer Showroom (in-dealership kiosk)
  "showroom:browse": VehicleShowroom,
  "showroom:saved": CustomerUnavailable,
  "showroom:mydeal": ShowroomDeal,
  // My Garage (downloadable customer app) — shares the showroom browse
  "mygarage:showroom": VehicleShowroom,
  // Phase 7 + 4: PII/data screens behind identity verification, now with real data.
  "mygarage:vehicles": MyGarageVehicles,
  "mygarage:offers": MyGarageOffers,
  "mygarage:book": CustomerUnavailable,
  "mygarage:alerts": CustomerUnavailable,
  "mygarage:rewards": MyGarageRewards,
  "mygarage:messages": CustomerMessages,
  "showroom:messages": CustomerMessages,
  // Phase 4/7 (final two): live estimate approvals/pay + service status, real data.
  "mygarage:approvals": MyGarageApprovals,
  "mygarage:status": MyGarageStatus,
  // DevHub: internal development work-tracking app (staff-only, not in public launcher).
  "devhub:dashboard": DashboardScreen,
  "devhub:items": ItemsScreen,
  "devhub:aiconfig": AiConfig,
};

export function wiredScreen(slug: string, screenKey: string): WiredScreenComponent | undefined {
  return WIRED[`${slug}:${screenKey}`];
}
