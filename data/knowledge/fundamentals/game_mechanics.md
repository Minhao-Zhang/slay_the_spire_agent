---
tags: [combat, general, reference, defect, watcher]
---

# Game mechanics (retrieved reference)

- **Buff / debuff text**: `PLAYER POWERS` / monster `powers=` include `effect=` from the **reference catalog**; **BUFF GLOSSARY** covers `[Token]` names on relics/potions—canonical per modifier; not repeated here.
- **Turn loop**: Draw to hand (default 5). Spend **Energy** (default 3). Unplayed cards discard at EOT unless **Retain** / **Ethereal**. Empty draw pile → shuffle discard into a new draw pile.
- **Hand cap**: Max **10**; draws past the cap are discarded (no effect).
- **Card roles**: **Attack** / **Skill** / **Power** (played from hand; stays as a combat buff). **Status** clogs the deck this fight; **Curse** persists in the main deck until removed.
- **Card keywords** (printed on cards): **Ethereal** (unplayed at EOT → exhaust), **Exhaust**, **Innate**, **Retain**, **Unplayable**—not the same thing as combat **Power** buffs on the character.
- **Composing attack damage**: **Additive first** (base + **Strength** per hit), **then % modifiers** (**Weak** on you, **Vulnerable** on target). **Floats** internally—don’t floor step-by-step; trust **intent/UI**.
- **Block**: Reduces hit damage before HP. Default: your Block clears at the **start of your turn** unless a power on you says otherwise (see that power’s `effect=` line, e.g. Barricade, Blur).
- **Orbs (Defect)**: When the prompt has **ORBS**, passive and evoke behavior is spelled out there (orb reference bundled with the agent). **Focus** scales Lightning/Frost/Dark; **Plasma** gives Energy and ignores Focus.
- **Watcher tempo**: Stance names (**Calm**, **Wrath**, **Divinity**) and **Mantra** are in the catalog when active—**Wrath** is a damage race; never enter it without a plan to exit, block, or kill.
- After act boss: full heal + boss relic choice.
- **Ascension** / patches change numbers—**in-game intent** is truth.
