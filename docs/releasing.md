# Release process

Publishing is manual. CI builds reviewable artifacts but does not release them or receive publishing credentials.

Before the first public release:

1. Choose the actual hosting repository and maintainers. Enable private vulnerability reporting or publish a real private security contact; update SECURITY.md accordingly.
2. Confirm the existing MIT license and contributor attribution. Add real project URLs to package metadata once the hosting identity is known.
3. Review source and Git history for secrets and private recordings. Ignore/archive rules cannot sanitize history. Rotate exposed credentials if any are found.
4. Confirm the package name is available on the intended package index and configure trusted publishing for the actual repository if desired. Do not assume the generic `playflow` index name belongs to this project.
5. Exercise the integration scenarios in the roadmap on a developer-owned test app before claiming end-to-end publishing support.

For a release:

1. Update the version in `pyproject.toml` and `src/playflow/__init__.py`, and add release notes to CHANGELOG.md. Document compatibility changes and migrations.
2. In a clean checkout, install `.[dev]`, run `make check`, remove stale `dist/` artifacts, and run `make dist`.
3. Verify source and wheel contents, reinstall the wheel in a fresh virtual environment, and run `playflow --help` outside the checkout. Wheels include the live Firefox bridge assets with credential-free configuration; the standalone recorder is also included in the source archive.
4. Confirm all CI matrix jobs pass. Review the exact artifacts, then tag and publish the intended version through the configured repository/index process.
5. Test installation from the published artifact and attach relevant checksums/release notes. Do not include service-account keys, local manifests, `.playflow/`, or browser profiles.

Dependencies use compatible major-version ranges because this is a reusable Python package. CI resolves those ranges and Dependabot proposes updates. An exact application lockfile can be added for a deployment workflow once one exists; it must not replace the library's supported dependency contract.

## Clean GitHub prototype export

Do not initialize or push a Git repository from a personal publishing workspace. After building and checking the distributions, create a new clean folder from the curated source archive:

```text
python tools/export_prototype.py --sdist dist/playflow-0.1.0a1.tar.gz --output dist/playflow-prototype
```

The exporter creates the source folder, full-source ZIP, standalone skill ZIP, and a sibling inventory of file hashes. It excludes build metadata and rejects unexpected root files, private runtime artifacts, unsafe archive members, and selected credential/account/path patterns. Existing output names are never overwritten.

Run an independent secret scanner and review the exact export before publishing. Pattern checks do not prove the absence of every possible secret. Use a new Git history and a public noreply author address. Never add the local manifest, private evidence directories, browser sessions, Android artifacts, or prior personal history. The exporter does not publish anything; a maintainer explicitly publishes the reviewed export.

Use the GitHub About description and relevant topics to explain the actual capability: Google Play Console automation, Android AAB publishing, Agent Skills, Python CLI, and Firefox. Keep README installation commands, limits, architecture, and evidence current. Search indexing and AI recommendations are external decisions; no ranking or universal compatibility is promised.
