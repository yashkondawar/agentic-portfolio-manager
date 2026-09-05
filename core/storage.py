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

        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            run_at TEXT NOT NULL,
            days_of_week TEXT NOT NULL,
            timezone TEXT NOT NULL,
            catch_up_minutes INTEGER NOT NULL DEFAULT 720,
            params_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_fired_key TEXT,
            last_run_at TEXT,
            last_run_id TEXT,
            last_status TEXT,
            last_error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_schedules_strategy
            ON schedules(strategy_id);

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


MARKET_DATA_TABLES: tuple[str, ...] = (
    "market_bars",
    "bhavcopy_days",
    "corporate_actions",
    "corporate_action_symbols",
    "corporate_action_windows",
    "index_membership",
    "quarterly_results",
    "nse_backfill_windows",
    "nse_filing_attempts",
)
"""Tables that hold *public market history* and nothing personal.

This is deliberately an **allow-list**, not a block-list of private tables.
Everything in the database that is not named here is excluded from a shared
copy. Forgetting to add a new market table means a friend gets less data;
forgetting to add a new private table to a block-list would leak it. Only one
of those two mistakes is recoverable.

Explicitly *not* here: ``documents`` (holds the Zerodha access token and your
portfolio), ``runs`` and ``artifacts`` (your reports), ``schedules`` (whose
parameters can contain holdings), ``application_logs``, and ``cache_entries``
(mixed, and rebuilds itself for free).
"""


def export_market_data(
    destination: Path,
    *,
    db_path: Optional[Path] = None,
) -> dict[str, int]:
    """Write a shareable copy containing only public market history.

    Scraping years of NSE bars and filings takes hours and hammers a public
    server, so sharing that work is genuinely worth doing. Sharing the whole
    database file is not: it also carries a live broker token and your
    holdings. This copies only :data:`MARKET_DATA_TABLES`.

    Returns:
        Row count per exported table, so the caller can show what was shared.
    """
    destination = Path(destination).expanduser()
    if destination.exists():
        raise FileExistsError(
            f"{destination} already exists. Delete it or choose another name."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    with connection_scope(db_path) as source:
        present = {
            row["name"]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        source.execute("ATTACH DATABASE ? AS shared", (str(destination),))
        try:
            for table in MARKET_DATA_TABLES:
                if table not in present:
                    continue
                for kind in ("table", "index"):
                    for row in source.execute(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type = ? AND tbl_name = ? AND sql IS NOT NULL",
                        (kind, table),
                    ).fetchall():
                        source.execute(_qualify_for_shared(row["sql"]))
                source.execute(
                    f"INSERT INTO shared.{table} SELECT * FROM main.{table}"
                )
                counts[table] = source.execute(
                    f"SELECT COUNT(*) FROM shared.{table}"
                ).fetchone()[0]
            source.commit()
        finally:
            source.execute("DETACH DATABASE shared")
    return counts


def _qualify_for_shared(sql: str) -> str:
    """Rewrite a CREATE statement to target the attached ``shared`` database.

    SQLite stores the statement exactly as it was written, so the name may or
    may not be preceded by ``IF NOT EXISTS``; a naive prefix would produce
    ``CREATE TABLE shared.IF NOT EXISTS ...``.
    """
    return _qualify_for(sql, "shared")


def _qualify_for_main(sql: str) -> str:
    return _qualify_for(sql, "main")


def _qualify_for(sql: str, schema: str) -> str:
    return re.sub(
        r"^\s*CREATE\s+(UNIQUE\s+)?(TABLE|INDEX)\s+(IF\s+NOT\s+EXISTS\s+)?",
        lambda m: (
            f"CREATE {m.group(1) or ''}{m.group(2)} "
            f"{m.group(3) or ''}{schema}."
        ),
        sql,
        count=1,
        flags=re.IGNORECASE,
    )


def import_market_data(
    source_file: Path,
    *,
    db_path: Optional[Path] = None,
) -> dict[str, int]:
    """Merge a shared market-history file into this machine's database.

    Rows that already exist are left alone, so this is safe to re-run and safe
    to apply on top of data you scraped yourself. Only
    :data:`MARKET_DATA_TABLES` are read, so a file that turns out to contain
    more than market history still cannot write anything else here.

    Returns:
        Rows actually added per table.
    """
    source_file = Path(source_file).expanduser()
    if not source_file.exists():
        raise FileNotFoundError(f"No such file: {source_file}")

    added: dict[str, int] = {}
    with connection_scope(db_path) as target:
        target.execute("ATTACH DATABASE ? AS incoming", (str(source_file),))
        try:
            incoming = {
                row["name"]
                for row in target.execute(
                    "SELECT name FROM incoming.sqlite_master WHERE type = 'table'"
                )
            }
            existing = {
                row["name"]
                for row in target.execute(
                    "SELECT name FROM main.sqlite_master WHERE type = 'table'"
                )
            }
            for table in MARKET_DATA_TABLES:
                if table not in incoming:
                    continue
                if table not in existing:
                    # A fresh machine has never run a backfill, so the table
                    # does not exist yet. Create it from the sender's schema.
                    for kind in ("table", "index"):
                        for row in target.execute(
                            "SELECT sql FROM incoming.sqlite_master "
                            "WHERE type = ? AND tbl_name = ? AND sql IS NOT NULL",
                            (kind, table),
                        ).fetchall():
                            target.execute(_qualify_for_main(row["sql"]))
                before = target.execute(
                    f"SELECT COUNT(*) FROM main.{table}"
                ).fetchone()[0]
                target.execute(
                    f"INSERT OR IGNORE INTO main.{table} "
                    f"SELECT * FROM incoming.{table}"
                )
                after = target.execute(
                    f"SELECT COUNT(*) FROM main.{table}"
                ).fetchone()[0]
                added[table] = after - before
            target.commit()
        finally:
            target.execute("DETACH DATABASE incoming")
    return added


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
    replace_state: bool = False,
    db_path: Optional[Path] = None,
) -> dict[str, int]:
    """Import known repository-local state without deleting the source files.

    ``replace_state`` makes mutable documents and caches in the source
    authoritative. Immutable runs and artifacts remain append-only and
    idempotent.
    """
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
        current = get_document(namespace, key, db_path=db_path)
        if current is None or (replace_state and current != value):
            set_document(namespace, key, value, db_path=db_path)
            imported["documents"] += 1

    legacy_watchlist = root / "swing_watchlist.txt"
    if legacy_watchlist.exists():
        symbols = []
        for line in legacy_watchlist.read_text(encoding="utf-8").splitlines():
            symbol = line.split("#", 1)[0].strip().upper()
            if symbol:
                symbols.append({"symbol": symbol})
        current_watchlist = get_document(
            "watchlists", "swing_current", db_path=db_path
        )
        current_symbols = (
            current_watchlist.get("picks")
            if isinstance(current_watchlist, dict)
            else None
        )
        if symbols and (
            current_watchlist is None
            or (replace_state and current_symbols != symbols)
        ):
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
            payload = path.read_bytes()
            current = get_cache(namespace, key, db_path=db_path)
            if current is None or (replace_state and current.payload != payload):
                put_cache(
                    namespace,
                    key,
                    payload,
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
    if _legacy_artifact_exists(
        legacy_path,
        category=category,
        label=label,
        artifacts=artifacts,
        db_path=db_path,
    ):
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
        if _legacy_artifact_exists(
            legacy_path,
            category=category,
            label=label,
            artifacts=artifacts,
            db_path=db_path,
        ):
            return False
        raise
    return True


def _legacy_artifact_exists(
    legacy_path: str,
    *,
    category: Optional[str] = None,
    label: Optional[str] = None,
    artifacts: Optional[Mapping[str, Any]] = None,
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
        if row is not None:
            return True
        if category is None or label is None or artifacts is None:
            return False
        rows = connection.execute(
            """
            SELECT g.id AS group_id, a.name, a.payload
            FROM artifact_groups AS g
            JOIN artifacts AS a ON a.group_id = g.id
            WHERE g.category = ? AND g.label = ?
            ORDER BY g.id, a.name
            """,
            (category, label),
        ).fetchall()

    expected = {
        name: _artifact_payload(value)
        for name, value in artifacts.items()
    }
    stored: dict[str, dict[str, bytes]] = {}
    for candidate in rows:
        stored.setdefault(candidate["group_id"], {})[candidate["name"]] = bytes(
            candidate["payload"]
        )
    return any(candidate == expected for candidate in stored.values())


def _artifact_payload(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, indent=2, default=str).encode("utf-8")


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
    migrate_parser.add_argument(
        "--replace-state",
        action="store_true",
        help="Replace changed mutable documents and caches with the source state",
    )
    share_parser = subparsers.add_parser(
        "share",
        help="Write a shareable copy with only market history (no personal data)",
    )
    share_parser.add_argument("output", type=Path, help="File to create")
    import_parser = subparsers.add_parser(
        "import-shared",
        help="Merge a shared market-history file from someone else",
    )
    import_parser.add_argument("source", type=Path, help="Shared file to read")
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
                migrate_legacy_storage(
                    args.repo_root,
                    replace_state=args.replace_state,
                    db_path=args.db,
                ),
                indent=2,
            )
        )
    elif args.command == "share":
        counts = export_market_data(args.output, db_path=args.db)
        total = sum(counts.values())
        for table, count in sorted(counts.items()):
            print(f"  {table:28s} {count:>12,}")
        print(f"\nWrote {total:,} rows of market history to {args.output}")
        print(
            "This file contains no API keys, broker tokens, holdings or "
            "reports - it is safe to send to someone else."
        )
    elif args.command == "import-shared":
        added = import_market_data(args.source, db_path=args.db)
        total = sum(added.values())
        for table, count in sorted(added.items()):
            print(f"  {table:28s} +{count:>11,}")
        print(f"\nAdded {total:,} new rows. Existing rows were left unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
