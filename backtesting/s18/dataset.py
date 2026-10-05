"""Immutable, checksummed S18 datasets in the application's SQLite database.

The folder reader is a one-time import/test adapter. Product services use
get_dataset() and never need the original experiment directory or unpack files.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import sqlite3
from typing import Iterator, Protocol
import zlib

import numpy as np
import pandas as pd

from core import storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS s18_datasets (
    id TEXT PRIMARY KEY,
    manifest_json TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    validation_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS s18_dataset_assets (
    dataset_id TEXT NOT NULL REFERENCES s18_datasets(id),
    name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    raw_size INTEGER NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY(dataset_id, name)
);
"""
BASE_NAMES = (
    "data/dates.npy",
    "data/open.npy",
    "data/high.npy",
    "data/low.npy",
    "data/close.npy",
    "data/universe.npy",
    "data/nifty500.npy",
    "data/companies.csv",
    "data/signals/rows.npy",
    "data/ext/gold_silver.npz",
)
REFERENCE_NAMES = (
    *(
        f"S18_reference/{combo}_{mode}_{ending}"
        for combo in ("P5", "P10", "P15", "P20", "A20")
        for mode in ("none", "both", "both_priority")
        for ending in ("trades.csv", "open_book_2026-08-31.csv")
    ),
    "output/analysis/s18/s18_combos.parquet",
    "output/analysis/s18/s18_nav.npy",
    "output/analysis/s18/s18_nav_index.csv",
)
ACTIVE_KEY = "active_dataset"


def _name(name):
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or ":" in name
        or any(part in ("", ".", "..") for part in name.split("/"))
    ):
        raise ValueError(f"Invalid S18 logical asset name: {name!r}")
    return str(path)


def _manifest_hash(files):
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode() + b"\0" + files[name]["sha256"].encode())
    return digest.hexdigest()


class AssetSource(Protocol):
    origin: dict

    def names(self) -> tuple[str, ...]: ...
    def read(self, name: str) -> bytes: ...
    def require(self, names) -> None: ...
    def provenance(self, names) -> dict: ...
    def fingerprint(self, reference: bool = False) -> str: ...
    def open(self, name: str) -> BytesIO: ...


class AssetReader:
    def require(self, names):
        missing = sorted(set(names) - set(self.names()))
        if missing:
            raise ValueError(f"Missing required S18 dataset assets: {missing}")

    def open(self, name):
        return BytesIO(self.read(name))

    def array(self, name):
        with self.open(name) as stream:
            result = np.load(stream, allow_pickle=False)
            if not isinstance(result, np.ndarray):
                result.close()
                raise ValueError(f"Expected a single array: {name}")
            return result

    @contextmanager
    def archive(self, name) -> Iterator[object]:
        with self.open(name) as stream:
            with np.load(stream, allow_pickle=False) as archive:
                yield archive

    def csv(self, name, **kwargs):
        with self.open(name) as stream:
            return pd.read_csv(stream, **kwargs)

    def parquet(self, name):
        with self.open(name) as stream:
            return pd.read_parquet(stream)

    def provenance(self, names):
        files = {
            name: hashlib.sha256(self.read(name)).hexdigest()
            for name in sorted(set(names))
        }
        digest = hashlib.sha256()
        for name, checksum in files.items():
            digest.update(name.encode() + b"\0" + checksum.encode())
        return {"content_hash": digest.hexdigest(), "files": files}

    def fingerprint(self, reference=False):
        names = (
            REFERENCE_NAMES
            if reference
            else tuple(n for n in self.names() if n.startswith("data/"))
        )
        self.require(names)
        if not names:
            raise ValueError("S18 dataset has no input data")
        return self.provenance(names)["content_hash"]


class FolderSource(AssetReader):
    """Read-only importer adapter, never selected by normal strategy execution."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.origin = {"source": "import_folder"}

    def names(self):
        files = []
        for folder in ("data", "S18_reference", "output/analysis/s18"):
            directory = self.root.joinpath(*folder.split("/"))
            if directory.is_dir():
                for path in directory.rglob("*"):
                    if path.is_file() and path.suffix.lower() in (
                        ".npy",
                        ".npz",
                        ".csv",
                        ".parquet",
                    ):
                        if not path.resolve().is_relative_to(self.root):
                            raise ValueError(
                                "S18 import cannot follow files outside its source"
                            )
                        files.append(path.relative_to(self.root).as_posix())
        for name in ("S18_Forward_Test_Spec.md", "README.md"):
            if (self.root / name).is_file():
                files.append(name)
        return tuple(sorted(files))

    def read(self, name):
        path = self.root.joinpath(*_name(name).split("/"))
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("S18 asset escaped its import directory")
        return path.read_bytes()


class Dataset(AssetReader):
    def __init__(self, dataset_id, manifest, *, db_path=None):
        self.id = dataset_id
        self.manifest = manifest
        self.db_path = Path(db_path) if db_path else storage.database_path()
        self.origin = {"source": "application_database", "dataset_id": dataset_id}
        if _manifest_hash(manifest) != dataset_id:
            raise ValueError("S18 dataset manifest checksum mismatch")

    def names(self):
        return tuple(sorted(self.manifest))

    def read(self, name):
        name = _name(name)
        self.require([name])
        with storage.connection_scope(self.db_path) as connection:
            row = connection.execute(
                "SELECT sha256,raw_size,payload FROM s18_dataset_assets "
                "WHERE dataset_id=? AND name=?",
                (self.id, name),
            ).fetchone()
        return self._decode(name, row)

    def _decode(self, name, row):
        if row is None:
            raise ValueError(f"S18 database asset is missing: {name}")
        expected = self.manifest[name]
        if row["sha256"] != expected["sha256"] or row["raw_size"] != expected["size"]:
            raise ValueError(f"S18 database asset metadata mismatch: {name}")
        try:
            inflater = zlib.decompressobj()
            payload = inflater.decompress(row["payload"], expected["size"] + 1)
        except zlib.error as error:
            raise ValueError(f"S18 database asset is corrupt: {name}") from error
        if (
            not inflater.eof
            or inflater.unused_data
            or inflater.unconsumed_tail
            or len(payload) != expected["size"]
            or hashlib.sha256(payload).hexdigest() != expected["sha256"]
        ):
            raise ValueError(f"S18 database asset checksum mismatch: {name}")
        return payload

    def fingerprint(self, reference=False):
        names = (
            REFERENCE_NAMES
            if reference
            else tuple(n for n in self.names() if n.startswith("data/"))
        )
        self.require(names)
        return _manifest_hash({name: self.manifest[name] for name in names})

    def status(self):
        return {
            "dataset_id": self.id,
            "storage": "application SQLite",
            "asset_count": len(self.manifest),
            "uncompressed_bytes": sum(v["size"] for v in self.manifest.values()),
            "external_source_required": False,
        }


def get_dataset(*, db_path=None) -> Dataset:
    active = storage.get_document("s18", ACTIVE_KEY, {}, db_path=db_path)
    dataset_id = active.get("dataset_id")
    if not dataset_id:
        raise ValueError(
            "S18 historical data is not installed in the application database. "
            "Restore the app database backup or run the one-time S18 dataset import."
        )
    with storage.connection_scope(db_path) as connection:
        row = connection.execute(
            "SELECT manifest_json FROM s18_datasets WHERE id=?", (dataset_id,)
        ).fetchone()
    if row is None:
        raise ValueError(
            "The active S18 database dataset is missing; restore its backup"
        )
    return Dataset(dataset_id, json.loads(row[0]), db_path=db_path)


def import_dataset(source, *, db_path=None):
    folder = FolderSource(source)
    folder.require((*BASE_NAMES, *REFERENCE_NAMES))
    # Import the original bytes only after independently reproducing the golden output.
    from .replay import validate_dataset

    validation, _ = validate_dataset(folder)
    names = folder.names()
    manifest = {}
    for name in names:
        payload = folder.read(name)
        manifest[name] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
    dataset_id = _manifest_hash(manifest)
    if (
        _manifest_hash({n: manifest[n] for n in names if n.startswith("data/")})
        != validation["data_hash"]
        or _manifest_hash({n: manifest[n] for n in REFERENCE_NAMES})
        != validation["reference_hash"]
    ):
        raise ValueError("S18 source changed after validation; import cancelled")
    now = datetime.now(timezone.utc).isoformat()
    with storage.connection_scope(db_path) as connection:
        connection.executescript(SCHEMA)
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(
            "SELECT id FROM s18_datasets WHERE id=?", (dataset_id,)
        ).fetchone()
        if previous is None:
            connection.execute(
                "INSERT INTO s18_datasets VALUES(?,?,?,?)",
                (
                    dataset_id,
                    json.dumps(manifest, sort_keys=True),
                    now,
                    json.dumps(validation),
                ),
            )
            for name in names:
                payload = folder.read(name)
                if hashlib.sha256(payload).hexdigest() != manifest[name]["sha256"]:
                    raise ValueError(f"S18 source changed during import: {name}")
                connection.execute(
                    "INSERT INTO s18_dataset_assets VALUES(?,?,?,?,?)",
                    (
                        dataset_id,
                        name,
                        manifest[name]["sha256"],
                        len(payload),
                        sqlite3.Binary(zlib.compress(payload, level=1)),
                    ),
                )
        else:
            # Idempotency is not permission to silently accept a damaged existing version.
            existing = Dataset(dataset_id, manifest, db_path=db_path)
            for name in names:
                row = connection.execute(
                    "SELECT sha256,raw_size,payload FROM s18_dataset_assets "
                    "WHERE dataset_id=? AND name=?",
                    (dataset_id, name),
                ).fetchone()
                existing._decode(name, row)
        active = {"dataset_id": dataset_id, "activated_at": now}
        connection.execute(
            "INSERT INTO documents(namespace,key,value_json,created_at,updated_at) "
            "VALUES('s18',?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET "
            "value_json=excluded.value_json,updated_at=excluded.updated_at",
            (ACTIVE_KEY, json.dumps(active), now, now),
        )
    return get_dataset(db_path=db_path).status()


def export_dataset(destination, *, db_path=None):
    dataset = get_dataset(db_path=db_path)
    target = Path(destination).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError("Dataset export destination must be empty")
    target.mkdir(parents=True, exist_ok=True)
    for name in dataset.names():
        path = target.joinpath(*_name(name).split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(dataset.read(name))
    return dataset.status()


def export_reference_artifacts(destination=None, *, db_path=None):
    """Project-local reference documents/outputs; historical price panels stay in DB."""
    dataset = get_dataset(db_path=db_path)
    target = (
        Path(destination).expanduser().resolve()
        if destination is not None
        else Path(__file__).resolve().parents[2]
        / "reports"
        / "s18"
        / "reference"
        / dataset.id
    )
    names = [
        *REFERENCE_NAMES,
        *(n for n in ("S18_Forward_Test_Spec.md", "README.md") if n in dataset.names()),
    ]
    for name in names:
        path = target.joinpath(*_name(name).split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dataset.read(name)
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(
                f"Refusing to replace a modified project reference artifact: {path}"
            )
        if not path.exists():
            path.write_bytes(payload)
    manifest_path = target / "dataset_manifest.json"
    payload = json.dumps(
        {**dataset.status(), "assets": dataset.manifest}, indent=2, sort_keys=True
    ).encode("utf-8")
    if manifest_path.exists() and manifest_path.read_bytes() != payload:
        raise ValueError("Refusing to replace a modified project dataset manifest")
    if not manifest_path.exists():
        manifest_path.write_bytes(payload)
    return {"reference_artifacts": str(target), "dataset_id": dataset.id}


def migrate_path_settings(*, db_path=None):
    """Remove operational folder parameters, without rewriting historical run evidence."""
    dataset = get_dataset(db_path=db_path)
    with storage.connection_scope(db_path) as connection:
        with connection:
            rows = connection.execute(
                "SELECT id,params_json FROM schedules WHERE strategy_id LIKE 's18_%'"
            ).fetchall()
            if any(
                json.loads(row["params_json"]).get("data_source") == "csv"
                for row in rows
            ):
                raise ValueError(
                    "An S18 schedule still uses an offline CSV feed; migrate its forward "
                    "history explicitly before switching the schedule to automatic NSE data"
                )
            for row in rows:
                params = json.loads(row["params_json"])
                for key in ("kit_path", "forward_path", "data_source"):
                    params.pop(key, None)
                connection.execute(
                    "UPDATE schedules SET params_json=? WHERE id=?",
                    (json.dumps(params), row["id"]),
                )
            for namespace, key in (
                ("s18", "settings"),
                ("strategy_defaults", "s18_daily"),
            ):
                row = connection.execute(
                    "SELECT value_json FROM documents WHERE namespace=? AND key=?",
                    (namespace, key),
                ).fetchone()
                if row is None:
                    continue
                value = json.loads(row[0])
                for field in ("kit_path", "forward_path", "data_source"):
                    value.pop(field, None)
                if namespace == "s18":
                    value["dataset_id"] = dataset.id
                connection.execute(
                    "UPDATE documents SET value_json=? WHERE namespace=? AND key=?",
                    (json.dumps(value), namespace, key),
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    references = commands.add_parser("export-reference")
    references.add_argument("--destination")
    importer = commands.add_parser("import")
    importer.add_argument("--source", required=True)
    exporter = commands.add_parser("export")
    exporter.add_argument("--destination", required=True)
    args = parser.parse_args()
    if args.command == "import":
        result = import_dataset(args.source)
        migrate_path_settings()
    elif args.command == "export":
        result = export_dataset(args.destination)
    elif args.command == "export-reference":
        result = export_reference_artifacts(args.destination)
    else:
        result = get_dataset().status()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
