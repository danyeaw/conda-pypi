# PEP 508 marker conversion

## Context

PyPI [environment markers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/#environment-markers) (`python_version`, `sys_platform`, `extra`, and related variables) are not valid conda `MatchSpec` syntax. conda-pypi **translates** them into dependency strings that may include **`[when="…"]`**, with the inner expression JSON-encoded (`json.dumps`) so nested quotes are safe.

Translation **does not** evaluate markers against the build machine at conversion time. Output is shaped for conda-style metadata and experimental repodata (including rattler-oriented consumers).

This topic is **not** [PEP 668 `EXTERNALLY-MANAGED`](../features.md#environment-marker-files) (marker *files* vs dependency markers).

## Optional dependency extras

Syntax such as `httpx[cli]>=0.24` denotes **PEP 508 optional extras** on the dependency name. That is distinct from the environment marker `extra == "dev"`. Brackets are preserved (sorted) via {py:func}`conda_pypi.markers.dependency_extras_suffix`. Aggregate forms such as `requests[extras=all]` are not broadly supported in conda; behavior varies by conda/rattler version.

## PEP 508 variables (PyPI census, Jan 2025)

The table is ordered by how often each variable appears in PyPI dependency metadata. The **Support** column describes `_normalize_marker_clause` in {py:mod}`conda_pypi.markers`: emit material for `when`, drop the atom, or special-case `extra`.

| Marker variable | ~Uses on PyPI (Jan 2025) | Support in conda-pypi |
| ----------------- | -----------------------: | --------------------- |
| `python_version` | 2,034,408 | Emits `python…` fragments; `not in "a, b"` becomes multiple `python!=…` terms. |
| `platform_system` | 243,706 | Maps known literals to virtual packages (`__win`, `__linux`, `__osx`, …). |
| `sys_platform` | 223,549 | Same mapping; partial handling of `!=` (e.g. `!= "win32"` → `__unix`). |
| `platform_machine` | 145,549 | Omitted—limited alignment between PEP 508 arch strings and conda virtuals. |
| `platform_python_implementation` | 89,434 | Partial: common interpreters omitted so noarch paths are not over-restricted. |
| `python_full_version` | 25,840 | Same rules as `python_version`. |
| `implementation_name` | 22,158 | Same general approach as `platform_python_implementation`. |
| `os_name` | 17,294 | `nt` / `windows` → `__win`, `posix` → `__unix`; partial `!=` handling. |
| `platform_release` | 6,316 | Omitted. |
| `platform_version` | 241 | Omitted. |
| `implementation_version` | 44 | Omitted. |
| `extra` | — | Drives `extra_depends` / extras map; remaining conditions may attach as `[when=…]` on that dependency. |

Variables not listed produce no fragment. Boolean `and` / `or` use `_combine_conditions` to retain a usable branch when one side cannot be translated.

Omissions are mostly **intentional**: virtual-package coverage is bounded, architecture strings map poorly to conda subdirs, and the default stance is slightly **permissive** on noarch-style metadata rather than incorrectly excluding dependencies.

## Where this runs in the codebase

| Location | Role |
| -------- | ---- |
| {py:mod}`conda_pypi.markers` | Marker AST walk and clause normalization. |
| {py:func}`conda_pypi.markers.extract_marker_condition_and_extras` | Splits a {py:class}`packaging.markers.Marker` into a condition string and `extra` names. |
| {py:func}`conda_pypi.markers.pypi_to_repodata_noarch_whl_entry` | Experimental `v3.whl` repodata from PyPI JSON; names use {py:func}`conda_pypi.name_mapping.pypi_to_conda_name`. |
| {py:func}`conda_pypi.translate.requires_to_conda` | `depends` / `extras` when building `.conda` packages from wheel `METADATA`. |

## `MatchSpec` vs `[when=…]`

**Current state:** `conda.models.match_spec.MatchSpec` does not expose a `when` field, so strings such as `pkg >=1[when="…"]` cannot be passed directly to `MatchSpec(...)`.

**Policy:** conda-pypi **still emits** `[when=…]` in converted metadata and repodata for forward-compatible consumers.

**Workaround:** Call sites that must parse a string with `MatchSpec` (e.g. {py:func}`conda_pypi.downloader.find_package`, {py:func}`conda_pypi.utils.pypi_spec_variants`) run {py:func}`conda_pypi.utils.matchspec_str_for_conda_parse` first to remove a trailing `[when=…]`. That shim should be **removed** once supported conda versions accept `when` in spec strings, or if the project changes encoding.

**Risk:** Stripping `when` for those paths may fetch PyPI wheels that a strict conditional install would omit on another platform—consistent with other conservative over-approximations (e.g. dropped atoms becoming unconditional).

If no translatable atoms remain and there is no `extra`, the dependency is recorded without `when` (somewhat broader than strict PEP 508).

## Implementation note

`Marker._markers` from `packaging` is private; restrict use to {py:mod}`conda_pypi.markers` to contain upgrade risk.
