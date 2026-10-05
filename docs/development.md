# Development

## Run locally

```bash
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
```

Tests isolate configuration in temporary directories and deny external network connections. Upload tests use simulated Drive and GitHub services; generated test images stay local. The OAuth callback test uses a loopback HTTP server and a simulated token exchange.

GitHub Actions runs linting, tests, and catalog validation on Python 3.11 and 3.13. It also checks for binary files and tracked files over 2 MB. Media belongs in Drive; `.gitignore` excludes common media formats.

## Code layout

| Module | Responsibility |
| --- | --- |
| `cli.py` | Commands, diagnostics, and actionable terminal errors. |
| `config.py` | Defaults, local settings, and private atomic JSON writes. |
| `google_auth.py` | Desktop OAuth with folder selection, refresh, and token storage. |
| `drive.py` | Destination checks, reserved file IDs, chunked transfers, and checksum verification. |
| `github.py` | Read/write catalog entries through `gh api`. |
| `metadata.py` | File facts, supplied source context, and schema validation. |
| `uploader.py` | Python API, versioning, transaction receipts, recovery, and publication. |

## Recovery behavior

A pending receipt records the destination, asset and transaction IDs, local file paths/checksums, supplied context, and each Drive file's reserved ID. The tool saves reserved IDs before starting a transfer. A repeat invocation checks for a completed file at that ID instead of allocating another file.

Transfers use resumable chunks with bounded retries within the running process. An incomplete file can restart from the beginning across invocations. Completed files are reused; they are not reuploaded when GitHub publication fails. Remote file checksums and sizes must match the planned local bytes before metadata is published.

A per-receipt lock prevents two local processes from running the same unfinished upload. GitHub publication reads the current entry and performs a conditional update using its file SHA. On a conflict, it reloads and appends the version with bounded retries. A transaction ID already present in the catalog counts as a successful previous publication, avoiding duplicate versions after an ambiguous response.

Receipts move to the local completed history after publication. They are not automatically deleted on failure, and the tool does not delete orphaned Drive files. Different machines have separate receipt stores; cross-machine recovery is not implemented.

## Live verification

The following checks succeeded on 5 October 2026 for `cyrille.rossant@internationalbrainlab.org` and GitHub account `rossant`, without uploading media:

1. Create the IBL Google Cloud project, enable Drive and Picker, and import the Desktop app configuration.
2. Complete browser consent and select the configured Media folder; verify the Google account via the Drive API before saving credentials.
3. Inspect the folder through the API: Media is in a Shared Drive and the account can add files.
4. Run `doctor` in a separate process, successfully reusing saved credentials.
5. Confirm GitHub repository Write access and inspect the `main` branch.
6. After the maintainer enabled public viewing, repeat `doctor` and confirm both upload access and public viewing.

Media now passes the permission checks with the saved credentials. See [setup](setup.md#enable-public-viewing-on-media) for the sharing configuration. These checks did not upload media or create catalog entries.

When media uploads are authorized, verify the remaining publication path:

1. Upload one small asset and verify its metadata commit.
2. Check signed-out viewing/downloading of the Drive file.
3. Upload another version and confirm earlier files remain accessible.

The actual desktop Picker callback and persisted credentials have been verified. File transfer, metadata commits, and inherited public access on new files remain untested against the live services. Branch write checks inspect repository access and report protection; they do not prove an authenticated write will pass every repository rule. Automated upload tests use simulated services.

A generated gallery, S3 delivery, automated backups, legacy import, and cross-machine recovery are outside this initial implementation.
