"""ParkPulse daily pipeline: ingest -> validate/clean -> weather -> diff -> load -> brief.

Run:  python pipeline.py
Live data: set NPS_API_KEY (free at nps.gov/subjects/developer). Optional real visitation:
put a Kaggle/IRMA CSV at data/raw/visitation.csv (park_code,year,month,recreational_visits,
non_recreational_visits,camping_nights). Without these, clearly labelled DEMO data is generated.
"""
import hashlib, json, math, os, random, sqlite3, time
from datetime import date, datetime, timezone
import numpy as np
import pandas as pd


def db_path():
    return os.environ.get("PARKPULSE_DB", "data/parkpulse.db")


US = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
COLS = ["park_code", "name", "state", "lat", "lon", "entry_fee", "alt", "annual_m"]
# code, name, state, lat, lon, entry fee ($, illustrative), altitude m, annual visits (millions)
SEED = [
    ("GRSM", "Great Smoky Mountains", "TN", 35.6, -83.5, 0, 600, 12.2), ("GRCA", "Grand Canyon", "AZ", 36.1, -112.1, 35, 2100, 4.7),
    ("ZION", "Zion", "UT", 37.3, -113.0, 35, 1500, 4.6), ("ROMO", "Rocky Mountain", "CO", 40.3, -105.7, 30, 2800, 4.1),
    ("YOSE", "Yosemite", "CA", 37.9, -119.5, 35, 1600, 3.9), ("ACAD", "Acadia", "ME", 44.3, -68.2, 35, 100, 3.9),
    ("YELL", "Yellowstone", "WY", 44.6, -110.5, 35, 2400, 3.8), ("GLAC", "Glacier", "MT", 48.7, -113.7, 35, 1500, 3.0),
    ("OLYM", "Olympic", "WA", 47.8, -123.6, 30, 600, 2.9), ("EVER", "Everglades", "FL", 25.3, -80.9, 30, 2, 1.0),
    ("DENA", "Denali", "AK", 63.3, -150.5, 15, 600, 0.5), ("GRTE", "Grand Teton", "WY", 43.7, -110.8, 35, 2100, 3.4),
    ("BRCA", "Bryce Canyon", "UT", 37.6, -112.2, 35, 2400, 2.5), ("ARCH", "Arches", "UT", 38.7, -109.6, 30, 1400, 1.8),
    ("JOTR", "Joshua Tree", "CA", 33.9, -115.9, 30, 1100, 3.0), ("SEKI", "Sequoia and Kings Canyon", "CA", 36.5, -118.6, 35, 2000, 1.7),
    ("BADL", "Badlands", "SD", 43.8, -102.5, 30, 800, 1.0), ("SHEN", "Shenandoah", "VA", 38.5, -78.4, 30, 800, 1.5),
    ("BIBE", "Big Bend", "TX", 29.3, -103.3, 30, 1000, 0.5), ("GRBA", "Great Basin", "NV", 38.9, -114.3, 0, 2000, 0.15),
    ("HAVO", "Hawaii Volcanoes", "HI", 19.4, -155.3, 30, 1200, 1.3), ("CUVA", "Cuyahoga Valley", "OH", 41.2, -81.5, 0, 250, 2.5),
    ("MORA", "Mount Rainier", "WA", 46.9, -121.7, 30, 1400, 1.6), ("CRLA", "Crater Lake", "OR", 42.9, -122.1, 30, 1900, 0.5),
    ("DEVA", "Death Valley", "CA", 36.5, -117.1, 30, 0, 1.1), ("SAGU", "Saguaro", "AZ", 32.2, -110.7, 25, 900, 1.0),
    ("INDU", "Indiana Dunes", "IN", 41.6, -87.1, 0, 200, 3.1), ("CONG", "Congaree", "SC", 33.8, -80.8, 0, 30, 0.2),
    ("ISRO", "Isle Royale", "MI", 48.1, -88.6, 7, 200, 0.02), ("KATM", "Katmai", "AK", 58.5, -155.0, 0, 0, 0.05),
]
ARID = {"DEVA": 12, "SAGU": 8, "JOTR": 6, "BIBE": 8, "ARCH": 3, "ZION": 3}
GROWTH = {2015: .97, 2016: 1, 2017: 1, 2018: .99, 2019: 1, 2020: .7, 2021: .9, 2022: .95, 2023: .98, 2024: 1, 2025: 1.01}
CATS = ["Road closure", "Wildfire smoke", "Trail closure", "Construction", "Wildlife activity", "Fee-free day"]


def temp_c(lat, alt, month, code=""):
    """Transparent climate model (demo). Swap for real climate normals in production."""
    amp = 14 * min(1, lat / 35)
    return 15 - 0.6 * (lat - 35) - 0.0035 * alt + ARID.get(code, 0) + amp * math.sin(2 * math.pi * (month - 4) / 12)


def status_of(t):
    return "Closed" if t < -3 else "Good" if 8 <= t <= 27 else "Limited"


# ---------- 1. ingest ----------
def ingest(today=None):
    today = today or date.today()
    parks, source, key = pd.DataFrame(SEED, columns=COLS), "demo", os.environ.get("NPS_API_KEY")
    if key:
        try:
            import requests
            r = requests.get("https://developer.nps.gov/api/v1/parks", params={"limit": 600, "api_key": key}, timeout=30)
            r.raise_for_status()
            rows = []
            for d in r.json()["data"]:
                if "National Park" in d.get("designation", "") and d.get("latitude"):
                    fees = [float(x["cost"]) for x in d.get("entranceFees", [])] or [0]
                    rows.append((d["parkCode"].upper(), d["fullName"], d["states"].split(",")[0], float(d["latitude"]), float(d["longitude"]), max(fees), 500, 1.0))
            if rows:
                parks, source = pd.DataFrame(rows, columns=COLS), "nps_api"
        except Exception as e:  # keep the daily job alive, fall back to demo
            print("NPS API failed, using demo data:", e)
    rng = np.random.default_rng(42)
    if os.path.exists("data/raw/visitation.csv"):
        stats = pd.read_csv("data/raw/visitation.csv")
    else:
        rows = []
        for code, lat, alt, ann in parks[["park_code", "lat", "alt", "annual_m"]].itertuples(index=False):
            w = np.array([math.exp(-((temp_c(lat, alt, m, code) - 20) / 10) ** 2) + .15 for m in range(1, 13)]); w /= w.sum()
            drift = rng.normal(0, .03)
            for y in range(2015, 2026):
                g = GROWTH[y] * (1 + drift) ** (y - 2015) * rng.lognormal(0, .06)
                for m in range(1, 13):
                    tot = ann * 1e6 * w[m - 1] * g * rng.lognormal(0, .05); non = tot * rng.uniform(.03, .1)
                    rows.append((code, y, m, round(tot - non), round(non), round(tot * .05)))
        stats = pd.DataFrame(rows, columns=["park_code", "year", "month", "recreational_visits", "non_recreational_visits", "camping_nights"])
    camps = []
    for code in parks.park_code:
        for i in range(rng.integers(2, 8)):
            camps.append((f"{code}-C{i}", code, f"{code} Campground {i + 1}", int(rng.choice([0, 15, 20, 25, 30, 35])), int(rng.integers(20, 200))))
    camps = pd.DataFrame(camps, columns=["id", "park_code", "name", "cost", "capacity"])
    fees = pd.DataFrame({"park_code": parks.park_code, "entry_fee": parks.entry_fee.astype(float), "pass_cost": 80.0, "is_parking_free": rng.integers(0, 2, len(parks))})
    r = random.Random(today.toordinal()); codes = parks.park_code.tolist(); al = []
    for _ in range(r.randint(25, 40)):
        code, cat = r.choice(codes), r.choice(CATS)
        al.append((hashlib.md5(f"{code}{cat}".encode()).hexdigest()[:8], code, cat, r.choice(["Info", "Caution", "Danger"])))
    alerts = pd.DataFrame(al, columns=["alert_id", "park_code", "category", "severity"])
    park = parks[["park_code", "name", "state", "lat", "lon", "alt"]].copy()
    if source == "demo":  # deliberately messy rows so validation/cleaning has real work
        park.loc[park.index[0], "state"] = "tn "; park.loc[park.index[1], "state"] = "az"
        camps = pd.concat([camps, camps.head(3)], ignore_index=True); fees.loc[fees.index[2], "entry_fee"] = np.nan
    return {"park": park, "stats": stats, "campgrounds": camps, "fees": fees, "alerts": alerts}, source


# ---------- 2. validate + clean ----------
def validate(t):
    p, c, f, s, issues = t["park"], t["campgrounds"], t["fees"], t["stats"], []
    def add(tbl, rule, n, action):
        if n: issues.append((tbl, rule, int(n), action))
    add("park", "state not a clean US code", (~p.state.isin(US)).sum(), "auto-fix")
    add("park", "duplicate park_code", p.park_code.duplicated().sum(), "drop")
    add("park", "lat/lon out of range", ((p.lat.abs() > 90) | (p.lon.abs() > 180)).sum(), "quarantine")
    add("campgrounds", "duplicate campground id", c.id.duplicated().sum(), "drop")
    add("fees", "missing entry_fee", f.entry_fee.isna().sum(), "impute median and flag")
    add("stats", "negative visits", (s.recreational_visits < 0).sum(), "quarantine")
    total = sum(len(x) for x in t.values()); bad = sum(i[2] for i in issues)
    cells = sum(x.size for x in t.values()); nulls = sum(int(x.isna().sum().sum()) for x in t.values())
    q = {"completeness": round(100 * (1 - nulls / cells), 2),
         "uniqueness": round(100 * (1 - (p.park_code.duplicated().sum() + c.id.duplicated().sum()) / (len(p) + len(c))), 2),
         "validity": round(100 * (1 - bad / total), 2), "rows": total}
    return pd.DataFrame(issues, columns=["table", "rule", "rows", "action"]), q


def clean(t):
    t = dict(t); p = t["park"].copy(); p["state"] = p.state.str.strip().str.upper()
    p = p.drop_duplicates("park_code"); t["park"] = p[p.lat.abs().le(90) & p.lon.abs().le(180)]
    t["campgrounds"] = t["campgrounds"].drop_duplicates("id")
    f = t["fees"].copy(); f["entry_fee"] = f.entry_fee.fillna(f.entry_fee.median()); f["is_entry_free"] = (f.entry_fee == 0).astype(int); t["fees"] = f
    t["alerts"] = t["alerts"].drop_duplicates("alert_id"); t["stats"] = t["stats"][t["stats"].recreational_visits >= 0]
    return t


def seasons(t):
    s = t["stats"].assign(v=t["stats"].recreational_visits + t["stats"].non_recreational_visits)
    m = s.groupby(["park_code", "month"]).v.mean().reset_index(); m["crowd"] = (m.v / m.groupby("park_code").v.transform("max")).round(2)
    m = m.merge(t["park"][["park_code", "lat", "alt"]], on="park_code")
    m["temp_c"] = [round(temp_c(a, b, c, d), 1) for a, b, c, d in zip(m.lat, m.alt, m.month, m.park_code)]
    m["status"] = m.temp_c.map(status_of)
    return m[["park_code", "month", "temp_c", "status", "crowd"]]


# ---------- 3. weather ----------
def weather(park):
    now, live, rows = datetime.now(timezone.utc), True, []
    for r in park.itertuples():
        t, src = round(temp_c(r.lat, r.alt, now.month, r.park_code), 1), "model"
        if live:
            try:
                import requests
                j = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": r.lat, "longitude": r.lon, "current": "temperature_2m"}, timeout=5).json()
                t, src = j["current"]["temperature_2m"], "open-meteo"
            except Exception:
                live = False  # one failure is enough; do not wait on 30 timeouts
        rows.append((r.park_code, t, src, now.isoformat(timespec="seconds")))
    return pd.DataFrame(rows, columns=["park_code", "temp_c", "source", "updated_at"])


# ---------- 4. diff ----------
def _hash(df):
    return df.astype(str).apply(lambda r: hashlib.md5("|".join(r).encode()).hexdigest(), axis=1) if len(df) else pd.Series(dtype=str)


def diff(old, new, key):
    """Return (new, updated, removed) row counts between yesterday's table and today's."""
    if old is None or old.empty:
        return len(new), 0, 0
    o, n = dict(zip(old[key], _hash(old))), dict(zip(new[key], _hash(new)))
    return len(n.keys() - o.keys()), sum(1 for k in n if k in o and n[k] != o[k]), len(o.keys() - n.keys())


KEYS = {"park": "park_code", "campgrounds": "id", "alerts": "alert_id"}


def run():
    t0, log = time.time(), []
    def done(name, t, detail, status="OK"):
        log.append({"step": name, "seconds": round(time.time() - t, 2), "detail": detail, "status": status}); print(f"[{status}] {name}: {detail}")
    t = time.time(); raw, source = ingest(); done("Ingest NPS API", t, f"{sum(map(len, raw.values()))} rows ({source})")
    t = time.time(); issues, quality = validate(raw); tabs = clean(raw); tabs["seasons"] = seasons(tabs)
    done("Validate", t, f"{len(issues)} rule(s) flagged, validity {quality['validity']}%", "WARN" if len(issues) else "OK")
    t = time.time(); tabs["weather"] = weather(tabs["park"]); done("Integrate weather, climate", t, f"{len(tabs['weather'])} parks, source {tabs['weather'].source.iloc[0]}")
    os.makedirs(os.path.dirname(db_path()) or ".", exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(db_path()) as c:
        t = time.time(); changes = []
        for tbl, key in KEYS.items():
            try: old = pd.read_sql(f"SELECT * FROM {tbl}", c)
            except Exception: old = None
            changes.append((stamp, tbl, *diff(old, tabs[tbl], key)))
        ch = pd.DataFrame(changes, columns=["run_id", "table", "new", "updated", "removed"])
        done("Diff", t, ", ".join(f"{r.table}: +{r.new}/~{r.updated}/-{r.removed}" for r in ch.itertuples()))
        t = time.time()
        for name, df in {**tabs, "issues": issues}.items():
            df.to_sql(name, c, if_exists="replace", index=False)
        ch.to_sql("changes", c, if_exists="append", index=False)
        done("Load SQLite", t, f"{sum(len(d) for d in tabs.values())} rows in {len(tabs)} tables")
        t = time.time(); mo = datetime.now().month
        top = tabs["seasons"].query("month == @mo and status == 'Good'").merge(tabs["park"], on="park_code").sort_values("crowd").head(3).name.tolist()
        brief = f"ParkPulse brief {date.today()} ({source} data)\n" + "\n".join(f"- {r.table}: {r.new} new, {r.updated} updated, {r.removed} removed" for r in ch.itertuples()) + f"\n- {int(issues.rows.sum()) if len(issues) else 0} data issues handled\n- Good low-crowd picks this month: {', '.join(top) or 'none'}\n"
        open(os.path.join(os.path.dirname(db_path()) or ".", "daily_brief.md"), "w").write(brief); done("Daily brief", t, "written")
        meta = {"source": source, "last_run": stamp, "weather_updated": tabs["weather"].updated_at.iloc[0], "quality": json.dumps(quality), "brief": brief}
        pd.DataFrame(list(meta.items()), columns=["key", "value"]).to_sql("meta", c, if_exists="replace", index=False)
        pd.DataFrame([(stamp, "OK", round(time.time() - t0, 1), json.dumps(log))], columns=["run_id", "status", "seconds", "steps"]).to_sql("runs", c, if_exists="append", index=False)
    return log


if __name__ == "__main__":
    run()
