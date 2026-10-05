"""Storage/migration tests use synthetic data, never self-certify real references."""

from io import BytesIO
import json
import shutil

import numpy as np
import pandas as pd
import pytest

from core import schedules, storage
from backtesting.s18 import data, dataset, replay, service
from backtesting.s18.config import COMBOS, METAL_MODES, S18Config
from test_s18_data import small_kit


@pytest.fixture(scope="module")
def import_source(tmp_path_factory):
    folder = small_kit(tmp_path_factory.mktemp("s18_source"), metals=True)
    dates = np.load(folder / "data" / "dates.npy")
    np.save(folder / "data" / "nifty500.npy", 1000 + np.arange(len(dates)) * 0.05)
    reference = folder / "S18_reference"
    output = folder / "output" / "analysis" / "s18"
    reference.mkdir()
    output.mkdir(parents=True)
    metrics, curves, index = [], [], []
    for mode in METAL_MODES:
        market = data.load_kit(folder, metals=mode != "none")
        for combo in COMBOS:
            books = replay.simulate(market, S18Config(combo, mode))
            frame = replay.trade_frame(books, market)
            tag = f"{combo}_{mode}"
            frame.to_csv(
                reference / f"{tag}_trades.csv", index=False, float_format="%.6g"
            )
            frame[frame.reason == "open at end"].to_csv(
                reference / f"{tag}_open_book_2026-08-31.csv",
                index=False,
                float_format="%.6g",
            )
            curve = replay.combined_curve(books, market)
            measured = replay.metrics(curve)
            metrics.append(
                {
                    "id": combo,
                    "mode": mode.replace("_", " "),
                    "Sharpe": measured["sharpe"],
                }
            )
            curves.append([r["nav"] / 2 for r in curve])
            index.append({"id": combo, "mode": mode.replace("_", " ")})
    pd.DataFrame(metrics).to_parquet(output / "s18_combos.parquet")
    np.save(output / "s18_nav.npy", np.array(curves))
    pd.DataFrame(index).to_csv(output / "s18_nav_index.csv", index=False)
    return folder


@pytest.fixture
def installed(import_source, tmp_path, monkeypatch):
    db = tmp_path / "portfolio.sqlite3"
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(db))
    monkeypatch.setattr(service, "REPORTS_ROOT", tmp_path / "reports")
    result = dataset.import_dataset(import_source)
    return dataset.get_dataset(), result


def test_import_is_atomic_idempotent_and_independent_of_source(
    installed, import_source, monkeypatch
):
    current, result = installed
    assert result["external_source_required"] is False
    again = dataset.import_dataset(import_source)
    assert again["dataset_id"] == current.id

    def no_source(*args, **kwargs):
        raise AssertionError("Product touched the external source directory")

    monkeypatch.setattr(dataset.FolderSource, "read", no_source)
    monkeypatch.setenv("S18_KIT_PATH", r"Z:\no-longer-exists")
    monkeypatch.setenv("S18_FORWARD_PATH", r"Z:\no-longer-exists")
    native = data.load_market(metals=True)
    assert native.provenance["source"] == "application_database"
    assert "kit_path" not in native.provenance
    validation = service.run_replay()
    assert validation["validation"]["tranches_checked"] == 30
    assert validation["dataset"]["dataset_id"] == current.id
    backtest = service.run_backtest(combo="P15", capital=500000, write_dossier=False)
    assert backtest["metrics"]["starting_capital"] == 500000
    assert backtest["validation"]["status"] == "passed"


def test_source_directory_can_be_removed_after_import(
    import_source, tmp_path, monkeypatch
):
    source = tmp_path / "temporary-import"
    shutil.copytree(import_source, source)
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "owned.sqlite3"))
    dataset.import_dataset(source)
    shutil.rmtree(source)
    assert not source.exists()
    assert data.load_market(metals=True).close.shape[1] == 4
    assert replay.validate_dataset()[0]["status"] == "passed"


def test_corrupt_import_preserves_previous_active_dataset(
    installed, import_source, tmp_path
):
    original, _ = installed
    broken = tmp_path / "bad-import"
    shutil.copytree(import_source, broken)
    (broken / "S18_reference" / "P15_none_trades.csv").write_text(
        "invalid", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="schema|trades"):
        dataset.import_dataset(broken)
    assert dataset.get_dataset().id == original.id


def test_tampered_database_blob_is_not_silently_accepted(installed):
    current, _ = installed
    with storage.connection_scope() as connection:
        connection.execute(
            "UPDATE s18_dataset_assets SET payload=? WHERE dataset_id=? AND name=?",
            (b"broken", current.id, "data/close.npy"),
        )
    with pytest.raises(ValueError, match="corrupt|checksum"):
        data.load_market()


def test_database_export_roundtrip_and_safe_names(installed, tmp_path):
    current, _ = installed
    target = tmp_path / "export"
    dataset.export_dataset(target)
    assert (target / "data" / "close.npy").read_bytes() == current.read(
        "data/close.npy"
    )
    for name in ("../secrets", r"data\close.npy", "/absolute", "C:/absolute"):
        with pytest.raises(ValueError, match="logical asset"):
            current.read(name)
    with pytest.raises(ValueError, match="must be empty"):
        dataset.export_dataset(target)


def test_project_reference_artifacts_exclude_bulk_panels(installed, tmp_path):
    current, _ = installed
    target = tmp_path / "project-references"
    result = dataset.export_reference_artifacts(target)
    assert result["dataset_id"] == current.id
    assert (target / "dataset_manifest.json").is_file()
    assert (target / "S18_reference" / "P15_none_trades.csv").is_file()
    assert not (target / "data").exists()
    assert dataset.export_reference_artifacts(target) == result
    (target / "S18_reference" / "P15_none_trades.csv").write_text("local edit")
    with pytest.raises(ValueError, match="modified project reference"):
        dataset.export_reference_artifacts(target)


def test_existing_schedule_migrates_without_becoming_enabled(installed):
    current, _ = installed
    job = schedules.create_schedule(
        strategy_id="s18_daily",
        run_at="19:00",
        enabled=False,
        params={
            "kit_path": "old-folder",
            "forward_path": "old-forward",
            "data_source": "nse",
            "book_id": "preserve",
            "capital": 500000,
        },
    )
    storage.set_document("strategy_defaults", "s18_daily", dict(job.params))
    storage.set_document("s18", "settings", {"kit_path": "old-folder"})
    dataset.migrate_path_settings()
    migrated = schedules.get_schedule(job.id)
    assert not migrated.enabled
    assert migrated.params == {"book_id": "preserve", "capital": 500000}
    assert storage.get_document("strategy_defaults", "s18_daily") == migrated.params
    assert storage.get_document("s18", "settings") == {"dataset_id": current.id}


def test_missing_dataset_does_not_fall_back_to_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "empty.sqlite3"))
    monkeypatch.setenv("S18_KIT_PATH", "looks-valid-but-not-used")
    with pytest.raises(ValueError, match="not installed"):
        service.run_backtest()


def test_dataset_reader_preserves_array_bytes(installed):
    current, _ = installed
    values = current.array("data/nifty500.npy")
    expected = np.load(BytesIO(current.read("data/nifty500.npy")), allow_pickle=False)
    np.testing.assert_array_equal(values, expected)
    with storage.connection_scope() as connection:
        manifests = connection.execute(
            "SELECT manifest_json FROM s18_datasets"
        ).fetchall()
    assert len(manifests) == 1
    assert json.loads(manifests[0][0])["data/nifty500.npy"]["size"] > 0
