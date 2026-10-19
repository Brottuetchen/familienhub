# Themes

A theme is a single `theme.json` file: colours plus a small, fixed set of style switches. A theme contains no CSS, no code and no free text apart from its name, so any theme is safe to install.

Familienhub ships five themes (`backend/app/themes/`): Warm, Liquid Glass, Clean Cards, Neo-Brutalism and Pixel. Admins can install more from GitHub, for example the eleven from the [theme gallery](#theme-gallery). Each person picks a theme and *Light / Dark / Automatic* per device under **More → Appearance**.

## Theme gallery

[**Brottuetchen/familienhub-themes**](https://github.com/Brottuetchen/familienhub-themes) has eleven ready-made themes, each with a light and a dark variant: 8-Bit Gameboy, Candy Pop, Cyberpunk, E-Ink Reader, Matcha Zen, Midnight OLED, Nordic Fjord, Retro Synthwave, Solarized Paper, Swiss Bauhaus and Präzision.

To install one, an admin opens **More → Appearance → From GitHub** and pastes its link from the gallery's README, e.g. `https://github.com/Brottuetchen/familienhub-themes/blob/main/gameboy-pocket/theme.json`. New themes for the gallery are welcome as pull requests there.

## The file

```jsonc
{
  "name": "Forest",                         // max. 60 characters
  "colors": {                               // all #RRGGBB
    "primary": "#2E7D32", "secondary": "#A5D6A7",
    "background": "#0B1F0E", "surface": "#13301A", "surfaceHigh": "#1C4224", "border": "#2C5A35",
    "onPrimary": "#FFFFFF", "onSurface": "#E8F5E9"          // optional: onPrimary, onSecondary, onBackground, onSurface
  },
  "style": {                                // everything optional, defaults in brackets
    "background": {"type": "glow", "colors": ["#1B5E20", "#004D40"]},   // solid | gradient | glow (solid), max. 4 colours
    "card": {"radius": 16, "border": 1, "shadow": "soft", "glass": false, "header": "plain"},
                                            // radius 0–40 (20), border 0–4 (1), shadow none|soft|hard (none), header plain|band
    "accents": ["#66BB6A", "#FFCA28"],      // max. 6 colours for tiles and avatars
    "layout": "bento",                      // list | bento (list) – how "Today" arranges its cards
    "nav": "floating",                      // bar | floating (bar)
    "titleWeight": 700,                     // 400–900 in steps of 100 (500)
    "uppercaseTitles": false,
    "font": {"title": "grotesk", "body": "system", "label": "mono"}   // system | pixel | mono | grotesk
  },
  "variants": {                             // optional: light and/or dark version
    "light": {
      "colors": { "primary": "#2E7D32", "secondary": "#66BB6A", "background": "#F1F8E9",
                  "surface": "#FFFFFF", "surfaceHigh": "#E8F5E9", "border": "#C5E1A5" },
      "style": {"background": {"type": "solid"}}            // only what differs from the base style
    }
  }
}
```

- **`colors`** is the base version. The app works out light or dark from the background colour.
- **`variants.light` / `variants.dark`** need a complete colour set. Their `style` only lists differences; background and card are merged field by field. If you offer both variants, *Automatic* follows the phone. Without variants, the base version is used in every mode.
- **Fonts** ship with the app and work offline:
  - `pixel` (Pixelify Sans)
  - `mono` (JetBrains Mono)
  - `grotesk` (Space Grotesk)
  - `system` (the platform font)

  All are under the SIL Open Font License. Other fonts are not possible on purpose: a theme can't make the app download anything.

The server checks every field (`validate_theme` in `backend/app/routers/themes.py`). Unknown fields are dropped. Wrong values are rejected with a message that names the field.

## Share a theme

1. Create a public GitHub repository, or a folder in an existing one, with your `theme.json`. A screenshot in the README helps.
2. Anyone with admin rights on a hub opens **More → Appearance → From GitHub** and pastes the address, e.g.
   - `https://github.com/you/familienhub-forest` (uses `theme.json` in the default branch)
   - `https://github.com/you/themes/blob/main/forest/theme.json`

   The hub fetches it from `raw.githubusercontent.com` only, follows no redirects and accepts at most 64 KB.
3. Installed themes are available to everyone in the family. Admins can remove them again.

Reviewed themes and plugins can also be installed with one click from the [plugin and theme store](store.md) (**Administration → Store**). To list your theme there, open a pull request to the store repository, see [store.md](store.md#submitting-an-entry).

## Add a built-in theme

Add a JSON file to `backend/app/themes/`; the file name becomes the id (`builtin:<name>`). Run `backend/tests/test_themes.py`, it validates every shipped theme. Please include light and dark variants.
