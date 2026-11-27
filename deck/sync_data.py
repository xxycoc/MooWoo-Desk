"""Copy deck/data.json into the inline snapshot in deck/index.html.

Browsers cannot fetch data.json when the deck is opened from file://, so the
page carries a copy for offline use. Run this after every data.json edit.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data.json"
PAGE = ROOT / "index.html"
SNAPSHOT = re.compile(
    r'(<script id="deck-data" type="application/json">\r?\n)(.*?)(\r?\n</script>)',
    re.DOTALL,
)


def main():
    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.exit(f"sync_data.py: cannot read {DATA.name}: {exc}")

    payload = json.dumps(data, indent=2, ensure_ascii=True)
    if "</script>" in payload:
        sys.exit("sync_data.py: data contains a closing script tag")

    try:
        html = PAGE.read_text(encoding="utf-8")
    except OSError as exc:
        sys.exit(f"sync_data.py: cannot read {PAGE.name}: {exc}")

    if not SNAPSHOT.search(html):
        sys.exit(
            "sync_data.py: snapshot markers missing in index.html "
            '(expected <script id="deck-data" type="application/json">)'
        )

    updated = SNAPSHOT.sub(lambda match: match.group(1) + payload + match.group(3), html, count=1)
    PAGE.write_text(updated, encoding="utf-8", newline="\n")
    print(f"Synced {PAGE.name} snapshot from {DATA.name} ({len(payload)} bytes).")


if __name__ == "__main__":
    main()
