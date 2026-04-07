"""
Tests for making sure the conda_local_channel fixture functions as we expect

This module intentionally validates marker-conversion edge cases using
selected pure-Python wheels in `wheel_packages.txt` (for example `ipython`,
`uvicorn`, `0x-web3`, `adup`, and `advancedselector`).
"""

import json
import re
import urllib.request
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


HERE = Path(__file__).parent


def _v3_whl_record(repodata: dict, *, name: str, version: str) -> dict:
    """Resolve a wheel record by conda ``name`` / ``version`` (not v3 dict keys)."""
    matches = [
        r
        for r in repodata["v3"]["whl"].values()
        if r.get("name") == name and r.get("version") == version
    ]
    assert len(matches) == 1, (
        f"expected one v3.whl record for {name}=={version}, got {len(matches)}"
    )
    return matches[0]


def test_conda_channel(conda_local_channel):
    """Verify the conda channel server is working."""
    url = f"{conda_local_channel}/noarch/repodata.json"
    with urllib.request.urlopen(url) as response:
        repodata = json.loads(response.read())

    assert "v3" in repodata
    assert "whl" in repodata["v3"]
    assert len(repodata["v3"]["whl"]) > 0


def test_local_channel_repodata_no_per_package_record_version():
    """Wheel entries omit per-package record_version; repodata comes from conda-index."""
    repodata = json.loads((HERE / "conda_local_channel" / "noarch" / "repodata.json").read_text())
    assert isinstance(repodata.get("repodata_version"), int)
    assert "repodata_revisions" in repodata["info"]
    for record in repodata["v3"]["whl"].values():
        assert "record_version" not in record


def test_conda_channel_extras_in_repodata():
    """Verify that wheel entries keep extras as a dedicated repodata field."""
    repodata = json.loads((HERE / "conda_local_channel" / "noarch" / "repodata.json").read_text())

    record = _v3_whl_record(repodata, name="requests", version="2.32.5")
    assert "extra_depends" in record
    socks_dep = record["extra_depends"]["socks"][0]
    base_req = Requirement(socks_dep)
    assert base_req.name == "pysocks"
    assert base_req.specifier == SpecifierSet(">=1.5.6,!=1.5.7")


def test_conditional_dependencies_stay_in_depends():
    """Verify non-extra markers are encoded as `when` conditions in `depends`."""
    repodata = json.loads((HERE / "conda_local_channel" / "noarch" / "repodata.json").read_text())

    record = _v3_whl_record(repodata, name="annotated-types", version="0.7.0")
    assert any(
        dep.startswith("typing_extensions>=4.0.0") and '[when="python<3.9"]' in dep
        for dep in record["depends"]
    )


def test_sys_platform_markers_are_normalized_for_ipython():
    """IPython marker dependencies should use virtual-package conditions."""
    repodata = json.loads((HERE / "conda_local_channel" / "noarch" / "repodata.json").read_text())

    record = _v3_whl_record(repodata, name="ipython", version="8.30.0")
    colorama_dep = next(dep for dep in record["depends"] if dep.startswith("colorama"))
    assert '[when="__win"]' in colorama_dep

    pexpect_dep = next(dep for dep in record["depends"] if dep.startswith("pexpect>4.3"))
    assert '[when="__unix"]' in pexpect_dep
    assert "sys_platform" not in pexpect_dep


def test_uvicorn_standard_extra_has_clean_when_condition():
    """Uvicorn extra deps should not emit malformed logical expressions."""
    repodata = json.loads((HERE / "conda_local_channel" / "noarch" / "repodata.json").read_text())

    record = _v3_whl_record(repodata, name="uvicorn", version="0.34.0")
    uvloop_dep = next(
        dep for dep in record["extra_depends"]["standard"] if dep.startswith("uvloop")
    )
    assert '[when="__unix"]' in uvloop_dep
    assert "and and" not in uvloop_dep
    assert "or or" not in uvloop_dep
    assert "sys_platform" not in uvloop_dep
    assert re.search(r"\b(and|or)\s*\)", uvloop_dep) is None


def test_extended_marker_families_are_normalized_in_examples():
    """Known edge-case marker families should normalize in selected records."""
    repodata = json.loads((HERE / "conda_local_channel" / "noarch" / "repodata.json").read_text())

    web3_record = _v3_whl_record(repodata, name="0x-web3", version="4.8.2.1")
    cytoolz_dep = next(dep for dep in web3_record["depends"] if dep.startswith("cytoolz"))
    toolz_dep = next(dep for dep in web3_record["depends"] if dep.startswith("toolz<1.0.0"))
    assert "[when=" not in cytoolz_dep
    assert "[when=" not in toolz_dep

    aba_record = _v3_whl_record(repodata, name="aba-cli-scrapper", version="0.7.6")
    nodeenv_dep = next(dep for dep in aba_record["depends"] if dep.startswith("nodeenv==1.9.1"))
    charset_dep = next(
        dep for dep in aba_record["depends"] if dep.startswith("charset-normalizer==3.3.2")
    )
    assert '[when="' in nodeenv_dep
    assert "python>=2.7" in nodeenv_dep
    assert "python!=3.0" in nodeenv_dep
    assert "python!=3.6" in nodeenv_dep
    assert "python_version" not in nodeenv_dep
    assert '[when="python>=3.7.0"]' in charset_dep
    assert "python_full_version" not in charset_dep

    adup_record = _v3_whl_record(repodata, name="adup", version="0.1.0")
    psutil_dep = next(
        dep for dep in adup_record["extra_depends"]["testing"] if dep.startswith("psutil")
    )
    assert "[when=" not in psutil_dep

    advancedselector_record = _v3_whl_record(repodata, name="advancedselector", version="3.1.0")
    getch_dep = next(dep for dep in advancedselector_record["depends"] if dep.startswith("getch"))
    assert '[when="__unix"]' in getch_dep

    ali2b_record = _v3_whl_record(repodata, name="ali2b-cli-scrapper", version="1.0.1")
    greenlet_dep = next(
        dep for dep in ali2b_record["depends"] if dep.startswith("greenlet==3.0.3")
    )
    assert "[when=" not in greenlet_dep
    assert "or" not in greenlet_dep
