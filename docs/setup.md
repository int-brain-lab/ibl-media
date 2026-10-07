# Setup and permissions

Contributors sign in once with their own Google and GitHub accounts. IBL maintains a single Google OAuth application and the Media destination; contributors do not create Google Cloud projects.

## Current IBL configuration

Verified on 5 October 2026 during the one-member pilot:

| Item | Configuration or result |
| --- | --- |
| GitHub repository | `int-brain-lab/ibl-media`, branch `main` |
| Google Cloud project | [`ibl-media`](https://console.cloud.google.com/home/dashboard?project=ibl-media), number `16395456236` |
| Workspace organization | `internationalbrainlab.org` |
| Enabled APIs | Google Drive API and Google Picker API |
| OAuth app | `ibl-media`, audience **Internal** |
| OAuth client | Desktop app, named `ibl-media CLI` |
| Requested scope | `https://www.googleapis.com/auth/drive.file` |
| Drive destination | [Media](https://drive.google.com/drive/folders/1aWO70W8pRQDO6Ow-XFXNOSchAIm6ZolL), in a Shared Drive |
| Pilot Google account | `cyrille.rossant@internationalbrainlab.org`; browser login and folder selection succeeded |
| Saved credentials | A separate invocation of `doctor` successfully reused them |
| Upload capability | Confirmed for the pilot account |
| Public viewing | Enabled; API permission inspection confirms public viewing |
| Pilot GitHub account | `rossant`; repository Write access confirmed |

Media was created for this collection and is the intended publication folder. No additional destination folder is needed. The first asset, [Brain Wide Map overview (legacy)](../assets/22f5f7a71844403aaa379e555b3a0f02.yaml), was published on 5 October 2026. Its metadata passed schema validation and CI; an anonymous download returned the original PNG with a matching SHA-256 checksum.

## Contributor setup

Ask an IBL maintainer for upload access to **Media** and **Write** access to this repository. Also ask for **Read** access to the private [`ibl-media-config`](https://github.com/int-brain-lab/ibl-media-config) repository. Accept any pending GitHub invitations before login; organization SSO authorization may also be needed. Use your own accounts; do not copy another contributor's tokens.

After [installing the tool](../README.md#set-up-once):

```bash
gh auth login --hostname github.com   # skip if already signed in on github.com
ibl-media login --account YOUR_IBL_EMAIL
ibl-media doctor
```

The browser asks you to authorize the application and select **Media**. `--account` checks the Google account returned by the API before saving credentials. The `/u/2/` in a Drive browser URL is only a browser session index; it does not select the API account.

The current app accepts accounts in the IBL Workspace organization. An external university or personal Google account needs a maintainer to change the audience as described below, even if that account already has access to the folder.

On a fresh profile, login uses your GitHub authentication to download the shared desktop client from the private configuration release. It verifies that the repository is private, checks the download against the package's pinned SHA-256 checksum, and checks the expected client ID, project, and Google endpoints before saving it locally. The public package contains only the release location, client ID, and checksum. Login uses your GitHub display name as the default credit. To choose an attribution line:

```bash
ibl-media configure --credit 'Your name'
```

On later runs, saved credentials are reused; login only needs repeating if authorization becomes invalid or the account or destination changes.

These commands do not upload files, change sharing, or write to GitHub. `doctor` returns a nonzero exit status if either upload access or public viewing is missing.

## Enable public viewing on Media

This step is complete for Media, and `doctor` confirms public viewing. To configure a replacement destination or restore sharing if it changes:

1. Open [Media](https://drive.google.com/drive/folders/1aWO70W8pRQDO6Ow-XFXNOSchAIm6ZolL) in Google Drive and open **Share**.
2. Under **General access**, choose **Anyone with the link**, with the role **Viewer**, and save.
3. Run `ibl-media doctor`. It should report `Upload access: True; public viewing: True` for an authorized contributor.

If the option is unavailable, check the Shared Drive and Workspace sharing settings with an administrator. Contributors need permission to add files; the Shared Drive Contributor role (`writer` in the API) permits this. Shared Drive files belong to the organization. See Google's [Shared Drive roles](https://developers.google.com/workspace/drive/api/guides/about-shareddrives).

Files uploaded into Media inherit its sharing. The tool inspects permissions and never changes them automatically. Permission inspection is a readiness check; the first asset's download was also verified without authentication. Repeat that check if the sharing configuration changes. See [sharing and inheritance](https://developers.google.com/workspace/drive/api/guides/manage-sharing).

## Maintainer: Google application

The IBL application is already configured. For a replacement project or client:

1. Create or choose an IBL-managed [Google Cloud project](https://console.cloud.google.com/).
2. In **APIs & Services → Library**, enable **Google Drive API** and **Google Picker API**.
3. Under **Google Auth platform**, configure branding and contact details. Select **Internal** for contributors in the project's Workspace organization.
4. Under **Data Access**, add only `https://www.googleapis.com/auth/drive.file`.
5. Under **Clients**, create an OAuth client of type **Desktop app**, then download its JSON.

Distribute the IBL desktop-client configuration privately as described below. A custom deployment can instead import its own client using `login --client-secrets`; only maintainers need access to the Cloud project. Personal access tokens, refresh tokens, and service-account keys must stay out of the repository.

### Private desktop-client distribution

The [`ibl-media-config`](https://github.com/int-brain-lab/ibl-media-config) repository is private. Release `oauth-client-v1` carries the desktop-client JSON as the `desktop-client.json` attachment; credentials are never committed to its Git history. The public package's `oauth_client_manifest.json` identifies the exact release, asset, client ID, project, and SHA-256 checksum. Only maintainers should have permission to change releases; contributors need Read access. Organization owners retain their inherited administrative access.

To replace the configuration, download the **ibl-media CLI** Desktop app JSON from the existing [`ibl-media` Google Cloud project](https://console.cloud.google.com/auth/clients?project=ibl-media). Check its project and desktop-client type, upload it as an attachment to a new versioned release in the private repository, and update the public manifest's tag and checksum. Verify authenticated retrieval in an empty profile before distributing the updated package. Do not upload credentials to this public repository or to a public release. Google's [OAuth policy](https://developers.google.com/identity/protocols/oauth2/policies) prohibits committing client credentials to public code repositories.

Authorized contributors can extract the configuration from their local installations. This is a property of [desktop OAuth clients](https://developers.google.com/identity/protocols/oauth2/native-app): private distribution controls who can download it, but does not prove that a program using the client ID is the genuine IBL tool. Keep the app Internal to IBL and ask a Workspace administrator to enforce the required `drive.file` access rather than relying on the Python scope constant as an allowlist. Personal Google tokens remain private to each contributor.

Onboarding requires upload access to Media, Write access to this catalog, and Read access to the private configuration repository. Then contributors use:

```bash
uv tool install --force .
gh auth login --hostname github.com
ibl-media login --account YOUR_IBL_EMAIL
ibl-media doctor
```

An explicitly imported local client is reused, so existing installations and custom deployments retain their selected application. Changing the release does not overwrite an existing custom import; reimport a replacement explicitly when needed. Downloading configuration and running login never uploads media, changes Drive sharing, or writes to GitHub.

The implementation uses Google's [desktop Picker OAuth flow](https://developers.google.com/workspace/drive/picker/guides/desktop-mobile-picker). Folder selection is part of browser authorization; a separate Picker API key or web app is unnecessary. Login checks that the returned folder ID matches the configured destination. The limited [`drive.file` scope](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) covers app-created files and items explicitly selected for the app. Knowing a folder ID alone does not authorize access.

### Adding contributors outside the IBL Workspace

Before onboarding external Google accounts, a maintainer must change the app audience to **External** and configure its publishing status. For a short trial, add those accounts as test users. External apps in **Testing** have seven-day authorizations and refresh tokens for Drive access; sustained use requires **In production** and any applicable verification. This is separate from the current Internal configuration. See Google's [audience and publishing rules](https://support.google.com/cloud/answer/15549945).

### Changing the destination

Media is the default. To use another folder for a separate deployment:

```bash
ibl-media configure --folder FOLDER_ID
ibl-media login --account YOUR_IBL_EMAIL
ibl-media doctor
```

Select the new destination during login to authorize it. The implementation supports Shared Drives on the relevant API requests.

## GitHub access

The tool reuses [GitHub CLI authentication](https://cli.github.com/manual/gh_auth_login). Check it independently of Google:

```bash
ibl-media doctor --github-only
```

The check reads account, repository, and branch information; it does not create a test commit. If the branch is protected, the output notes that direct writes may be blocked. Actual publication uses GitHub's [Contents API](https://docs.github.com/en/rest/repos/contents) through `gh api`, creating a metadata commit without a local clone. Branch rules requiring a pull request would conflict with direct publication.

Organization SSO and app restrictions still apply. A repository-scoped fine-grained token can alternatively be supplied through `GH_TOKEN`, with **Contents: Read and write** for this repository. Organization approval may be required. This permission applies to repository contents, not only `assets/`.

## Local defaults and credentials

```bash
ibl-media configure                   # show defaults and configuration location
ibl-media configure --reuse 'Permission required'
```

Configuration uses the standard OS user configuration directory. Tokens use the OS keyring where available; otherwise they are stored in owner-only files. The downloaded or explicitly imported desktop-client JSON is saved in the configuration directory with owner-only permissions. Receipts use the OS user state directory and owner-only files. None of these files belong in Git.

For isolated testing or a separate profile, set `IBL_MEDIA_HOME` to a directory of your choice. The tool places configuration, owner-only token files, and a `state/` subdirectory there; it never reads or writes the default OS keyring in this mode. That directory can contain credentials and should remain private.

`ibl-media logout` removes locally saved Google tokens. It does not revoke the application grant in your Google account. GitHub credentials stay managed by `gh`.

## Troubleshooting

| Problem | Action |
| --- | --- |
| Private configuration inaccessible | Sign in to GitHub, accept the configuration repository invitation, and check SSO authorization. Ask a maintainer for Read access to `ibl-media-config`. |
| Configuration checksum fails | Nothing is saved. Ask a maintainer to check the release and manifest; do not bypass verification. |
| Google application configuration missing | Run `ibl-media login` to retrieve it automatically. A custom deployment can import its own client with `login --client-secrets`. |
| Wrong Google account | Run `login --account YOUR_IBL_EMAIL` again. |
| `org_internal` authorization error | Use an IBL Workspace account, or ask a maintainer to configure external contributors. |
| Folder inaccessible | Check upload access and select the configured Media folder during login. |
| Public viewing is false | Complete Media's sharing setup; check Shared Drive and Workspace policy if the option is unavailable. |
| Login expires after a week | Check whether an External OAuth app is still in Testing. |
| GitHub write access missing | Grant the authenticated account Write access and check organization SSO authorization. |
| Branch rules block metadata commits | Align the catalog branch rules with direct publication. |
| GitHub fails after Drive upload | Run `pending`, then `resume UPLOAD_ID`; completed files are reused. |
