# PEP 508 marker conversion

PyPI dependency lines can include [environment markers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/#environment-markers) — expressions like `python_version`, `sys_platform`, and `extra` that constrain when a dependency applies. Conda solvers do not consume PEP 508 marker syntax directly; they work with `MatchSpec` strings with optional `[when="…"]` clauses, so conda-pypi translates marker expressions into that shape rather than evaluating them against the current Python at conversion time.

This page covers the translation policy and where it runs in the codebase. It is not the same topic as [PEP 668 `EXTERNALLY-MANAGED`](../features.md#environment-marker-files) (environment marker *files* for pip).

## Dependency optional extras

Brackets on the dependency itself — e.g. `httpx[cli]>=0.24` — indicate PEP 508 optional extras for that package, distinct from the environment marker `extra == "dev"`. conda-pypi copies those brackets onto conda dependency strings (sorted for stability) via {py:func}`conda_pypi.markers.dependency_extras_suffix`. This keeps metadata faithful to PyPI and aligns with how `conda pypi install` builds named root specs like `httpx[cli]`.

conda does not yet support aggregate syntax such as `requests[extras=all]`. Optional groups must be named explicitly. Because this part of the conda ecosystem is still evolving, emitting accurate bracket extras is primarily a metadata-fidelity measure; end-to-end solve behavior depends on your conda or rattler version.

## PEP 508 variables: usage on PyPI and conda-pypi support

The counts below reflect how often each marker variable appeared in PyPI dependency metadata as of January 2025, ordered by frequency. They indicate how much of the ecosystem each translation rule covers.

"Support" describes what `_normalize_marker_clause` in {py:mod}`conda_pypi.markers` does when that variable appears in a marker atom: emit a condition fragment for `when`, drop the atom silently (contributing nothing to `and`/`or`), or handle it as a special case (`extra`).

| Marker variable | ~Uses on PyPI (Jan 2025) | Support in conda-pypi |
| --------------- | -----------------------: | --------------------- |
| `python_version` | 2,034,408 | Translated to a `python…` MatchSpec fragment (e.g. `python<3.11`). `not in "a, b"` becomes a conjunction of `python!=…` clauses. |
| `platform_system` | 243,706 | Known values map to virtual packages (`__win`, `__linux`, `__osx`, …). Unrecognized values or unsupported operators yield no fragment. |
| `sys_platform` | 223,549 | Same virtual-package mapping as `platform_system`. `!=` is partial: `!= "win32"` collapses to `__unix`; other negations may yield no fragment. |
| `platform_machine` | 145,549 | Not supported — atom is always dropped. Conda virtual packages are far more specific than a single PEP 508 arch string. |
| `platform_python_implementation` | 89,434 | Partial — common implementations (`cpython`, `pypy`, `jython`) drop the atom; no build-string translation yet. |
| `python_full_version` | 25,840 | Translated using the same rules as `python_version`. |
| `implementation_name` | 22,158 | Same partial handling as `platform_python_implementation`. |
| `os_name` | 17,294 | `nt` / `windows` → `__win`, `posix` → `__unix`. `!=` toggles between win and unix-style virtuals for known values. |
| `platform_release` | 6,316 | Not supported — atom omitted. |
| `platform_version` | 241 | Not supported — atom omitted. |
| `implementation_version` | 44 | Not supported — atom omitted. |
| `extra` | *(not in this census)* | Special — never part of the `when` string. Values route the dependency to `extra_depends` or the package extras map, with any non-`extra` conditions attached as `[when="…"]` on that dependency. |

Any PEP 508 variable not listed here also produces no fragment for that atom.

Boolean combinations follow `and` / `or`: if one side has no translation, the combiner (`_combine_conditions`) still emits a useful condition from the other side.

### Why some marker dimensions are not supported

`sys_platform` / `platform_system` — negation and disjunction on PyPI are common ("not Windows"), but conda-pypi maps only a small set of known literals to virtual packages. Broader support would require more virtual packages and a clearer policy for uncommon values.

`platform_machine` — arch strings like `x86_64` or `aarch64` are very specific. Mapping them to conda virtual packages for noarch-style metadata is fragile, and the relationship between PyPI platform tags and conda subdirs is not 1:1.

`platform_python_implementation` / `implementation_name` — a full mapping could align with conda build strings, but today common "default" interpreters simply drop the constraint so the dependency is not incorrectly excluded on noarch paths.

## Where translation is used

| Location | Role |
| -------- | ---- |
| {py:mod}`conda_pypi.markers` | Core AST walk and clause normalization. |
| {py:func}`conda_pypi.markers.extract_marker_condition_and_extras` | Splits a {py:class}`packaging.markers.Marker` into an optional condition string and any `extra == "…"` names. |
| {py:func}`conda_pypi.markers.pypi_to_repodata_noarch_whl_entry` | Builds experimental wheel repodata entries (`depends`, `extra_depends`) from a PyPI JSON API response. Record and dependency names use {py:func}`conda_pypi.name_mapping.pypi_to_conda_name` (same as `requires_to_conda`). |
| {py:func}`conda_pypi.translate.requires_to_conda` | Populates `depends` and `extras` when building `.conda` packages from wheel `METADATA`. Used by `conda pypi install`, `conda pypi convert`, and similar flows. |

Both paths share the same `[when=…]` encoding: the inner condition is passed through `json.dumps` so quotes and special characters are safe inside the bracket metadata.

### When conditions vanish

If every translatable atom is dropped and there are no `extra` atoms, the dependency is recorded without a `when` clause. This is conservative — it slightly over-approximates install sets compared to strict PEP 508 evaluation.

## Implementation note

Translation inspects `Marker._markers`, which is a private attribute of `packaging`. All access is confined to {py:mod}`conda_pypi.markers` so future `packaging` upgrades only require changes in one module.

## Tests

- `tests/test_markers.py` — unit tests for extraction and repodata shaping.
- `tests/test_translate.py` — `requires_to_conda` marker behavior.
- `tests/test_conda_local_channel.py` — integration checks against committed wheel repodata fixtures.
