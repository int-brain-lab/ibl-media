"""A small argparse CLI with read-only diagnostics and offline dry runs."""

import argparse
import json
import sys
from dataclasses import asdict

import yaml

from . import MediaError, upload
from .config import Settings, config_dir, import_client
from .drive import Drive
from .github import GitHub
from .google_auth import TokenStore, login
from .metadata import validate_asset
from .oauth_client import ensure_client
from .uploader import pending, resume


def parser():
    root = argparse.ArgumentParser(description="Upload IBL media and record provenance.")
    root.add_argument("--version", action="version", version="ibl-media 0.1.0")
    commands = root.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure", help="Set local defaults; no network requests.")
    for field in ("repository", "branch", "folder", "credit", "reuse"):
        configure.add_argument(f"--{field}")
    configure.add_argument("--client-secrets", help="Import Google OAuth desktop-client JSON.")
    auth = commands.add_parser("login", help="Authorize Google folder access; upload nothing.")
    auth.add_argument("--client-secrets")
    auth.add_argument("--credit")
    auth.add_argument("--account", help="Require this Google account before saving credentials.")
    commands.add_parser("logout", help="Remove saved Google tokens locally.")
    doctor = commands.add_parser(
        "doctor", help="Check access without uploading or writing to GitHub."
    )
    doctor.add_argument("--github-only", action="store_true")
    put = commands.add_parser("upload", help="Upload files, or preview metadata offline.")
    put.add_argument("files", nargs="+")
    for field in ("title", "description", "credit", "reuse", "source", "dataset", "asset"):
        put.add_argument(f"--{field}")
    put.add_argument("--dry-run", action="store_true", help="No network access or state changes.")
    commands.add_parser("pending", help="List local unfinished uploads.")
    retry = commands.add_parser("resume", help="Finish an upload from its saved receipt.")
    retry.add_argument("upload_id")
    commands.add_parser("list", help="List published asset IDs from GitHub.")
    show = commands.add_parser("show", help="Read an asset's metadata from GitHub.")
    show.add_argument("asset_id")
    validate = commands.add_parser(
        "validate", help="Validate local catalog YAML without network access."
    )
    validate.add_argument("files", nargs="+")
    return root


def run(args):
    settings = Settings.load()
    if args.command == "configure":
        for field in ("repository", "branch", "folder", "credit", "reuse"):
            value = getattr(args, field)
            if value is not None:
                setattr(settings, field, value)
        settings.validate()
        if args.client_secrets:
            import_client(args.client_secrets)
        settings.save()
        print(yaml.safe_dump(asdict(settings), sort_keys=False).strip())
        print(f"Configuration: {config_dir()}")
    elif args.command == "login":
        if args.client_secrets:
            import_client(args.client_secrets)
        user = GitHub(settings).check()
        ensure_client()
        if args.credit is not None:
            settings.credit = args.credit
        elif not settings.credit:
            settings.credit = user["name"]
        login(settings.folder, account=args.account)
        settings.save()
        info = Drive().folder_info(settings.folder)
        if not info["can_upload"]:
            raise MediaError("Google login succeeded, but the account lacks upload access.")
        print(f"Google authorized for {info['name']}; GitHub account: {user['account']}.")
        print(f"Credit: {settings.credit}")
        print(
            "Public folder: "
            + ("yes" if info["public"] else "no; sharing must be set before upload")
        )
    elif args.command == "logout":
        TokenStore().clear()
        print("Saved Google tokens removed. Google account grants are unchanged.")
    elif args.command == "doctor":
        github = GitHub(settings).check()
        print(
            f"GitHub: {github['account']} can write to {github['repository']} ({github['branch']})."
        )
        if github["protected"]:
            print("Branch is protected; direct API writes may be blocked by repository rules.")
        if not args.github_only:
            info = Drive().folder_info(settings.folder)
            print(
                f"Drive: {info['name']} ({'Shared Drive' if info['shared_drive'] else 'My Drive'})."
            )
            print(f"Upload access: {info['can_upload']}; public viewing: {info['public']}.")
            if not info["can_upload"] or not info["public"]:
                raise MediaError(
                    "Drive destination is not ready for public uploads; see docs/setup.md."
                )
        print("Read-only checks completed; no media uploaded or catalog writes performed.")
    elif args.command == "upload":
        kwargs = vars(args).copy()
        files = kwargs.pop("files")
        kwargs.pop("command")
        result = upload(*files, **kwargs)
        if result.dry_run:
            print(yaml.safe_dump(result.metadata, sort_keys=False, allow_unicode=True).strip())
            print("Dry run: no network requests or state changes.")
        else:
            print(json.dumps(asdict(result), indent=2))
    elif args.command == "pending":
        for receipt in pending():
            done = sum(bool(f.get("storage")) for f in receipt["files"])
            print(
                f"{receipt['upload_id']}  {receipt['asset_id']}  "
                f"{done}/{len(receipt['files'])} files"
            )
    elif args.command == "resume":
        print(json.dumps(asdict(resume(args.upload_id)), indent=2))
    elif args.command == "list":
        for asset_id in GitHub(settings).list_assets():
            print(asset_id)
    elif args.command == "show":
        from .metadata import validate_asset_id

        entry, _ = GitHub(settings).get_asset(validate_asset_id(args.asset_id))
        if entry is None:
            raise MediaError(f"Asset {args.asset_id} does not exist.")
        validate_asset(entry)
        print(yaml.safe_dump(entry, sort_keys=False, allow_unicode=True).strip())
    elif args.command == "validate":
        from pathlib import Path

        for path in args.files:
            file = Path(path)
            if file.stat().st_size > 1_000_000:
                raise MediaError(f"Catalog entry exceeds supported size: {path}")
            entry = yaml.safe_load(file.read_text())
            validate_asset(entry)
            if file.stem != entry["id"]:
                raise MediaError(f"Asset ID does not match the filename: {path}")
            print(f"Valid: {path}")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        run(args)
    except (MediaError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Check ibl-media pending if an upload was running.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
