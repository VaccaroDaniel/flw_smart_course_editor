# S2B Accessibility

Created: 2026-08-23

## Implemented

The FLW in-unit navigator is rendered as:

```html
<nav id="flw-unit-navigator" aria-label="Unit lesson navigation">
```

Controls are semantic buttons/details:

- Previous button
- Next button
- expandable `<details>` / `<summary>` lesson list with `aria-expanded` and `aria-controls`
- one button per available component

Previous and Next expose the destination in their accessible name, for example `Next: Lesson 2`. At narrow widths their visible text collapses to icons while these names remain available to assistive technology.

The current component uses:

```text
aria-current="page"
```

Locked items use:

```text
aria-disabled="true"
```

Status messages use:

```text
role="status"
aria-live="polite"
```

## Keyboard and focus

All navigator actions are native buttons or summary controls, so they are keyboard reachable by default. CSS provides visible `:focus-visible` outlines.

## No color-only state

States are textual and symbolic:

```text
✓ Completed
● Current
○ Available
◇ Locked
```

Color is supplemental only.

## Responsive behavior

On narrow viewports the navigator collapses into:

```text
←  4 of 13 · Lesson 1  Lessons  →
```

The control remains one compact row with 40-pixel touch targets. The lesson list opens as a one-column, independently scrollable overlay, so it does not push lesson content down.

## Verification

Navigator v4 passed the JavaScript/static smoke checks and browser checks on a freshly exported 13-component Chinese unit at 1280px and 390px viewport widths. The narrow menu was verified to remain within the viewport and scroll independently.

Local lesson-to-lesson navigation uses a short page-ready transition so unfiltered source content is never presented while the next component initializes. `prefers-reduced-motion: reduce` shortens the transition to effectively instantaneous without exposing the unready page.
