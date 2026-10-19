# Terrateam Action

The Terrateam action operates based on a work specification, called a Work
Manifest, which informs which operations it should execute.  It is capable of
the following operations:

- Terraform plan
- Terraform apply

The action is meant to be executed manually (via a `workflow_dispatch` event)
rather than automatically triggered.

## Versioning and pinning

Releases are cut from `main` and tagged `vX.Y.Z`. The tag `vX` is a moving tag.
It points at the latest stable release of that major line and moves at every
stable release.

| Pin | Behaviour | Dependabot |
|-----|-----------|------------|
| `terrateamio/action@v1` | The latest stable `v1.x.y` release. Moves at every stable release, never to a breaking change. **Recommended.** | No pull requests until a `v2` tag exists. |
| `terrateamio/action@v1.4.0` | Frozen at one release. | Pull requests for `v1.4.1`, `v1.5.0`, and so on. |
| `terrateamio/action@<commit sha>` | Frozen at one commit. | Pull requests that advance the SHA and update the comment to `# v1.5.0`. |

Recommended:

```yaml
- uses: terrateamio/action@v1
```

Recommended if your policy is to pin by commit:

```yaml
- uses: terrateamio/action@a1b2c3d4e5f6...  # v1.4.0
```

Pin to an exact tag or commit when your policy requires a frozen pin. Dependabot
raises the pull request for the next release.

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

`X` changes only on a deliberate, announced break. A new major gets a new moving
tag, so a `v2.0.0` release creates `v2` and `v1` stays at the last v1 release.
`Y` increases when a release adds functionality. `Z` increases for fixes and
internal changes. Prereleases are tagged `v1.5.0-rc.1`, are marked as
prereleases, and never move a major tag. See the Releases page for the
changelog.

### What a pin actually freezes

Pinning to a release tag or to the commit it points at freezes everything the
action runs:

- the Python payload in `terrat_runner/` and the scripts in `bin/`;
- the base image, which `Dockerfile` and `Dockerfile.fips` reference by digest
  rather than by a movable tag.

A release writes nothing into the tree, so a tag names an ordinary `main`
commit and the two are interchangeable.

**The FIPS action is the exception.** `fips/action.yml` runs a prebuilt image:

```yaml
  image: 'docker://ghcr.io/terrateamio/action-fips:v1'
```

That tag moves with every release, so `terrateamio/action/fips@<any ref>` runs
the newest release regardless of what you pinned. To freeze it, pin the image
digest on your side. Every release publishes the digest, and you can read it
back at any time:

```console
$ docker buildx imagetools inspect --format '{{.Manifest.Digest}}' \
    ghcr.io/terrateamio/action-fips:v1.1.0
```

The FIPS **base** image is a different matter and is pinned here, by digest, in
`Dockerfile.fips`. A CI check called `fips-pin` enforces that, refuses a line
whose tag and digest disagree, and comments on a pull request when a newer base
build exists. The comment does not fail the check.

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
of `main`, whatever ref you dispatch it from. It does five things:

1. computes the version from the git tags and refuses to reuse one;
2. builds and pushes both images, tagged `vX.Y.Z` and `vX`;
3. tags the `main` commit it built. The tree is untouched, so the tag is that
   commit and nothing else. Only the tag is pushed, so the workflow needs no
   write access to `main`;
4. moves the `vX` tag to that commit. A prerelease leaves it where it is;
5. creates the GitHub Release.

The FIPS base image is updated separately, by the `base-fips` workflow. Run it
when the base has to change, paste the line it prints into `Dockerfile.fips`,
and open a pull request. The `fips-pin` check validates that line.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TERRATEAM_INFRACOST_COMPACT_LOG` | `false` | When set to `1` or `true`, replaces the full Infracost diff JSON logged to the Actions console with a single summary line (`projects`, `prev`, `curr`, `diff` monthly costs). Useful for large monorepos where the JSON output spans hundreds of thousands of lines. The full diff JSON is still computed and sent to the Terrateam API regardless of this setting. |
