"""Matplotlib integration for :mod:`aapalette` (optional dependency).

Importing this module requires ``matplotlib``. Install it with::

    pip install pyaapalette[plot]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._core import get_palette, residues, scheme_info

if TYPE_CHECKING:  # pragma: no cover - typing only
    from matplotlib.colors import ListedColormap
    from matplotlib.figure import Figure

__all__ = ["to_listed_colormap", "swatch"]


def to_listed_colormap(scheme: str = "typical") -> "ListedColormap":
    """Return a :class:`~matplotlib.colors.ListedColormap` for ``scheme``.

    Colours are listed in canonical residue order
    (``A C D E F G H I K L M N P Q R S T V W Y``), so colormap index ``i`` maps
    to ``residues()[i]``. The colormap is named ``f"aapalette_{scheme}"``.
    """
    from matplotlib.colors import ListedColormap

    palette = get_palette(scheme)
    return ListedColormap(list(palette.values()), name=f"aapalette_{scheme}")


def swatch(
    scheme: str = "typical",
    ncols: int = 5,
    swatch_size: float = 0.9,
    show_names: bool = True,
) -> "Figure":
    """Render a preview swatch of ``scheme`` and return the matplotlib figure.

    Parameters
    ----------
    scheme:
        Scheme ID to preview.
    ncols:
        Number of swatches per row.
    swatch_size:
        Size of each swatch cell in inches.
    show_names:
        If the scheme provides per-residue colour ``names``, print them under
        each residue label.

    Returns
    -------
    matplotlib.figure.Figure
        The figure containing the swatch grid. Call ``fig.savefig(...)`` or
        ``matplotlib.pyplot.show()`` to display it.
    """
    import matplotlib.pyplot as plt

    palette = get_palette(scheme)
    info = scheme_info(scheme)
    names = info.get("names", {}) if show_names else {}

    res = list(palette.keys())
    n = len(res)
    nrows = -(-n // ncols)  # ceil division

    fig, ax = plt.subplots(figsize=(ncols * swatch_size * 1.6, nrows * swatch_size + 0.6))
    ax.set_xlim(0, ncols)
    ax.set_ylim(0, nrows)
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title(f"{info['label']}  ({info['vision']})", fontsize=11, loc="left")

    for i, r in enumerate(res):
        row, col = divmod(i, ncols)
        hexv = palette[r]
        ax.add_patch(
            plt.Rectangle(
                (col + 0.05, row + 0.05),
                0.9,
                0.9,
                facecolor=hexv,
                edgecolor="0.5",
                linewidth=0.5,
            )
        )
        label = f"{r}  {hexv}"
        if r in names:
            label += f"\n{names[r]}"
        ax.text(
            col + 0.5,
            row + 0.5,
            label,
            ha="center",
            va="center",
            fontsize=7,
            color=_readable_text_color(hexv),
        )

    fig.tight_layout()
    return fig


def _readable_text_color(hex_color: str) -> str:
    """Return black or white, whichever contrasts better with ``hex_color``."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    # Perceived luminance (ITU-R BT.601).
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "black" if luminance > 0.55 else "white"
