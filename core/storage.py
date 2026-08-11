"""Central local SQLite persistence for the application.

The database lives in the operating system's per-user data directory by default,
not in the repository. Set ``PORTFOLIO_DB_PATH`` to choose another location.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

from dotenv import load_dotenv

load_dotenv()

_APP_DIR_NAME = "AgenticPortfolioManager"
_SCHEMA_VERSION = 1


def default_data_dir() -> Path:
    """Return the platform-appropriate persistent data directory."""
    if os.name == "nt":
        root = os.getenv("LOCALAPPDATA")
        return Path(root) / _APP_DIR_NAME if root else Path.home() / _APP_DIR_NAME
    if os.uname().sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / _APP_DIR_NAME
    root = os.getenv("XDG_DATA_HOME")
    return (Path(root) if root else Path.home() / ".local" / "share") / (
        _APP_DIR_NAME.lower()
    )


def database_path() -> Path:
    override = (
        os.getenv("PORTFOLIO_DB_PATH", "").strip()
        or os.getenv("TRADER_WORKBENCH_DB", "").strip()
    )
    return Path(override).expanduser() if override else default_data_dir() / "portfolio.sqlite3"


def runtime_dir() -> Path:
    path = database_path().parent / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def connect(
    db_path: Optional[Path] = None,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open a configured connection and ensure the current schema exists."""
    path = Path(db_path) if db_path is not None else database_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(
        path, timeout=30, check_same_thread=check_same_thread
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")
    _initialize_schema(connection)
    _restrict_permissions(path)
    return connection


@contextmanager
def connection_scope(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Open a transactional connection and always release its file handles."""
    connection = connect(db_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _restrict_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    if path.parent == default_data_dir():
        path.parent.chmod(0o700)
    path.chmod(0o600)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.exists():
            sidecar.chmod(0o600)


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_info (
            version INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            params_json TEXT NOT NULL,
            report TEXT NOT NULL,
            data_json TEXT NOT NULL,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_runs_created_at
            ON runs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_runs_strategy_created
            ON runs(strategy_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS documents (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (namespace, key)
        );
        CREATE INDEX IF NOT EXISTS idx_documents_updated
            ON documents(namespace, updated_at DESC);

        CREATE TABLE IF NOT EXISTS cache_entries (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            payload BLOB NOT NULL,
            format TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT,
            PRIMARY KEY (namespace, key)
        );
        CREATE INDEX IF NOT EXISTS idx_cache_expires
            ON cache_entries(expires_at);

        CREATE TABLE IF NOT EXISTS artifact_groups (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            label TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_artifact_groups_created
            ON artifact_groups(category, created_at DESC);

        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL REFERENCES artifact_groups(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            content_type TEXT NOT NULL,
            encoding TEXT,
            payload BLOB NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (group_id, name)
        );

        CREATE TABLE IF NOT EXISTS application_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            level TEXT NOT NULL,
            logger TEXT NOT NULL,
            message TEXT NOT NULL,
            session_id TEXT,
            agent_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_application_logs_created
            ON application_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_application_logs_level_created
            ON application_logs(level, created_at DESC);
        """
    )
    row = connection.execute("SELECT version FROM schema_info LIMIT 1").fetchone()
    if row is None:
        connection.execute("INSERT INTO schema_info(version) VALUES (?)", (_SCHEMA_VERSION,))
    elif row["version"] != _SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported database schema {row['version']}; expected {_SCHEMA_VERSION}"
        )
    connection.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def set_document(
    namespace: str,
    key: str,
    value: Any,
    *,
    db_path: Optional[Path] = None,
) -> None:
    now = _utc_now()
    with connection_scope(db_path) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                namespace, key, value_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(namespace, key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (namespace, key, _json(value), now, now),
        )


def get_document(
    namespace: str,
    key: str,
    default: Any = None,
    *,
    db_path: Optional[Path] = None,
) -> Any:
    with connection_scope(db_path) as connection:
        row = connection.execute(
            "SELECT value_json FROM documents WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()
    return default if row is None else json.loads(row["value_json"])


def delete_document(
    namespace: str,
    key: str,
    *,
    db_path: Optional[Path] = None,
) -> bool:
    with connection_scope(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM documents WHERE namespace = ? AND key = ?",
            (namespace, key),
        )
    return cursor.rowcount > 0


@dataclass(frozen=True)
class CacheEntry:
    payload: bytes
    format: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    expires_at: Optional[str]


def put_cache(
    namespace: str,
    key: str,
    payload: bytes,
    *,
    format: str = "binary",
    metadata: Optional[Mapping[str, Any]] = None,
    expires_at: Optional[datetime] = None,
    db_path: Optional[Path] = None,
) -> None:
    now = _utc_now()
    expiry = expires_at.astimezone(timezone.utc).isoformat() if expires_at else None
    with connection_scope(db_path) as connection:
        connection.execute(
            """
            INSERT INTO cache_entries (
                namespace, key, payload, format, metadata_json,
                created_at, updated_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(namespace, key) DO UPDATE SET
                payload = excluded.payload,
                format = excluded.format,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at,
                expires_at = excluded.expires_at
            """,
            (
                namespace,
                key,
                sqlite3.Binary(payload),
                format,
                _json(dict(metadata or {})),
                now,
                now,
                expiry,
            ),
        )


def get_cache(
    namespace: str,
    key: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[CacheEntry]:
    with connection_scope(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM cache_entries WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()
        if row is not None and row["expires_at"] and row["expires_at"] <= _utc_now():
            connection.execute(
                "DELETE FROM cache_entries WHERE namespace = ? AND key = ?",
                (namespace, key),
            )
            row = None
    if row is None:
        return None
    return CacheEntry(
        payload=bytes(row["payload"]),
        format=row["format"],
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )


def delete_cache(
    namespace: str,
    key: Optional[str] = None,
    *,
    db_path: Optional[Path] = None,
) -> int:
    with connection_scope(db_path) as connection:
        if key is None:
            cursor = connection.execute(
                "DELETE FROM cache_entries WHERE namespace = ?", (namespace,)
            )
        else:
            cursor = connection.execute(
                "DELETE FROM cache_entries WHERE namespace = ? AND key = ?",
                (namespace, key),
            )
    return cursor.rowcount


@dataclass(frozen=True)
class StoredArtifact:
    group_id: str
    name: str
    content_type: str
    encoding: Optional[str]
    payload: bytes
    metadata: dict[str, Any]

    @property
    def text(self) -> str:
        return self.payload.decode(self.encoding or "utf-8")


def save_artifacts(
    category: str,
    label: str,
    artifacts: Mapping[str, Any],
    *,
    metadata: Optional[Mapping[str, Any]] = None,
    content_types: Optional[Mapping[str, str]] = None,
    db_path: Optional[Path] = None,
    group_id: Optional[str] = None,
) -> tuple[str, dict[str, str]]:
    """Persist a related set of text, JSON, or binary artifacts atomically."""
    group_id = group_id or uuid.uuid4().hex
    now = _utc_now()
    references: dict[str, str] = {}
    with connection_scope(db_path) as connection:
        connection.execute(
            """
            INSERT INTO artifact_groups(id, category, label, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (group_id, category, label, _json(dict(metadata or {})), now),
        )
        for name, value in artifacts.items():
            content_type = (content_types or {}).get(name)
            encoding: Optional[str]
            if isinstance(value, bytes):
                payload = value
                content_type = content_type or "application/octet-stream"
                encoding = None
            elif isinstance(value, str):
                payload = value.encode("utf-8")
                content_type = content_type or "text/plain"
                encoding = "utf-8"
            else:
                payload = json.dumps(value, indent=2, default=str).encode("utf-8")
                content_type = content_type or "application/json"
                encoding = "utf-8"
            connection.execute(
                """
                INSERT INTO artifacts(
                    id, group_id, name, content_type, encoding,
                    payload, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    group_id,
                    name,
                    content_type,
                    encoding,
                    sqlite3.Binary(payload),
                    "{}",
                    now,
                ),
            )
            references[name] = artifact_uri(group_id, name)
    return group_id, references


def artifact_uri(group_id: str, name: str) -> str:
    return f"sqlite://artifacts/{group_id}/{name}"


def get_artifact(
    group_id: str,
    name: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[StoredArtifact]:
    with connection_scope(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM artifacts WHERE group_id = ? AND name = ?",
            (group_id, name),
        ).fetchone()
    if row is None:
        return None
    return StoredArtifact(
        group_id=row["group_id"],
        name=row["name"],
        content_type=row["content_type"],
        encoding=row["encoding"],
        payload=bytes(row["payload"]),
        metadata=json.loads(row["metadata_json"]),
    )


def list_artifact_groups(
    *,
    category: Optional[str] = None,
    limit: int = 25,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    query = (
        "SELECT g.id, g.category, g.label, g.metadata_json, g.created_at, "
        "COUNT(a.id) AS artifact_count "
        "FROM artifact_groups g LEFT JOIN artifacts a ON a.group_id = g.id"
    )
    values: list[Any] = []
    if category:
        query += " WHERE g.category = ?"
        values.append(category)
    query += " GROUP BY g.id ORDER BY g.created_at DESC LIMIT ?"
    values.append(max(1, int(limit)))
    with connection_scope(db_path) as connection:
        rows = connection.execute(query, values).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        result.append(item)
    return result


def export_artifact_group(
    group_id: str,
    output_dir: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with connection_scope(db_path) as connection:
        rows = connection.execute(
            "SELECT name, payload FROM artifacts WHERE group_id = ? ORDER BY name",
            (group_id,),
        ).fetchall()
    if not rows:
        raise KeyError(f"Artifact group not found: {group_id}")
    written = []
    for row in rows:
        path = output_dir / row["name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(row["payload"]))
        written.append(path)
    return written


def database_summary(*, db_path: Optional[Path] = None) -> dict[str, Any]:
    with connection_scope(db_path) as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "runs",
                "documents",
                "cache_entries",
                "artifact_groups",
                "artifacts",
                "application_logs",
            )
        }
    return {"path": str(Path(db_path) if db_path else database_path()), **counts}


def list_logs(
    *,
    level: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM application_logs"
    values: list[Any] = []
    if level:
        query += " WHERE level = ?"
        values.append(level.upper())
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    values.append(max(1, int(limit)))
    with connection_scope(db_path) as connection:
        rows = connection.execute(query, values).fetchall()
    return [dict(row) for row in rows]


def migrate_legacy_storage(
    repo_root: Path,
    *,
    db_path: Optional[Path] = None,
) -> dict[str, int]:
    """Import known repository-local state without deleting the source files."""
    root = Path(repo_root).resolve()
    imported = {"runs": 0, "documents": 0, "caches": 0, "artifact_groups": 0}

    legacy_runs = root / ".trader_workbench" / "runs.sqlite3"
    if legacy_runs.exists():
        source = sqlite3.connect(legacy_runs)
        source.row_factory = sqlite3.Row
        try:
            rows = source.execute("SELECT * FROM runs").fetchall()
        finally:
            source.close()
        with connection_scope(db_path) as destination:
            for row in rows:
                cursor = destination.execute(
                    """
                    INSERT OR IGNORE INTO runs(
                        id, strategy_id, status, created_at, duration_ms,
                        params_json, report, data_json, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuple(row),
                )
                imported["runs"] += cursor.rowcount

    state_dir = root / "qtr_results" / "state"
    document_files = {
        "ledger.json": ("qtr_results", "ledger"),
        "memory.json": ("qtr_results", "memory"),
        "portfolio.json": ("qtr_results", "portfolio"),
        "sector_cache.json": ("qtr_results", "sector_cache"),
        "universe.json": ("qtr_results", "liquid_universe"),
        "nse_seen.json": ("nse_events_seen", "nse_seen"),
    }
    for filename, (namespace, key) in document_files.items():
        path = state_dir / filename
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if get_document(namespace, key, db_path=db_path) is None:
            set_document(namespace, key, value, db_path=db_path)
            imported["documents"] += 1

    legacy_watchlist = root / "swing_watchlist.txt"
    if (
        legacy_watchlist.exists()
        and get_document("watchlists", "swing_current", db_path=db_path) is None
    ):
        symbols = []
        for line in legacy_watchlist.read_text(encoding="utf-8").splitlines():
            symbol = line.split("#", 1)[0].strip().upper()
            if symbol:
                symbols.append({"symbol": symbol})
        if symbols:
            set_document(
                "watchlists",
                "swing_current",
                {
                    "updated_at": _utc_now(),
                    "index": "legacy",
                    "picks": symbols,
                },
                db_path=db_path,
            )
            imported["documents"] += 1

    cache_mappings = (
        (
            root / "backtesting" / "swing_trading" / "data_cache",
            "prices_*.pkl",
            "backtest_prices",
            r"^prices_(.+)\.pkl$",
        ),
        (
            root / "backtesting" / "qtr_results" / "data_cache",
            "prices_*.pkl",
            "backtest_prices",
            r"^prices_(.+)\.pkl$",
        ),
        (
            root / "backtesting" / "qtr_results" / "fundamentals_cache",
            "fundamentals_*.pkl",
            "qtr_backtest_fundamentals",
            r"^fundamentals_(.+)\.pkl$",
        ),
        (
            root / "backtesting" / "qtr_results" / "fundamentals_cache",
            "result_dates_*.pkl",
            "qtr_backtest_result_dates",
            r"^result_dates_(.+)\.pkl$",
        ),
        (
            root / "backtesting" / "qtr_results" / "fundamentals_cache",
            "sectors_cache.pkl",
            "qtr_backtest_sectors",
            r"^(sectors_cache\.pkl)$",
        ),
    )
    for directory, pattern, namespace, key_pattern in cache_mappings:
        if not directory.exists():
            continue
        for path in directory.glob(pattern):
            match = re.match(key_pattern, path.name)
            if not match:
                continue
            key = match.group(1)
            if get_cache(namespace, key, db_path=db_path) is None:
                put_cache(
                    namespace,
                    key,
                    path.read_bytes(),
                    format="pickle",
                    metadata={"legacy_path": str(path)},
                    db_path=db_path,
                )
                imported["caches"] += 1

    result_roots = (
        ("swing_backtest", root / "backtesting" / "swing_trading" / "results"),
        ("qtr_results_backtest", root / "backtesting" / "qtr_results" / "results"),
    )
    for category, result_root in result_roots:
        if not result_root.exists():
            continue
        for run_dir in (path for path in result_root.iterdir() if path.is_dir()):
            files = {
                str(path.relative_to(run_dir)): path.read_bytes()
                for path in run_dir.rglob("*")
                if path.is_file()
            }
            if files and _save_legacy_artifacts(
                category,
                run_dir.name,
                files,
                str(run_dir),
                db_path=db_path,
            ):
                imported["artifact_groups"] += 1

    report_patterns = (
        "watchlist_report_*.md",
        "analysis_*.md",
        "swing_today.md",
        "swing_discover_today.md",
        "forensic_*.md",
        "logs/*.log",
    )
    for pattern in report_patterns:
        for path in root.glob(pattern):
            if _save_legacy_artifacts(
                "legacy_report",
                path.stem,
                {path.name: path.read_bytes()},
                str(path),
                db_path=db_path,
            ):
                imported["artifact_groups"] += 1
    return imported


def _save_legacy_artifacts(
    category: str,
    label: str,
    artifacts: Mapping[str, Any],
    legacy_path: str,
    *,
    db_path: Optional[Path] = None,
) -> bool:
    if _legacy_artifact_exists(legacy_path, db_path=db_path):
        return False
    group_id = uuid.uuid5(uuid.NAMESPACE_URL, f"legacy:{legacy_path}").hex
    try:
        save_artifacts(
            category,
            label,
            artifacts,
            metadata={"legacy_path": legacy_path},
            db_path=db_path,
            group_id=group_id,
        )
    except sqlite3.IntegrityError:
        if _legacy_artifact_exists(legacy_path, db_path=db_path):
            return False
        raise
    return True


def _legacy_artifact_exists(
    legacy_path: str,
    *,
    db_path: Optional[Path] = None,
) -> bool:
    with connection_scope(db_path) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM artifact_groups
            WHERE json_extract(metadata_json, '$.legacy_path') = ?
            LIMIT 1
            """,
            (legacy_path,),
        ).fetchone()
    return row is not None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect local portfolio storage")
    parser.add_argument("--db", type=Path, default=None, help="Override database path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("path", help="Print the active database path")
    subparsers.add_parser("summary", help="Print row counts")
    list_parser = subparsers.add_parser("list-artifacts", help="List artifact groups")
    list_parser.add_argument("--category")
    list_parser.add_argument("--limit", type=int, default=25)
    export_parser = subparsers.add_parser("export", help="Export an artifact group")
    export_parser.add_argument("group_id")
    export_parser.add_argument("output_dir", type=Path)
    logs_parser = subparsers.add_parser("logs", help="List recent application logs")
    logs_parser.add_argument("--level")
    logs_parser.add_argument("--limit", type=int, default=100)
    migrate_parser = subparsers.add_parser(
        "migrate", help="Import legacy repository-local persistence"
    )
    migrate_parser.add_argument(
        "--repo-root", type=Path, default=Path.cwd(), help="Repository to scan"
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "path":
        print(Path(args.db) if args.db else database_path())
    elif args.command == "summary":
        print(json.dumps(database_summary(db_path=args.db), indent=2))
    elif args.command == "list-artifacts":
        print(
            json.dumps(
                list_artifact_groups(
                    category=args.category, limit=args.limit, db_path=args.db
                ),
                indent=2,
            )
        )
    elif args.command == "export":
        for path in export_artifact_group(
            args.group_id, args.output_dir, db_path=args.db
        ):
            print(path)
    elif args.command == "logs":
        print(
            json.dumps(
                list_logs(level=args.level, limit=args.limit, db_path=args.db),
                indent=2,
            )
        )
    elif args.command == "migrate":
        print(
            json.dumps(
                migrate_legacy_storage(args.repo_root, db_path=args.db),
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
