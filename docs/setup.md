# Setup and permissions

The CLI is implemented. GitHub access has been checked for Cyrille (`rossant`); Google access still needs its OAuth client and first login. Start with one member and read-only checks. Do not upload media during this initial setup.

## Google setup for the first member

A maintainer performs these steps once in an IBL-managed [Google Cloud project](https://console.cloud.google.com/). Members will subsequently reuse the same application configuration.

1. Create or choose a project for `ibl-media`.
2. In **APIs & Services → Library**, enable **Google Drive API** and **Google Picker API**.
3. Under **Google Auth platform**, configure branding and audience. Choose **Internal** only if the contributor's account belongs to this Workspace organization. Otherwise choose **External** and, for the first test, add your Google account as a test user.
4. Configure the scope `https://www.googleapis.com/auth/drive.file` under **Data Access**.
5. Under **Clients**, create an OAuth client of type **Desktop app** and download its JSON.

The tool uses Google's desktop OAuth Picker flow, which includes folder selection in the browser consent flow. A separate Picker API key or web app is not required by this implementation. The folder is preselected through its configured ID; login verifies that the returned selection is exactly that folder.

From the local checkout:

```bash
uv run ibl-media login --client-secrets /path/to/downloaded_client.json
uv run ibl-media doctor
```

Choose the Google account that can access the IBL collection. The `/u/2/` in a Drive browser URL is a browser session index, not an API account identity. Login imports the desktop-client configuration, saves Google credentials locally, and records your GitHub display name as the default credit. Override it if desired:

```bash
uv run ibl-media configure --credit 'Cyrille Rossant'
```

These commands do not upload media, alter Drive sharing, or write to GitHub.

External apps in **Testing** expire Drive authorizations and refresh tokens after seven days. That is acceptable for this first test; for sustained use, move to **In production** and satisfy applicable verification requirements. Workspace administrators may also need to allow the application.

## Drive destination and sharing

The default destination is [the supplied IBL folder](https://drive.google.com/drive/folders/1aWO70W8pRQDO6Ow-XFXNOSchAIm6ZolL). Ownership and permissions have not yet been inspected through an authenticated API call.

`doctor` reports:

- Folder name and whether it belongs to a Shared Drive or My Drive.
- Whether the signed-in account can add files.
- Whether the folder grants public viewing.

Give contributors upload access. A Shared Drive Contributor (`writer` in the API) can add files. Prefer an organizational Shared Drive, whose files belong to the organization. In a shared My Drive folder, new files ordinarily belong to their individual uploader.

For publication, configure the destination as **Anyone with the link: Viewer**, if organizational policy permits. The uploaded files inherit sharing from that folder. The tool never changes sharing automatically. `login` can complete while the folder is private; `doctor` reports it as not ready for publication, and actual uploads require both upload access and public viewing.

Only the publication folder needs public access. A different destination can be configured locally:

```bash
ibl-media configure --folder FOLDER_ID
ibl-media login
```

The limited `drive.file` scope covers app-created files and items explicitly selected for the app. Knowing a pre-existing folder ID alone does not authorize it. Selecting a changed destination requires login again. The implementation includes Shared Drive support on relevant API requests.

Before any first media upload, confirm the destination and public-sharing configuration. A later, explicitly requested upload should be checked from a signed-out browser to verify viewing and downloading in practice; a permission inspection alone cannot prove an end-to-end public download.

## GitHub

The default repository is `int-brain-lab/ibl-media`, on branch `main`. Contributors need **Write** access and a usable GitHub CLI login:

```bash
gh auth login
ibl-media doctor --github-only
```

The check reads account, repository, and branch information. It does not create a test commit. If the branch is protected, the output notes that direct writes may be blocked. Actual publication uses GitHub's Contents API through `gh api`, creating a commit without a local clone. Branch rules requiring a pull request would conflict with this direct-publication workflow.

Organization SSO/app restrictions still apply. A repository-scoped fine-grained token can alternatively be supplied through `GH_TOKEN`, with **Contents: Read and write** for this repository. Organization approval may be required. This permission applies to repository contents, not only `assets/`.

## Local defaults and credentials

```bash
ibl-media configure
ibl-media configure --reuse 'Permission required'
```

Configuration uses the standard OS user configuration directory. Tokens use the OS keyring where available; otherwise they are stored in owner-only files. The downloaded desktop-client JSON is copied to the configuration directory with owner-only permissions. Receipts use the OS user state directory and owner-only files. None of these files belong in Git.

For isolated testing or a separate profile, set `IBL_MEDIA_HOME` to a directory of your choice. The tool places configuration and a `state/` subdirectory there. Do not share that directory: it can contain credentials.

`ibl-media logout` removes the locally saved Google tokens. It does not revoke the application grant in your Google account. GitHub credentials stay managed by `gh`.

## Troubleshooting

| Problem | Action |
| --- | --- |
| Google client missing | Complete the five Cloud setup steps and import the downloaded Desktop app JSON. |
| Wrong Google account or folder inaccessible | Run `login` again with the authorized account; check the folder selection and member access. |
| Public viewing is false | Configure the publication folder's sharing; check Workspace policy if the option is unavailable. |
| Login expires after a week | Check whether the External OAuth app is still in Testing. |
| GitHub write access missing | Grant the authenticated account Write access and check organization SSO authorization. |
| Branch rules block metadata commits | Align the catalog branch rules with direct publication. |
| GitHub fails after Drive upload | Run `pending`, then `resume UPLOAD_ID`; completed files are reused. |

## References

- [Google desktop Picker OAuth flow](https://developers.google.com/workspace/drive/picker/guides/desktop-mobile-picker)
- [Google desktop OAuth client setup](https://developers.google.com/workspace/drive/api/quickstart/python)
- [Google Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [Drive sharing and inheritance](https://developers.google.com/workspace/drive/api/guides/manage-sharing)
- [Shared Drive ownership and roles](https://developers.google.com/workspace/drive/api/guides/about-shareddrives)
- [OAuth audience and publishing status](https://support.google.com/cloud/answer/15549945)
- [GitHub CLI authentication](https://cli.github.com/manual/gh_auth_login)
- [GitHub repository Contents API](https://docs.github.com/en/rest/repos/contents)
