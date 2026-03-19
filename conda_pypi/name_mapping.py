"""PyPI ↔ conda package name mapping.

Default table is derived from grayskull (``grayskull_pypi_mapping.json``).
Keys are PyPI canonical names from :func:`packaging.utils.canonicalize_name`.
"""

from __future__ import annotations

import json
import pkgutil

from packaging.utils import canonicalize_name

# conda_pypi.name_mapping.grayskull_pypi_mapping['zope-hookable']
# {
#     "pypi_name": "zope-hookable",
#     "conda_name": "zope.hookable",
#     "import_name": "zope.hookable",
#     "mapping_source": "regro-bot",
# }
grayskull_pypi_mapping: dict[str, dict] = json.loads(
    pkgutil.get_data("conda_pypi", "grayskull_pypi_mapping.json") or "{}"
)

_to_pypi_name_map: dict[str, dict] = {}


def pypi_to_conda_name(pypi_name: str, pypi_to_conda_name_mapping: dict | None = None) -> str:
    pypi_name = canonicalize_name(pypi_name)
    return (
        pypi_to_conda_name_mapping
        if pypi_to_conda_name_mapping is not None
        else grayskull_pypi_mapping
    ).get(
        pypi_name,
        {
            "pypi_name": pypi_name,
            "conda_name": pypi_name,
            "import_name": None,
            "mapping_source": None,
        },
    )["conda_name"]


def conda_to_pypi_name(name: str) -> str:
    if not _to_pypi_name_map:
        for value in grayskull_pypi_mapping.values():
            conda_name = value["conda_name"]
            # XXX sometimes conda:pypi is n:1
            _to_pypi_name_map[conda_name] = value

    found = _to_pypi_name_map.get(name)
    if found:
        name = found["pypi_name"]
    return canonicalize_name(name)
