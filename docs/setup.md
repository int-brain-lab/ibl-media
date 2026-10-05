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

Media was created for this collection and is the intended publication folder. No additional destination folder is needed. No media upload or catalog publication has been performed yet.

## Contributor setup

Ask an IBL maintainer for upload access to **Media**, **Write** access to this repository, and the existing OAuth desktop-client JSON. Use your own accounts; do not copy another contributor's tokens.

After [installing the tool](../README.md#set-up-once):

```bash
gh auth login                         # skip if already signed in
ibl-media login --client-secrets /path/to/client_secret.json --account YOUR_IBL_EMAIL
ibl-media doctor
```

The browser asks you to authorize the application and select **Media**. `--account` checks the Google account returned by the API before saving credentials. The `/u/2/` in a Drive browser URL is only a browser session index; it does not select the API account.

The current app accepts accounts in the IBL Workspace organization. An external university or personal Google account needs a maintainer to change the audience as described below, even if that account already has access to the folder.

Login imports the client JSON locally and uses your GitHub display name as the default credit. To choose an attribution line:

```bash
ibl-media configure --credit 'Your name'
```

For Cyrille's existing setup, the client is already imported and login has succeeded. `ibl-media doctor` passes with the saved credentials; login only needs repeating if authorization becomes invalid or the account or destination changes.

These commands do not upload files, change sharing, or write to GitHub. `doctor` returns a nonzero exit status if either upload access or public viewing is missing.

## Enable public viewing on Media

This step is complete for Media, and `doctor` confirms public viewing. To configure a replacement destination or restore sharing if it changes:

1. Open [Media](https://drive.google.com/drive/folders/1aWO70W8pRQDO6Ow-XFXNOSchAIm6ZolL) in Google Drive and open **Share**.
2. Under **General access**, choose **Anyone with the link**, with the role **Viewer**, and save.
3. Run `ibl-media doctor`. It should report `Upload access: True; public viewing: True` for an authorized contributor.

If the option is unavailable, check the Shared Drive and Workspace sharing settings with an administrator. Contributors need permission to add files; the Shared Drive Contributor role (`writer` in the API) permits this. Shared Drive files belong to the organization. See Google's [Shared Drive roles](https://developers.google.com/workspace/drive/api/guides/about-shareddrives).

Files uploaded into Media inherit its sharing. The tool inspects permissions and never changes them automatically. Permission inspection is a readiness check; the first real asset still needs a signed-out viewing and download check. See [sharing and inheritance](https://developers.google.com/workspace/drive/api/guides/manage-sharing).

## Maintainer: Google application

The IBL application is already configured. For a replacement project or client:

1. Create or choose an IBL-managed [Google Cloud project](https://console.cloud.google.com/).
2. In **APIs & Services → Library**, enable **Google Drive API** and **Google Picker API**.
3. Under **Google Auth platform**, configure branding and contact details. Select **Internal** for contributors in the project's Workspace organization.
4. Under **Data Access**, add only `https://www.googleapis.com/auth/drive.file`.
5. Under **Clients**, create an OAuth client of type **Desktop app**, then download its JSON.

Provide that desktop-client configuration to authorized contributors. Keep downloaded client JSON and user tokens out of this repository. Contributors import it using `login --client-secrets`; only maintainers need access to the Cloud project.

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

Configuration uses the standard OS user configuration directory. Tokens use the OS keyring where available; otherwise they are stored in owner-only files. The imported desktop-client JSON is copied to the configuration directory with owner-only permissions. Receipts use the OS user state directory and owner-only files. None of these files belong in Git.

For isolated testing or a separate profile, set `IBL_MEDIA_HOME` to a directory of your choice. The tool places configuration and a `state/` subdirectory there. That directory can contain credentials and should remain private.

`ibl-media logout` removes locally saved Google tokens. It does not revoke the application grant in your Google account. GitHub credentials stay managed by `gh`.

## Troubleshooting

| Problem | Action |
| --- | --- |
| Google client missing | Obtain the existing Desktop app JSON from an IBL maintainer and import it with `login --client-secrets`. |
| Wrong Google account | Run `login --account YOUR_IBL_EMAIL` again. |
| `org_internal` authorization error | Use an IBL Workspace account, or ask a maintainer to configure external contributors. |
| Folder inaccessible | Check upload access and select the configured Media folder during login. |
| Public viewing is false | Complete Media's sharing setup; check Shared Drive and Workspace policy if the option is unavailable. |
| Login expires after a week | Check whether an External OAuth app is still in Testing. |
| GitHub write access missing | Grant the authenticated account Write access and check organization SSO authorization. |
| Branch rules block metadata commits | Align the catalog branch rules with direct publication. |
| GitHub fails after Drive upload | Run `pending`, then `resume UPLOAD_ID`; completed files are reused. |
