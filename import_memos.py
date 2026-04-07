#!/usr/bin/env python3

import argparse
import base64
import datetime as dt
import json
import os
import tempfile
import zipfile
from pathlib import Path

from memos_api import MemosAPI


def parse_args():
    parser = argparse.ArgumentParser(
        description="Import a memos export bundle into a Memos instance."
    )
    parser.add_argument("--base-url", default=os.environ.get("MEMOS_BASE_URL"))
    parser.add_argument("--token", default=os.environ.get("MEMOS_TOKEN"))
    parser.add_argument("--bundle", required=True)
    parser.add_argument(
        "--conflict-strategy",
        choices=["fail", "skip"],
        default="fail",
    )
    parser.add_argument(
        "--state-file",
        default="",
        help="Optional import state path. Defaults to <bundle>.import-state.json",
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


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def attachment_id_from_name(name):
    if not name:
        return ""
    return name.split("/", 1)[-1]


def memo_id_from_name(name):
    if not name:
        return ""
    return name.split("/", 1)[-1]


def default_state_file(bundle_path):
    return f"{bundle_path}.import-state.json"


def initial_state(bundle_path, base_url):
    return {
        "bundle_path": str(Path(bundle_path).resolve()),
        "target_instance": base_url.rstrip("/"),
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_memos": {},
        "patched_memos": {},
        "skipped_memos": {},
        "uploaded_attachments": {},
        "applied_relations": {},
        "failures": [],
    }


def touch_state(state, state_file):
    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    write_json(state_file, state)


def record_failure(state, state_file, stage, memo_id, detail):
    state["failures"].append(
        {
            "stage": stage,
            "memo_id": memo_id,
            "detail": detail,
        }
    )
    touch_state(state, state_file)


def load_or_initialize_state(state_file, bundle_path, base_url):
    if not state_file.exists():
        state = initial_state(bundle_path, base_url)
        touch_state(state, state_file)
        return state

    state = load_json(state_file)
    expected_bundle_path = str(Path(bundle_path).resolve())
    expected_target = base_url.rstrip("/")
    if state.get("bundle_path") != expected_bundle_path:
        raise SystemExit(
            "Existing state file belongs to a different bundle. "
            "Use --state-file with a different path or remove the old state file."
        )
    if state.get("target_instance") != expected_target:
        raise SystemExit(
            "Existing state file belongs to a different target instance. "
            "Use --state-file with a different path or remove the old state file."
        )

    for key, default in (
        ("created_memos", {}),
        ("patched_memos", {}),
        ("skipped_memos", {}),
        ("uploaded_attachments", {}),
        ("applied_relations", {}),
        ("failures", []),
    ):
        state.setdefault(key, default.copy() if isinstance(default, dict) else list(default))
    return state


def load_manifest(extracted_dir):
    manifest_path = Path(extracted_dir) / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Bundle is missing manifest.json")
    manifest = load_json(manifest_path)
    if manifest.get("format_version") != 1:
        raise SystemExit(f"Unsupported format_version: {manifest.get('format_version')}")
    if manifest.get("bundle_type") != "memos-export":
        raise SystemExit(f"Unsupported bundle_type: {manifest.get('bundle_type')}")
    return manifest


def validate_manifest_files(extracted_dir, manifest):
    root = Path(extracted_dir)
    for item in manifest.get("items", []):
        memo_path = root / item["memo_json_path"]
        if not memo_path.exists():
            raise SystemExit(f"Missing memo payload file: {memo_path}")


def build_create_memo_payload(memo):
    payload = {
        "state": memo.get("state") or "NORMAL",
        "content": memo.get("content") or "",
        "visibility": memo.get("visibility") or "PRIVATE",
    }
    for field in ("createTime", "updateTime", "displayTime", "location"):
        if memo.get(field) is not None:
            payload[field] = memo[field]
    if memo.get("pinned") is not None:
        payload["pinned"] = memo["pinned"]
    return payload


def build_update_memo_payload(memo_id, memo):
    return {
        "name": f"memos/{memo_id}",
        "state": memo.get("state") or "NORMAL",
        "pinned": bool(memo.get("pinned", False)),
    }


def memo_needs_post_create_patch(memo):
    desired_state = memo.get("state") or "NORMAL"
    desired_pinned = bool(memo.get("pinned", False))
    return desired_state != "NORMAL" or desired_pinned


def build_attachment_payload(memo_id, attachment, extracted_dir):
    payload = {
        "filename": attachment.get("filename") or attachment_id_from_name(attachment.get("name")),
        "type": attachment.get("type") or "application/octet-stream",
        "memo": f"memos/{memo_id}",
    }
    exported_path = attachment.get("exportedPath")
    if exported_path:
        file_path = Path(extracted_dir) / exported_path
        if not file_path.exists():
            raise FileNotFoundError(f"Attachment file not found: {file_path}")
        payload["content"] = base64.b64encode(file_path.read_bytes()).decode("ascii")
        return payload
    if attachment.get("externalLink"):
        payload["externalLink"] = attachment["externalLink"]
        return payload
    raise ValueError("Attachment has neither exportedPath nor externalLink")


def normalize_relations(relations):
    normalized = []
    for relation in relations:
        memo_name = ((relation.get("memo") or {}).get("name") or "").strip()
        related_memo_name = ((relation.get("relatedMemo") or {}).get("name") or "").strip()
        relation_type = relation.get("type") or "TYPE_UNSPECIFIED"
        if not memo_name or not related_memo_name:
            continue
        normalized.append(
            {
                "memo": {"name": memo_name},
                "relatedMemo": {"name": related_memo_name},
                "type": relation_type,
            }
        )
    return normalized


def target_memo_name(state, memo_id):
    return state["created_memos"].get(memo_id) or state["skipped_memos"].get(memo_id) or ""


def target_has_memo(api, state, memo_id, existence_cache):
    if not memo_id:
        return False
    if target_memo_name(state, memo_id):
        return True
    if memo_id not in existence_cache:
        existing = api.get_memo(memo_id)
        existence_cache[memo_id] = existing.get("name", "") if existing else ""
    return bool(existence_cache[memo_id])


def build_existing_attachment_index(api, memo_id):
    attachment_ids = {}
    for attachment in api.list_memo_attachments(memo_id):
        attachment_id = attachment_id_from_name(attachment.get("name"))
        if attachment_id:
            attachment_ids[attachment_id] = attachment.get("name", "")
    return attachment_ids


def main():
    args = parse_args()
    require(args.base_url, "base_url")
    require(args.token, "token")

    bundle_path = Path(args.bundle).resolve()
    if not bundle_path.exists():
        raise SystemExit(f"Bundle not found: {bundle_path}")

    state_file = Path(args.state_file or default_state_file(bundle_path)).resolve()
    state = load_or_initialize_state(state_file, bundle_path, args.base_url)

    api = MemosAPI(args.base_url, args.token, timeout=args.timeout)
    api.get_current_user()

    with tempfile.TemporaryDirectory(prefix="memos-import-") as temp_dir:
        with zipfile.ZipFile(bundle_path) as archive:
            archive.extractall(temp_dir)

        manifest = load_manifest(temp_dir)
        validate_manifest_files(temp_dir, manifest)

        memo_payloads = []
        for item in manifest.get("items", []):
            memo_path = Path(temp_dir) / item["memo_json_path"]
            memo_payloads.append((item, load_json(memo_path)))

        existence_cache = {}
        pending = list(memo_payloads)
        while pending:
            progressed = False
            next_pending = []
            for item, memo in pending:
                memo_id = item["memo_id"]
                if memo_id in state["created_memos"] or memo_id in state["skipped_memos"]:
                    progressed = True
                    continue

                parent_name = memo.get("parent") or ""
                parent_id = memo_id_from_name(parent_name)
                if parent_id and not target_has_memo(api, state, parent_id, existence_cache):
                    next_pending.append((item, memo))
                    continue

                existing = api.get_memo(memo_id)
                if existing is not None:
                    if args.conflict_strategy == "fail":
                        raise SystemExit(f"Memo already exists in target instance: {memo_id}")
                    state["skipped_memos"][memo_id] = existing.get("name", f"memos/{memo_id}")
                    touch_state(state, state_file)
                    existence_cache[memo_id] = state["skipped_memos"][memo_id]
                    progressed = True
                    continue

                try:
                    if parent_id:
                        created = api.create_memo_comment(
                            parent_id,
                            memo_id,
                            build_create_memo_payload(memo),
                        )
                    else:
                        created = api.create_memo(memo_id, build_create_memo_payload(memo))
                except Exception as exc:
                    record_failure(state, state_file, "create_memo", memo_id, str(exc))
                    progressed = True
                    continue

                state["created_memos"][memo_id] = created.get("name", f"memos/{memo_id}")
                touch_state(state, state_file)
                existence_cache[memo_id] = state["created_memos"][memo_id]
                progressed = True

            if not next_pending:
                break
            if not progressed:
                unresolved = ", ".join(sorted(item["memo_id"] for item, _memo in next_pending))
                raise SystemExit(
                    "Some parented memos could not be created because their parent memo "
                    f"does not exist in the target instance: {unresolved}"
                )
            pending = next_pending

        for item, memo in memo_payloads:
            memo_id = item["memo_id"]
            if memo_id not in state["created_memos"]:
                continue
            if memo_id in state["patched_memos"]:
                continue
            if not memo_needs_post_create_patch(memo):
                state["patched_memos"][memo_id] = True
                touch_state(state, state_file)
                continue
            try:
                api.update_memo(
                    memo_id,
                    build_update_memo_payload(memo_id, memo),
                    update_mask=["state", "pinned"],
                )
            except Exception as exc:
                record_failure(state, state_file, "update_memo", memo_id, str(exc))
                continue
            state["patched_memos"][memo_id] = True
            touch_state(state, state_file)

        for item, memo in memo_payloads:
            memo_id = item["memo_id"]
            if not target_memo_name(state, memo_id):
                continue
            uploaded = state["uploaded_attachments"].setdefault(memo_id, {})
            existing_attachment_ids = build_existing_attachment_index(api, memo_id)
            new_existing = {
                key: value
                for key, value in existing_attachment_ids.items()
                if key not in uploaded
            }
            if new_existing:
                uploaded.update(new_existing)
                touch_state(state, state_file)

            for attachment in memo.get("attachments", []):
                if (
                    manifest.get("attachment_mode") != "embedded_files"
                    and not attachment.get("externalLink")
                ):
                    continue
                attachment_id = attachment_id_from_name(attachment.get("name"))
                if attachment_id and attachment_id in uploaded:
                    continue
                try:
                    payload = build_attachment_payload(memo_id, attachment, temp_dir)
                    created = api.create_attachment(attachment_id, payload)
                except Exception as exc:
                    record_failure(
                        state,
                        state_file,
                        "create_attachment",
                        memo_id,
                        f"{attachment.get('filename')}: {exc}",
                    )
                    continue
                uploaded_key = attachment_id or created.get("name", "")
                uploaded[uploaded_key] = created.get("name", "")
                touch_state(state, state_file)

        for item, memo in memo_payloads:
            memo_id = item["memo_id"]
            if not target_memo_name(state, memo_id):
                continue
            if memo_id in state["applied_relations"]:
                continue
            relations = normalize_relations(memo.get("relations", []))
            if not relations:
                state["applied_relations"][memo_id] = True
                touch_state(state, state_file)
                continue
            try:
                api.set_memo_relations(memo_id, relations)
            except Exception as exc:
                record_failure(state, state_file, "set_relations", memo_id, str(exc))
                continue
            state["applied_relations"][memo_id] = True
            touch_state(state, state_file)

    report = {
        "started_at": state["started_at"],
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_instance": args.base_url.rstrip("/"),
        "created_memo_count": len(state["created_memos"]),
        "patched_memo_count": len(state["patched_memos"]),
        "skipped_memo_count": len(state["skipped_memos"]),
        "uploaded_attachment_count": sum(
            len(items) for items in state["uploaded_attachments"].values()
        ),
        "applied_relation_count": len(state["applied_relations"]),
        "failures": state["failures"],
    }
    report_path = state_file.with_suffix(state_file.suffix + ".report.json")
    write_json(report_path, report)

    print(f"Created memos: {report['created_memo_count']}")
    print(f"Patched memos: {report['patched_memo_count']}")
    print(f"Skipped memos: {report['skipped_memo_count']}")
    print(f"Uploaded attachments: {report['uploaded_attachment_count']}")
    print(f"Applied relations: {report['applied_relation_count']}")
    print(f"State file: {state_file}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
