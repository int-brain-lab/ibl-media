# ibl-media

Videos, figures, illustrations, animations, and other media from the International Brain Laboratory, with credits and provenance.

The files live in Google Drive. This repository holds their metadata and the tool for uploading them. Members publish directly with one command or from Python.

> Initial implementation: automated tests use simulated services. Google login against the IBL destination and live uploads remain to be verified. The catalog is currently empty.

## Install

Requires Python 3.11+ and [GitHub CLI](https://cli.github.com/). From this checkout:

```bash
uv sync --group dev
uv run ibl-media --help
uv run ibl-media doctor --github-only
```

Alternatively, install the command with `uv tool install .`, or run `python -m pip install -e .` inside a virtual environment. All `ibl-media` commands below can also be invoked as `uv run ibl-media` from this checkout.

For video dimensions and duration, install `ffprobe` (part of FFmpeg). It is optional; image dimensions, file sizes, and checksums work without it.

## Start with access checks

The first rollout is for one member, Cyrille. No media should be uploaded during the initial authentication setup.

GitHub checks are ready to run now. Google access needs a one-time desktop OAuth client created in Google Cloud; follow [setup](docs/setup.md). Then:

```bash
ibl-media login --client-secrets /path/to/client_secret.json
ibl-media doctor
```

Neither command uploads media or writes to GitHub. To inspect metadata for an existing local file without any network requests:

```bash
ibl-media upload /path/to/figure.png --dry-run
```

Actual upload commands below publish files and should be run only when ready to publish media.

## Upload an asset

After [one-time setup](docs/setup.md):

```bash
ibl-media upload coverage.png
```

The tool uploads the file, records its metadata in this repository, and returns a shareable Drive link and an asset ID. A title is inferred from the filename; credit comes from your configured identity.

Add context when useful:

```bash
ibl-media upload overview.mp4 \
  --title "Brain-wide map overview" \
  --description "Recorded neurons coloured by brain region" \
  --credit "Example Creator; Example Collaborator"
```

Related files can share one entry:

```bash
ibl-media upload illustration.png illustration.psd \
  --title "Brain illustration"
```

Uploads go to the public collection. All files supplied to the command, including editable sources, are intended for public sharing. No separate form, pull request, or review is required.

## Upload from Python

```python
from ibl_media import upload

fig.savefig("coverage.png")
asset = upload(
    "coverage.png",
    title="Insertion coverage",
    source=__file__,
)
print(asset.id)
print(asset.url)
```

When a source script is supplied, the tool records its path and, if available, its Git repository, commit, and whether the working tree has uncommitted changes. It does not infer which dataset generated a figure. Add a dataset reference or description when that context matters:

```bash
ibl-media upload coverage.png \
  --source scripts/plot_coverage.py \
  --dataset "Dataset DOI, release ID, or other versioned reference"
```

In notebooks, supply a source path explicitly or omit it. The Python function accepts `description`, `credit`, `dataset`, and `reuse` as optional keywords alongside `title` and `source`.

## Publish another version

Reuse the asset ID returned by the first upload:

```bash
ibl-media upload coverage.png --asset ASSET_ID
```

A new version receives new Drive files. The metadata retains previous versions, their links, and their checksums. A filename alone does not identify an existing asset.

## What gets recorded

Each asset has an ID, title, credit, reuse terms, and a list of versions. Each version records the uploader, upload time, supplied context, and file details: Drive ID and link, filename, format, size, checksum, and dimensions or duration where supported.

Metadata is readable YAML in `assets/`. See [metadata and provenance](docs/metadata.md) for an example and the distinction between automatically recorded facts and contributor-supplied information.

The default reuse terms are **Permission required** until IBL chooses a collection-wide policy. Set a local default with `ibl-media configure --reuse 'TERMS'`, or override one upload with `--reuse`. Public access alone does not specify reuse terms. Each version retains its own credit and reuse terms.

## Access and authentication

Sign in once with your own Google account and GitHub account. You need upload access to the configured Drive folder and write access to this repository. The tool reuses GitHub CLI authentication and stores Google credentials locally outside the checkout.

```bash
gh auth login                         # if not already signed in
ibl-media login                       # Google sign-in and setup checks
```

See [setup and permissions](docs/setup.md) for contributor setup and the one-time configuration maintained by IBL.

## If an upload fails

The tool reports whether the file upload or the metadata publication failed. It reports success only when both are complete. If Drive upload succeeds but GitHub publication fails, it retains a local receipt so the same command can resume without uploading the files again. Repeating the same command resumes a matching unfinished upload. You can also resume explicitly:

```bash
ibl-media pending
ibl-media resume UPLOAD_ID
```

Completed files are reused. A transfer interrupted before completion may restart that file from the beginning on a subsequent invocation. After a successful upload, running the same command again creates a new asset (or another version when `--asset` is supplied).

## Browse and validate

```bash
ibl-media list
ibl-media show ASSET_ID
ibl-media validate assets/ASSET_ID.yaml
```

`list` and `show` read GitHub; `validate` checks local files offline. See [development](docs/development.md) for testing, recovery details, and remaining live checks.

## Legacy visualizations

[ibl-viz](https://github.com/int-brain-lab/ibl-viz) contains earlier visualizations, notebooks, and media. New catalog entries can link to those original files and source commits. Legacy assets are added as they become useful; unknown credits or source details remain explicitly unknown.
