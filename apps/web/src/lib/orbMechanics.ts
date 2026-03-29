import orbMechanicsJson from "../../../../data/processed/orb_mechanics.json";

export type OrbTypeMeta = {
  short?: string;
  passive_detail?: string;
  evoke_detail?: string;
};

export type OrbMechanicsDoc = {
  schema_version?: number;
  global?: { bullets?: string[] };
  types?: Record<string, OrbTypeMeta>;
  ui?: {
    strip_label?: string;
    strip_help_title?: string;
    empty_chip?: string;
  };
};

export const orbMechanics = orbMechanicsJson as OrbMechanicsDoc;

export function orbTypeMeta(orb: Record<string, unknown>): OrbTypeMeta {
  const types = orbMechanics.types ?? {};
  const id = String(orb.id ?? "").trim();
  const name = String(orb.name ?? "").trim();
  if (id) {
    const byId = types[id];
    if (byId) return byId;
  }
  if (name) {
    const byName = types[name];
    if (byName) return byName;
  }
  return types._default ?? {};
}

export function formatOrbChipTooltip(orb: Record<string, unknown>): string {
  const name = String(orb.name ?? "").trim();
  const pa = orb.passive_amount;
  const ea = orb.evoke_amount;
  const m = orbTypeMeta(orb);
  const head =
    name === "Orb Slot"
      ? (orbMechanics.ui?.empty_chip ?? "Empty slot")
      : name || "?";
  const lines = [
    head,
    `passive_amount=${String(pa)} evoke_amount=${String(ea)}`,
  ];
  if (m.passive_detail) lines.push(m.passive_detail);
  if (m.evoke_detail) lines.push(m.evoke_detail);
  return lines.join("\n\n");
}

export function orbStripHelpText(): string {
  const title = orbMechanics.ui?.strip_help_title ?? "Orb mechanics";
  const bullets = orbMechanics.global?.bullets ?? [];
  return [title, ...bullets.map((b) => `• ${b}`)].join("\n\n");
}
