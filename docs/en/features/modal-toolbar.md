# Modal Toolbar

The unified toolbar at the bottom of the detail modal provides access to all primary controls during image/video viewing.

## Structure

### Primary Bar (always visible)

**Still image mode:**
- ☆ Favorite
- ⓘ Toggle info panel
- ‹ › Previous / Next
- Zoom (− / 100% / +)
- Fit mode (fit / fit-w / fit-h / fit-custom + height / original)
- Spread 2P / direction ↔ (when applicable)
- ⛶ Immersive / ⤢ Fullscreen
- 📁 Collection
- Bridge Send (Send prompt ▾ / Send image ▾)

**Video / audio mode (2-tier layout):**
- Top: time display + seek bar (max-width 720px cap)
- Bottom: ☆ Fav / ⓘ Info / ‹ › / ▶ Play ⏪ ⏩ / ♪ Mute + volume / ⛶ ⤢ / 📁

### Overflow Menu (… button)

Consolidates low-frequency operations in a vertical list:
- Autoplay + interval
- Repeat / speed / resume (for video)
- FPB / character grid (for still images)
- ZIP / container view
- Keyboard guide ?
- Collapse toolbar «

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `T` | Toggle toolbar visibility |
| `V` | Immersive mode |
| `F` | Fullscreen |
| `I` | Info panel |
| `H` | Keyboard guide |
| `P` | Autoplay |
| `Space` / `K` | Play / pause (video) |
| `J` / `0` | Rewind (video) |
| `L` | Fast forward (video) |
| `M` | Mute (video) |
| `R` | Repeat (video) |
| `←` / `→` | Previous / next image |
| `ESC` | Close overflow menu → modal in order |

## Collapse and Restore

Methods to collapse the toolbar:
- From the overflow menu (…), select "Collapse toolbar"
- Press `T` key

Methods to restore:
- Click the edge handle at the bottom center of the screen
- Press `T` key again

The edge handle position auto-adjusts based on filmstrip presence during collapsed state.

## Accessibility

- Entire toolbar has `role="toolbar"`
- Overflow button uses `aria-haspopup="menu"` / `aria-expanded` updated dynamically
- Overflow menu items have `role="menuitem"`
- Edge handle is a standard `<button>` operable with Enter / Space
- To satisfy WCAG 2.5.5 (Target Size), the visually 8px handle has a 24px-high invisible hit area extended via `::before`
