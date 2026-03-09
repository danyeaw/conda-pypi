"""
Tests for making sure the conda_local_channel fixture functions as we expect
"""

import json
import urllib.request
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


HERE = Path(__file__).parent


def test_conda_channel(conda_local_channel):
    """Verify the conda channel server is working."""
    url = f"{conda_local_channel}/noarch/repodata.json"
    with urllib.request.urlopen(url) as response:
        repodata = json.loads(response.read())

    assert "packages.whl" in repodata
    assert len(repodata["packages.whl"]) > 0


def test_conda_channel_extras_in_repodata():
    """Verify that wheel entries with extras are present in the repodata."""
    repodata = json.loads((HERE / "conda_local_channel" / "noarch" / "repodata.json").read_text())

    record = repodata["packages.whl"]["requests-2.32.5-py3_none_any_0"]
    assert "extras" in record
    socks_deps = record["extras"]["socks"]
    assert len(socks_deps) == 1
    req = Requirement(socks_deps[0])
    assert req.name == "pysocks"
    assert req.specifier == SpecifierSet(">=1.5.6,!=1.5.7")
