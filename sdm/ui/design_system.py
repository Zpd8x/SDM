"""Central visual tokens for the SDM desktop interface.

The values in this module are deliberately small and stable.  New widgets
should use these tokens instead of introducing one-off sizes or colours.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Colors:
    background: str = "#050b0f"
    surface: str = "#071217"
    surface_elevated: str = "#09191d"
    border: str = "#18382d"
    border_strong: str = "#285543"
    text: str = "#f2fff7"
    text_muted: str = "#9eb5aa"
    primary: str = "#55e59a"
    primary_hover: str = "#72efaa"
    success: str = "#31d47f"
    warning: str = "#efc768"
    danger: str = "#ff7e8a"


@dataclass(frozen=True)
class Radius:
    small: int = 4
    medium: int = 6
    large: int = 8
    panel: int = 10


@dataclass(frozen=True)
class Spacing:
    xxs: int = 4
    xs: int = 8
    sm: int = 12
    md: int = 16
    lg: int = 20
    xl: int = 24
    xxl: int = 32


@dataclass(frozen=True)
class Metrics:
    toolbar_height: int = 40
    control_height: int = 34
    icon_size: int = 18
    row_height: int = 42
    title_bar_height: int = 58


COLORS = Colors()
RADIUS = Radius()
SPACING = Spacing()
METRICS = Metrics()
