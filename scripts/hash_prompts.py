"""Print promptVersion: SHA-256 of a canonical, path-framed prompt manifest."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prompt_version(root=ROOT):
    root = Path(root)
    paths = sorted(root.glob("agents/*/system.md"))
    if not paths:
        raise ValueError("no agent prompts")
    paths += [root / "schemas/rating.schema.json", root / "agents/permissions.json"]
    manifest = []
    for path in sorted(paths):
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        if path.suffix == ".json":
            text = json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, allow_nan=False)
        manifest.append({"path": path.relative_to(root).as_posix(), "content": text})
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


if __name__ == "__main__":
    print(f"promptVersion={prompt_version()}")
