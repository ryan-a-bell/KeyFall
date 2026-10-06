"""Theme definitions: color tokens, fonts, and which visual effects a style uses."""

from __future__ import annotations

from dataclasses import dataclass

from keyfall.renderer.draw import Color, hex_color


@dataclass(frozen=True)
class Palette:
    bg: Color
    bg2: Color  # gradient end / secondary background
    panel: Color
    panel2: Color
    line: Color
    text: Color
    muted: Color
    faint: Color
    accent: Color
    accent2: Color
    good: Color
    gold: Color
    miss: Color
    right: Color  # right-hand notes (overridden by colorblind palettes)
    left: Color


@dataclass(frozen=True)
class Theme:
    name: str
    display_name: str
    description: str
    palette: Palette
    ui_font: str  # bundled family name or "mono"
    display_font: str  # big numbers / titles
    label_font: str  # small caps labels
    glow: bool = False
    particles: bool = False
    light_beams: bool = False


CLASSIC = Theme(
    name="classic",
    display_name="Classic",
    description="The original KeyFall look: flat colors and a monospace font.",
    palette=Palette(
        bg=(18, 18, 24), bg2=(18, 18, 24), panel=(30, 30, 40), panel2=(40, 40, 52),
        line=(60, 60, 75), text=(220, 220, 220), muted=(120, 120, 140), faint=(80, 80, 100),
        accent=(80, 220, 100), accent2=(66, 135, 245), good=(80, 220, 100),
        gold=(180, 220, 80), miss=(220, 60, 60), right=(66, 135, 245), left=(245, 166, 66),
    ),
    ui_font="mono", display_font="mono", label_font="mono",
)

STUDIO = Theme(
    name="studio",
    display_name="Studio",
    description="Modern and professional: calm colors, clean type, detailed practice stats.",
    palette=Palette(
        bg=hex_color("#0D0F13"), bg2=hex_color("#14171E"), panel=hex_color("#15181E"),
        panel2=hex_color("#1B1F27"), line=hex_color("#262B35"), text=hex_color("#E8EAEE"),
        muted=hex_color("#8B93A3"), faint=hex_color("#5A6272"), accent=hex_color("#6E8BFF"),
        accent2=hex_color("#8FA4FF"), good=hex_color("#34C38F"), gold=hex_color("#F2C14E"),
        miss=hex_color("#E5484D"), right=hex_color("#5B8DEF"), left=hex_color("#F2A541"),
    ),
    ui_font="inter", display_font="inter", label_font="inter",
)

NEON = Theme(
    name="neon",
    display_name="Neon Arcade",
    description="Rhythm-game energy: glowing notes, combos, sparks and light beams.",
    palette=Palette(
        bg=hex_color("#07031A"), bg2=hex_color("#1C0838"), panel=hex_color("#160A30"),
        panel2=hex_color("#21103F"), line=hex_color("#3A2366"), text=hex_color("#F4F0FF"),
        muted=hex_color("#A49BC8"), faint=hex_color("#6C5F98"), accent=hex_color("#18E7FF"),
        accent2=hex_color("#FF2FD0"), good=hex_color("#4BFF9B"), gold=hex_color("#FFD23F"),
        miss=hex_color("#FF4D6D"), right=hex_color("#18E7FF"), left=hex_color("#FF2FD0"),
    ),
    ui_font="rajdhani", display_font="orbitron", label_font="rajdhani",
    glow=True, particles=True, light_beams=True,
)

THEMES: dict[str, Theme] = {t.name: t for t in (CLASSIC, STUDIO, NEON)}
THEME_ORDER = ["classic", "studio", "neon"]
