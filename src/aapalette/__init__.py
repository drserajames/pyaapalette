"""aapalette — consistent, colour-vision-aware amino-acid colour palettes.

Ten amino-acid colour schemes are exposed, all read from a bundled
``aa_palettes.json`` that is the single source of truth shared with the sibling
packages ``aapalette`` (R) and ``jalaapalette`` (Jalview).

Three schemes are new to this project (the "AApalette" amino-acid colour
alphabet, released CC-BY-4.0): ``typical`` (normal vision), ``redgreen``
(deuteranopia & protanopia safe) and ``blueyellow`` (tritanopia safe). Seven are
community-standard schemes, attributed to their original sources: ``clustal``,
``zappo``, ``taylor``, ``lesk``, ``cinema``, ``rasmol`` and ``shapely``.

Recommended schemes: ``typical`` (normal), ``redgreen`` (red-green CVD), ``blueyellow``
(tritan CVD). No 20-colour palette is safe for every colour-vision deficiency at
once; for robust figures, pair colour with the residue letter.

Example
-------
>>> import aapalette
>>> aapalette.color_for("W", scheme="typical")
'#FFECB1'
>>> list(aapalette.get_palette("zappo"))[:3]
['A', 'C', 'D']

Matplotlib helpers (:func:`to_listed_colormap`, :func:`swatch`) require the
optional ``matplotlib`` dependency and live in :mod:`aapalette.plotting`; they
are re-exported here for convenience but only import matplotlib when called.
"""

from __future__ import annotations

from ._core import (
    SCHEME_IDS,
    UNKNOWN_CODES,
    GAP_CODES,
    color_for,
    defaults,
    get_palette,
    list_schemes,
    load_data,
    meta,
    palette_dict,
    recommended,
    residues,
    scheme_info,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "SCHEME_IDS",
    "UNKNOWN_CODES",
    "GAP_CODES",
    "color_for",
    "defaults",
    "get_palette",
    "list_schemes",
    "load_data",
    "meta",
    "palette_dict",
    "recommended",
    "residues",
    "scheme_info",
    "to_listed_colormap",
    "swatch",
]


def to_listed_colormap(scheme: str = "typical"):
    """Return a matplotlib ``ListedColormap`` of ``scheme`` in residue order.

    Thin wrapper around :func:`aapalette.plotting.to_listed_colormap`; requires
    the optional ``matplotlib`` dependency.
    """
    from .plotting import to_listed_colormap as _impl

    return _impl(scheme)


def swatch(scheme: str = "typical", **kwargs):
    """Render a labelled swatch preview of ``scheme``.

    Thin wrapper around :func:`aapalette.plotting.swatch`; requires the optional
    ``matplotlib`` dependency.
    """
    from .plotting import swatch as _impl

    return _impl(scheme, **kwargs)
