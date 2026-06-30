"""Core data loading and palette accessors for :mod:`aapalette`.

All palette data is read from the bundled ``data/aa_palettes.json`` file, which
is the single source of truth shared with the sibling packages ``aapalette``
(R) and ``jalaapalette`` (Jalview). Hex values are never altered in code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Dict, List, Optional

__all__ = [
    "load_data",
    "residues",
    "list_schemes",
    "get_palette",
    "scheme_info",
    "color_for",
    "palette_dict",
    "recommended",
    "defaults",
    "meta",
    "SCHEME_IDS",
    "UNKNOWN_CODES",
    "GAP_CODES",
]

#: One-letter codes treated as unknown/ambiguous -> ``defaults.unknown_XBZJ``.
UNKNOWN_CODES = frozenset("XBZJ")

#: Symbols treated as gaps -> ``defaults.gap``.
GAP_CODES = frozenset("-.")


@lru_cache(maxsize=1)
def load_data() -> Dict:
    """Return the parsed contents of the bundled ``aa_palettes.json``.

    The result is cached; callers must treat it as read-only.
    """
    resource = files("aapalette.data").joinpath("aa_palettes.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def residues() -> List[str]:
    """Return the 20 standard amino acids in canonical order."""
    return list(load_data()["residues"])


#: The 10 scheme IDs, in the order they appear in the JSON.
def _scheme_ids() -> List[str]:
    return list(load_data()["schemes"].keys())


SCHEME_IDS = tuple(_scheme_ids())


def _require_scheme(scheme: str) -> Dict:
    schemes = load_data()["schemes"]
    if scheme not in schemes:
        raise KeyError(
            f"Unknown scheme {scheme!r}. Available schemes: "
            f"{', '.join(schemes.keys())}"
        )
    return schemes[scheme]


def list_schemes() -> List[Dict[str, str]]:
    """List the available colour schemes.

    Returns
    -------
    list of dict
        One entry per scheme with keys ``id``, ``label``, ``vision`` and
        ``source``, in canonical order.
    """
    out: List[Dict[str, str]] = []
    for sid, s in load_data()["schemes"].items():
        out.append(
            {
                "id": sid,
                "label": s["label"],
                "vision": s["vision"],
                "source": s["source"],
            }
        )
    return out


def get_palette(
    scheme: str = "typical",
    include_gap: bool = False,
    include_unknown: bool = False,
) -> Dict[str, str]:
    """Return a residue -> hex mapping for ``scheme`` in canonical order.

    Parameters
    ----------
    scheme:
        A scheme ID (see :func:`list_schemes`). Defaults to ``"typical"``.
    include_gap:
        If ``True``, append the gap symbol ``"-"`` mapped to
        ``defaults.gap``.
    include_unknown:
        If ``True``, append the unknown/ambiguous codes ``X, B, Z, J`` each
        mapped to ``defaults.unknown_XBZJ``.

    Returns
    -------
    dict
        Ordered ``{residue: "#RRGGBB"}``. The 20 standard residues always come
        first, in canonical order, followed by any requested extras.
    """
    data = load_data()
    colors = _require_scheme(scheme)["colors"]
    palette: Dict[str, str] = {r: colors[r] for r in data["residues"]}
    if include_unknown:
        unknown_hex = data["defaults"]["unknown_XBZJ"]
        for code in ("X", "B", "Z", "J"):
            palette[code] = unknown_hex
    if include_gap:
        palette["-"] = data["defaults"]["gap"]
    return palette


def scheme_info(scheme: str) -> Dict:
    """Return metadata for ``scheme``.

    Always includes ``id``, ``label``, ``kind``, ``vision`` and ``source``.
    Includes ``min_deltaE`` and per-residue ``names`` and ``note`` when present
    in the source data.
    """
    s = _require_scheme(scheme)
    info: Dict = {
        "id": scheme,
        "label": s["label"],
        "kind": s["kind"],
        "vision": s["vision"],
        "source": s["source"],
    }
    for optional in ("min_deltaE", "names", "note"):
        if optional in s:
            info[optional] = s[optional]
    return info


def _normalise(residue: str) -> str:
    if len(residue) != 1:
        raise ValueError(f"Expected a single-character code, got {residue!r}")
    return residue.upper()


def color_for(residue: str, scheme: str = "typical") -> str:
    """Return the hex colour for a single ``residue`` under ``scheme``.

    Lower-case input is accepted. Unknown/ambiguous codes (``X, B, Z, J``)
    resolve to ``defaults.unknown_XBZJ`` and gap symbols (``-``, ``.``) to
    ``defaults.gap``.
    """
    data = load_data()
    code = _normalise(residue)
    if code in GAP_CODES:
        return data["defaults"]["gap"]
    colors = _require_scheme(scheme)["colors"]
    if code in colors:
        return colors[code]
    if code in UNKNOWN_CODES:
        return data["defaults"]["unknown_XBZJ"]
    # Any other symbol is treated as unknown.
    return data["defaults"]["unknown_XBZJ"]


def palette_dict(scheme: str = "typical") -> Dict[str, str]:
    """Return a plain residue -> hex dict suitable for sequence tools.

    This is the mapping to hand to e.g. ``logomaker``'s ``color_scheme``
    argument. Equivalent to :func:`get_palette` with no extras.
    """
    return get_palette(scheme)


def recommended() -> Dict[str, str]:
    """Return the recommended scheme per vision context.

    Keys: ``normal``, ``red_green_cvd``, ``tritan_cvd``.
    """
    return dict(load_data()["recommended"])


def defaults() -> Dict[str, str]:
    """Return the default colours for unknown codes and gaps."""
    return dict(load_data()["defaults"])


def meta() -> Dict[str, str]:
    """Return project metadata (licences, exclusions, CVD caveat)."""
    return dict(load_data()["meta"])
