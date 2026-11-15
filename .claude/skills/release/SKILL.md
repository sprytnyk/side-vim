---
name: release
description: Release side-vim with a reviewed changelog, signed commit and tag, a tested wheel, and PyPI trusted publishing. Use when the user asks to release or ship a version.
argument-hint: '[version, e.g. 0.1.0; derived from commits if omitted]'
disable-model-invocation: true
---

# Release

Use this skill only for a release request. Editing the release tooling is not a
request to release. A release request authorizes the release commit, signed tag
and push to the existing `origin`. Global rules still apply, including approval
for each command that runs third-party code. Ask separately before auditing
dependencies or creating a GitHub release. Never approve the `pypi` environment
on the user's behalf.

If a check fails, stop and explain it. Never bypass hooks, overwrite tags,
force-push, or add AI attribution. Use signing key `0xC00C0F0D647BD3C6` for
every new commit and tag.

## 1. Pre-flight

- Be on `main`. Fetch the existing `origin`; stop if local `main` is behind or
  diverged. Follow the user's permission rules for network access.
- Review pending changes. Commit release-related work in separate signed
  Conventional Commits, with hooks enabled. Ask about anything whose ownership
  or inclusion is unclear. Do not stage scratch files or secrets. The project
  release skill belongs in git.
- Find the previous release with `git describe --tags --abbrev=0`. With no tag,
  use the full history and default to `0.1.0`.
- Check signatures with `git log --format='%h %G? %s' <last-tag>..HEAD`, or `HEAD`
  for the first release. Every new commit must show `G`. Stop for missing or
  invalid signatures; do not rewrite history automatically.
- Check that `uv run python --version` matches `.python-version` in major and
  minor version. Run `uv lock --check`, `uv run ruff check .`,
  `uv run ruff format --check .` and `uv run pytest`.
- Ask before the dependency audit: it sends dependency names and versions to
  PyPI's vulnerability service. Write requirements to a fresh temporary path:

  ```sh
  uv export --locked --no-emit-project --format requirements-txt -o <scratchpad>/requirements.txt
  uv run pip-audit --strict --require-hashes --disable-pip -r <scratchpad>/requirements.txt
  ```

  Report findings and ask before updating dependencies.
- Compare user-visible changes with README's Install, Usage and Supported keys
  sections. Update documentation as needed; remove the pre-release installation
  note for the first release. If key handling changed since the last release,
  ask the user to run `make mac-keys` on a Mac and send the result.
- Confirm the user has configured the `pypi` GitHub environment with a required
  reviewer and the matching PyPI trusted publisher, as described in README.

## 2. Version and changelog

Use the requested version. Otherwise derive it from commits since the last tag:
breaking changes mean major, `feat` means minor, and other changes mean patch.
Explain the choice in one sentence. Pending release work must be committed before
changing the version.

Run `uv version X.Y.Z`. The real version lives in `pyproject.toml`; include the
resulting `uv.lock` change. Add `## X.Y.Z - YYYY-MM-DD` to `CHANGELOG.md`, newest
first, with entries from the commits. Use only sections with content: Breaking,
Highlights, Fixes, Changes, Removed. Write plain, short sentences. Do not add an
Unreleased section.

Show the proposed version and changelog to the user and wait for review before
the release commit. Local build checks may proceed while waiting.

## 3. Build, commit and tag

Run `uv build --out-dir <scratchpad>/dist` using a fresh directory. Create a
throwaway virtualenv in the scratchpad with `uv venv`, then install that exact
wheel with `uv pip install --python <venv-python> <wheel-path>`. Run from the
scratchpad, outside this checkout, so the source tree cannot hide missing files:

```sh
<venv-python> -I -c 'from importlib.metadata import version; from side_vim import Mode, UKRAINIAN, VimMode; assert version("side-vim") == "X.Y.Z"; print(version("side-vim"))'
```

Use explicit paths. Follow the user's approvals for downloads, temporary code
execution, and access outside this project. Confirm the import comes from the
throwaway environment, and recheck `uv lock --check` after the version change.

After review and passing checks, stage only the release files and make:

```sh
git commit -S0xC00C0F0D647BD3C6 -m "chore(release): vX.Y.Z"
```

Let hooks run; inspect and restage any fixes before retrying. Write the tag
message to a scratch file: `vX.Y.Z`, a blank line, and a short release summary.

```sh
git tag -s -u 0xC00C0F0D647BD3C6 vX.Y.Z -F <scratchpad>/tag-message
git verify-commit HEAD
git tag -v vX.Y.Z
```

Both signatures must be good and from the required key. If gpg's pinentry times
out, ask the user to run the command themselves with a `!` prefix. The tag must point at
the release commit, with matching package version and changelog heading.

## 4. Push and wait for approval

```sh
git push origin main
git push origin vX.Y.Z
```

Find the tag's run with `gh run list --workflow release.yml --branch vX.Y.Z`.
Use `gh run view <id> --json url,status,conclusion,jobs` to check progress. The
workflow reuses CI's lint, platform tests, lowest-dependency tests and audit,
then verifies the version and builds the distributions.

When the checks and build pass, give the user the run link and wait for them to
approve the `pypi` job. Do not wait for the entire workflow to finish before
asking: publishing cannot start until that approval. Never approve or bypass
the environment gate. After approval, use `gh run watch <id> --exit-status` to
wait for publication. Stop and report any failure.

CI can also run before tagging, from **Actions → CI → Run workflow**. The release
workflow runs it again for the pushed tag. If that run fails, nothing is published.
Don't delete or move the tag. Report the failure; the fix goes out as the next patch
version unless the user decides otherwise.

## 5. Confirm and write GitHub notes

Check `https://pypi.org/pypi/side-vim/X.Y.Z/json` and confirm the published
version, wheel and source distribution. Use the reviewed CHANGELOG section as
the release notes, saved to a temporary file.

Attach the wheel PyPI serves, not the local build, so the GitHub file is the one
people install. Take its `url` and `digests.sha256` from the `bdist_wheel` entry
in that JSON. Download it into a fresh, empty scratchpad directory, keeping
PyPI's filename, and check the hash. Stop if it doesn't match.

```sh
curl -fsSL -o <scratchpad>/pypi-wheel/side_vim-X.Y.Z-py3-none-any.whl <url>
echo "<sha256>  <scratchpad>/pypi-wheel/side_vim-X.Y.Z-py3-none-any.whl" | sha256sum -c
```

Write `SHA256SUMS` next to it from that checked hash, with the bare filename so
`sha256sum -c SHA256SUMS` works in a download folder. Sign it with the release
key and check the signature. It must be good and from the required key; if gpg's
pinentry times out, ask the user to run the signing command with a `!` prefix.

```sh
printf '%s  %s\n' <sha256> side_vim-X.Y.Z-py3-none-any.whl > <scratchpad>/pypi-wheel/SHA256SUMS
gpg --local-user 0xC00C0F0D647BD3C6 --armor --detach-sign --output <scratchpad>/pypi-wheel/SHA256SUMS.asc <scratchpad>/pypi-wheel/SHA256SUMS
gpg --verify <scratchpad>/pypi-wheel/SHA256SUMS.asc <scratchpad>/pypi-wheel/SHA256SUMS
```

Ask: publish the GitHub release, create a draft, or leave it to the user?

```sh
gh release create vX.Y.Z --verify-tag --title "side-vim vX.Y.Z" --notes-file <scratchpad>/release-notes.md <scratchpad>/pypi-wheel/side_vim-X.Y.Z-py3-none-any.whl <scratchpad>/pypi-wheel/SHA256SUMS <scratchpad>/pypi-wheel/SHA256SUMS.asc
```

Add `--draft` only if requested. Attach only those three files. Confirm with
`gh release view vX.Y.Z --json url,isDraft,assets`. The assets must list exactly
the wheel, `SHA256SUMS` and `SHA256SUMS.asc`, and the wheel must have the same
name, size and sha256 as on PyPI.

Report the version, signature checks (commit, tag and `SHA256SUMS.asc`), local
wheel check, CI result, PyPI link, and GitHub release link or notes path. State any unfinished work.
