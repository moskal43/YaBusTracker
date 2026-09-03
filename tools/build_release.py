"""Build a deterministic local install archive without secrets or test artifacts."""

import json
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads(
        (ROOT / "custom_components/yandex_transit/manifest.json").read_text()
    )
    output = ROOT / f"dist/YaBusTracker-{manifest['version']}.zip"
    output.parent.mkdir(exist_ok=True)
    files = [
        *sorted((ROOT / "custom_components/yandex_transit").rglob("*.py")),
        *sorted((ROOT / "custom_components/yandex_transit").rglob("*.json")),
        *sorted((ROOT / "custom_components/yandex_transit/brand").glob("*.png")),
        ROOT / "hacs.json",
        ROOT / "LICENSE",
        ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / "CHANGELOG.md",
        ROOT / "custom_components/yandex_transit/LICENSE",
        ROOT / "README.md",
        *sorted((ROOT / "examples").glob("*.yaml")),
        ROOT / "docs/install.md",
    ]
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(files):
            info = ZipInfo(
                path.relative_to(ROOT).as_posix(), date_time=(2026, 9, 3, 0, 0, 0)
            )
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    print(f"{output.name}: {len(files)} files, {output.stat().st_size} bytes")
    print(f"sha256: {sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
