# MAINTAINING — scolta-django

The Django and Wagtail adapter over scolta-python. Publishes to PyPI.

Everything true of more than one Scolta repo lives in
[scolta-core/MAINTAINING.md](https://github.com/tag1consulting/scolta-core/blob/main/MAINTAINING.md):
the version rules, the release order, the fleet checks, the rules every repo shares.

**What it is.** A Django and Wagtail adapter, glue only. It depends on the `scolta` binding
(`scolta-python`), never on `scolta-core` directly.

**Where the version lives.** `src/scolta_django/__init__.py` `__version__`, and only there.
`pyproject.toml` reads it through `[tool.hatch.version]`, so the metadata and
`scolta_django.__version__` cannot drift apart.

**Where it publishes.** PyPI, as `scolta-django`. To confirm: `pip install scolta-django` in a clean
venv resolves it.

**CI checks.** `test` (ruff lint, `ruff format --check`, and pytest across Python 3.10 to 3.13 against
both ends of the supported Django range, 4.2 and 5.2; the 4.2 row pins Wagtail 6.3 LTS because the lock
resolves a Wagtail that needs Django 5.2) and `Build & validate PyPI artifacts` (`uv build`,
`uvx twine check`, `scripts/validate_dist.py`). The `test` job checks out `scolta-python` as a sibling,
because `[tool.uv.sources]` points `scolta` at `../scolta-python` for resolution; the `dist` job
deliberately does not, since building this wheel does not need the binding installed.

**On release day.** Release this after `scolta` is on PyPI, or it won't resolve. **There is no release
workflow**, so the upload is manual: `uv build` then `twine upload dist/*`.

**Watch out for.**

- This package declares no trove classifiers, so `Framework :: Django` and `Framework :: Wagtail` are
  absent and the Django Packages and Wagtail directories cannot find it. Being installable is not the
  same as being found; adding them is an open item.
- The dependency on the binding is a floor (`scolta>=…`), not a caret, so a `scolta` release is picked up
  without a change here. Bump the floor when you start calling something new.
- Wagtail support is an optional `[wagtail]` extra that auto-loads when Wagtail is installed.
- This package carries no copy of the browser bundle. The Django admin page is status-only, with no
  editable provider field, so a hardcoded-provider check does not apply here.
- Mass `QuerySet.update()` bypasses the signals that trigger auto-rebuild. Run `manage.py scolta_build`
  after a bulk operation.
