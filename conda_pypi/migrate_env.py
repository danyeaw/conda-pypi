"""
Rewrite an environment.yaml by promoting pip packages to conda dependencies
when they are available in a wheels channel.

Uses a conda solver dry-run to determine which packages can be promoted:
all pip packages are tentatively moved to conda deps, the solver is invoked,
and only the packages the solver could not find are put back in the pip block.
"""

from __future__ import annotations

import copy
import logging
import sys
from pathlib import Path
from typing import Any

from conda.base.context import context, fresh_context
from conda.cli.main import main_subshell
from conda.exceptions import DryRunExit, PackagesNotFoundError, UnsatisfiableError
from packaging.requirements import InvalidRequirement, Requirement
from ruamel.yaml import YAML

from conda_pypi.convert_tree import parse_libmamba_solver_error, parse_rattler_solver_error
from conda_pypi.name_mapping import pypi_to_conda_name

logger = logging.getLogger(__name__)

DEFAULT_WHEELS_CHANNEL = "conda-pypi"


_PIP_ONLY_PREFIXES = (
    "-e ",  # editable installs: -e . / -e ./path / -e git+...
    "./",  # relative local paths
    "../",
    "/",  # absolute local paths
    "git+",  # VCS URLs
    "hg+",
    "svn+",
    "bzr+",
    "http://",  # direct URL dependencies
    "https://",
)


def _is_pip_only(dep: str) -> bool:
    """Return True for dep syntaxes that are pip-specific and cannot be conda packages."""
    return dep.startswith(_PIP_ONLY_PREFIXES)


def _pip_dep_to_conda(pip_dep: str, name_mapping: dict | None) -> tuple[str, str]:
    """Parse a pip dependency string and return ``(conda_name, conda_dep_string)``.

    The conda dep string preserves the version specifier, e.g.
    ``requests>=2.28.0`` stays ``requests>=2.28.0``.  The name is translated
    via :func:`~conda_pypi.name_mapping.pypi_to_conda_name`.
    """
    req = Requirement(pip_dep)
    conda_name = pypi_to_conda_name(req.name, name_mapping)
    specifier = str(req.specifier)
    conda_dep = f"{conda_name}{specifier}" if specifier else conda_name
    return conda_name, conda_dep


def migrate_environment(
    env_data: dict,
    channel_urls: list[str],
    name_mapping: dict | None = None,
) -> tuple[dict, list[str]]:
    """Rewrite *env_data* in-place, promoting pip packages via a conda solver dry-run.

    All pip packages are first translated to conda names and tentatively
    promoted.  A ``conda env create --dry-run`` is then run with *channel_urls*
    added to the channels list.  Packages the solver cannot find are demoted
    back to the pip block.

    Returns ``(env_data, warnings)`` where *warnings* is a list of human-readable
    messages about packages that could not be promoted.
    """
    warnings: list[str] = []

    deps: list = env_data.get("dependencies") or []
    pip_block_idx: int | None = None
    pip_list: list[str] = []
    for i, dep in enumerate(deps):
        if isinstance(dep, dict) and "pip" in dep:
            pip_block_idx = i
            pip_list = list(dep["pip"])
            break

    if pip_block_idx is None or not pip_list:
        return env_data, warnings

    # Build a list of (original_pip_dep, conda_name, conda_dep_string) triples.
    # Unparseable entries go straight to remaining_pip.
    # _Entry is (original_pip, conda_name_lower, conda_dep_string)
    translatable: list[tuple[str, str, str]] = []
    remaining_pip: list[str] = []

    for pip_dep in pip_list:
        pip_dep_str = str(pip_dep).strip()
        if _is_pip_only(pip_dep_str):
            logger.debug("Keeping pip-only dependency in pip section: %s", pip_dep_str)
            remaining_pip.append(pip_dep_str)
            continue
        try:
            conda_name, conda_dep = _pip_dep_to_conda(pip_dep_str, name_mapping)
        except InvalidRequirement:
            warnings.append(
                f"Could not parse pip dependency '{pip_dep_str}' — keeping in pip section."
            )
            remaining_pip.append(pip_dep_str)
            continue
        translatable.append((pip_dep_str, conda_name.lower(), conda_dep))

    if not translatable:
        return env_data, warnings

    # Build a trial env dict with all translatable packages promoted.
    trial_env = copy.deepcopy(dict(env_data))
    trial_deps: list = trial_env.setdefault("dependencies", [])

    # Add wheels channels to the trial env.
    trial_channels: list = trial_env.setdefault("channels", [])
    for url in channel_urls:
        if url not in trial_channels:
            trial_channels.append(url)

    # Remove the pip block and append all promoted conda deps.
    trial_pip_idx = next(
        (i for i, d in enumerate(trial_deps) if isinstance(d, dict) and "pip" in d),
        None,
    )
    if trial_pip_idx is not None:
        del trial_deps[trial_pip_idx]
    for _, _, conda_dep in translatable:
        trial_deps.append(conda_dep)

    # Run the conda solver dry-run; collect missing package names (lowercase).
    missing_conda_names: set[str] = _dry_run_solve(trial_env)

    # Partition translatable entries into promoted vs demoted.
    promoted_conda_deps: list[str] = []
    demoted_pip: list[str] = []

    for original_pip, conda_name_lower, conda_dep in translatable:
        if conda_name_lower in missing_conda_names:
            demoted_pip.append(original_pip)
            warnings.append(
                f"'{original_pip}' (conda name: '{conda_name_lower}') could not be resolved"
                " in the conda channels — keeping in pip section."
            )
        else:
            promoted_conda_deps.append(conda_dep)

    all_pip = remaining_pip + demoted_pip

    # Apply changes to the original env_data.
    if promoted_conda_deps:
        # Insert promoted packages before the pip block position.
        insert_at = pip_block_idx
        for dep in promoted_conda_deps:
            deps.insert(insert_at, dep)
            insert_at += 1
        # The pip block has shifted down by len(promoted_conda_deps).
        pip_block_idx = insert_at

    if all_pip:
        deps[pip_block_idx]["pip"] = all_pip
    else:
        del deps[pip_block_idx]
        # Remove the bare "pip" conda dep — it was only needed to support the
        # pip: block.  Leave version-constrained entries (e.g. "pip>=23") alone
        # since those signal an intentional version requirement.
        deps[:] = [d for d in deps if not (isinstance(d, str) and d.strip().lower() == "pip")]

    # Add channels to the real env_data only when something was actually promoted.
    if promoted_conda_deps:
        actual_channels: list = env_data.setdefault("channels", [])
        for url in channel_urls:
            if url not in actual_channels:
                actual_channels.append(url)

    return env_data, warnings


def _specs_from_env(env_data: dict) -> list[str]:
    """Extract flat conda dep strings from *env_data*, skipping the pip sub-dict."""
    specs: list[str] = []
    for dep in env_data.get("dependencies") or []:
        if isinstance(dep, dict):
            continue  # skip pip: block
        specs.append(str(dep))
    return specs


def _dry_run_solve(env_data: dict) -> set[str]:
    """Run ``conda create --dry-run`` with the deps and channels from *env_data*.

    Uses ``conda create`` (not ``conda env create``) so that all configured
    solver backends — including rattler, which is required for v3.whl repodata
    from the conda-pypi channel — are supported.

    Returns the set of lowercase conda package names that the solver could
    not find.  Returns an empty set when the solve succeeds.
    """
    specs = _specs_from_env(env_data)
    channel_args: list[str] = []
    for ch in env_data.get("channels") or []:
        channel_args += ["--channel", str(ch)]

    cmd = [
        "create",
        "--dry-run",
        "--name",
        "_conda_pypi_migrate_dryrun_",
        *channel_args,
        *specs,
    ]

    try:
        with fresh_context(solver=context.solver):
            main_subshell(*cmd)
    except DryRunExit:
        # Success — the solve produced a valid plan.
        return set()
    except PackagesNotFoundError as exc:
        pkgs: list[str] = exc._kwargs.get("packages", [])
        return {str(p).split("[")[0].split(" ")[0].lower() for p in pkgs}
    except UnsatisfiableError as exc:
        missing: set[str] = set()
        missing.update(parse_libmamba_solver_error(exc.message))
        missing.update(parse_rattler_solver_error(exc.message))
        return {p.lower() for p in missing}
    except Exception as exc:
        logger.warning("Unexpected solver error during dry-run: %s", exc)
        return set()

    return set()


def load_env_file(path: Path) -> Any:
    """Load *path* with ruamel.yaml, preserving comments and block style."""
    yaml = _make_yaml()
    with open(path) as fh:
        return yaml.load(fh)


def dump_env(env_data: Any, dest: Path | None = None) -> None:
    """Write *env_data* to *dest* or stdout when *dest* is ``None``."""
    yaml = _make_yaml()
    if dest is None:
        yaml.dump(env_data, sys.stdout)
    else:
        with open(dest, "w") as fh:
            yaml.dump(env_data, fh)


def _make_yaml() -> YAML:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    return yaml
