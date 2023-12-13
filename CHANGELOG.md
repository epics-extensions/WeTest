# Changelog

All notable changes to this project are documented in this file.

## [2.0.0rc1] - 2023-12-13

### Highlights

This release drops support for Python 2.7.
This version should be compatible with Python 3.7 and later.

The build system was also switched to Poetry.

Nix files were also added as a way to build and test the project.

No changes were made to the scenario YAML format.
You can update the version in your YAML files to `2.0.0`.

### Bug Fixes

- Crash when creating PDF report
- Fix reader tests
- Don't run CI on every push
- Only run Ruff GitHub Action on changed Python files
- Correctly parse Python versions
- Fix Ruff action ignoring changed files

### Features

- Configure ruff in pyproject.toml
- Add ruff check as GitHub action
- Add editor config file
- Add editor config check as GitHub action
- Add support for Nix without flakes
- Add Nix build as GitHub action
- Generate Nix bundle archives on tagged releases
- Add CHANGELOG generation support with git-cliff

### Miscellaneous Tasks

- [**breaking**] convert codebase to Python 3
- [**breaking**] switch build system to Poetry
- Add Nix build
- Support more architectures with Nix, add a simple test
- Ruff format everything
- Run ruff check --fix
- Run ruff check --fix --unsafe-fixes
- Other ruff lint manual fixes
- Correct spelling toogle -> toggle
- Remove trailing whitespace, ensure final newlines
- Update README installation instructions
- README formatting and wording
- Add metadata to the Nix WeTest package
- Improve project metadata
- [**breaking**] Add pytest, bump min Python version to 3.7
- Move tests to own directory
- Don't ask compatibility question
- Link to repository instead of print changelog
- Remove non-working tests
- Rename Ruff lint action workflow, make it clearer
- Update install-nix-action in CI
- Run Nix checks instead of build on CI
- Use Python3.9 in the Nix build

### Refactor

- Make validate_file return boolean
- Rename _version_is_supported -> supports_version
- Better fetch of WeTest version
- Use semver for version comparison
