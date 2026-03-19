# PEP 508 marker conversion

PyPI dependency lines can include [environment markers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/#environment-markers) (`python_version`, `sys_platform`, `extra`, and many others). Conda solvers do not consume PEP 508 marker syntax directly; they work with `MatchSpec` strings, including optional `**[when="…"]**` clauses, so conda-pypi **translates** marker expressions into that shape instead of only evaluating them against the current Python at conversion time.

This page describes the translation policy and where it runs in the codebase. It is **not** the same topic as [PEP 668 `EXTERNALLY-MANAGED`](../features.md#environment-marker-files) (environment marker *files* for pip).

**Dependency optional extras** (brackets on the *dependency* itself, e.g. `httpx[cli]>=0.24`, not the same as environment marker `extra == "dev"`) are copied onto conda dependency strings as `[cli,…]` (sorted when several) via {py:func}`conda_pypi.markers.dependency_extras_suffix`, used in {py:func}`conda_pypi.translate.requires_to_conda` and {py:func}`conda_pypi.markers.pypi_to_repodata_noarch_whl_entry`. Goal: PyPI-faithful metadata and alignment with how `conda pypi install` builds **named** root specs (`pkg[extra1,extra2]` with explicit groups).

### Conda `MatchSpec` extras (current limits)

conda does **not** yet support **aggregate** optional-extra syntax like `requests[extras=all]` (one spec meaning “install every extra group”). Optional groups remain **named** (`requests[socks]`, `httpx[cli,http2]`) where the stack implements them.

Because that story is still evolving, emitting PEP 508–accurate brackets is primarily **metadata parity** with PyPI; end-to-end solve behavior depends on your conda / rattler version and may not match pip for every edge case until the ecosystem completes extras support.

## PEP 508 variables: usage on PyPI and conda-pypi support

The approximate counts below are how often each marker name appeared in PyPI dependency metadata **as of January 2025** (order: most frequent first). They give a sense of how much of the ecosystem each rule affects.

“**Support**” means: when this variable appears in a marker atom, `_normalize_marker_clause` in {py:mod}`conda_pypi.markers` either emits a **condition fragment** for `when`, drops that atom only (contributes `None` to `and`/`or`), or treats it specially (`extra`).


| Marker variable                  | ~Uses on PyPI (Jan 2025) | Support in conda-pypi                                                                                                                                                                                    |
| -------------------------------- | ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python_version`                 | 2,034,408                | **Yes** — translated to a `**python`…** MatchSpec fragment (e.g. `python<3.11`). Supports `not in "a, b"` as a conjunction of `python!=…`.                                                               |
| `platform_system`                | 243,706                  | **Yes** — known values map to virtual packages (`__win`, `__linux`, `__osx`, …). Unknown `==` / other ops yield no fragment.                                                                             |
| `sys_platform`                   | 223,549                  | **Yes** — same virtual-package mapping as `platform_system`. `**!=`** is partial: e.g. `!= "win32"` (and similar) collapses to `__unix`; other negations may yield no fragment (e.g. `!= "emscripten"`). |
| `platform_machine`               | 145,549                  | **No** — atom is always dropped (`None`). Conda would need much more specific virtual packages than a single PEP 508 string to model this safely for solves.                                             |
| `platform_python_implementation` | 89,434                   | **Partial** — `== "Cpython"`, `pypy`, `jython` (case-normalized) drop the atom; other values drop the atom as well (no dedicated “build string” translation yet).                                        |
| `python_full_version`            | 25,840                   | **Yes** — same rules as `python_version` (`python`… fragments).                                                                                                                                          |
| `implementation_name`            | 22,158                   | **Partial** — same as `platform_python_implementation` (common implementations drop the atom).                                                                                                           |
| `os_name`                        | 17,294                   | **Yes** — `nt` / `windows` → `__win`, `posix` → `__unix`; `**!=`** toggles between win vs unix-style virtuals when the positive form is known.                                                           |
| `platform_release`               | 6,316                    | **No** — not handled by name; atom omitted.                                                                                                                                                              |
| `platform_version`               | 241                      | **No** — not handled by name; atom omitted.                                                                                                                                                              |
| `implementation_version`         | 44                       | **No** — not handled by name; atom omitted.                                                                                                                                                              |
| `extra`                          | *(not in this census)*   | **Special** — never part of the `when` string; values feed `**extra_depends`** / package **extras** lists, possibly with `when` on the dependency from *other* variables in the same marker.             |


Other PEP 508 environment names (anything not in the table) also produce **no fragment** for that atom until explicitly implemented.

Boolean combinations use `and` / `or`: if one side has no translation, the combiner may still produce a useful condition from the other side (see `_combine_conditions` in {py:mod}`conda_pypi.markers`).

### Design notes (why not “full” platform markers)

- `**sys_platform` / `platform_system`**: Negation and disjunction on PyPI are common (“not Windows”). conda-pypi maps a **small** set of literals to `**__unix` / `__win` / …** so the conda solver can filter installs; broader support would need more virtuals and more policy.
- `**platform_machine`**: Very specific (arch strings); mapping to a single conda virtual per wheel family is fragile for noarch-style metadata.
- `**platform_python_implementation` / `implementation_name**`: A full mapping could align with **build strings** or track-specific packages; today, common “default” interpreters simply **drop** the constraint so the dependency is not incorrectly excluded on noarch paths.

## Where translation is used


| Location                                                          | Role                                                                                                                                                                                                          |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| {py:mod}`conda_pypi.markers`                                      | Core AST walk and clause normalization.                                                                                                                                                                       |
| {py:func}`conda_pypi.markers.extract_marker_condition_and_extras` | Turns a {py:class}`packaging.markers.Marker` into an optional condition string plus any `extra == "…"` names.                                                                                                 |
| {py:func}`conda_pypi.markers.pypi_to_repodata_noarch_whl_entry`   | Builds experimental **wheel repodata** entries (`depends`, `extra_depends`) from a PyPI JSON API payload.                                                                                                     |
| {py:func}`conda_pypi.translate.requires_to_conda`                 | Fills `depends` / `extras` when building `**.conda` packages** from wheel `METADATA` ({py:class}`conda_pypi.translate.CondaMetadata`). Used by `conda pypi install`, `conda pypi convert`, and similar flows. |


Both repodata and `requires_to_conda` share the same `**[when=…]`** encoding: the inner condition is passed through `**json.dumps**` so quotes and special characters are safe inside the bracket metadata.

### Markers that vanish from the `when` string

If **every** translatable atom is dropped and there are **no** `extra` atoms, the dependency may still be recorded **without** `when` (conservative behavior for noarch metadata). That can slightly **over-approximate** install sets compared to a strict PEP 508 evaluator.

## Implementation note

Translation inspects {attr}`~packaging.markers.Marker._markers`, which is a **private** attribute of `packaging`. All access is confined to {py:mod}`conda_pypi.markers` so upgrades to `packaging` only require changes in one module.
