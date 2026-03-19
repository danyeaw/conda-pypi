# Developer Notes

This section contains implementation notes, technical insights, and development considerations for conda-pypi.

## PyPI Package Analysis

Example: https://pypi.org/project/torch/#files

2.5.1 e.g., torch has only wheels, no sdists. Is called pytorch in conda-land.

## Conda Integration

LibMambaSolver (used to have) LibMambaIndexHelper.reload_local_channels() used
for conda-build, reloads all file:// indices.

(Can't figure out where this is used) See also reload_channel().

```
for channel in conda_build_channels:
    index.reload_channel(channel)
```

If we call the solver ourselves or if we use the post-solve hook, we could
handle "metadata but not package data converted" and generate the final .conda's
at that time. While generating repodata from the METADATA files downloaded
separately.

We could generate unpacked `<base env>/pkgs/<package>/` directories at the
post-solve hook and skip the `.conda` archive. Conda should think it has already
cached the new wheel -> conda packages.

In the twine example we wind up converting two versions of a package from wheel
to conda. One of them might have conflicted with the discovered solution.

Hash of a regular Python package is something like py312hca03da5_0

## Environment Markers

**Two different ideas** use the word “marker” in this project:

1. **PEP 668 / `EXTERNALLY-MANAGED`** — marker *files* that discourage naive `pip` use (user-facing docs: [Environment marker files](../features.md#environment-marker-files)).
2. **PEP 508 dependency markers** — boolean expressions on individual `Requires-Dist` lines. conda-pypi **translates** these to conda `MatchSpec` **`[when="…"]`** strings (and extras tables) rather than only evaluating them at metadata build time. See {doc}`marker-conversion`.

For **evaluation** against a live environment (as opposed to translation for the solver), `packaging` supports:

```python
some_environment = packaging.markers.default_environment()
packaging.markers.Marker("python_full_version=='3.12.4'").evaluate(
    environment=some_environment
)
```

The test `build` uses environment markers and extras; PyPI metadata corpora are useful for both evaluation and translation tests.

## Architecture Packages

"arch" packages should be allowed.

## Build System Design

A little bit like conda-build:

Build packages from wheels or sdists or checkouts, then keep them in the local
channel for later. (But what if we are in CI?)

## Editable Installation

'editable' command:

Modern replacement for conda-build develop; works like pip install -e . --no-build-isolation
