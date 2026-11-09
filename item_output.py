"""Versioned, filesystem-only handoff for an AOM item."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shlex
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA_VERSION = "1.0.0"
MANIFEST = "item_manifest.json"
INVENTORY = "inventory-qa-measurements.csv"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def file_record(path, relative_path, role, sha256=None):
    stat = path.stat()
    if sha256 is None:
        with path.open("rb") as file:
            sha256 = hashlib.file_digest(file, "sha256").hexdigest()
        if file_stamp(path) != (stat.st_size, stat.st_mtime_ns, stat.st_ino, stat.st_dev):
            raise ValueError(f"File changed while hashing: {path.name}")
    return {
        "path": relative_path,
        "role": role,
        "size_bytes": stat.st_size,
        "sha256": sha256,
    }


def file_stamp(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino, stat.st_dev


def wavefront_tokens(value):
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    return list(lexer)


def texture_name(value):
    """Read standard MTL map options before the filename."""
    args = wavefront_tokens(value)
    fixed = {
        "-blendu": 1, "-blendv": 1, "-boost": 1, "-mm": 2, "-texres": 1,
        "-clamp": 1, "-bm": 1, "-imfchan": 1, "-type": 1, "-cc": 1,
        "-colorspace": 1,
    }
    while args and args[0].startswith("-"):
        option = args.pop(0).lower()
        if option in fixed and len(args) > fixed[option]:
            del args[:fixed[option]]
        elif option in ("-o", "-s", "-t"):
            count = 0
            while count < min(3, len(args) - 1):
                try:
                    float(args[count])
                except ValueError:
                    break
                count += 1
            if not count:
                return None
            del args[:count]
        else:
            return None
    return " ".join(args) or None


def source_dependencies(entry, root):
    """Snapshot declared local dependencies without changing renderer resolution."""
    root = root.resolve()
    records = {}
    stamps = {}
    references = []

    def reference(owner, raw, role, status="resolved", target_name=None):
        target = None
        candidate = None
        if status == "resolved":
            try:
                name = raw if target_name is None else target_name
                if urlsplit(name).scheme or Path(name).is_absolute():
                    raise ValueError("absolute or external")
                candidate = (owner.parent / name.replace("\\", "/")).resolve()
                target = candidate.relative_to(root).as_posix()
            except (ValueError, OSError, RuntimeError):
                status = "outside_input"
            if status == "resolved" and target not in records:
                try:
                    before = file_stamp(candidate)
                    record = file_record(candidate, target, role)
                    records[target] = record
                    stamps[candidate] = before
                except FileNotFoundError:
                    status = "missing"
                except (OSError, ValueError):
                    status = "unreadable"
        references.append({
            "from": owner.relative_to(root).as_posix(), "reference": raw,
            "target": target, "role": role, "status": status,
        })
        return candidate if status == "resolved" else None

    if entry.suffix.lower() == ".obj":
        parsed_mtls = set()
        with entry.open("rb") as source:
            for line in source:
                parts = line.lstrip().split(None, 1)
                if len(parts) != 2 or parts[0].lower() != b"mtllib":
                    continue
                raw = parts[1].decode("utf-8", errors="replace").strip()
                try:
                    names = wavefront_tokens(raw)
                except ValueError:
                    names = []
                # A common exporter writes an unquoted MTL filename with spaces.
                whole = " ".join(names)
                if len(names) > 1 and (entry.parent / whole).is_file():
                    names = [whole]
                if not names:
                    reference(entry, raw, "material", "unsupported")
                for name in names:
                    mtl = reference(entry, name, "material")
                    if mtl is None or mtl in parsed_mtls:
                        continue
                    parsed_mtls.add(mtl)
                    try:
                        material = mtl.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        reference(mtl, "", "texture", "unreadable")
                        continue
                    for statement in material.splitlines():
                        tokens = statement.split(None, 1)
                        if not tokens or not (
                            tokens[0].lower().startswith("map_")
                            or tokens[0].lower() in ("bump", "disp", "decal", "refl", "norm")
                        ):
                            continue
                        raw_map = tokens[1] if len(tokens) == 2 else ""
                        try:
                            name = texture_name(raw_map)
                        except ValueError:
                            name = None
                        reference(mtl, raw_map, "texture",
                                  "resolved" if name else "unsupported", target_name=name)
    elif entry.suffix.lower() == ".glb":
        try:
            with entry.open("rb") as source:
                magic, version, _ = struct.unpack("<4sII", source.read(12))
                length, chunk = struct.unpack("<I4s", source.read(8))
                if (magic, version, chunk) != (b"glTF", 2, b"JSON"):
                    raise ValueError("Invalid GLB header")
                if length > entry.stat().st_size - 20:
                    raise ValueError("Invalid GLB JSON length")
                description = json.loads(source.read(length))
            for key in ("buffers", "images"):
                for item in description.get(key, []):
                    uri = item.get("uri")
                    if uri and not uri.lower().startswith("data:"):
                        reference(entry, uri, "external_glb_resource", "unsupported")
        except (ValueError, OSError, struct.error, TypeError, AttributeError):
            reference(entry, "", "glb_json", "unreadable")
    return records, references, stamps


def obj_read_record(reference, path, data):
    return {
        "reference": reference,
        "status": "read",
        "path": path,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def source_manifest(entry, root, source_sha256, dependencies, obj_reads=()):
    records, references, _ = dependencies
    entry_path = entry.relative_to(root.resolve()).as_posix()
    main = file_record(entry, entry_path, "model", source_sha256)
    files_by_path = {**records, entry_path: main}
    reads = []
    for read in obj_reads:
        if read["status"] != "read":
            reads.append(read)
            continue
        path = (entry.parent / read["path"]).relative_to(root.resolve()).as_posix()
        prior = files_by_path.get(path)
        if prior is not None and prior["sha256"] != read["sha256"]:
            raise ValueError(f"読み込み中に入力ファイルが変更されました: {path}")
        if prior is None:
            files_by_path[path] = {
                "path": path,
                "role": "material" if Path(path).suffix.lower() == ".mtl" else "texture",
                "size_bytes": read["size_bytes"],
                "sha256": read["sha256"],
            }
        reads.append({**read, "path": path})
    files = sorted(files_by_path.values(), key=lambda item: item["path"])
    complete = (
        all(ref["status"] == "resolved" for ref in references)
        and all(read["status"] == "read" for read in reads)
    )
    identity = [entry_path, [[item["path"], item["sha256"]] for item in files]]
    canonical = json.dumps(identity, ensure_ascii=True, separators=(",", ":"))
    return {
        "entry": entry_path,
        "source_sha256": source_sha256,
        "source_bundle_sha256": (
            hashlib.sha256(canonical.encode("ascii")).hexdigest() if complete else None
        ),
        "bundle_hash_encoding": "aom-ordered-json-v1",
        "status": "complete" if complete else "incomplete",
        "reference_basis": "declared_and_observed_obj_reads",
        "files": files,
        "references": references,
        "loader_reads": reads,
    }


def append_inventory(path, row):
    """Append one row with atomic replacement. Caller serializes writers."""
    fieldnames = list(row)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", dir=path.parent,
            prefix=".aom-inventory-", delete=False,
        ) as output:
            temp = Path(output.name)
            writer = csv.writer(output)
            writer.writerow(fieldnames)
            if path.exists():
                with path.open(encoding="utf-8-sig", newline="") as old:
                    reader = csv.reader(old, strict=True)
                    if next(reader, None) != fieldnames:
                        raise ValueError("既存の一覧CSVの列構成が一致しません。")
                    for previous in reader:
                        if len(previous) != len(fieldnames):
                            raise ValueError("既存の一覧CSVに不正な行があります。")
                        writer.writerow(previous)
            writer.writerow(row.values())
            output.flush()
            os.fsync(output.fileno())
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def inventory_row(folder, output_root):
    """Read the saved revision, keeping current GUI settings out of the CSV."""
    manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    metadata = {}
    for role in ("measurements", "quality"):
        expected = next((item for item in manifest["outputs"] if item["role"] == role), None)
        if expected is None or Path(expected["path"]).name != expected["path"]:
            raise ValueError(f"資料マニフェストの {role} が無効です。")
        path = folder / expected["path"]
        actual = file_record(path, expected["path"], role)
        if actual["sha256"] != expected["sha256"]:
            raise ValueError(f"確定後に変更されたファイルがあります: {path.name}")
        metadata[role] = path
    quality = json.loads(metadata["quality"].read_text(encoding="utf-8"))
    with metadata["measurements"].open(encoding="utf-8-sig", newline="") as file:
        measurements = list(csv.DictReader(file))
    model = next((row for row in measurements if row["record_type"] == "model_bbox"), None)
    if model is None:
        raise ValueError("モデル全体の計測行がありません。")
    if any(data["revision_id"] != manifest["revision_id"] for data in [quality, *measurements]):
        raise ValueError("処理版IDが一致しません。")
    sections = [
        {key: row[key] for key in (
            "record_id", "section_plane", "section_position_percent", "section_coordinate_mm",
            "bbox_x_mm", "bbox_y_mm", "bbox_z_mm", "status",
        )}
        for row in measurements if row["record_type"] == "section_bbox"
    ]
    return {
        "item_id": manifest["item_id"],
        "revision_id": manifest["revision_id"],
        "artifact_type": manifest["artifact_type"],
        "output_path": folder.relative_to(output_root).as_posix(),
        "source_file": model["source_file"],
        "source_sha256": manifest["inputs"]["source_sha256"],
        "source_bundle_sha256": manifest["inputs"]["source_bundle_sha256"],
        "input_unit": manifest["input_unit"],
        "bbox_x_mm": model["bbox_x_mm"],
        "bbox_y_mm": model["bbox_y_mm"],
        "bbox_z_mm": model["bbox_z_mm"],
        "surface_area_mm2": model["surface_area_mm2"],
        "volume_mm3": model["volume_mm3"],
        "vertices": quality["vertices"],
        "faces": quality["faces"],
        "source_file_size_bytes": quality["source_file_size_bytes"],
        "is_watertight": quality["is_watertight"],
        "source_dependencies": quality["checks"]["source_dependencies"],
        "normals_status": quality["checks"]["normals"],
        "appearance_kind": quality["checks"]["appearance"],
        "volume_status": quality["checks"]["volume"],
        "warning_codes": "|".join(quality["warnings"]),
        "sections_json": json.dumps(sections, ensure_ascii=False, separators=(",", ":")),
        "appended_at_utc": utc_now(),
    }
