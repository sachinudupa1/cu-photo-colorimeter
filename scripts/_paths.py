"""Lets the scripts run without installing the package: python scripts/train.py ..."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# plot colours: ink for text, one blue for the main series, one orange for a second series
INK, MUTED, GRID = "#1f2933", "#6b7785", "#e3e7eb"
BLUE, ORANGE = "#2b5fb3", "#d9732a"


def style_axes(ax):
    """Quiet axes: no top/right frame, faint grid, text in ink colours."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)
    ax.title.set_color(INK)
