/**
 * Card name color by Slay the Spire type (wiki-aligned: Status/Curse = gold).
 * Types come from game / KB as strings (e.g. ATTACK, SKILL, POWER, STATUS, CURSE).
 */
export function cardNameClass(type: unknown): string {
  const t = String(type ?? "").trim().toUpperCase();
  if (t === "ATTACK") return "font-bold text-spire-danger";
  if (t === "SKILL") return "font-bold text-spire-secondary";
  if (t === "POWER") return "font-bold text-spire-success";
  if (t === "STATUS") return "font-bold text-spire-warning";
  if (t === "CURSE") return "font-bold text-spire-warning";
  return "font-bold text-spire-label";
}
