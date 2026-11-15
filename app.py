"""ParkPulse dashboard. Run: streamlit run app.py"""
import json, os, sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

DB = os.environ.get("PARKPULSE_DB", "data/parkpulse.db")
st.set_page_config(page_title="ParkPulse", page_icon="🏞️", layout="wide")

GREEN, AMBER, INK, MUTED, LINE = "#1F5F4A", "#C98A1B", "#1E2A24", "#66726B", "#D9DDD2"
pio.templates["pp"] = go.layout.Template(layout=dict(
    font=dict(family="Inter, Segoe UI, sans-serif", color=INK, size=12), paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
    colorway=[GREEN, AMBER, "#4C8C78", "#8A6D3B", "#7FB5A0", "#B9473F", "#3C4A43", "#D9B26A"],
    xaxis=dict(gridcolor="#E4E7DF", linecolor=LINE, zeroline=False), yaxis=dict(gridcolor="#E4E7DF", linecolor=LINE, zeroline=False)))
pio.templates.default = "pp"; px.defaults.template = "pp"

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500&display=swap');
html, body, .stApp, [class*="css"] { font-family: Inter, 'Segoe UI', sans-serif; }
.stApp { background: #F6F7F3; color: #1E2A24; }
.stApp p, .stApp label, .stApp span, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4 { color: #1E2A24; }
* { border-radius: 0 !important; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.4rem; max-width: 1200px; }
h2, h3 { font-size: 16px !important; font-weight: 500 !important; margin: 1rem 0 .4rem !important; }
button[data-baseweb="tab"] { background: transparent; color: #66726B; font-size: 13px; padding: 0 2px 9px; margin-right: 16px; }
button[data-baseweb="tab"][aria-selected="true"] { color: #1F5F4A; font-weight: 500; }
[data-baseweb="tab-list"] { border-bottom: 1px solid #D9DDD2; gap: 0; }
[data-baseweb="tab-highlight"] { background: #1F5F4A; height: 2px; }
[data-testid="stMetric"] { background: #fff; border: 1px solid #D9DDD2; padding: 14px 16px; }
[data-testid="stMetricLabel"] p { color: #66726B; font-size: 12px; }
[data-baseweb="select"] > div, [data-baseweb="input"] > div, input { background: #fff !important; border: 1px solid #D9DDD2 !important; color: #1E2A24 !important; }
[data-baseweb="popover"] *, [data-baseweb="menu"] { background: #fff; color: #1E2A24; }
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"], [data-testid="stExpander"] { border: 1px solid #D9DDD2; background: #fff; }
pre, [data-testid="stCode"] { background: #fff !important; border: 1px solid #D9DDD2; }
pre code, pre span { color: #1E2A24 !important; }
.hdr { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.brand { display: flex; align-items: center; gap: 12px; }
.logo { width: 38px; height: 38px; background: #1F5F4A; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 18px; }
.brand b { font-size: 20px; font-weight: 500; display: block; line-height: 1.15; }
.brand span, .l { font-size: 12px; color: #66726B; letter-spacing: .02em; }
.pill { font-size: 12px; font-weight: 500; padding: 3px 10px; margin-left: 6px; white-space: nowrap; display: inline-block; }
.ok { background: #DCEFE5; color: #17543F; } .wn { background: #FBEFD5; color: #8A5A0B; } .nt { background: #EDEFE8; color: #3C4A43; }
.kgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 6px 0 12px; }
.kpi, .card { background: #fff; border: 1px solid #D9DDD2; padding: 14px 16px; }
.kpi .v { font-size: 26px; font-weight: 500; margin: 2px 0; } .kpi .s { font-size: 12px; } .g { color: #1F5F4A; } .a { color: #8A5A0B; }
.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 10px; margin-top: 10px; text-align: center; font-size: 12px; }
.steps b { display: block; font-weight: 500; } .steps span { color: #66726B; }
.dot { width: 26px; height: 26px; margin: 0 auto 6px; background: #DCEFE5; color: #17543F; display: flex; align-items: center; justify-content: center; font-size: 13px; }
.dot.w { background: #FBEFD5; color: #8A5A0B; }
.rec { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-top: 1px solid #E4E7DF; font-size: 13px; flex-wrap: wrap; }
.rec:first-child { border-top: 0; } .rec .nm { flex: 1; min-width: 160px; }
</style>""", unsafe_allow_html=True)
if not os.path.exists(DB):
    import pipeline; pipeline.run()


@st.cache_data(ttl=300)
def q(sql, params=()):
    with sqlite3.connect(DB) as c:
        return pd.read_sql(sql, c, params=params)


MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
V = "(s.recreational_visits + s.non_recreational_visits)"
YEARLY = f"WITH y AS (SELECT park_code, year, SUM({V}) v FROM stats s GROUP BY 1,2), l AS (SELECT park_code, year, v, LAG(v) OVER (PARTITION BY park_code ORDER BY year) pv FROM y) "
MOVE = "SELECT p.name, p.state, pv AS previous_visits, v AS current_visits, ROUND((v-pv)*100.0/pv,2) AS pct_change FROM l JOIN park p USING(park_code) WHERE year=(SELECT MAX(year) FROM stats) AND pv>0 AND v{op}pv ORDER BY pct_change {order} LIMIT 10"
# id: (title, chart kind, SQL). Same ten analyses as the original app, rewritten for SQLite.
QUERIES = {
    "q1": ("Year-over-year total visits growth", "line", f"WITH y AS (SELECT year, SUM({V}) total_visits FROM stats s GROUP BY year) SELECT year, total_visits, total_visits - LAG(total_visits) OVER (ORDER BY year) AS visit_change FROM y"),
    "q2": ("Best season to visit each park", "heat", "SELECT p.name, s.month, s.status FROM seasons s JOIN park p USING(park_code)"),
    "q3": ("Parks by state count", "map", "SELECT state, COUNT(*) AS number_of_parks FROM park GROUP BY state"),
    "q4": ("Revenue per visitor by fee structure", "bar", f"SELECT CASE WHEN f.entry_fee=0 THEN 'Free entry' ELSE 'Paid entry' END AS fee_structure, COUNT(*) AS parks, ROUND(AVG(f.pass_cost),2) AS avg_pass_cost, ROUND(AVG(a.avg_visits)) AS avg_annual_visits FROM fees f JOIN (SELECT park_code, SUM({V})*1.0/COUNT(DISTINCT year) avg_visits FROM stats s GROUP BY park_code) a USING(park_code) GROUP BY fee_structure"),
    "q5": ("Campground cost-to-capacity ratio", "bar", "SELECT p.name, COUNT(*) AS campgrounds, ROUND(AVG(c.cost),2) AS avg_cost, ROUND(n.nights/AVG(c.cost)) AS efficiency_score FROM campgrounds c JOIN park p USING(park_code) JOIN (SELECT park_code, SUM(camping_nights)*1.0/COUNT(DISTINCT year) nights FROM stats GROUP BY park_code) n USING(park_code) WHERE c.cost>0 GROUP BY p.name ORDER BY efficiency_score DESC LIMIT 10"),
    "q6": ("Rising stars", "bar", YEARLY + MOVE.format(op=">", order="DESC")),
    "q7": ("State-level park statistics", "table", f"SELECT p.state, COUNT(DISTINCT p.park_code) AS parks, SUM({V}) AS total_visits, ROUND(SUM({V})*1.0/COUNT(DISTINCT p.park_code)) AS avg_visits_per_park, SUM(s.camping_nights) AS camping_nights FROM park p JOIN stats s USING(park_code) GROUP BY p.state ORDER BY total_visits DESC"),
    "q8": ("Falling stars: parks needing attention", "bar", YEARLY + MOVE.format(op="<", order="ASC")),
    "q9": ("Recreational visits by state", "pie", "SELECT p.state, SUM(s.recreational_visits) AS recreational_visits FROM park p JOIN stats s USING(park_code) GROUP BY p.state"),
    "q10": ("Non-recreational visits by state", "pie", "SELECT p.state, SUM(s.non_recreational_visits) AS non_recreational_visits FROM park p JOIN stats s USING(park_code) GROUP BY p.state"),
}


def chart(df, kind, key):
    a, b = df.columns[0], df.columns[1]
    if kind == "line": fig = px.line(df, x=a, y=b, markers=True)
    elif kind == "bar": fig = px.bar(df, x=a, y=df.columns[-1], hover_data=list(df.columns))
    elif kind == "map": fig = px.choropleth(df, locations=a, locationmode="USA-states", color=b, scope="usa", color_continuous_scale=["#EEF3EC", GREEN]); fig.update_geos(bgcolor="#FFFFFF", landcolor="#EDEFE8", subunitcolor=LINE)
    elif kind == "pie": fig = px.pie(df, names=a, values=b)
    elif kind == "heat":
        z = df.assign(n=df.status.map({"Closed": 0, "Limited": 1, "Good": 2})).pivot(index="name", columns="month", values="n").rename(columns=dict(enumerate(MON, 1)))
        fig = px.imshow(z, color_continuous_scale=[(0, "#B9473F"), (.5, "#E3B23C"), (1, GREEN)], aspect="auto", labels={"color": "0 closed, 1 limited, 2 good"})
    else: return
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=330)
    st.plotly_chart(fig, key=key)


meta = dict(q("SELECT key, value FROM meta").values)
quality = json.loads(meta["quality"])
def ago(ts):
    s = (pd.Timestamp.now(tz="UTC") - pd.Timestamp(ts)).total_seconds()
    return "just now" if s < 90 else f"{int(s // 60)} min ago" if s < 5400 else f"{int(s // 3600)} h ago" if s < 172800 else f"{int(s // 86400)} d ago"


src_pill = '<span class="pill wn">Demo data</span>' if meta["source"] == "demo" else '<span class="pill ok">Live NPS data</span>'
st.markdown(f'<div class="hdr"><div class="brand"><div class="logo">&#9650;</div><div><b>ParkPulse</b><span>National Parks Intelligence System</span></div></div>'
            f'<div>{src_pill}<span class="pill ok">Weather updated {ago(meta["weather_updated"])}</span><span class="pill ok">Last run {ago(meta["last_run"])}</span></div></div>', unsafe_allow_html=True)
tabs = st.tabs(["Home", "Explorer", "Trip planner", "Compare", "Dashboards", "Ask", "Automation", "Data health", "Integrations"])

with tabs[0]:
    tot = q("SELECT COUNT(*) n FROM park").n[0]; last = q(f"SELECT year, SUM({V}) v FROM stats s GROUP BY year ORDER BY year DESC LIMIT 2")
    nst = q("SELECT COUNT(DISTINCT state) n FROM park").n[0]; yoy = (last.v[0] / last.v[1] - 1) * 100
    steps = pd.DataFrame(json.loads(q("SELECT steps FROM runs ORDER BY run_id DESC LIMIT 1").steps[0]))
    iss = int(q("SELECT COALESCE(SUM(rows),0) n FROM issues").n[0])
    def kpi(l, v, sub, tone="g"): return f'<div class="kpi"><div class="l">{l}</div><div class="v">{v}</div><div class="s {tone}">{sub}</div></div>'
    st.markdown('<div class="kgrid">' + kpi("Park units", tot, f"across {nst} states") + kpi("Records tracked", f"{quality['rows']:,}", "in the database")
                + kpi(f"Visits {last.year[0]}", f"{last.v[0] / 1e6:.0f}M", f"{yoy:+.1f}% YoY", "g" if yoy >= 0 else "a")
                + kpi("Data quality", f"{quality['validity']}%", f"{iss} rows handled", "a" if iss else "g") + '</div>', unsafe_allow_html=True)
    st.markdown('<div class="card"><div class="l">PIPELINE, LAST RUN</div><div class="steps">' + "".join(
        f'<div><div class="dot{" w" if r.status != "OK" else ""}">{"!" if r.status != "OK" else "&#10003;"}</div><b>{r.step}</b><span>{r.detail}</span></div>' for r in steps.itertuples()) + '</div></div>', unsafe_allow_html=True)
    a, b = st.columns([3, 2])
    with a: st.subheader(QUERIES["q1"][0]); chart(q(QUERIES["q1"][2]), "line", "home")
    with b: st.subheader("Daily brief"); st.code(meta["brief"], language=None)

with tabs[1]:
    df = q(f"SELECT p.name, p.state, p.lat, p.lon, f.entry_fee, ROUND(SUM({V})/1e6/COUNT(DISTINCT s.year),2) AS visits_m FROM park p JOIN fees f USING(park_code) JOIN stats s USING(park_code) GROUP BY p.park_code")
    df["fee_type"] = df.entry_fee.map(lambda x: "Free" if x == 0 else "Paid")
    a, b = st.columns(2); sts = a.multiselect("State", sorted(df.state.unique())); ft = b.radio("Fee type", ["All", "Free", "Paid"], horizontal=True)
    if sts: df = df[df.state.isin(sts)]
    if ft != "All": df = df[df.fee_type == ft]
    fig = px.scatter_geo(df, lat="lat", lon="lon", size="visits_m", color="fee_type", hover_name="name", scope="usa", color_discrete_map={"Free": GREEN, "Paid": AMBER})
    fig.update_geos(bgcolor="#FFFFFF", landcolor="#EDEFE8", subunitcolor=LINE)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=450); st.plotly_chart(fig)
    st.dataframe(df.sort_values("visits_m", ascending=False).drop(columns=["lat", "lon"]), hide_index=True)

with tabs[2]:
    a, b = st.columns(2); mo = a.selectbox("Month of visit", range(1, 13), index=pd.Timestamp.today().month - 1, format_func=lambda m: MON[m - 1])
    budget = b.radio("Entry fee", ["Any", "Free only", "Paid is fine"], horizontal=True)
    r = q("SELECT p.name, p.state, f.entry_fee, s.status, s.crowd, s.temp_c, (SELECT ROUND(AVG(cost)) FROM campgrounds c WHERE c.park_code=p.park_code AND cost>0) AS camp_per_night FROM seasons s JOIN park p USING(park_code) JOIN fees f USING(park_code) WHERE s.month=?", (mo,))
    r["score"] = r.status.map({"Good": 3, "Limited": 1, "Closed": -9}) - 2 * r.crowd
    if budget == "Free only": r = r[r.entry_fee == 0]
    if budget == "Paid is fine": r = r[r.entry_fee > 0]
    top = r[r.status != "Closed"].sort_values("score", ascending=False).head(5)
    st.subheader(f"Best parks in {MON[mo - 1]}")
    html = ""
    for x in top.itertuples():
        crowd = "Busy, go early" if x.crowd > .8 else "Moderate crowds" if x.crowd > .5 else "Quiet"
        fee = '<span class="pill ok">Free entry</span>' if x.entry_fee == 0 else f'<span class="pill nt">${x.entry_fee:.0f} entry</span>'
        season = f'<span class="pill {"ok" if x.status == "Good" else "wn"}">{x.status} season</span>'
        html += f'<div class="rec"><div class="nm"><b>{x.name}</b> <span class="l">{x.state} &middot; {x.temp_c}&deg;C typical</span></div>{season}<span class="l" style="min-width:110px">{crowd}</span>{fee}</div>'
    if html: st.markdown(f'<div class="card">{html}</div>', unsafe_allow_html=True)
    if top.empty: st.info("No open parks match. Try another month or fee option.")
    elif (top.entry_fee > 0).sum() >= 2: st.success("Visiting 2 to 3 paid parks? An $80 annual pass usually costs less than paying at each gate.")
    st.subheader("Best months for every park"); chart(q(QUERIES["q2"][2]), "heat", "heat")

with tabs[3]:
    names = q("SELECT name FROM park ORDER BY name").name.tolist(); a, b = st.columns(2)
    p1 = a.selectbox("Park A", names, index=names.index("Zion")); p2 = b.selectbox("Park B", names, index=names.index("Acadia"))
    d = q(f"SELECT p.name, p.state, f.entry_fee, ROUND(SUM({V})/1e6/COUNT(DISTINCT s.year),2) AS visits_m, (SELECT ROUND(AVG(cost)) FROM campgrounds c WHERE c.park_code=p.park_code AND cost>0) AS camp_per_night FROM park p JOIN fees f USING(park_code) JOIN stats s USING(park_code) WHERE p.name IN (?,?) GROUP BY p.park_code", (p1, p2))
    st.dataframe(d.set_index("name").T.astype(str))
    m = q(f"SELECT p.name, s.month, AVG({V}) AS visits FROM stats s JOIN park p USING(park_code) WHERE p.name IN (?,?) GROUP BY p.name, s.month", (p1, p2))
    fig = px.line(m, x="month", y="visits", color="name", markers=True); fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0)); st.plotly_chart(fig)

with tabs[4]:
    ids = ["q6", "q8", "q5", "q4", "q3", "q9"]
    for row in range(0, len(ids), 2):
        for col, i in zip(st.columns(2), ids[row:row + 2]):
            with col: st.subheader(QUERIES[i][0]); chart(q(QUERIES[i][2]), QUERIES[i][1], "d" + i)

with tabs[5]:
    pick = st.selectbox("Saved question", list(QUERIES), format_func=lambda k: QUERIES[k][0]); title, kind, sql = QUERIES[pick]
    with st.expander("SQL", expanded=True): st.code(sql, language="sql")
    res = q(sql); chart(res, kind, "ask"); st.dataframe(res, hide_index=True)

with tabs[6]:
    c = st.columns(3); c[0].metric("Schedule", "06:00 UTC daily"); c[1].metric("Runner", "GitHub Actions"); c[2].metric("Last duration", f"{q('SELECT seconds FROM runs ORDER BY run_id DESC LIMIT 1').seconds[0]} s")
    st.subheader("Last run"); st.dataframe(steps, hide_index=True)
    st.subheader("What changed (by run)"); st.dataframe(q("SELECT run_id, \"table\", new, updated, removed FROM changes ORDER BY run_id DESC LIMIT 15"), hide_index=True)
    st.subheader("Run history"); st.dataframe(q("SELECT run_id, status, seconds FROM runs ORDER BY run_id DESC LIMIT 10"), hide_index=True)

with tabs[7]:
    c = st.columns(3); c[0].metric("Completeness", f"{quality['completeness']}%"); c[1].metric("Uniqueness", f"{quality['uniqueness']}%"); c[2].metric("Validity", f"{quality['validity']}%")
    counts = pd.DataFrame([(t, q(f"SELECT COUNT(*) n FROM {t}").n[0]) for t in ["park", "stats", "seasons", "campgrounds", "fees", "alerts", "weather"]], columns=["table", "rows"])
    st.subheader("Rows by table"); st.plotly_chart(px.bar(counts, x="rows", y="table", orientation="h").update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0)))
    st.subheader("Issues found and handled this run"); st.dataframe(q("SELECT * FROM issues"), hide_index=True)

with tabs[8]:
    src = meta["source"]; w = q("SELECT source FROM weather LIMIT 1").source[0]
    rows = [("NPS API", "Parks, fees, alerts", "Connected" if src == "nps_api" else "Set NPS_API_KEY to enable"), ("Open-Meteo", "Current weather", "Connected" if w == "open-meteo" else "Using climate model (offline fallback)"),
            ("Kaggle / IRMA visitation", "Historical monthly visits", "Drop CSV in data/raw/visitation.csv"), ("SQLite", "Analytics store", f"Active: {DB}"), ("GitHub Actions", "Daily 06:00 UTC refresh", "See .github/workflows"), ("Email or Slack", "Daily brief delivery", "Optional, not configured")]
    st.dataframe(pd.DataFrame(rows, columns=["Integration", "Purpose", "Status"]), hide_index=True)
