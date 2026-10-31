"use client";

// Shared entity-360-profile rendering, used by both app/profile/[id]/page.tsx (the
// standalone permalink page) and app/workspace/page.tsx (inline in the chat-triggered
// workspace panel — see BUILD_QUEUE.md session 21: profile lookup moved from a manual
// "type an ID" box to being purely chat-triggered, same mechanic as dashboard
// suggestions). Pulled out here so both call sites render identically instead of
// duplicating the section/card layout.
//
// `onSelect` decides what happens when someone clicks a connected entity's card to drill
// in — the standalone page navigates to that entity's own /profile/[id]; the workspace
// panel re-fetches and re-renders in place instead, so drilling through a chain of
// related entities never leaves the workspace.
//
// Session 76 fourth follow-up: every branch below now also mounts
// components/ConnectionsExplorer.tsx at the bottom -- the hand-picked Sections above it
// (Vehicles/Finance Contracts/etc) are specific one-hop relationships each entity type's
// core/queries.py get_*_360() function already knew to fetch; the explorer is the
// generic, multi-hop "whatever's really connected to this, including chat mentions and
// Knowledge pins" view that works the same way for every entity type, not just the
// three with a dedicated profile shape.

import { useState } from "react";
import { ConnectionsExplorer } from "@/components/ConnectionsExplorer";
import { InlineEntityFields } from "@/components/InlineEntityFields";

export type EntitySummary = {
  id: string;
  entity_type: string;
  attributes: Record<string, unknown>;
};

export type CustomerProfile = {
  entity_type: "Customer";
  customer: EntitySummary | null;
  finances: EntitySummary[];
  vehicles: EntitySummary[];
  service_records: EntitySummary[];
  lead_sources: EntitySummary[];
  documents: EntitySummary[];
};

export type EmployeeProfile = {
  entity_type: "Employee";
  employee: EntitySummary | null;
  customers: EntitySummary[];
  leads: EntitySummary[];
};

export type VehicleProfile = {
  entity_type: "Vehicle";
  vehicle: EntitySummary | null;
  owners: EntitySummary[];
  finance_contracts: EntitySummary[];
  service_records: EntitySummary[];
  documents: EntitySummary[];
  images: EntitySummary[];
};

export type FallbackProfile = {
  entity_type: string;
  entity: EntitySummary | null;
  relationships: {
    direction: "IN" | "OUT";
    relationship: string;
    entity: EntitySummary;
  }[];
};

export type Profile =
  | CustomerProfile
  | EmployeeProfile
  | VehicleProfile
  | FallbackProfile;

export function displayName(entity: EntitySummary | null): string {
  if (!entity) return "(not visible to your role)";

  const attrs = entity.attributes ?? {};

  const candidate =
    (attrs["Name"] as string) ??
    (attrs["FirstName"] && attrs["LastName"]
      ? `${attrs["FirstName"]} ${attrs["LastName"]}`
      : undefined) ??
    (attrs["Make"] && attrs["Model"]
      ? `${attrs["Make"]} ${attrs["Model"]}`
      : undefined) ??
    (attrs["VIN"] as string);

  return candidate ? `${candidate} — ${entity.id}` : entity.id;
}

function EntityCard({
  entity,
  onSelect,
}: {
  entity: EntitySummary;
  onSelect: (entityId: string) => void;
}) {
  const attrs = Object.entries(entity.attributes ?? {}).slice(0, 4);

  return (
    <button
      onClick={() => onSelect(entity.id)}
      className="w-full text-left bg-zinc-900 border border-zinc-800 rounded-lg p-3 hover:border-[#3FBCC4] transition"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium">{displayName(entity)}</span>
        <span className="text-xs uppercase tracking-wider text-zinc-500">
          {entity.entity_type}
        </span>
      </div>
      {attrs.length > 0 && (
        <div className="text-xs text-zinc-500 space-y-0.5">
          {attrs.map(([key, value]) => (
            <div key={key}>
              {key}: {String(value)}
            </div>
          ))}
        </div>
      )}
    </button>
  );
}

function Section({
  title,
  entities,
  onSelect,
}: {
  title: string;
  entities: EntitySummary[];
  onSelect: (entityId: string) => void;
}) {
  return (
    <div className="mb-6">
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
        {title} ({entities.length})
      </div>

      {entities.length === 0 ? (
        <div className="text-sm text-zinc-600">
          None visible to your role, or none on record.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {entities.map((entity) => (
            <EntityCard key={entity.id} entity={entity} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}

export function EntityProfileView({
  profile,
  onSelect,
}: {
  profile: Profile;
  onSelect: (entityId: string) => void;
}) {
  // `profile` is a plain prop, not owned state -- this component has no server-refetch
  // mechanism of its own the way Customer360Panel/LeadRecordModal do (both call their
  // own dedicated GET endpoint and can re-fetch on demand). Editing a Vehicle's own
  // identity fields below merges the saved patch into this small local-only override
  // dict instead, so the header/identity card reflect the edit immediately without
  // requiring the parent page to plumb a refetch trigger through every one of its own
  // call sites (app/profile/[id]/page.tsx, app/panel/entity/page.tsx, and the inline
  // workspace panel). A real page reload still picks up the true persisted value from
  // the backend, same as any other client-side optimistic-merge pattern in this app.
  const [vehicleOverrides, setVehicleOverrides] = useState<Record<string, unknown>>({});

  // Explicit casts (session 87) rather than relying on entity_type-based narrowing --
  // FallbackProfile's `entity_type` is typed as plain `string` (not a literal, since it
  // covers whatever unrecognized entity types the backend might send), so TypeScript
  // can't prove it's excluded by a `=== "Customer"` check the way it could with a fully
  // literal discriminated union. This was a real, previously-uncaught type error --
  // found the moment this codebase went through its first real `next build` (Coolify),
  // see app/panel/entity/page.tsx's identical fix for the fuller story.
  if (profile.entity_type === "Customer") {
    const p = profile as CustomerProfile;
    return (
      <>
        <h2 className="text-2xl font-semibold mb-1">
          {displayName(p.customer)}
        </h2>
        <div className="text-xs uppercase tracking-wider text-zinc-500 mb-6">
          Customer Profile
        </div>
        <Section title="Vehicles" entities={p.vehicles} onSelect={onSelect} />
        <Section title="Finance Contracts" entities={p.finances} onSelect={onSelect} />
        <Section title="Service Records" entities={p.service_records} onSelect={onSelect} />
        <Section title="Lead Sources" entities={p.lead_sources} onSelect={onSelect} />
        <Section title="Documents" entities={p.documents} onSelect={onSelect} />
        <ConnectionsExplorer entityId={p.customer?.id} onSelect={onSelect} />
      </>
    );
  }

  if (profile.entity_type === "Employee") {
    const p = profile as EmployeeProfile;
    return (
      <>
        <h2 className="text-2xl font-semibold mb-1">
          {displayName(p.employee)}
        </h2>
        <div className="text-xs uppercase tracking-wider text-zinc-500 mb-6">
          Employee Profile
        </div>
        <Section title="Assigned Customers" entities={p.customers} onSelect={onSelect} />
        <Section title="Assigned Leads" entities={p.leads} onSelect={onSelect} />
        <ConnectionsExplorer entityId={p.employee?.id} onSelect={onSelect} />
      </>
    );
  }

  if (profile.entity_type === "Vehicle") {
    const p = profile as VehicleProfile;
    const vAttrs = { ...(p.vehicle?.attributes ?? {}), ...vehicleOverrides };
    const vShim = p.vehicle ? { ...p.vehicle, attributes: vAttrs } : null;
    return (
      <>
        <div className="flex items-start justify-between gap-3 mb-1">
          <h2 className="text-2xl font-semibold">
            {displayName(vShim)}
          </h2>
          {p.vehicle && (
            <InlineEntityFields
              theme="dark"
              entityId={p.vehicle.id}
              fields={[
                { key: "Year", label: "Year", value: vAttrs.Year, type: "number" },
                { key: "Make", label: "Make", value: vAttrs.Make },
                { key: "Model", label: "Model", value: vAttrs.Model },
                { key: "Trim", label: "Trim", value: vAttrs.Trim },
                { key: "Color", label: "Color", value: vAttrs.Color },
                { key: "Mileage", label: "Mileage", value: vAttrs.Mileage, type: "number" },
              ]}
              onSaved={(patch) => setVehicleOverrides((prev) => ({ ...prev, ...patch }))}
            />
          )}
        </div>
        <div className="text-xs uppercase tracking-wider text-zinc-500 mb-6">
          Vehicle Profile — VIN {String(vAttrs.VIN ?? "—")} · Stock {String(vAttrs.StockNumber ?? "—")}
        </div>
        <Section title="Owners" entities={p.owners} onSelect={onSelect} />
        <Section title="Finance Contracts" entities={p.finance_contracts} onSelect={onSelect} />
        <Section title="Service Records" entities={p.service_records} onSelect={onSelect} />
        <Section title="Documents" entities={p.documents} onSelect={onSelect} />
        <Section title="Images" entities={p.images} onSelect={onSelect} />
        <ConnectionsExplorer entityId={p.vehicle?.id} onSelect={onSelect} />
      </>
    );
  }

  const fallback = profile as FallbackProfile;

  return (
    <>
      <h2 className="text-2xl font-semibold mb-1">{displayName(fallback.entity)}</h2>
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-6">
        {profile.entity_type} Profile
      </div>
      <Section
        title="Connected Entities"
        entities={fallback.relationships.map((r) => r.entity)}
        onSelect={onSelect}
      />
      <ConnectionsExplorer entityId={fallback.entity?.id} onSelect={onSelect} />
    </>
  );
}
