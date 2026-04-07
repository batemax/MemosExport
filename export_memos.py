#!/usr/bin/env python3

import argparse
import base64
import datetime as dt
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from memos_api import MemosAPI


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export memos from a Memos instance into a zip bundle."
    )
    parser.add_argument("--base-url", default=os.environ.get("MEMOS_BASE_URL"))
    parser.add_argument("--token", default=os.environ.get("MEMOS_TOKEN"))
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--order-by", default="display_time desc")
    parser.add_argument("--filter", default="")
    parser.add_argument(
        "--state",
        choices=["normal", "archived", "all"],
        default="all",
    )
    parser.add_argument(
        "--attachment-mode",
        choices=["metadata_only", "embedded_files"],
        default="metadata_only",
    )
    parser.add_argument(
        "--bundle-name",
        default="",
        help="Optional output zip filename or path. Defaults to ./memos-export-<timestamp>.zip",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds for each request.",
    )
    return parser.parse_args()


def require(value, name):
    if not value:
        raise SystemExit(
            f"Missing {name}. Pass --{name.replace('_', '-')} or set the matching environment variable."
        )


def sanitize_filename(value, fallback):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return cleaned or fallback


def memo_id_from_name(name):
    return name.split("/", 1)[-1]


def attachment_id_from_name(name):
    return name.split("/", 1)[-1]


def export_timestamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def decode_attachment_content(content):
    if not content:
        return None
    try:
        return base64.b64decode(content)
    except Exception:
        return None


def download_attachment_bytes(api, attachment):
    attachment_name = attachment.get("name") or ""
    attachment_id = attachment_id_from_name(attachment_name)
    filename = attachment.get("filename") or attachment_id
    if not attachment_id or not filename:
        return None
    content_bytes, _headers = api.download_attachment_file(attachment_id, filename)
    return content_bytes


def build_manifest(source_instance, source_user, attachment_mode, order_by, filter_expression):
    return {
        "format_version": 1,
        "bundle_type": "memos-export",
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_instance": source_instance,
        "source_user": source_user,
        "memo_count": 0,
        "attachment_mode": attachment_mode,
        "states": [],
        "order_by": order_by,
        "filter": filter_expression,
        "items": [],
        "warnings": [],
    }


def sanitize_user(user):
    if not isinstance(user, dict):
        return user
    sanitized = dict(user)
    sanitized.pop("password", None)
    return sanitized


def write_bundle(staging_dir, bundle_path):
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging_dir))


def resolve_bundle_path(bundle_name_arg):
    default_name = f"memos-export-{export_timestamp()}.zip"
    if bundle_name_arg:
        candidate = Path(bundle_name_arg)
        if candidate.is_absolute() or candidate.parent != Path("."):
            bundle_path = candidate.resolve()
        else:
            bundle_path = (Path.cwd() / candidate.name).resolve()
    else:
        bundle_path = (Path.cwd() / default_name).resolve()
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    return bundle_path


def main():
    args = parse_args()
    require(args.base_url, "base_url")
    require(args.token, "token")

    api = MemosAPI(args.base_url, args.token, timeout=args.timeout)
    source_user = api.get_current_user()

    states = []
    if args.state == "all":
        states = ["NORMAL", "ARCHIVED"]
    elif args.state == "normal":
        states = ["NORMAL"]
    else:
        states = ["ARCHIVED"]

    bundle_path = resolve_bundle_path(args.bundle_name)

    with tempfile.TemporaryDirectory(prefix="memos-export-") as temp_dir:
        staging_dir = Path(temp_dir)
        memos_dir = staging_dir / "memos"
        attachments_dir = staging_dir / "attachments"
        memos_dir.mkdir(parents=True, exist_ok=True)
        if args.attachment_mode == "embedded_files":
            attachments_dir.mkdir(parents=True, exist_ok=True)

        manifest = build_manifest(
            source_instance=args.base_url.rstrip("/"),
            source_user=sanitize_user(source_user),
            attachment_mode=args.attachment_mode,
            order_by=args.order_by,
            filter_expression=args.filter,
        )
        manifest["states"] = states

        seen = {}
        for state in states:
            for memo in api.list_memos(
                state=state,
                page_size=args.page_size,
                order_by=args.order_by,
                filter_expression=args.filter,
            ):
                seen[memo["name"]] = memo

        for memo_name in sorted(seen.keys()):
            memo = seen[memo_name]
            memo_id = memo_id_from_name(memo["name"])
            attachments = api.list_memo_attachments(memo_id)
            exported_attachments = []

            if args.attachment_mode == "embedded_files":
                target_attachment_dir = attachments_dir / memo_id
                target_attachment_dir.mkdir(parents=True, exist_ok=True)
            else:
                target_attachment_dir = None

            for index, attachment in enumerate(attachments, start=1):
                exported_attachment = dict(attachment)
                content_bytes = decode_attachment_content(attachment.get("content"))
                if (
                    args.attachment_mode == "embedded_files"
                    and not attachment.get("externalLink")
                    and content_bytes is None
                ):
                    try:
                        content_bytes = download_attachment_bytes(api, attachment)
                    except Exception:
                        content_bytes = None
                if args.attachment_mode == "embedded_files" and content_bytes is not None:
                    filename = sanitize_filename(
                        attachment.get("filename") or f"attachment-{index}",
                        f"attachment-{index}",
                    )
                    destination = target_attachment_dir / filename
                    if destination.exists():
                        destination = target_attachment_dir / f"{destination.stem}--{index}{destination.suffix}"
                    destination.write_bytes(content_bytes)
                    exported_attachment["exportedPath"] = str(
                        destination.relative_to(staging_dir)
                    )
                    exported_attachment.pop("content", None)
                else:
                    if (
                        args.attachment_mode == "embedded_files"
                        and not attachment.get("externalLink")
                        and content_bytes is None
                    ):
                        manifest["warnings"].append(
                            {
                                "type": "attachment_not_exportable",
                                "memo_id": memo_id,
                                "attachment_name": attachment.get("name"),
                                "detail": "Attachment metadata was exported, but file bytes were not available from the public API.",
                            }
                        )
                    exported_attachment.pop("content", None)
                exported_attachments.append(exported_attachment)

            memo_payload = {
                "name": memo.get("name"),
                "memo_id": memo_id,
                "state": memo.get("state"),
                "creator": memo.get("creator"),
                "createTime": memo.get("createTime"),
                "updateTime": memo.get("updateTime"),
                "displayTime": memo.get("displayTime"),
                "content": memo.get("content"),
                "visibility": memo.get("visibility"),
                "pinned": memo.get("pinned", False),
                "tags": memo.get("tags", []),
                "parent": memo.get("parent"),
                "snippet": memo.get("snippet"),
                "location": memo.get("location"),
                "attachments": exported_attachments,
                "relations": memo.get("relations", []),
            }

            memo_filename = f"memos_{sanitize_filename(memo_id, memo_id)}.json"
            memo_path = memos_dir / memo_filename
            memo_path.write_text(
                json.dumps(memo_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            manifest["items"].append(
                {
                    "memo_name": memo.get("name"),
                    "memo_id": memo_id,
                    "memo_json_path": str(memo_path.relative_to(staging_dir)),
                    "attachment_dir": (
                        f"attachments/{memo_id}"
                        if args.attachment_mode == "embedded_files"
                        and any(item.get("exportedPath") for item in exported_attachments)
                        else ""
                    ),
                    "attachment_count": len(exported_attachments),
                }
            )

        manifest["memo_count"] = len(manifest["items"])
        (staging_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_bundle(staging_dir, bundle_path)

    print(f"Exported {manifest['memo_count']} memos")
    print(f"Bundle: {bundle_path}")
    if manifest["warnings"]:
        print(f"Warnings: {len(manifest['warnings'])}")


if __name__ == "__main__":
    main()
