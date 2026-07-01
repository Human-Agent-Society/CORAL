"""Human-friendly agent nicknames.

Agents used to be named ``agent-1``, ``agent-2``, ... which reads like a
serial number. Instead we draw from an ocean-themed pool — sea captains,
explorers, deep-sea deities — so a run looks like a crew sailing the same
waters the framework is named for, rather than a rack of machines.

The pool is *combinable* so it never runs dry. The first ``len(CURATED)``
agents get iconic named characters (``captain-nemo``, ``poseidon``, ...);
beyond that, names are composed as ``<ocean-adjective>-<sea-creature>``
(``azure-marlin``, ``briny-kraken``, ...). That yields
``len(ADJECTIVES) * len(NOUNS)`` further unique names on top of the curated
set — hundreds of agents before the ultimate Roman-numeral lap suffix
(``-ii``, ``-iii``, ...) ever appears.

Multi-island runs name each island too (``atlantis``, ``avalon``, ...) and
render an agent as ``<nickname>-from-<island>`` — e.g. ``poseidon-from-avalon``
— so an id carries its birth island as readable provenance. Single-island runs
keep the bare nickname.

Every name is kebab-case ``[a-z-]`` — the same shape the rest of the system
already expects of ``agent_id`` (git branch ``coral/<id>``, worktree dir
``agents/<id>/``, attempt JSON keyed by id) and of ``island_id`` (shared-state
dir ``.coral/islands/<id>/``). Curated names and generated ``adjective-noun``
combos are disjoint by construction, so the two sources never collide.

Assignment is deterministic by index — the Nth agent always gets the Nth
name, the Nth island the Nth place — so a resumed run reconstructs the same
identities.
"""

from __future__ import annotations

# Iconic named characters, used first. Kebab-safe, no leading digits, unique.
# Order matters: it is the deterministic assignment order, so keep the marquee
# names up front.
CURATED: tuple[str, ...] = (
    # Captains & sailors of story
    "captain-nemo",
    "captain-ahab",
    "jack-sparrow",
    "davy-jones",
    "long-john-silver",
    "sinbad-the-sailor",
    "horatio-hornblower",
    "jack-aubrey",
    "captain-flint",
    "blackbeard",
    "ishmael",
    "queequeg",
    "santiago",
    "quint",
    # Real explorers & ocean pioneers
    "jacques-cousteau",
    "captain-cook",
    "ferdinand-magellan",
    "ernest-shackleton",
    "vasco-da-gama",
    "francis-drake",
    "zheng-he",
    "leif-erikson",
    "sylvia-earle",
    "robert-ballard",
    # Sea gods & myth, across cultures
    "poseidon",
    "neptune",
    "triton",
    "amphitrite",
    "oceanus",
    "nereus",
    "proteus",
    "glaucus",
    "calypso",
    "mazu",
    "tangaroa",
    "ryujin",
    "aegir",
    "njord",
    "ran",
    "sedna",
    "yemaya",
    "varuna",
    # Monsters & legends of the deep
    "the-kraken",
    "leviathan",
    "charybdis",
    "scylla",
    "moby-dick",
    "the-siren",
    "flying-dutchman",
    # Famous ships
    "nautilus",
    "black-pearl",
    "hms-beagle",
    "argo",
    # A little Finding Nemo
    "nemo",
    "dory",
    "bruce-the-shark",
)

# Building blocks for the combinable tail: ``<adjective>-<noun>``. Keep these
# single-word and disjoint from CURATED so no combo can reproduce a curated id.
ADJECTIVES: tuple[str, ...] = (
    "azure",
    "briny",
    "coral",
    "tidal",
    "abyssal",
    "cerulean",
    "saline",
    "drifting",
    "cresting",
    "foaming",
    "glassy",
    "stormy",
    "frothy",
    "pearly",
    "silver",
    "teal",
    "sunken",
    "roaring",
    "shimmering",
    "restless",
    "moonlit",
    "jade",
    "misty",
    "frosty",
)

NOUNS: tuple[str, ...] = (
    "marlin",
    "narwhal",
    "orca",
    "manta",
    "barnacle",
    "anemone",
    "seahorse",
    "urchin",
    "mackerel",
    "sardine",
    "grouper",
    "stingray",
    "jellyfish",
    "cuttlefish",
    "octopus",
    "dolphin",
    "walrus",
    "albatross",
    "pelican",
    "mariner",
    "corsair",
    "tempest",
    "current",
    "riptide",
)

_COMBO_SPAN = len(ADJECTIVES) * len(NOUNS)

# Greedy value→symbol table for lowercase Roman numerals. ``m`` repeats for
# thousands, so this handles arbitrarily large numbers (4000 -> "mmmm"), just
# growing longer — never overflowing.
_ROMAN: tuple[tuple[int, str], ...] = (
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)


def _roman(n: int) -> str:
    """Lowercase Roman numeral for ``n >= 1`` (e.g. 2 -> ``ii``, 14 -> ``xiv``)."""
    out: list[str] = []
    for value, symbol in _ROMAN:
        count, n = divmod(n, value)
        out.append(symbol * count)
    return "".join(out)


def _lap_suffix(base: str, lap: int) -> str:
    """``base`` on lap 0, else ``base-<roman(lap+1)>`` (``-ii``, ``-iii``, ...)."""
    return base if lap == 0 else f"{base}-{_roman(lap + 1)}"


# Island names: legendary, sunken, and otherworldly isles from myth across
# cultures — many drawn from sea voyages (Ogygia, Aeaea, Scheria from the
# Odyssey; Penglai and Horai from East Asian lore). Kebab-safe, unique.
ISLAND_NAMES: tuple[str, ...] = (
    "atlantis",
    "avalon",
    "lemuria",
    "hyperborea",
    "lyonesse",
    "ogygia",
    "aeaea",
    "scheria",
    "thule",
    "hy-brasil",
    "bimini",
    "penglai",
    "horai",
    "tir-na-nog",
    "elysium",
    "buyan",
    "meropis",
    "thrinacia",
    "ys",
    "mu",
)


def nickname_for_index(index: int) -> str:
    """Return a deterministic nickname for a zero-based agent index.

    ``0..len(CURATED)-1`` map to the curated names directly. The next
    ``len(ADJECTIVES) * len(NOUNS)`` indices are ``<adjective>-<noun>`` combos.
    Only past *both* pools does a Roman-numeral lap suffix appear
    (``-ii``, ``-iii``, ...), so ids stay unique for arbitrarily large agent
    counts.
    """
    if index < 0:
        raise ValueError(f"index must be >= 0, got {index}")

    if index < len(CURATED):
        return CURATED[index]

    combo_idx = index - len(CURATED)
    lap = combo_idx // _COMBO_SPAN
    slot = combo_idx % _COMBO_SPAN
    # Adjective varies fastest so consecutive agents differ in the first token.
    adjective = ADJECTIVES[slot % len(ADJECTIVES)]
    noun = NOUNS[(slot // len(ADJECTIVES)) % len(NOUNS)]
    return _lap_suffix(f"{adjective}-{noun}", lap)


def assign_nicknames(count: int) -> list[str]:
    """Return ``count`` unique nicknames in deterministic spawn order."""
    return [nickname_for_index(i) for i in range(count)]


def island_name_for_index(index: int) -> str:
    """Return a deterministic island name for a zero-based island index.

    Wraps with a Roman-numeral ``-ii``/``-iii`` suffix past the pool, mirroring
    ``nickname_for_index``. Callers minting island directories and callers
    minting ``agent_id`` provenance must both route through here so the two
    always agree.
    """
    if index < 0:
        raise ValueError(f"index must be >= 0, got {index}")
    base = ISLAND_NAMES[index % len(ISLAND_NAMES)]
    lap = index // len(ISLAND_NAMES)
    return _lap_suffix(base, lap)
