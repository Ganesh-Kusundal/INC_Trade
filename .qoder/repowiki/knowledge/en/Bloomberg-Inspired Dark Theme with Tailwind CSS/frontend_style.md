## Overview

The TradeXV2 frontend uses a **Tailwind CSS v3** utility-first styling system with a custom **Bloomberg-inspired dark theme**. The design emphasizes high information density, tabular numeric data presentation, and a professional trading-terminal aesthetic.

## Styling Stack

- **CSS Framework**: Tailwind CSS v3.4.17 with PostCSS
- **Build Tool**: Vite v6
- **Utility Helper**: `clsx` for conditional class composition (`cn()` function)
- **Icon Library**: Lucide React (no icon font or SVG sprite system)
- **No component library**: All UI components are hand-built using Tailwind utilities and custom CSS component classes

## Design Token System

Design tokens are defined as **CSS custom properties** in `globals.css` and mapped to Tailwind color utilities via the `tailwind.config.js` theme extension. This enables alpha-channel opacity modifiers (e.g., `bg-bamb/20`).

### Color Palette (Dark Surfaces)

| Token | RGB Value | Purpose |
|-------|-----------|---------|
| `--bbg` | `8 10 14` | Page background (deepest) |
| `--bbg-1` | `13 16 22` | Panel surfaces |
| `--bbg-2` | `18 22 30` | Elevated surfaces / inputs |
| `--bbg-3` | `25 31 42` | Hover states |
| `--bline` | `34 42 56` | Borders |
| `--bline-2` | `48 58 76` | Strong borders / scrollbar thumb |
| `--bfg` | `222 226 235` | Primary text |
| `--bfg-m` | `156 165 188` | Muted text |
| `--bfg-d` | `102 115 140` | Dim/disabled text |

### Accent Colors

| Token | RGB Value | Purpose |
|-------|-----------|---------|
| `--bamb` | `255 168 38` | Bloomberg amber (brand accent, active tabs) |
| `--bcy` | `34 211 238` | Cyan (focus rings, live LTP indicators) |
| `--bmg` | `217 70 239` | Magenta (secondary accent) |
| `--bull` | `34 197 94` | Green (positive price change, live connection) |
| `--bear` | `239 68 68` | Red (negative price change) |

### Typography

- **Sans-serif**: Inter (primary), with system-ui fallbacks
- **Monospace**: JetBrains Mono (numeric data, timestamps, keyboard hints)
- **Custom sizes**: `2xs` (0.625rem), `xs` (0.6875rem), `sm` (0.8125rem), `base` (0.875rem) — all smaller than Tailwind defaults for high-density layouts
- **Font features**: Tabular nums (`tnum`), contextual alternates enabled globally

## Component Class Conventions

Reusable component classes are defined in the `@layer components` block of `globals.css`, prefixed with `b-` (for "Bloomberg" or "base"):

- `.b-panel` — Card/panel container with background, border, and shadow
- `.b-btn` — Base button styles (compact, 24px height, subtle hover transitions)
- `.b-btn-primary` — Primary action button variant (amber-tinted)
- `.b-input` — Form input fields (28px height, cyan focus ring)
- `.b-tab` / `.b-tab-active` — Tab navigation items
- `.b-kbd` — Keyboard shortcut badges (9px mono text)

These classes use `@apply` to compose Tailwind utilities, ensuring consistency while keeping the HTML markup clean.

## Responsive Strategy

The codebase shows **no explicit responsive breakpoints** or mobile-specific adaptations. The layout is designed for desktop trading terminals with fixed-height bars, dense data grids, and canvas-based charts. The `ResizeObserver` in chart components handles dynamic width adjustments, but there is no evidence of mobile-first or adaptive layouts.

## Animations

Custom keyframe animations defined in Tailwind config:

- `marquee` — Horizontal scrolling (news ticker)
- `pulse-soft` — Gentle opacity pulsing (status indicators)
- `flash-up` / `flash-down` — Brief background flash on price updates (green/red tint)

## Key Files

- `frontend/src/styles/globals.css` — CSS custom properties, base resets, component classes
- `frontend/tailwind.config.js` — Theme extension (colors, fonts, sizes, shadows, animations)
- `frontend/postcss.config.js` — PostCSS pipeline (Tailwind + Autoprefixer)
- `frontend/src/lib/utils.ts` — `cn()` helper for conditional class composition, formatting utilities
- `frontend/src/components/*.tsx` — All UI components use the `b-` prefixed classes and color tokens directly

## Developer Rules

1. **Use semantic color tokens** (`bg-bbg1`, `text-bfg`, `border-bline`) instead of raw RGB/hex values
2. **Apply `b-` prefixed component classes** for consistent button, input, panel, and tab styling
3. **Use `cn()` from `@/lib/utils`** for conditional class composition (never string concatenation)
4. **Numeric data must use `.num` class** or `font-mono` for tabular alignment
5. **Positive/negative values** should use `text-bull`/`text-bear` via the `pnlColor()` helper
6. **No inline styles** except for dynamic values (e.g., canvas dimensions, opacity overrides)
7. **Dark mode only** — `darkMode: 'class'` is configured but no light theme tokens exist