import sqlite3
import pandas as pd
import pipeline


def test_validate_flags_dirty_data_and_clean_fixes_it():
    raw, _ = pipeline.ingest()
    issues, q = pipeline.validate(raw)
    assert set(issues.rule) >= {"state not a clean US code", "duplicate campground id", "missing entry_fee"}
    t = pipeline.clean(raw)
    assert t["park"].state.isin(pipeline.US).all()
    assert not t["campgrounds"].id.duplicated().any()
    assert t["fees"].entry_fee.notna().all()


def test_diff_counts():
    old = pd.DataFrame({"k": [1, 2, 3], "v": ["a", "b", "c"]})
    new = pd.DataFrame({"k": [2, 3, 4], "v": ["b", "X", "d"]})
    assert pipeline.diff(old, new, "k") == (1, 1, 1)
    assert pipeline.diff(None, new, "k") == (3, 0, 0)


def test_seasons_are_sensible():
    raw, _ = pipeline.ingest(); s = pipeline.seasons(pipeline.clean(raw))
    assert s[(s.park_code == "YELL") & (s.month == 1)].status.iloc[0] == "Closed"
    assert s[(s.park_code == "EVER") & (s.month == 1)].status.iloc[0] == "Good"


def test_full_run_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKPULSE_DB", str(tmp_path / "t.db"))
    monkeypatch.chdir(tmp_path)
    pipeline.run(); pipeline.run()
    c = sqlite3.connect(tmp_path / "t.db")
    ch = pd.read_sql("SELECT * FROM changes", c)
    assert len(pd.read_sql("SELECT * FROM park", c)) == 30
    assert ch[ch["table"] == "park"].new.tolist() == [30, 0]
    assert len(pd.read_sql("SELECT * FROM runs", c)) == 2
