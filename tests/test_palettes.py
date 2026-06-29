"""Tests for :mod:`aapalette`.

The overriding contract: the package's output must equal the bundled
``aa_palettes.json`` exactly. The JSON is the single source of truth shared
across the sibling packages, so these tests both validate it and prove the
Python API reproduces it faithfully.
"""

from __future__ import annotations

import json
import re
from importlib.resources import files

import pytest

import aapalette

HEX_RE = re.compile(r"^#[0-9A-F]{6}$")

CANONICAL_RESIDUES = list("ACDEFGHIKLMNPQRSTVWY")
EXPECTED_SCHEME_IDS = {
    "hue",
    "redgreen",
    "tritan",
    "clustal",
    "zappo",
    "taylor",
    "lesk",
    "cinema",
    "rasmol",
    "shapely",
}


@pytest.fixture(scope="module")
def raw():
    """The bundled JSON, parsed independently of the package accessors."""
    text = files("aapalette.data").joinpath("aa_palettes.json").read_text("utf-8")
    return json.loads(text)


# --- Source data sanity -----------------------------------------------------


def test_residues_canonical(raw):
    assert raw["residues"] == CANONICAL_RESIDUES
    assert aapalette.residues() == CANONICAL_RESIDUES


def test_ten_schemes(raw):
    assert set(raw["schemes"]) == EXPECTED_SCHEME_IDS
    assert len(raw["schemes"]) == 10
    assert set(aapalette.SCHEME_IDS) == EXPECTED_SCHEME_IDS


def test_every_scheme_has_20_valid_hex(raw):
    """Each scheme defines all 20 residues with valid 6-digit upper-case hex."""
    for sid, scheme in raw["schemes"].items():
        colors = scheme["colors"]
        assert set(colors) == set(CANONICAL_RESIDUES), f"{sid} residue set mismatch"
        for res, hexv in colors.items():
            assert HEX_RE.match(hexv), f"{sid}/{res} invalid hex: {hexv!r}"


def test_defaults_valid(raw):
    assert HEX_RE.match(raw["defaults"]["unknown_XBZJ"])
    assert HEX_RE.match(raw["defaults"]["gap"])


# --- Package equals JSON ----------------------------------------------------


def test_get_palette_equals_json(raw):
    """The crux: get_palette() reproduces the JSON colours exactly, in order."""
    for sid, scheme in raw["schemes"].items():
        palette = aapalette.get_palette(sid)
        # Same residues, same canonical order.
        assert list(palette.keys()) == CANONICAL_RESIDUES
        # Identical hex values, untouched.
        assert palette == scheme["colors"]


def test_default_scheme_is_hue():
    assert aapalette.get_palette() == aapalette.get_palette("hue")


def test_list_schemes_matches_json(raw):
    listed = aapalette.list_schemes()
    assert [s["id"] for s in listed] == list(raw["schemes"].keys())
    for entry in listed:
        src = raw["schemes"][entry["id"]]
        assert entry["label"] == src["label"]
        assert entry["vision"] == src["vision"]
        assert entry["source"] == src["source"]


def test_scheme_info_exposes_optional_fields(raw):
    # hue has min_deltaE + names + note.
    info = aapalette.scheme_info("hue")
    assert info["min_deltaE"] == raw["schemes"]["hue"]["min_deltaE"]
    assert info["names"]["W"] == "wheat"
    assert "note" in info
    # clustal has none of the optional fields.
    clustal = aapalette.scheme_info("clustal")
    assert "min_deltaE" not in clustal
    assert "names" not in clustal
    assert clustal["source"] == "Clustal X / Jalview"


def test_recommended_and_meta(raw):
    assert aapalette.recommended() == raw["recommended"]
    assert aapalette.recommended()["normal"] == "hue"
    assert aapalette.recommended()["red_green_cvd"] == "redgreen"
    assert aapalette.recommended()["tritan_cvd"] == "tritan"
    assert aapalette.meta() == raw["meta"]


# --- Residue / symbol handling ----------------------------------------------


def test_color_for_standard_residue(raw):
    assert aapalette.color_for("A", "hue") == raw["schemes"]["hue"]["colors"]["A"]


def test_color_for_lowercase_accepted():
    assert aapalette.color_for("a", "hue") == aapalette.color_for("A", "hue")
    assert aapalette.get_palette("hue")["A"] == aapalette.color_for("a")


@pytest.mark.parametrize("code", ["X", "B", "Z", "J", "x", "b"])
def test_unknown_codes_resolve_to_grey(code, raw):
    assert aapalette.color_for(code, "hue") == raw["defaults"]["unknown_XBZJ"]


@pytest.mark.parametrize("code", ["-", "."])
def test_gap_codes_resolve_to_gap_colour(code, raw):
    assert aapalette.color_for(code, "hue") == raw["defaults"]["gap"]


def test_include_gap_and_unknown(raw):
    palette = aapalette.get_palette("hue", include_gap=True, include_unknown=True)
    keys = list(palette.keys())
    # 20 standard residues first, in order.
    assert keys[:20] == CANONICAL_RESIDUES
    # Then unknowns then gap.
    assert keys[20:] == ["X", "B", "Z", "J", "-"]
    assert palette["X"] == raw["defaults"]["unknown_XBZJ"]
    assert palette["-"] == raw["defaults"]["gap"]


def test_palette_dict_is_plain_mapping():
    pd = aapalette.palette_dict("zappo")
    assert pd == aapalette.get_palette("zappo")
    assert len(pd) == 20


# --- Error handling ---------------------------------------------------------


def test_unknown_scheme_raises():
    with pytest.raises(KeyError):
        aapalette.get_palette("nonsuch")
    with pytest.raises(KeyError):
        aapalette.scheme_info("nonsuch")


def test_multichar_residue_raises():
    with pytest.raises(ValueError):
        aapalette.color_for("AA", "hue")


# --- Optional matplotlib integration ----------------------------------------


def test_to_listed_colormap_order():
    pytest.importorskip("matplotlib")
    cmap = aapalette.to_listed_colormap("hue")
    assert cmap.N == 20
    assert cmap.name == "aapalette_hue"


def test_swatch_returns_figure():
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    fig = aapalette.swatch("tritan")
    assert fig is not None
    # 20 swatch rectangles drawn on the single axes.
    rects = [p for p in fig.axes[0].patches]
    assert len(rects) == 20
