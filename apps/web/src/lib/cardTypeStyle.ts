/**
 * Card name color by Slay the Spire type (wiki-aligned: Status/Curse = gold).
 * Types come from game / KB as strings (e.g. ATTACK, SKILL, POWER, STATUS, CURSE).
 */
export function cardNameClass(type: unknown): string {
  const t = String(type ?? "").trim().toUpperCase();
  if (t === "ATTACK") return "font-bold text-red-400";
  if (t === "SKILL") return "font-bold text-blue-400";
  if (t === "POWER") return "font-bold text-purple-400";
  if (t === "STATUS") return "font-bold text-amber-300";
  if (t === "CURSE") return "font-bold text-amber-400";
  return "font-bold text-slate-300";
}
