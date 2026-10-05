# ibl-media

Videos, figures, illustrations, animations, and other media from the International Brain Laboratory, with credits and provenance.

The files live in the IBL [Media folder on Google Drive](https://drive.google.com/drive/folders/1aWO70W8pRQDO6Ow-XFXNOSchAIm6ZolL). This repository holds their metadata and the tool for uploading them. Members publish directly with one command or from Python; no form, pull request, or review is required.

> Pilot status, 5 October 2026: the first asset is published. Google login, saved credentials, Drive permissions, metadata publication, and an anonymous download with a matching checksum have been verified for Cyrille. Browse the [Brain Wide Map overview](https://drive.google.com/file/d/1Vwr6Qdc8fFLPWI24uwd7_Hjdp3k3K_i4/view) and its [metadata](assets/22f5f7a71844403aaa379e555b3a0f02.yaml). See [setup](docs/setup.md).

## Set up once

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and [GitHub CLI](https://cli.github.com/). You need upload access to Media, write access to this repository, and the shared OAuth desktop-client JSON from an IBL maintainer. Contributors do not need their own Google Cloud project.

From a checkout of this repository:

```bash
uv tool install .
gh auth login                         # skip if already signed in
ibl-media login --client-secrets /path/to/client_secret.json --account YOUR_IBL_EMAIL
ibl-media doctor
```

In the browser, sign in with your IBL Google account and select **Media**. The tool verifies the requested account before saving credentials. The current Google app is Internal to the IBL Workspace organization; using a university or other external Google account needs a maintainer to adjust the app's audience first.

Login uses your GitHub display name as the default credit. Set your preferred attribution once if needed:

```bash
ibl-media configure --credit 'Your name'
```

Credentials are stored locally outside the checkout. On later runs, the tool reuses them. These setup commands do not upload media, change Drive sharing, or write to GitHub. See [setup and permissions](docs/setup.md) for details and troubleshooting.

For Python use, install the package into the environment that generates your figures with `python -m pip install -e /path/to/ibl-media`. Alternatively, run commands from this checkout with `uv run ibl-media` and scripts with `uv run python`; a separate tool installation is then unnecessary.

For video dimensions and duration, install `ffprobe` (part of FFmpeg). It is optional; image dimensions, file sizes, and checksums work without it.

## Preview without uploading

To inspect metadata for an existing local file without any network requests or state changes:

```bash
ibl-media upload /path/to/figure.png --dry-run
```

To check saved access without uploading:

```bash
ibl-media doctor
```

`doctor` exits with an error if upload access or public viewing is missing. Media currently passes both checks for the pilot account. Use a dry run to inspect a file's metadata before publishing it.

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

The tool requires public viewing on the destination before uploading. All files supplied to the command, including editable sources, are intended for public sharing. Files made in Photoshop or another desktop app use the same command; a source script is optional.

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

Metadata is readable YAML in `assets/`, created on the first successful publication. See [metadata and provenance](docs/metadata.md) for an example and the distinction between automatically recorded facts and contributor-supplied information.

The default reuse terms are **Permission required** until IBL chooses a collection-wide policy. Set a local default with `ibl-media configure --reuse 'TERMS'`, or override one upload with `--reuse`. Public access alone does not specify reuse terms. Each version retains its own credit and reuse terms.

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

## Documentation

- [Setup and permissions](docs/setup.md): contributor access, maintainer configuration, and troubleshooting.
- [Metadata and provenance](docs/metadata.md): recorded fields, attribution, and version history.
- [Development](docs/development.md): tests, implementation, recovery behavior, and live verification.
