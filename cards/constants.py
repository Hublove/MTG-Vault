"""Shared constants for card classification.

The decklist view and the Card model both need a single, consistent notion of a
card's "primary type" so multi-type cards (e.g. "Legendary Artifact Creature")
land in exactly one bucket. The order below is both the bucket-priority order
(first match wins) AND the display order in the grouped decklist.
"""
import random

# Display/priority order for type groups. A multi-type card is bucketed by the
# FIRST entry whose keyword appears in its type line — so an "Artifact Creature"
# is a Creature, and a "Land" is always last among its competitors.
TYPE_GROUP_ORDER = [
    ("Creature", "Creatures"),
    ("Planeswalker", "Planeswalkers"),
    ("Instant", "Instants"),
    ("Sorcery", "Sorceries"),
    ("Artifact", "Artifacts"),
    ("Enchantment", "Enchantments"),
    ("Battle", "Battles"),
    ("Land", "Lands"),
]

# Fallback bucket for anything unmatched (tokens, dungeons, schemes, etc.).
OTHER_GROUP = "Other"

# Just the singular keywords, in priority order, for parsing type lines.
TYPE_PRIORITY = [keyword for keyword, _label in TYPE_GROUP_ORDER]

# Map singular keyword -> plural display label.
TYPE_LABELS = dict(TYPE_GROUP_ORDER)


def primary_type_for(type_line: str) -> str:
    """Return the singular primary-type keyword for a Scryfall type line.

    Picks the highest-priority type present so multi-type cards bucket
    deterministically. Returns ``OTHER_GROUP`` when nothing matches.
    """
    if not type_line:
        return OTHER_GROUP
    # Scryfall double-faced type lines look like "Front // Back"; classify on
    # the front face, which is what determines a card's deck role.
    front = type_line.split("//")[0]
    for keyword in TYPE_PRIORITY:
        if keyword in front:
            return keyword
    return OTHER_GROUP


# Color identity codes in canonical WUBRG order, for display/sorting.
COLOR_ORDER = ["W", "U", "B", "R", "G"]
COLOR_NAMES = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
}

# --- Tag colors -----------------------------------------------------------
#
# A 64-color (8×8) palette for tag chips: 16 vibrant Tailwind hues × shades
# 400/500/600/700, stored as hex on Tag.color. Hex (not Tailwind family names)
# lets us offer a full 64-swatch picker; chips render these via inline styles.
TAG_PALETTE = [
    # red,      orange,    amber,     yellow,    lime,      green,     emerald,   teal
    "#f87171", "#fb923c", "#fbbf24", "#facc15", "#a3e635", "#4ade80", "#34d399", "#2dd4bf",
    "#ef4444", "#f97316", "#f59e0b", "#eab308", "#84cc16", "#22c55e", "#10b981", "#14b8a6",
    "#dc2626", "#ea580c", "#d97706", "#ca8a04", "#65a30d", "#16a34a", "#059669", "#0d9488",
    "#b91c1c", "#c2410c", "#b45309", "#a16207", "#4d7c0f", "#15803d", "#047857", "#0f766e",
    # cyan,     sky,       blue,      indigo,    violet,    purple,    fuchsia,   pink
    "#22d3ee", "#38bdf8", "#60a5fa", "#818cf8", "#a78bfa", "#c084fc", "#e879f9", "#f472b6",
    "#06b6d4", "#0ea5e9", "#3b82f6", "#6366f1", "#8b5cf6", "#a855f7", "#d946ef", "#ec4899",
    "#0891b2", "#0284c7", "#2563eb", "#4f46e5", "#7c3aed", "#9333ea", "#c026d3", "#db2777",
    "#0e7490", "#0369a1", "#1d4ed8", "#4338ca", "#6d28d9", "#7e22ce", "#a21caf", "#be185d",
]


def random_tag_color():
    """A random hex color from the tag palette (for new/backfilled tags)."""
    return random.choice(TAG_PALETTE)

# Tailwind classes for each WUBRG color toggle. Each value carries an UNSELECTED
# tint (colored letter + subtle colored border, so the buttons are distinguishable
# at a glance) plus the CHECKED fill in that mana color. Black uses a light-grey
# letter when idle (black-on-dark would be invisible) and a true near-black fill
# when selected. Literal strings so the Tailwind Play CDN picks them up from the DOM.
COLOR_SWATCH = {
    "W": "text-amber-200 border-amber-700/60 "
         "has-[:checked]:bg-amber-100 has-[:checked]:text-slate-900 has-[:checked]:border-amber-200",
    "U": "text-sky-300 border-sky-800/60 "
         "has-[:checked]:bg-blue-500 has-[:checked]:text-white has-[:checked]:border-blue-300",
    "B": "text-zinc-300 border-zinc-600/60 "
         "has-[:checked]:bg-neutral-900 has-[:checked]:text-white has-[:checked]:border-neutral-500",
    "R": "text-red-300 border-red-800/60 "
         "has-[:checked]:bg-red-600 has-[:checked]:text-white has-[:checked]:border-red-300",
    "G": "text-green-300 border-green-800/60 "
         "has-[:checked]:bg-green-600 has-[:checked]:text-white has-[:checked]:border-green-300",
}
