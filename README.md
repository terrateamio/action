# Terrateam Action

The Terrateam action operates based on a work specification, called a Work
Manifest, which informs which operations it should execute.  It is capable of
the following operations:

- Terraform plan
- Terraform apply

The action is meant to be executed manually (via a `workflow_dispatch` event)
rather than automatically triggered.

## Versioning and pinning

Releases are cut from `main` and tagged `vX.Y.Z`. A tag freezes everything the
action runs, so a tag is what you should pin to.

`v1` is a **branch**, not a tag. It is legacy, it is being deprecated, and it no
longer tracks releases. Move off it.

| Pin | Behaviour | Dependabot |
|-----|-----------|------------|
| `terrateamio/action@v1.4.0` | Frozen at one release. **Recommended.** | Pull requests for `v1.4.1`, `v1.5.0`, and so on. |
| `terrateamio/action@<commit sha>` | Frozen at one commit. | Pull requests that advance the SHA, annotated `# v1.5.0`. |
| `terrateamio/action@v1` | The legacy `v1` branch. Deprecated, and it does not follow releases. | No pull requests. Dependabot only ever moves a `@v1` pin to `@v2`. |

Recommended:

```yaml
- uses: terrateamio/action@v1.4.0
```

Recommended if your policy is to pin by commit:

```yaml
- uses: terrateamio/action@a1b2c3d4e5f6...  # v1.4.0
```

There is no pin that rolls forward automatically and still tracks releases. A
branch pin follows every merge rather than every release, which is why `@v1` is
going away. Pin to a release and let Dependabot raise the pull request.

### Things worth knowing about the Dependabot pins

- **Pin to a commit a release tag points at**, not to an arbitrary commit. For a
  SHA that carries no tag, Dependabot advances the pin to the head of the branch
  that contains it rather than to a release, and it removes the `# v1.4.0`
  comment instead of updating it.
- **Pin `terrateamio/action` and `terrateamio/action/fips` at the same
  precision.** Dependabot treats them as one dependency and flattens to the
  coarsest precision present, so `@v1` in one workflow and `@v1.4.0` in another
  stops both from ever updating.
- A new release produces no pull request for about three days. That is
  Dependabot's default cooldown, not a broken tag.

### Version numbers

`X` changes only on a deliberate, announced break, which means a new release
channel. `Y` increases when a release adds functionality. `Z` increases for
fixes and internal changes. Prereleases are tagged `v1.5.0-rc.1`, are marked as
prereleases, and never move a major image tag. See the Releases page for the
changelog.

### What a pin actually freezes

Pinning to a release tag or to the commit it points at freezes everything the
action runs:

- the Python payload in `terrat_runner/` and the scripts in `bin/`;
- the base image, which `Dockerfile` and `Dockerfile.fips` reference by digest
  rather than by a movable tag;
- the prebuilt image that the FIPS action runs. `fips/action.yml` is rewritten
  at release time to name that release's image by digest, and the release tag
  points at the commit that carries it.

The release commit lives on the tag, not on `main`. On `main`, `fips/action.yml`
keeps a movable `action-fips:v1` reference, so pinning an arbitrary `main` commit
gives you the newest release of the v1 line rather than a frozen image. Pin a
release tag, or the commit that tag points at, to freeze it.

### Prebuilt images

The action builds its image from `Dockerfile` on every run. The same image is
also published prebuilt, which is faster to pull than to build. The FIPS action
runs the prebuilt image directly.

```text
ghcr.io/terrateamio/action:v1.4.0    # one release
ghcr.io/terrateamio/action:v1        # newest release of the v1 line
```

These track releases, so `:v1` changes when a release is cut rather than on
every merge. A prerelease publishes `:v1.5.0-rc.1` only, and never moves `:v1`.

### Cutting a release

Run the `release` workflow from the Actions tab. It always operates on the head
of `main`, whatever ref you dispatch it from. It builds and pushes the images,
writes the new FIPS image pin into `fips/action.yml`, commits that on top of the
`main` head it built, and pushes the tag. The tag carries the commit, so the
workflow never writes to `main` and needs no exception from the branch ruleset.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TERRATEAM_INFRACOST_COMPACT_LOG` | `false` | When set to `1` or `true`, replaces the full Infracost diff JSON logged to the Actions console with a single summary line (`projects`, `prev`, `curr`, `diff` monthly costs). Useful for large monorepos where the JSON output spans hundreds of thousands of lines. The full diff JSON is still computed and sent to the Terrateam API regardless of this setting. |
