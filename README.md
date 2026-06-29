# pyaapalette

Consistent, colour-vision-aware **amino-acid colour palettes** for Python.

`pyaapalette` ships ten amino-acid colour schemes — three new colour-vision-aware
alphabets from the AApalette project plus seven attributed community-standard
schemes — all read from a single bundled `aa_palettes.json` that is the source of
truth shared with the sibling packages **`aapalette`** (R) and **`jalaapalette`**
(Jalview). The three packages use identical scheme IDs, identical hex values, and
identical residue handling.

The repository directory is `pyaapalette`; the importable package is **`aapalette`**:

```python
import aapalette
```

## Install

```sh
pip install pyaapalette            # core, no heavy deps
pip install pyaapalette[plot]      # + matplotlib helpers
```

Or from a checkout:

```sh
pip install -e .[dev]
python -m build
```

Python ≥ 3.9. The core package has **no required dependencies**; matplotlib is
optional and only needed for the plotting helpers.

## The 10 schemes

| ID | Label | Vision | Source |
|----|-------|--------|--------|
| `hue` | AApalette hue (normal vision) | normal | This work (aapalette) |
| `redgreen` | AApalette red-green CVD safe | deuteranopia & protanopia safe | This work (aapalette) |
| `tritan` | AApalette tritan CVD safe | tritanopia safe | This work (aapalette) |
| `clustal` | Clustal X | normal | Clustal X / Jalview |
| `zappo` | Zappo | normal | Zappo / Jalview |
| `taylor` | Taylor | normal | Taylor (1997) / Jalview |
| `lesk` | Lesk | normal | Lesk, *Introduction to Protein Architecture* |
| `cinema` | Cinema | normal | CINEMA (Parry-Smith et al. 1998) |
| `rasmol` | RasMol amino | normal | RasMol amino colour scheme |
| `shapely` | RasMol shapely | normal | RasMol/Jmol shapely (Fletterick Shapely models) |

**Recommended:** `hue` for normal vision, `redgreen` for red-green CVD,
`tritan` for tritan CVD.

## Usage

```python
import aapalette

# 1. List the schemes (id, label, vision, source).
for s in aapalette.list_schemes():
    print(s["id"], "—", s["label"])

# 2. Get a palette: residue -> hex, in canonical order
#    (A C D E F G H I K L M N P Q R S T V W Y).
pal = aapalette.get_palette("hue")
pal["W"]                       # '#FFECB1'

# Optionally include the documented defaults.
aapalette.get_palette("hue", include_gap=True, include_unknown=True)
# -> 20 residues, then X/B/Z/J (#BEBEBE), then '-' (#FFFFFF)

# 3. Scheme metadata (label, source, vision, min_deltaE, names).
info = aapalette.scheme_info("hue")
info["min_deltaE"]             # {'normal': 15.0, 'deutan': 3.7, ...}
info["names"]["Y"]             # 'yellow'

# 4. One residue. Lower-case is accepted; unknown/ambiguous and gaps resolve
#    to the documented defaults.
aapalette.color_for("k", "redgreen")   # '#4F69C6'
aapalette.color_for("X")               # '#BEBEBE'  (unknown/ambiguous)
aapalette.color_for("-")               # '#FFFFFF'  (gap)
```

### Residue & symbol handling

Identical across all three sibling packages:

- The 20 standard residues each get the scheme colour.
- Unknown / ambiguous codes `X, B, Z, J` → `#BEBEBE`.
- Gap symbols `-` and `.` → `#FFFFFF`.
- Lower-case residue letters are accepted (treated as upper-case).

### Sequence tools (e.g. logomaker)

`palette_dict(scheme)` returns a plain `{residue: hex}` mapping suitable for
passing straight to sequence-visualisation tools:

```python
import logomaker
logo = logomaker.Logo(df, color_scheme=aapalette.palette_dict("hue"))
```

### Matplotlib

Requires `pip install pyaapalette[plot]`.

```python
import matplotlib.pyplot as plt
import aapalette

# A ListedColormap in residue order (index i -> residues()[i]).
cmap = aapalette.to_listed_colormap("redgreen")

# Render a labelled swatch preview of any scheme.
fig = aapalette.swatch("hue")
plt.show()
# fig.savefig("hue.png", dpi=150)
```

## Attribution

The `hue`, `redgreen`, and `tritan` schemes are the **AApalette amino-acid
colour alphabet**, created for this project and released under **CC-BY-4.0**.
If you use them, please cite the forthcoming methods write-up:

> *AApalette: colour-vision-aware amino-acid colour alphabets* (in preparation).

The seven classical schemes are community-standard colour schemes, included for
interoperability and attributed to their original sources:

- **Clustal X** — Clustal X / Jalview
- **Zappo** — Zappo / Jalview
- **Taylor** — Taylor (1997) / Jalview
- **Lesk** — Lesk, *Introduction to Protein Architecture*
- **Cinema** — CINEMA, Parry-Smith et al. 1998
- **RasMol amino** — RasMol amino colour scheme
- **RasMol shapely** — RasMol/Jmol shapely (Fletterick Shapely models)

### Deliberate exclusions

Polychrome, Green-Armytage, and Biotite/Gecos (flower/blossom/sunset) palettes,
along with any personal/agent palettes, are **intentionally not included**.

## Colour-vision caveat

> No 20-colour palette is safe for every colour-vision deficiency at once; for
> robust figures, pair colour with the residue letter (redundant coding). ΔE
> values are CIEDE2000 minima.

The `min_deltaE` values in `scheme_info(...)` report the minimum CIEDE2000
colour difference between any two residues under normal, deutan, protan, and
tritan vision — higher is more distinguishable. Use them to choose a scheme for
your audience, but always keep the residue letter visible.

## Licences

- **Code:** MIT — see [`LICENSE`](LICENSE).
- **Palette data** (`aa_palettes.json`): CC-BY-4.0 — see [`LICENSE-DATA`](LICENSE-DATA).

## Source of truth & regeneration

All palette data comes from `aa_palettes.json`, bundled at
`src/aapalette/data/aa_palettes.json`. Never hand-edit the hex values. See
[`data-raw/README.md`](data-raw/README.md) for the regeneration procedure. The
test suite asserts the package's output equals the JSON exactly.

## Tests

```sh
pip install -e .[test]
pytest
```
