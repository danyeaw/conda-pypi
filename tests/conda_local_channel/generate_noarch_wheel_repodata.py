"""
Utility for generating test-specific local channel repodata.

Run this script to regenerate ``tests/conda_local_channel/noarch/repodata.json``
from the packages listed in ``wheel_packages.txt``. Fetches PyPI JSON in parallel,
then writes channel files via conda-index (experimental ``repodata_v3`` layout).

Not for production.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from conda_index.index import ChannelIndex
from conda_index.utils import CONDA_PACKAGE_EXTENSIONS

from conda_pypi.markers import pypi_to_repodata_noarch_whl_entry

SUBDIR = "noarch"


def get_repodata_entry(name: str, version: str) -> dict[str, Any] | None:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    data = response.json()
    if not data:
        return None
    return pypi_to_repodata_noarch_whl_entry(data)


def parse_wheel_packages(path: Path) -> list[tuple[str, str]]:
    packages: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            print(f"  skip (expected name==version): {line!r}")
            continue
        n, v = line.split("==", 1)
        packages.append((n.strip(), v.strip()))
    return packages


def index_wheel_entries(channel_root: Path, entries: list[dict[str, Any]]) -> None:
    (channel_root / SUBDIR).mkdir(parents=True, exist_ok=True)

    channel_index = ChannelIndex(
        channel_root,
        channel_root.name,
        subdirs=[SUBDIR],
        repodata_v3=True,
        update_only=False,
        save_fs_state=False,
        write_current_repodata=False,
        write_zst=True,
        compact_json=False,
        cache_kwargs={"package_extensions": CONDA_PACKAGE_EXTENSIONS + (".whl",)},
    )
    cache = channel_index.cache_for_subdir(SUBDIR)

    stated = [(rec, int(rec.get("timestamp", 1))) for rec in entries]

    cache.store_fs_state(
        (
            {
                "path": cache.database_path(rec["fn"]),
                "mtime": ts,
                "size": rec["size"],
            }
            for rec, ts in stated
        )
    )

    for rec, ts in stated:
        idx = dict(rec)
        idx["md5"] = None
        assert "sha256" in idx and "fn" in idx
        cache.store(
            cache.database_path(rec["fn"]),
            idx["size"],
            ts,
            {},
            idx,
        )

    channel_index.index(patch_generator=None)
    channel_index.update_channeldata(rss=False)


if __name__ == "__main__":
    here = Path(__file__).parent.resolve()
    packages = parse_wheel_packages(here / "wheel_packages.txt")
    entries: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(get_repodata_entry, n, v): (n, v) for n, v in packages}
        for future in as_completed(futures):
            n, v = futures[future]
            try:
                result = future.result()
                if result:
                    entries.append(result)
            except Exception as e:
                print(f"Error processing {n} {v}: {e}")

    index_wheel_entries(here, entries)
    print(f"Wrote conda-index output under {here} ({len(entries)} wheels).")
