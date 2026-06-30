# data-raw — palette regeneration

## Single source of truth

The authoritative palette data lives in **`aa_palettes.json`** at the repository
root. The packaged copy at `src/aapalette/data/aa_palettes.json` is bundled as
package data and is what the library reads at runtime via
`importlib.resources`.

**Never hand-edit the hex values** in either copy. They are shared, byte-for-byte,
with the sibling packages:

- `aapalette` (R)
- `pyaapalette` (this package, importable as `aapalette`)
- `jalaapalette` (Jalview)

Consistency across the three is a hard requirement — identical scheme IDs,
identical hex values, identical residue handling.

## Regenerating the bundled copy

If the root `aa_palettes.json` changes, refresh the packaged copy:

```sh
cp aa_palettes.json src/aapalette/data/aa_palettes.json
```

Then run the test suite — `tests/test_palettes.py` asserts that the package's
output equals the JSON exactly and that every scheme has 20 valid 6-digit hex
colours:

```sh
pip install -e .[test]
pytest
```

## Provenance of the data

- `typical`, `redgreen`, `blueyellow` — created by the AApalette project; CC-BY-4.0.
- `clustal`, `zappo`, `taylor`, `lesk`, `cinema`, `rasmol`, `shapely` —
  community-standard schemes, attributed to their original sources in each
  scheme's `source` field and in the top-level README.

Deliberately **excluded**: Polychrome, Green-Armytage, Biotite/Gecos
(flower/blossom/sunset), and any personal/agent palettes.
