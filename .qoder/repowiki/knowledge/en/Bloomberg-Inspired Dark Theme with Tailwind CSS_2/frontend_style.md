The frontend employs a **Bloomberg-inspired dark aesthetic** built on **Tailwind CSS v3** and **React**. The design system prioritizes high-density information display, financial data readability, and a professional "terminal-like" experience.

### 1. Styling Architecture
- **Framework**: Tailwind CSS for utility-first styling, processed via PostCSS.
- **Build Tool**: Vite.
- **Utility Helper**: `clsx` (via `cn` in `lib/utils.ts`) for conditional class merging.
- **Iconography**: `lucide-react` for consistent, lightweight SVG icons.

### 2. Design Tokens & Theming
The theme is defined in `frontend/src/styles/globals.css` using CSS custom properties (variables) mapped to Tailwind utilities in `tailwind.config.js`. This allows for easy theming adjustments without changing component code.

**Color Palette (Bloomberg-ish Dark):**
- **Surfaces**: `--bbg` (page bg), `--bbg-1` (panel), `--bbg-2` (elevated), `--bbg-3` (hover).
- **Borders**: `--bline` (standard), `--bline-2` (strong/focus).
- **Typography**: `--bfg` (primary text), `--bfg-m` (muted), `--bfg-d` (dim).
- **Accents**: `--bamb` (Bloomberg Amber/Orange), `--bcy` (Cyan), `--bmg` (Magenta).
- **Semantic**: `--bull` (Green #22c55e), `--bear` (Red #ef4444).

**Typography:**
- **Sans**: `Inter` for UI elements.
- **Mono**: `JetBrains Mono` for numerical data, ensuring tabular alignment (`tnum`).
- **Sizes**: Custom `2xs` (0.625rem) for dense data displays.

### 3. Component Conventions
Components follow a strict naming convention prefixed with `b-` (for "Bloomberg" or "Base") defined in the `@layer components` of `globals.css`:
- `.b-panel`: Standard container with background, border, and shadow.
- `.b-btn`: Compact button (h-6, text-2xs) with hover/active states.
- `.b-btn-primary`: Amber-accented primary action.
- `.b-input`: Compact input field (h-7) with cyan focus ring.
- `.b-tab`: Tab navigation with amber active indicator.
- `.b-kbd`: Keyboard shortcut hint styling.

### 4. Responsive & Layout Strategy
- **Layout**: Fixed-height header (`h-9`), flexible content areas. 
- **Scrollbars**: Custom styled scrollbars (9px width) to match the dark theme.
- **Data Display**: Heavy use of `font-mono num` (tabular nums) for financial figures to prevent layout shifts during updates.
- **Animations**: Custom keyframes for `flash-up` (green flash) and `flash-down` (red flash) to indicate price changes, and `marquee` for tickers.

### 5. Developer Rules
- **Use Semantic Colors**: Always use `bg-bbg1`, `text-bfg`, `border-bline` etc., instead of hardcoded hex values.
- **Tabular Numbers**: Apply `num` class or `font-mono` to all financial data (prices, volumes, P&L).
- **Compact UI**: Prefer `h-6` or `h-7` for interactive elements to maintain high information density.
- **State Feedback**: Use `flash-up`/`flash-down` animations for real-time data updates.
- **Keyboard Accessibility**: Implement keyboard shortcuts (e.g., `Cmd+K` for search) as seen in `TopBar.tsx`.