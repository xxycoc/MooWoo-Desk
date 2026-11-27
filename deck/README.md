# MooWoo Desk deck

Static 16-slide presentation. No build step, no external fonts or scripts.

## Open it

- Offline: open `deck/index.html` directly in a browser. The inline data snapshot is used because `file://` cannot fetch JSON.
- Hosted: serve the `deck/` folder (for example, Qoder Sites). The page fetches `data.json` instead.

## Keys

- Right, Space, Page Down, or click the right half: next slide.
- Left, Page Up, or click the left half: previous slide.
- Home / End: first / last slide.
- `p`: show or hide the speaker note for the current slide.
- `#5` in the URL opens slide 5.
- Ctrl+P prints one slide per page.

## Update numbers

1. Edit `deck/data.json`.
2. Run `python deck/sync_data.py` to copy the file into the inline snapshot in `deck/index.html`.
3. Reload the page.

`sync_data.py` fails if the snapshot markers are missing. A `null` value renders as a muted `[28 Nov]` tag; speaker notes are the `notes` array, one entry per slide.
