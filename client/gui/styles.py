"""
P2P Tunnel Monochrome Dark & Light Themes (QSS & Palette Definitions).
Provides both Monochrome Dark (#0c0c0e canvas, #141417 cards) and
Monochrome Light (#efeff2 canvas, #ffffff cards) palettes.
"""

THEME_PALETTES = {
    "dark": {
        "window_bg": "#0c0c0e",
        "card_bg": "#141417",
        "card_border": "#232329",
        "text_primary": "#f4f4f6",
        "text_secondary": "#8e8e99",
        "text_muted": "#686873",
        "dock_bg": "#18181c",
        "dock_border": "#27272f",
        "pill_bg": "#1c1c22",
        "pill_border": "#2e2e38",
        "divider": "#232329",
        "input_bg": "#18181c",
        "input_bg_focus": "#1e1e24",
        "input_border": "#2c2c35",
        "input_border_focus": "#f4f4f6",
        "dropdown_popup_bg": "#18181c",
        "dropdown_popup_border": "#3f3f4a",
        "role_badge_bg": "#232329",
        "role_badge_fg": "#f4f4f6",
        "role_badge_border": "#34343d",
    },
    "light": {
        "window_bg": "#efeff2",
        "card_bg": "#ffffff",
        "card_border": "#e2e2e7",
        "text_primary": "#141417",
        "text_secondary": "#686873",
        "text_muted": "#71717a",
        "dock_bg": "#141417",
        "dock_border": "#232329",
        "pill_bg": "#141417",
        "pill_border": "#27272a",
        "divider": "#e4e4e7",
        "input_bg": "#f4f4f6",
        "input_bg_focus": "#ffffff",
        "input_border": "#d4d4d8",
        "input_border_focus": "#141417",
        "dropdown_popup_bg": "#ffffff",
        "dropdown_popup_border": "#141417",
        "role_badge_bg": "#141417",
        "role_badge_fg": "#ffffff",
        "role_badge_border": "#27272a",
    },
}


def build_theme_stylesheet(theme: str = "dark") -> str:
    pal = THEME_PALETTES.get(theme, THEME_PALETTES["dark"])
    return f"""
QMainWindow, QWidget#MainRoot, QWidget#PageMain, QWidget#PageConfig {{
    background-color: {pal["window_bg"]};
    color: {pal["text_primary"]};
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
}}

QLabel {{
    background: transparent;
    border: none;
    color: {pal["text_primary"]};
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
}}

/* Typography & Section Headers */
QLabel#BrandTitle {{
    font-size: 13px;
    font-weight: 800;
    color: {pal["text_primary"]};
    letter-spacing: 1.2px;
}}

QLabel#PageTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {pal["text_primary"]};
    letter-spacing: 0.2px;
}}

QLabel#SectionHeader {{
    font-size: 11px;
    font-weight: 700;
    color: {pal["text_secondary"]};
    letter-spacing: 0.5px;
}}

/* Center Hero Card */
QFrame#HeroCard {{
    background-color: {pal["card_bg"]};
    border: 1px solid {pal["card_border"]};
    border-radius: 16px;
}}

QLabel#HeroStatusTitle {{
    font-size: 22px;
    font-weight: 800;
    color: {pal["text_primary"]};
    letter-spacing: -0.3px;
}}

/* Role Badge (Monochrome Pill) */
QLabel#RoleBadge {{
    background-color: {pal["role_badge_bg"]};
    color: {pal["role_badge_fg"]};
    border: 1px solid {pal["role_badge_border"]};
    border-radius: 6px;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    letter-spacing: 0.5px;
}}

/* Server-Provided Connection Address Pill */
QFrame#AddressPill {{
    background-color: {pal["pill_bg"]};
    border: 1px solid {pal["pill_border"]};
    border-radius: 11px;
}}

QLabel#AddressText {{
    font-family: "Consolas", "Cascadia Mono", "Segoe UI", monospace;
    font-size: 13px;
    font-weight: 700;
    color: #fafafa;
    letter-spacing: 0.3px;
}}

/* Bottom Active Server Dock */
QFrame#ServerDockCard {{
    background-color: {pal["dock_bg"]};
    border: 1px solid {pal["dock_border"]};
    border-radius: 14px;
}}

QLabel#ServerNameTitle {{
    font-size: 13.5px;
    font-weight: 700;
    color: #fafafa;
}}

QLabel#ServerCodeSub {{
    font-size: 11.5px;
    font-weight: 500;
    color: #a1a1aa;
}}

/* Settings Form Card */
QFrame#FormCard {{
    background-color: {pal["card_bg"]};
    border: 1px solid {pal["card_border"]};
    border-radius: 14px;
}}

QFrame#FormDivider {{
    background-color: {pal["divider"]};
    border: none;
}}

/* Footer */
QLabel#AppVersionLabel {{
    color: {pal["text_muted"]};
    font-size: 11px;
    font-weight: 600;
}}
"""


DARK_THEME = build_theme_stylesheet("dark")
LIGHT_THEME = build_theme_stylesheet("light")
MONOCHROME_THEME = DARK_THEME
