"""Trophy definitions master.

Centrally manages type / title / tier / category / judgement conditions for each trophy.
"""

from typing import NamedTuple


class TrophyDef(NamedTuple):
    trophy_type: str
    title: str
    tier: str        # bronze / silver / gold / platinum
    category: str    # milestone / streak / diversity / source / hidden
    hidden: bool


# --- File count milestones ---
MILESTONE_DEFS: list[TrophyDef] = [
    TrophyDef("milestone_100",  "100 Files",     "bronze",   "milestone", False),
    TrophyDef("milestone_500",  "500 Files",     "bronze",   "milestone", False),
    TrophyDef("milestone_1k",   "1,000 Files",   "silver",   "milestone", False),
    TrophyDef("milestone_5k",   "5,000 Files",   "silver",   "milestone", False),
    TrophyDef("milestone_10k",  "10,000 Files",  "gold",     "milestone", False),
    TrophyDef("milestone_50k",  "50,000 Files",  "gold",     "milestone", False),
    TrophyDef("milestone_100k", "100,000 Files", "platinum", "milestone", False),
]

# --- Consecutive day streaks ---
STREAK_DEFS: list[TrophyDef] = [
    TrophyDef("streak_7",   "7 Days Streak",   "bronze",   "streak", False),
    TrophyDef("streak_30",  "30 Days Streak",   "silver",   "streak", False),
    TrophyDef("streak_365", "365 Days Streak", "platinum", "streak", False),
]

# --- Tag diversity ---
DIVERSITY_DEFS: list[TrophyDef] = [
    TrophyDef("tags_100",  "100 Unique Tags",   "bronze", "diversity", False),
    TrophyDef("tags_500",  "500 Unique Tags",   "silver", "diversity", False),
    TrophyDef("tags_1000", "1,000 Unique Tags", "gold",   "diversity", False),
]

# --- Sources ---
SOURCE_DEFS: list[TrophyDef] = [
    TrophyDef("source_all", "All Sources Used", "gold", "source", False),
]

# --- Hidden trophies ---
HIDDEN_DEFS: list[TrophyDef] = [
    TrophyDef("night_owl", "Night Owl",  "silver", "hidden", True),
    TrophyDef("centurion", "Centurion",  "gold",   "hidden", True),
]

# Flatten all definitions
ALL_TROPHY_DEFS: list[TrophyDef] = (
    MILESTONE_DEFS + STREAK_DEFS + DIVERSITY_DEFS + SOURCE_DEFS + HIDDEN_DEFS
)

# type -> TrophyDef reverse lookup
TROPHY_MAP: dict[str, TrophyDef] = {d.trophy_type: d for d in ALL_TROPHY_DEFS}
