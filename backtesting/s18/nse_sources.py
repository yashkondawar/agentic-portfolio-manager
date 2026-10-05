"""Strict, read-only NSE collection with immutable, content-addressed evidence.

Only ``s18.nse.*`` documents and raw artifacts are written; existing market bars
and membership tables are never modified. HTTP failures are not trading-day
classifications. A current constituents file is an observation, not a historical
membership reconstruction.
Pre-close membership captures are informational and are fetched again after
18:00 IST; they cannot stand in for a missed historical close. Corporate-action
history is collected in complete, separately evidenced calendar-month windows.

Calendar completeness means every requested date has a classification against
the publications observed today. It does not promise that NSE will not announce
an emergency closure or another special session tomorrow. Closed historical
dates are checked against the validated final bhavcopy archive. Known special
sessions (including the starred Diwali holiday) must have explicit evidence.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import re
import sqlite3
import time
import uuid
import zipfile
from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from core import storage
from scraper import bhavcopy as existing_bhavcopy
from scraper.corporate_actions import classify, is_demerger, parse_bonus, parse_split

IST = ZoneInfo("Asia/Kolkata")
ARCHIVES = "https://nsearchives.nseindia.com"
CONSTITUENTS_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
SECURITIES_URL = f"{ARCHIVES}/content/equities/EQUITY_L.csv"
ETF_URL = f"{ARCHIVES}/content/equities/eq_etfseclist.csv"
SYMBOL_CHANGES_URL = f"{ARCHIVES}/content/equities/symbolchange.csv"
HOLIDAYS_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
HOLIDAY_PAGE_URL = "https://www.nseindia.com/resources/exchange-communication-holidays"
TIMINGS_URL = "https://www.nseindia.com/market-data/market-timings"
ACTIONS_URL = "https://www.nseindia.com/api/corporates-corporateActions"
NAMESPACE = "s18.nse.sources.v1"
MAX_PAYLOAD = 16 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MIN_REQUEST_INTERVAL = 0.5
MAX_ATTEMPTS = 2


class SourceUnavailable(RuntimeError):
    """An official source could not establish the requested facts."""


class SourceNotFound(SourceUnavailable):
    """HTTP 404 only. This never, by itself, means that a market was closed."""


@dataclass(frozen=True)
class SourceResult:
    records: list[dict]
    source: str
    fetched_at: str
    metadata: dict


def _text(payload: bytes) -> str:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("NSE payload is not UTF-8 text") from exc


def _csv(payload: bytes, required: set[str]) -> list[dict]:
    text = _text(payload)
    if text.lstrip().startswith(("<", "{", "[")):
        raise ValueError("Expected CSV, received HTML/JSON")
    reader = csv.DictReader(io.StringIO(text), skipinitialspace=True)
    fields = [f.strip() for f in reader.fieldnames or []]
    if not required.issubset(fields) or len(fields) != len(set(fields)):
        raise ValueError(f"Missing/duplicate CSV columns; required {sorted(required)}")
    reader.fieldnames = fields
    rows = []
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("CSV row length does not match its header")
        rows.append({k: v.strip() for k, v in row.items()})
    if not rows:
        raise ValueError("NSE CSV contains no records")
    return rows


def _date(value: str, *formats: str) -> date:
    for fmt in formats or ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            pass
    raise ValueError(f"Invalid NSE date: {value!r}")


def _price(value: str) -> float:
    try:
        number = float(value.replace(",", ""))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid NSE price: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"Nonpositive/nonfinite NSE price: {value!r}")
    return number


def _identity(symbol: str, isin: str) -> dict:
    symbol, isin = symbol.strip().upper(), isin.strip().upper()
    if not symbol or not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
        raise ValueError(f"Missing/invalid security identity: {symbol!r}, {isin!r}")
    return {"symbol": symbol, "isin": isin}


def _unique(records: list[dict]) -> list[dict]:
    for key in ("symbol", "isin"):
        values = [r[key] for r in records]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate security {key} in NSE source")
    return records


def _json(payload: bytes):
    try:
        return json.loads(_text(payload))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid NSE JSON payload") from exc


def _html_text(payload: bytes) -> str:
    text = _text(payload)
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def _parse_bhavcopy(
    payload: bytes, day: date, *, legacy: bool, metadata: dict | None = None
) -> list[dict]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            files = [f for f in archive.infolist() if not f.is_dir()]
            if (
                len(files) != 1
                or not files[0].filename.lower().endswith(".csv")
                or files[0].file_size > MAX_EXPANDED
            ):
                raise ValueError("Expected one size-bounded bhavcopy CSV")
            payload = archive.read(files[0])
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError("Invalid bhavcopy ZIP payload") from exc
    if legacy:
        columns = ("OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE")
        required = {"TIMESTAMP", "SYMBOL", "SERIES", "ISIN", *columns}
    else:
        columns = ("OpnPric", "HghPric", "LwPric", "ClsPric", "PrvsClsgPric")
        required = {
            "TradDt",
            "BizDt",
            "Sgmt",
            "Src",
            "FinInstrmTp",
            "ISIN",
            "TckrSymb",
            "SctySrs",
            *columns,
        }
    records = []
    rows = _csv(payload, required)
    for row in rows:
        if legacy:
            if _date(row["TIMESTAMP"], "%d-%b-%Y") != day:
                raise ValueError(f"Legacy bhavcopy TIMESTAMP differs from {day}")
            symbol, series = row["SYMBOL"], row["SERIES"]
        else:
            if any(_date(row[k], "%Y-%m-%d") != day for k in ("TradDt", "BizDt")):
                raise ValueError(f"Bhavcopy dates differ from requested {day}")
            if row["Sgmt"] != "CM" or row["Src"] != "NSE":
                raise ValueError("Bhavcopy is not the NSE cash market")
            symbol, series = row["TckrSymb"], row["SctySrs"]
            if row["FinInstrmTp"] != "STK":
                continue
        if series not in {"EQ", "BE", "BZ"}:
            continue
        record = {
            **_identity(symbol, row["ISIN"]),
            "date": day.isoformat(),
            "series": series,
            **dict(
                zip(
                    ("open", "high", "low", "close", "prev_close"),
                    (_price(row[c]) for c in columns),
                )
            ),
        }
        if not (
            record["low"]
            <= min(record["open"], record["close"])
            <= max(record["open"], record["close"])
            <= record["high"]
        ):
            raise ValueError(f"Inconsistent OHLC for {symbol} on {day}")
        records.append(record)
    if not records:
        raise ValueError(f"Bhavcopy for {day} has no EQ/BE/BZ stock records")
    if metadata is not None:
        metadata.update(
            {
                "payload_record_count": len(rows),
                "retained_record_count": len(records),
                "excluded_record_count": len(rows) - len(records),
                "retained_series": ["EQ", "BE", "BZ"],
            }
        )
    return _unique(records)


class NseSources:
    """Reusable official-source client; inject a requests-compatible session in tests.

    ``now`` must be timezone-aware. It is a reproducible clock override, not
    permission to label a current download as a historical observation.
    """

    def __init__(
        self, db_path: Path | None = None, session=None, now: datetime | None = None
    ):
        if now is not None and now.tzinfo is None:
            raise ValueError("NseSources.now must be timezone-aware")
        self.db_path, self.session, self.now = db_path, session, now
        self._last_request = 0.0

    def _now(self) -> datetime:
        return (self.now or datetime.now(IST)).astimezone(IST)

    def _observed_today(self) -> date:
        today = self._now().date()
        if self.session is None and today != datetime.now(IST).date():
            raise SourceUnavailable(
                "A live NSE observation cannot be backdated or future-dated by a clock "
                "override. Omit now for real collection; inject a mock session for tests."
            )
        return today

    def _get(self, key):
        return storage.get_document(NAMESPACE, key, db_path=self.db_path)

    def _put(self, key, value):
        storage.set_document(NAMESPACE, key, value, db_path=self.db_path)

    def _audit(self, **fields):
        self._put(
            "audit:" + uuid.uuid4().hex, {"at": self._now().isoformat(), **fields}
        )

    def _capture(self, payload: bytes, url: str, fetched_at: str) -> dict:
        digest = hashlib.sha256(payload).hexdigest()
        group = "s18-nse-sha256-" + digest
        if storage.get_artifact(group, "payload", db_path=self.db_path) is None:
            try:
                storage.save_artifacts(
                    "s18.nse.raw",
                    url,
                    {"payload": payload},
                    metadata={"url": url, "sha256": digest, "fetched_at": fetched_at},
                    group_id=group,
                    db_path=self.db_path,
                )
            except sqlite3.IntegrityError:
                if storage.get_artifact(group, "payload", db_path=self.db_path) is None:
                    raise
        return {
            "source": storage.artifact_uri(group, "payload"),
            "sha256": digest,
            "url": url,
            "fetched_at": fetched_at,
        }

    def _payload(self, snapshot: dict) -> bytes:
        artifact = storage.get_artifact(
            "s18-nse-sha256-" + snapshot["sha256"], "payload", db_path=self.db_path
        )
        if (
            artifact is None
            or hashlib.sha256(artifact.payload).hexdigest() != snapshot["sha256"]
        ):
            raise SourceUnavailable("Stored NSE raw evidence is absent or corrupted")
        return artifact.payload

    def _download(self, url: str, *, refresh: bool = False) -> tuple[bytes, dict]:
        key = f"download:{self._now().date()}:{url}"
        if not refresh and (saved := self._get(key)):
            return self._payload(saved), saved
        for attempt in range(1, MAX_ATTEMPTS + 1):
            wait = MIN_REQUEST_INTERVAL - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            response, evidence, status = None, None, None
            try:
                session = (
                    self.session
                    if self.session is not None
                    else existing_bhavcopy.get_session()
                )
                response = session.get(url, timeout=(10, 30), stream=True)
                status = response.status_code
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_PAYLOAD:
                    raise SourceUnavailable(
                        f"NSE response exceeds {MAX_PAYLOAD} bytes: {url}"
                    )
                chunks, size = [], 0
                for chunk in response.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > MAX_PAYLOAD:
                        raise SourceUnavailable(
                            f"NSE response exceeds {MAX_PAYLOAD} bytes: {url}"
                        )
                    chunks.append(chunk)
                payload = b"".join(chunks)
                evidence = self._capture(payload, url, self._now().isoformat())
                if status == 404:
                    raise SourceNotFound(f"NSE HTTP 404 (not holiday evidence): {url}")
                if status != 200:
                    raise SourceUnavailable(f"NSE HTTP {status}: {url}")
                if not payload:
                    raise SourceUnavailable(f"Empty NSE HTTP response: {url}")
                self._audit(
                    url=url,
                    attempt=attempt,
                    status=status,
                    outcome="downloaded",
                    evidence=evidence,
                )
                self._put(key, evidence)
                return payload, evidence
            except (requests.RequestException, SourceUnavailable, ValueError) as exc:
                self._audit(
                    url=url,
                    attempt=attempt,
                    status=status,
                    outcome="failed",
                    error=str(exc),
                    evidence=evidence,
                )
                if isinstance(exc, SourceNotFound):
                    raise
                if attempt == MAX_ATTEMPTS or (
                    status is not None and 400 <= status < 500 and status != 429
                ):
                    raise SourceUnavailable(
                        f"Official NSE source unavailable: {url}: {exc}"
                    ) from exc
            finally:
                if response is not None:
                    response.close()
        raise AssertionError("Unreachable")

    def _result(
        self, key, url, parser, *, refresh=False, metadata=None
    ) -> SourceResult:
        if not refresh and (saved := self._get("result:" + key)):
            snapshot = saved["metadata"]["snapshot"]
            payload = self._payload(snapshot)
            if saved["metadata"].get("parser_version") == (metadata or {}).get(
                "parser_version"
            ):
                return SourceResult(**saved)
        else:
            payload, snapshot = self._download(url, refresh=refresh)
        try:
            records = parser(payload)
        except (ValueError, KeyError, TypeError, SourceUnavailable) as exc:
            self._audit(url=url, outcome="invalid", error=str(exc), evidence=snapshot)
            raise ValueError(f"Invalid official NSE source {url}: {exc}") from exc
        result = SourceResult(
            records,
            snapshot["source"],
            snapshot["fetched_at"],
            {"snapshot": snapshot, "sha256": snapshot["sha256"], **(metadata or {})},
        )
        self._put(
            f"observation:{key}:{snapshot['fetched_at']}:{snapshot['sha256']}:"
            f"{(metadata or {}).get('parser_version', '1')}",
            asdict(result),
        )
        self._put("result:" + key, asdict(result))
        return result

    def _daily(self, name, url, parser, **metadata):
        today = self._observed_today()
        return self._result(
            f"{name}:{today}",
            url,
            parser,
            metadata={"observed_on": str(today), **metadata},
        )

    def _combined(
        self, name: str, results: list[SourceResult], records: list[dict], metadata=None
    ):
        snapshots = list(
            dict.fromkeys(
                [r.source for r in results]
                + [
                    r["source"]
                    for r in records
                    if r.get("source", "").startswith("sqlite://")
                ]
            )
        )
        payload = json.dumps(
            {
                "kind": name,
                "records": records,
                "sources": snapshots,
                "metadata": metadata or {},
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        captured = self._capture(payload, f"derived:{name}", self._now().isoformat())
        return SourceResult(
            records,
            captured["source"],
            captured["fetched_at"],
            {
                "source_snapshots": snapshots,
                "sha256": captured["sha256"],
                **(metadata or {}),
            },
        )

    def bhavcopy(self, day: date, *, refresh: bool = False) -> SourceResult:
        if day > self._now().date():
            raise SourceUnavailable("Cannot collect a future bhavcopy")
        legacy = day < existing_bhavcopy.UDIFF_FROM
        url = (
            existing_bhavcopy.legacy_url(day)
            if legacy
            else existing_bhavcopy.udiff_url(day)
        )
        metadata = {
            "trade_date": str(day),
            "format": "legacy" if legacy else "udiff",
            "parser_version": "equity-series-v2",
        }
        return self._result(
            f"bhavcopy:{day}",
            url,
            lambda p: _parse_bhavcopy(p, day, legacy=legacy, metadata=metadata),
            refresh=refresh,
            metadata=metadata,
        )

    def index_close(self, day: date, *, refresh: bool = False) -> SourceResult:
        if day > self._now().date():
            raise SourceUnavailable("Cannot collect a future index close")

        def parse(payload):
            rows = _csv(payload, {"Index Name", "Index Date", "Closing Index Value"})
            if any(_date(r["Index Date"], "%d-%m-%Y") != day for r in rows):
                raise ValueError(f"Index dates differ from requested {day}")
            chosen = [r for r in rows if r["Index Name"].casefold() == "nifty 500"]
            if len(chosen) != 1:
                raise ValueError("Expected exactly one Nifty 500 price-index row")
            return [
                {"date": str(day), "close": _price(chosen[0]["Closing Index Value"])}
            ]

        return self._result(
            f"index:{day}",
            f"{ARCHIVES}/content/indices/ind_close_all_{day:%d%m%Y}.csv",
            parse,
            refresh=refresh,
            metadata={"index": "Nifty 500", "return_type": "price"},
        )

    def constituents(self, day: date) -> SourceResult:
        """Return a dated observation, refreshing intraday captures after 18:00 IST.

        A timestamp passing the cutoff is necessary, not sufficient, for a close:
        the consumer must independently establish that this exact date traded.
        Holiday observations cannot fill a previous session's membership gap.
        Official series are exposed per record and in ``metadata.series_by_isin``.
        No membership exclusions are inferred from missing security-master entries.
        """
        key = f"constituents:{day}"
        now = self._now()

        def annotated(result):
            observed = datetime.fromisoformat(result.fetched_at)
            if observed.tzinfo is None or observed.astimezone(IST).date() != day:
                raise SourceUnavailable(
                    f"Membership observation timestamp does not establish {day}"
                )
            if observed > self._now():
                raise SourceUnavailable(
                    f"Membership observation for {day} was not yet available at the requested clock"
                )
            rows = _csv(
                self._payload(result.metadata["snapshot"]),
                {"Symbol", "ISIN Code", "Series"},
            )
            series_by_isin = {
                row["ISIN Code"].upper(): row["Series"].upper() for row in rows
            }
            if len(series_by_isin) != len(rows) or set(series_by_isin) != {
                r["isin"] for r in result.records
            }:
                raise SourceUnavailable(
                    "Stored membership does not match its raw series evidence"
                )
            return SourceResult(
                [{**r, "series": series_by_isin[r["isin"]]} for r in result.records],
                result.source,
                result.fetched_at,
                {
                    **result.metadata,
                    "series_by_isin": series_by_isin,
                    "observed_after_close_cutoff": observed.astimezone(IST).hour >= 18,
                    "close_cutoff_ist": "18:00",
                    "use_constraint": (
                        "Only the exact observed date with a confirmed exchange session "
                        "can use this as closing membership. Pre-close and holiday "
                        "observations are informational, never backdated."
                    ),
                },
            )

        if day > now.date():
            raise SourceUnavailable("Cannot use a future membership observation")
        if saved := self._get("result:" + key):
            result = annotated(SourceResult(**saved))
            if result.metadata["observed_after_close_cutoff"] or (
                day == now.date() and now.hour < 18
            ):
                return result
            if day < now.date():
                raise SourceUnavailable(
                    f"Only a pre-close membership observation exists for {day} "
                    f"(fetched {result.fetched_at}); a >=18:00 IST same-date snapshot "
                    "is required. Today's list cannot repair the missed close."
                )
        if day != now.date():
            raise SourceUnavailable(
                f"No observed Nifty 500 constituents snapshot for {day}; collect today's "
                "snapshot for forward decisions or import independently dated official "
                "membership evidence. A current list cannot be backdated."
            )
        self._observed_today()

        def parse(payload):
            if self._observed_today() != day:
                raise SourceUnavailable(
                    "IST date changed during membership collection; retry for today"
                )
            rows = _csv(payload, {"Symbol", "ISIN Code", "Series"})
            if any(r["Series"] not in {"EQ", "BE", "BZ", "RR"} for r in rows):
                raise ValueError("Unexpected Nifty 500 constituent series")
            records = _unique(
                [
                    {**_identity(r["Symbol"], r["ISIN Code"]), "series": r["Series"]}
                    for r in rows
                ]
            )
            if not 450 <= len(records) <= 550:
                raise ValueError(
                    f"Implausible Nifty 500 constituent count: {len(records)}"
                )
            return records

        result = self._result(
            key,
            CONSTITUENTS_URL,
            parse,
            refresh=now.hour >= 18,
            metadata={
                "observed_on": str(day),
                "membership_policy": "dated observation; never backdated",
            },
        )
        return annotated(result)

    def etfs(self) -> SourceResult:
        """Official ETF identities and explicit listing dates; unknown stays None."""

        def parse(payload):
            rows = _csv(payload, {"Symbol", "ISINNumber", "DateofListing"})
            return _unique(
                [
                    {
                        **_identity(r["Symbol"], r["ISINNumber"]),
                        "listed_on": (
                            str(_date(r["DateofListing"], "%d-%b-%y", "%d-%b-%Y"))
                            if r["DateofListing"] not in {"", "-", "NA"}
                            else None
                        ),
                    }
                    for r in rows
                ]
            )

        return self._daily("etfs", ETF_URL, parse)

    def securities(self) -> SourceResult:
        def parse(payload):
            rows = _csv(payload, {"SYMBOL", "ISIN NUMBER", "DATE OF LISTING"})
            return _unique(
                [
                    {
                        **_identity(r["SYMBOL"], r["ISIN NUMBER"]),
                        "listed_on": str(_date(r["DATE OF LISTING"], "%d-%b-%Y")),
                        **({"series": r["SERIES"]} if r.get("SERIES") else {}),
                    }
                    for r in rows
                ]
            )

        equities = self._daily(
            "equities", SECURITIES_URL, parse, parser_version="equity-series-v2"
        )
        etfs = self.etfs()
        records = _unique(equities.records + etfs.records)
        return self._combined(
            "securities",
            [equities, etfs],
            records,
            {"observed_on": str(self._now().date())},
        )

    def symbol_changes(self) -> SourceResult:
        def parse(payload):
            if _text(payload).lstrip().startswith(("<", "{", "[")):
                raise ValueError("Expected headerless symbol-change CSV")
            records, seen = [], set()
            for row in csv.reader(io.StringIO(_text(payload)), skipinitialspace=True):
                if not row:
                    continue
                if len(row) != 4 or not row[1].strip() or not row[2].strip():
                    raise ValueError("Malformed symbol-change row")
                record = {
                    "old_symbol": row[1].strip().upper(),
                    "new_symbol": row[2].strip().upper(),
                    "effective_date": str(_date(row[3], "%d-%b-%Y")),
                }
                key = (record["old_symbol"], record["effective_date"])
                if key in seen:
                    raise ValueError("Duplicate/ambiguous symbol change")
                seen.add(key)
                records.append(record)
            if not records:
                raise ValueError("Empty symbol-change source")
            return records

        return self._daily("symbol_changes", SYMBOL_CHANGES_URL, parse)

    def actions(self, start: date, end: date) -> SourceResult:
        """Collect monthly notices, collapsing exact duplicates without losing evidence.

        Raw payloads remain immutable. Duplicate counts are exposed per window and
        in aggregate; contradictory identities, face values or adjustment factors
        raise rather than choosing one notice.
        """
        if start > end:
            raise ValueError("Corporate-action start is after end")
        results, records, windows = [], [], []
        cursor = start
        while cursor <= end:
            last = min(
                end, cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
            )
            deduplication = {"raw_record_count": 0, "duplicate_count": 0}

            def parse(payload, first=cursor, final=last):
                rows = _json(payload)
                if not isinstance(rows, list):
                    raise ValueError("Corporate-action API did not return a JSON list")
                deduplication["raw_record_count"] = len(rows)
                out, seen, financial_factors = [], {}, {}
                for row in rows:
                    if not isinstance(row, dict):
                        raise ValueError("Malformed corporate-action record")
                    identity = _identity(row["symbol"], row["isin"])
                    ex = _date(row["exDate"])
                    if not first <= ex <= final:
                        raise ValueError(
                            "Corporate-action ex-date outside requested window"
                        )
                    subject = row["subject"].strip()
                    if not subject:
                        raise ValueError("Empty corporate-action subject")
                    original, _, dividend = classify(subject)
                    split, bonus = parse_split(subject), parse_bonus(subject)
                    factor = None
                    non_equity_bonus = bool(
                        re.search(r"bonus", subject, re.I)
                        and re.search(
                            r"debenture|ncrps|ncd|preference|warrant", subject, re.I
                        )
                    )
                    if (split is not None or bonus is not None) and is_demerger(
                        subject
                    ):
                        raise ValueError(
                            f"Combined reorganization needs explicit review: {subject}"
                        )
                    if non_equity_bonus:
                        kind = "other"
                    elif split is not None or bonus is not None:
                        kind = (
                            "split_bonus"
                            if split is not None and bonus is not None
                            else ("split" if split is not None else "bonus")
                        )
                        factor = (split or 1.0) * (bonus or 1.0)
                    elif is_demerger(subject):
                        kind = "demerger"
                    elif re.search(r"\bisin\b", subject, re.I):
                        kind = "isin_change"
                    elif "dividend" in subject.lower():
                        kind = "dividend"
                    else:
                        kind = "other"
                    if (
                        re.search(r"split|spl[t]|sub.?division|bonus", subject, re.I)
                        and factor is None
                        and not non_equity_bonus
                    ):
                        raise ValueError(f"Unresolved split/bonus action: {subject}")
                    review = (
                        non_equity_bonus
                        or kind in {"demerger", "isin_change"}
                        or bool(
                            re.search(
                                r"rights|merger|amalgamat|consolidat|reduc|delist|buy.?back|restructur",
                                subject,
                                re.I,
                            )
                        )
                    )
                    record = {
                        **identity,
                        "ex_date": str(ex),
                        "subject": subject,
                        "kind": kind,
                        "factor": factor,
                        "requires_review": review,
                        "source_classification": original,
                    }
                    if dividend is not None:
                        record["dividend"] = dividend
                    key = (identity["isin"], str(ex), subject)
                    # Book-closure/record-date metadata may differ between duplicate notices.
                    face_value = str(row.get("faceVal") or "").strip().replace(",", "")
                    if face_value in {"", "-"}:
                        face_value = None
                    else:
                        try:
                            face_value = float(face_value)
                        except ValueError:
                            pass
                    if key in seen:
                        if seen[key] != (record, face_value):
                            raise ValueError(
                                f"Conflicting corporate action for {identity['symbol']} "
                                f"({identity['isin']}) on {ex}: {subject}"
                            )
                        deduplication["duplicate_count"] += 1
                        continue
                    if kind in {"split", "bonus", "split_bonus"}:
                        financial_key = (identity["isin"], str(ex), kind)
                        if (
                            financial_key in financial_factors
                            and financial_factors[financial_key] != factor
                        ):
                            raise ValueError(
                                f"Conflicting {kind} factors for {identity['symbol']} "
                                f"({identity['isin']}) on {ex}"
                            )
                        financial_factors[financial_key] = factor
                    seen[key] = (record, face_value)
                    out.append(record)
                return out

            url = f"{ACTIONS_URL}?index=equities&from_date={cursor:%d-%m-%Y}&to_date={last:%d-%m-%Y}"
            result = self._daily(
                f"actions:{cursor}:{last}",
                url,
                parse,
                parser_version="actions-dedup-v2",
                deduplication=deduplication,
            )
            results.append(result)
            records.extend(result.records)
            windows.append(
                {
                    "from_date": str(cursor),
                    "to_date": str(last),
                    "record_count": len(result.records),
                    **result.metadata["deduplication"],
                    "source": result.source,
                }
            )
            cursor = last + timedelta(days=1)
        return self._combined(
            "actions",
            results,
            records,
            {
                "from_date": str(start),
                "to_date": str(end),
                "window_policy": "calendar_months",
                "windows": windows,
                "record_count": len(records),
                "raw_record_count": sum(w["raw_record_count"] for w in windows),
                "duplicate_count": sum(w["duplicate_count"] for w in windows),
                "requires_review": [r for r in records if r["requires_review"]],
            },
        )

    def load_special_sessions(
        self, records: list[dict], *, source_url: str
    ) -> SourceResult:
        """Import reviewed overrides with a verbatim quote from an official HTML page.

        Each row requires ``date``, boolean ``is_session`` and ``evidence``.
        This is a manual-review interface, not an inference from a holiday label.
        PDF circulars must first be supported by an official textual publication.
        """
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "www.nseindia.com",
            "nsearchives.nseindia.com",
            "archives.nseindia.com",
        }:
            raise ValueError(
                "Special-session evidence must be an official NSE HTTPS URL"
            )
        payload, snapshot = self._download(source_url)
        text, normalized, seen = _html_text(payload), [], set()
        for record in records:
            day = _date(record["date"], "%Y-%m-%d")
            quote = " ".join(record["evidence"].split())
            if (
                type(record["is_session"]) is not bool
                or len(quote) < 20
                or quote not in text
                or day in seen
                or not any(
                    token in quote
                    for token in (
                        day.isoformat(),
                        day.strftime("%B %d, %Y"),
                        day.strftime("%d-%b-%Y"),
                    )
                )
            ):
                raise ValueError(
                    "Special-session override lacks unique, dated, quoted official evidence"
                )
            normalized.append(
                {
                    "date": str(day),
                    "is_session": record["is_session"],
                    "source": snapshot["source"],
                    "evidence": quote,
                }
            )
            seen.add(day)
        for record in normalized:
            self._put("special:" + record["date"], record)
            self._put(
                f"special_observation:{record['date']}:{snapshot['sha256']}", record
            )
        return SourceResult(
            normalized,
            snapshot["source"],
            snapshot["fetched_at"],
            {"snapshot": snapshot},
        )

    def calendar(self, start: date, end: date) -> SourceResult:
        if start > end:
            raise ValueError("Calendar start is after end")
        today = self._now().date()
        timing = self._daily(
            "market_timings",
            TIMINGS_URL,
            lambda p: [{"text": _html_text(p)}],
        )
        timing_text = timing.records[0]["text"]
        if not all(token in timing_text for token in ("Equities", "09:15", "15:30")):
            raise SourceUnavailable(
                "Official page does not establish regular equity market timings"
            )
        notes = self._daily(
            "holiday_notes", HOLIDAY_PAGE_URL, lambda p: [{"text": _html_text(p)}]
        )
        results, holidays, published_special = [timing, notes], {}, {}
        note_text = notes.records[0]["text"]
        for match in re.finditer(
            r"([A-Z][a-z]+ \d{1,2}, \d{4}),? shall be a trading holiday"
            r".{0,160}?Muhurat Trading will be conducted on that day",
            note_text,
            re.I,
        ):
            day = _date(match.group(1), "%B %d, %Y")
            published_special[day] = notes.source
        for year in range(start.year, end.year + 1):

            def parse(payload, expected=year):
                data = _json(payload)
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("CM"), list)
                    or not data["CM"]
                ):
                    raise ValueError("NSE calendar lacks a nonempty CM holiday list")
                rows, seen = [], set()
                for row in data["CM"]:
                    day = _date(row["tradingDate"], "%d-%b-%Y")
                    if day.year != expected or day in seen:
                        raise ValueError(
                            f"Unsupported/ambiguous calendar year {expected}"
                        )
                    if not row.get("description"):
                        raise ValueError("Holiday description is missing")
                    seen.add(day)
                    rows.append({"date": str(day), **row})
                if len(rows) < 5:
                    raise ValueError(f"Incomplete holiday publication for {expected}")
                return rows

            url = HOLIDAYS_URL if year == today.year else f"{HOLIDAYS_URL}&year={year}"
            result = self._daily(f"holidays:{year}", url, parse)
            results.append(result)
            holidays.update(
                {
                    date.fromisoformat(r["date"]): (r, result.source)
                    for r in result.records
                }
            )
        records, annotations = [], []
        last_completed = today if self._now().hour >= 18 else today - timedelta(days=1)
        day = start
        while day <= end:
            holiday = holidays.get(day)
            is_session = day.weekday() < 5 and holiday is None
            source = holiday[1] if holiday else timing.source
            special = self._get("special:" + str(day))
            if day in published_special:
                special = {"is_session": True, "source": published_special[day]}
            if special:
                is_session, source = special["is_session"], special["source"]
                annotations.append(
                    {"date": str(day), "kind": "published_override", "source": source}
                )
            known_special = holiday and (
                bool(
                    re.search(
                        r"\*|muhurat|laxmi\s+pujan|special",
                        holiday[0]["description"],
                        re.I,
                    )
                )
                or any(
                    holiday[0].get(k) not in (None, "", "-", "Closed", "closed")
                    for k in ("morning_session", "evening_session")
                )
            )
            # An archive can prove a special session; an ordinary weekday 404 cannot prove a holiday.
            if (day.weekday() >= 5 or holiday) and day <= last_completed:
                negative_key = f"closed_archive_probe:{today}:{day}"
                negative = self._get(negative_key)
                try:
                    if (
                        negative
                        and not special
                        and not known_special
                        and self._get(f"result:bhavcopy:{day}") is None
                    ):
                        observed = None
                    else:
                        observed = self.bhavcopy(day)
                except SourceNotFound:
                    if is_session or (known_special and not special):
                        raise SourceUnavailable(
                            f"Unverified known special session on {day}: archive absent"
                        )
                    self._put(
                        negative_key,
                        {
                            "observed_at": self._now().isoformat(),
                            "basis": source,
                            "status": 404,
                        },
                    )
                    observed = None
                if observed:
                    is_session, source = True, observed.source
                    results.append(observed)
                    annotations.append(
                        {"date": str(day), "kind": "observed_archive", "source": source}
                    )
            if known_special and not special and not is_session:
                raise SourceUnavailable(
                    f"Special-session status for {day} ({holiday[0]['description']}) is unresolved; "
                    "provide dated official evidence via load_special_sessions, not a weekday assumption."
                )
            records.append(
                {"date": str(day), "is_session": bool(is_session), "source": source}
            )
            day += timedelta(days=1)
        return self._combined(
            "calendar",
            results,
            records,
            {
                "complete_through": str(end),
                "published_as_of": str(today),
                "annotations": annotations,
                "caveats": [
                    "Regular Mon-Fri equity schedule plus published CM holidays and explicit overrides.",
                    "Future classifications are as published today, not a guarantee against later circulars.",
                    "Muhurat session existence may be published before its trading hours; no hours inferred.",
                    "Historical closed-date 404 probes do not classify ordinary weekdays as holidays.",
                ],
            },
        )
