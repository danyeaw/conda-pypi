# PEP 508 marker conversion

This page documents how conda-pypi translates PEP 508 environment markers for repodata and for wheel → `.conda` conversion, and how that interacts with conda's `MatchSpec`.

## Context

PyPI [environment markers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/#environment-markers) (`python_version`, `sys_platform`, `extra`, and related variables) are not valid conda `MatchSpec` syntax on their own. For experimental wheel repodata ({py:func}`conda_pypi.markers.pypi_to_repodata_noarch_whl_entry`), conda-pypi translates marker logic into dependency strings that may append an experimental `[when="…"]` bracket suffix. The inner condition is JSON-encoded (`json.dumps`) so nested quotes are safe; that suffix is not standard conda `MatchSpec` yet (see below).

When building `.conda` packages from wheel `METADATA` ({py:func}`conda_pypi.translate.requires_to_conda`), markers are not encoded as `[when="…"]` (conda's `MatchSpec` does not parse `when` today). That path follows the historical behavior: only `extra == "…"` is split into the extras map; other marker dimensions are omitted from `depends`.

Translation does not evaluate markers against the build machine at conversion time. Output is shaped for conda-style metadata and repodata.

This topic is not [PEP 668 `EXTERNALLY-MANAGED`](../features.md#environment-marker-files) (marker *files* vs dependency markers).

## Optional dependency extras

Syntax such as `httpx[cli]>=0.24` denotes PEP 508 optional extras on the dependency name. That is distinct from the environment marker `extra == "dev"`. The [dependency specifier grammar](https://packaging.python.org/en/latest/specifications/dependency-specifiers/) allows a comma-separated list of extra names; multiple names union their requirements. There is no reserved name meaning “all extras.” Brackets are preserved (sorted) via {py:func}`conda_pypi.markers.dependency_extras_suffix`.

Serialized MatchSpec forms such as `pkg[extras=[a,b]]` are separate from PEP 508’s `pkg[a,b]` spelling. Optional extras carried in repodata are resolved by the solver: Rattler implements this as an experimental feature. conda’s `MatchSpec` parser does not yet cover those extended bracket forms or the `[when="…"]` syntax.

## PEP 508 variables

The table is ordered by how often each variable appears in PyPI dependency metadata (census from PyPI, January 2025). **Supported** summarizes whether `_normalize_marker_clause` in {py:mod}`conda_pypi.markers` emits a fragment for `when`, partially handles it, or omits it. **Notes** describe what is translated or why it is skipped.

| Marker variable | ~Uses on PyPI | Supported | Notes |
| --- | ---: | :--- | --- |
| `python_version` | 2,034,408 | Yes | Emits `python…` fragments; `not in "a, b"` becomes multiple `python!=…` terms. |
| `platform_system` | 243,706 | Yes | Maps known literals to virtual packages (`__win`, `__linux`, `__osx`, …). |
| `sys_platform` | 223,549 | Partial | Same mapping as `platform_system`; partial handling of `!=` (e.g. `!= "win32"` → `__unix`). |
| `platform_machine` | 145,549 | No | No fragment; limited alignment between PEP 508 arch strings and conda virtuals. |
| `platform_python_implementation` | 89,434 | Partial | Common interpreters omitted so noarch paths are not over-restricted. |
| `python_full_version` | 25,840 | Yes | Same rules as `python_version`. |
| `implementation_name` | 22,158 | Partial | Same general approach as `platform_python_implementation`. |
| `os_name` | 17,294 | Partial | `nt` / `windows` → `__win`, `posix` → `__unix`; partial `!=` handling. |
| `platform_release` | 6,316 | No | Omitted. |
| `platform_version` | 241 | No | Omitted. |
| `implementation_version` | 44 | No | Omitted. |
| `extra` | — | Yes | Drives `extra_depends` / extras map; in repodata, remaining conditions may attach as `[when="…"]` on that dependency. |

Variables not listed produce no fragment. Boolean `and` / `or` use `_combine_conditions` to retain a usable branch when one side cannot be translated.

Omissions are mostly intentional: virtual-package coverage is bounded, architecture strings map poorly to conda subdirs, and the default stance is slightly permissive on noarch-style metadata rather than incorrectly excluding dependencies.

## Where this runs in the codebase

| Location | Role |
| -------- | ---- |
| {py:mod}`conda_pypi.markers` | Marker AST walk and clause normalization. |
| {py:func}`conda_pypi.markers.extract_marker_condition_and_extras` | Splits a {py:class}`packaging.markers.Marker` into a condition string and `extra` names. |
| {py:func}`conda_pypi.markers.pypi_to_repodata_noarch_whl_entry` | Experimental `v3.whl` repodata from PyPI JSON; names use {py:func}`conda_pypi.name_mapping.pypi_to_conda_name`. |
| {py:func}`conda_pypi.translate.requires_to_conda` | `depends` / `extras` when building `.conda` packages from wheel `METADATA` (no `[when="…"]`; extras-only marker routing). |

## MatchSpec and `[when="…"]`

Strings such as `pkg >=1[when="…"]` are not valid conda `MatchSpec` input today: `conda.models.match_spec.MatchSpec` does not expose a `when` field, and the bracket encoding is experimental. Proposed standardization of conditional dependencies and the serialized `when` syntax lives in [CEP PR #111](https://github.com/conda/ceps/pull/111) (conditional dependencies, extras, and flags). If that CEP is approved and implemented in conda, these strings may become first-class `MatchSpec` forms.

conda-pypi emits `[when="…"]` in experimental repodata for solvers that understand it (Rattler). Wheel → `.conda` `index.json` does not include `[when="…"]` on dependency strings until conda’s `MatchSpec` can represent them.

If no translatable atoms remain and there is no `extra`, the dependency is recorded without `when` (somewhat broader than strict PEP 508).

## Implementation note

`Marker._markers` from `packaging` is private; restrict use to {py:mod}`conda_pypi.markers` to contain upgrade risk.
