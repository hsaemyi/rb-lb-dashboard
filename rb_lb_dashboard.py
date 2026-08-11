import streamlit as st
import pandas as pd
import gspread
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Operations Performance Dashboard", layout="wide")

SPREADSHEET_ID = "1_0c46TezCR0uFGQ-E9V2ntHO_d5P-faWy-mdJPNdueY"
RDV_THRESHOLD = 95.0
RB_RATE_LOW_THRESHOLD = 1.0
WEEKS = ["WK29", "WK30", "WK31", "WK32"]
CREATION_WEEKS = ["2026-W29", "2026-W30", "2026-W31", "2026-W32"]

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }
.block-container { padding-top: 2.2rem; max-width: 1200px; }
.app-header { font-size: 26px; font-weight: 700; color: #14141f; letter-spacing: -0.4px; }
.app-sub { font-size: 13px; color: #8b8b96; margin-bottom: 22px; }
.section-label { font-size: 11px; font-weight: 600; color: #a0a0ab; text-transform: uppercase; letter-spacing: 0.6px; margin: 26px 0 10px; }
.card-title { font-size: 13px; font-weight: 600; color: #45454f; margin-bottom: 2px; }
.card-nums { font-size: 11px; color: #9a9aa5; margin-bottom: 8px; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px !important; border-color: #ececf1 !important; }
.action-green, .action-amber, .action-red, .action-gray {
    border-radius: 10px; padding: 13px 16px; margin-bottom: 8px; font-weight: 600; font-size: 13.5px;
}
.action-green { background: #f0faf6; color: #16805a; border: 1px solid #cdeee0; }
.action-amber { background: #fef8ec; color: #b8760a; border: 1px solid #f6e3b8; }
.action-red   { background: #fdf2f2; color: #c23d3d; border: 1px solid #f5c9c9; }
.action-gray  { background: #f7f7f9; color: #6b6b76; border: 1px solid #e6e6ec; }
hr { border-color: #ececf1 !important; margin: 22px 0 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="app-header">Operations Performance Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="app-sub">Performance Trends, Operational Metrics & Thresholds</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# 시트 로드
# ══════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def load_all():
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)

    def parse_blocks(sheet_name, header_keyword_col1):
        ws = sh.worksheet(sheet_name)
        rows = ws.get_all_values()
        blocks = {}
        i, n = 0, len(rows)
        while i < n:
            row = rows[i]
            col_a = row[0].strip() if len(row) > 0 else ""
            col_b = row[1].strip() if len(row) > 1 else ""
            if col_a and col_b == header_keyword_col1:
                label = col_a
                header = [c.strip() for c in row[1:]]
                data_rows = []
                j = i + 1
                while j < n:
                    r = rows[j]
                    if len(r) <= 1 or all(c.strip() == "" for c in r[:3]):
                        break
                    if len(r) > 0 and r[0].strip() and r[0].strip() != label:
                        break
                    data_rows.append(r[1:1 + len(header)])
                    j += 1
                blocks[label] = pd.DataFrame(data_rows, columns=header)
                i = j
            else:
                i += 1
        return blocks

    def parse_single(sheet_name, header_row_idx, start_col_idx):
        ws = sh.worksheet(sheet_name)
        rows = ws.get_all_values()
        header = [c.strip() for c in rows[header_row_idx - 1][start_col_idx:]]
        data_rows = []
        for r in rows[header_row_idx:]:
            sliced = r[start_col_idx:start_col_idx + len(header)]
            if len(sliced) == 0 or all(c.strip() == "" for c in sliced):
                continue
            data_rows.append(sliced + [""] * (len(header) - len(sliced)))
        return pd.DataFrame(data_rows, columns=header)

    rdv_df = parse_single("RDV", header_row_idx=2, start_col_idx=2)
    creation_blocks = parse_blocks("Creation", header_keyword_col1="Region")
    param_blocks = parse_blocks("LB/RB Parameter Dashboard", header_keyword_col1="Cityid")
    kr_rb_blocks = parse_blocks("KR_RB", header_keyword_col1="Region")

    return rdv_df, creation_blocks, param_blocks, kr_rb_blocks


with st.spinner("Loading data..."):
    try:
        rdv_df, creation_blocks, param_blocks, kr_rb_blocks = load_all()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()


# ══════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════
def clean_num(raw):
    raw = str(raw).strip()
    if raw in ["", "-", "N/A", "#DIV/0!", "No RB"]:
        return None
    raw = raw.replace("%", "").replace(",", "")
    try:
        return float(raw)
    except:
        return None


def get_series(blocks, metric_name, city, week_cols):
    df = blocks.get(metric_name)
    if df is None or df.empty or "City" not in df.columns:
        return [None] * len(week_cols)
    row = df[df["City"].astype(str).str.strip() == city]
    if row.empty:
        return [None] * len(week_cols)
    return [clean_num(row.iloc[0][w]) if w in df.columns else None for w in week_cols]


def get_rdv_series(rdv_df, city, week_cols):
    if "City / Geo" not in rdv_df.columns:
        return [None] * len(week_cols)
    row = rdv_df[rdv_df["City / Geo"].astype(str).str.strip() == city]
    if row.empty:
        return [None] * len(week_cols)
    rdv_week_cols = [w.replace("WK", "Week ") for w in week_cols]
    return [clean_num(row.iloc[0][w]) if w in rdv_df.columns else None for w in rdv_week_cols]


def get_val(blocks, metric_name, city, week_col):
    s = get_series(blocks, metric_name, city, [week_col])
    return s[0]


def get_total(blocks, metric_name, week_col):
    return get_val(blocks, metric_name, "Total", week_col)


def get_param(param_blocks, metric_name, city, col_name):
    df = param_blocks.get(metric_name)
    if df is None or df.empty or "Cityname" not in df.columns:
        return None
    row = df[df["Cityname"].astype(str).str.strip() == city]
    if row.empty or col_name not in df.columns:
        return None
    val = str(row.iloc[0][col_name]).strip()
    return val if val else None


# ══════════════════════════════════════════════════════
# 도시 / 주 선택
# ══════════════════════════════════════════════════════
all_cities = sorted(set(
    kr_rb_blocks.get("RB/DV", pd.DataFrame(columns=["City"]))["City"].astype(str).str.strip().tolist()
))
all_cities = [c for c in all_cities if c and c != "Total"]

col1, col2 = st.columns(2)
with col1:
    default_idx = all_cities.index("Songpa") if "Songpa" in all_cities else 0
    city = st.selectbox("City", all_cities, index=default_idx)
with col2:
    week = st.selectbox("Week", WEEKS, index=len(WEEKS) - 1)


# ══════════════════════════════════════════════════════
# 그래프 카드
# ══════════════════════════════════════════════════════
st.markdown('<div class="section-label">Weekly Trend</div>', unsafe_allow_html=True)

def chart_card(col, title, city_series, nat_series, week_labels):
    with col:
        with st.container(border=True):
            latest = city_series[-1] if city_series else None
            nat_latest = nat_series[-1] if nat_series else None
            st.markdown(f'<div class="card-title">{title}</div>', unsafe_allow_html=True)
            sub = f"{city}: {latest:.2f}" if latest is not None else f"{city}: -"
            if nat_latest is not None:
                sub += f"  ·  전국: {nat_latest:.2f}"
            st.markdown(f'<div class="card-nums">{sub}</div>', unsafe_allow_html=True)
            if any(v is not None for v in city_series):
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=week_labels, y=city_series, name=city,
                    mode="lines+markers",
                    line=dict(color="#3562E0", width=3),
                    marker=dict(size=6, color="#3562E0"),
                    hovertemplate="%{y}<extra></extra>",
                ))
                if any(v is not None for v in nat_series):
                    fig.add_trace(go.Scatter(
                        x=week_labels, y=nat_series, name="전국",
                        mode="lines+markers",
                        line=dict(color="#c7c7d1", width=2, dash="dot"),
                        marker=dict(size=5, color="#c7c7d1"),
                        hovertemplate="%{y}<extra></extra>",
                    ))
                fig.update_layout(
                    height=170,
                    margin=dict(l=0, r=0, t=4, b=0),
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(size=10)),
                    plot_bgcolor="white", paper_bgcolor="white",
                    xaxis=dict(showgrid=False, tickfont=dict(size=10)),
                    yaxis=dict(showgrid=True, gridcolor="#f2f2f5", tickfont=dict(size=10)),
                    font=dict(family="Inter, sans-serif"),
                )
                # y축 자동 확대: 값 차이가 시각적으로 잘 보이도록 여백만 살짝 줌
                all_vals = [v for v in city_series + nat_series if v is not None]
                if all_vals:
                    lo, hi = min(all_vals), max(all_vals)
                    pad = (hi - lo) * 0.25 if hi != lo else max(abs(hi) * 0.1, 0.5)
                    fig.update_yaxes(range=[lo - pad, hi + pad])
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                st.caption("데이터 없음")


def empty_card(col, title, note="데이터 없음 (시트 미연동)"):
    with col:
        with st.container(border=True):
            st.markdown(f'<div class="card-title">{title}</div>', unsafe_allow_html=True)
            st.caption(note)


cols = st.columns(3)

# 1. RB/DV Creation
creation_series = get_series(creation_blocks, "RB Creation(RB/DV) - RANGER", city, CREATION_WEEKS)
creation_nat_series = get_series(creation_blocks, "RB Creation(RB/DV) - RANGER", "Total", CREATION_WEEKS)
chart_card(cols[0], "RB/DV Creation", creation_series, creation_nat_series, WEEKS)

# 2. RB/DV
s = get_series(kr_rb_blocks, "RB/DV", city, WEEKS)
n = get_series(kr_rb_blocks, "RB/DV", "Total", WEEKS)
chart_card(cols[1], "RB/DV", s, n, WEEKS)

# 3. RB/DV_MTI
s = get_series(kr_rb_blocks, "RB/DV_MTI", city, WEEKS)
n = get_series(kr_rb_blocks, "RB/DV_MTI", "Total", WEEKS)
chart_card(cols[2], "RB/DV MTI", s, n, WEEKS)

cols2 = st.columns(3)
# 4. RB/DV_RANGER
s = get_series(kr_rb_blocks, "RB/DV_RANGER", city, WEEKS)
n = get_series(kr_rb_blocks, "RB/DV_RANGER", "Total", WEEKS)
chart_card(cols2[0], "RB/DV Ranger", s, n, WEEKS)

# 5. 24H Trips/RB
s = get_series(kr_rb_blocks, "24H Trips / RB", city, WEEKS)
n = get_series(kr_rb_blocks, "24H Trips / RB", "Total", WEEKS)
chart_card(cols2[1], "24H Trips/RB", s, n, WEEKS)

# 6. 24H Trips/RB_MTI (비워둠)
empty_card(cols2[2], "24H Trips/RB MTI")

cols3 = st.columns(3)
# 7. 24H Trips/RB_Ranger
s = get_series(kr_rb_blocks, "24H Trips / RB_Ranger", city, WEEKS)
n = get_series(kr_rb_blocks, "24H Trips / RB_Ranger", "Total", WEEKS)
chart_card(cols3[0], "24H Trips/RB Ranger", s, n, WEEKS)

# 8. RDV
s = get_rdv_series(rdv_df, city, WEEKS)
chart_card(cols3[1], "RDV", s, [RDV_THRESHOLD] * len(WEEKS), WEEKS)

# 9. TPVD
s = get_series(kr_rb_blocks, "TPVD", city, WEEKS)
n = get_series(kr_rb_blocks, "TPVD", "Total", WEEKS)
chart_card(cols3[2], "TPVD", s, n, WEEKS)


# ══════════════════════════════════════════════════════
# LB / RB Threshold
# ══════════════════════════════════════════════════════
st.markdown('<div class="section-label">LB / RB Threshold</div>', unsafe_allow_html=True)

PARAM_CITY_ALIAS = {"Songpa": "Seoul", "Mapo": "Seoul"}
threshold_city = PARAM_CITY_ALIAS.get(city, city)
if threshold_city != city:
    st.caption(f"※ Threshold는 {city}가 아닌 {threshold_city} 기준으로 관리됩니다")

threshold_rows = []
for label, key_col, key_label in [
    ("Marshal Normal LB", "Threshold", "Threshold"),
    ("Marshal Super LB", "Threshold", "Threshold"),
    ("Ranger Normal LB", "Threshold", "Threshold"),
    ("Ranger Super LB", "Threshold", "Threshold"),
    ("Marshal Regular RB", "RB / Trip", "RB/Trip"),
    ("Ranger Regular RB", "RB / Trip", "RB/Trip"),
    ("Marshal Inactive RB", "Inactive Days", "Inactive Days"),
    ("Ranger Inactive RB", "Inactive Days", "Inactive Days"),
]:
    block_key = label.replace(" ", "_", 1)  # "Marshal Normal LB" -> "Marshal_Normal LB"
    val = get_param(param_blocks, block_key, threshold_city, key_col)
    priority = get_param(param_blocks, block_key, threshold_city, "Task Priority")
    reward = get_param(param_blocks, block_key, threshold_city, "Task Reward")
    threshold_rows.append({
        "Type": label,
        "Metric": key_label,
        "Value": val if val else "-",
        "Task Priority": priority if priority else "-",
        "Task Reward": reward if reward else "-",
    })

th_cols = st.columns(2)
lb_rows = [r for r in threshold_rows if "LB" in r["Type"]]
rb_rows = [r for r in threshold_rows if "RB" in r["Type"]]
with th_cols[0]:
    with st.container(border=True):
        st.markdown('<div class="card-title">LB Threshold</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(lb_rows), hide_index=True, use_container_width=True)
with th_cols[1]:
    with st.container(border=True):
        st.markdown('<div class="card-title">RB Threshold</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(rb_rows), hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════
# 판단 로직
# ══════════════════════════════════════════════════════
creation = get_val(creation_blocks, "RB Creation(RB/DV) - RANGER", city, CREATION_WEEKS[-1])
creation_nat = get_total(creation_blocks, "RB Creation(RB/DV) - RANGER", CREATION_WEEKS[-1])
tpvd = get_val(kr_rb_blocks, "TPVD", city, week)
tpvd_nat = get_total(kr_rb_blocks, "TPVD", week)
rb_dv_ranger = get_val(kr_rb_blocks, "RB/DV_RANGER", city, week)
rb_dv_ranger_nat = get_total(kr_rb_blocks, "RB/DV_RANGER", week)
effect_ranger = get_val(kr_rb_blocks, "24H Trips / RB_Ranger", city, week)
effect_ranger_nat = get_total(kr_rb_blocks, "24H Trips / RB_Ranger", week)
rdv_val = get_rdv_series(rdv_df, city, [week])[0]
ranger_inactive = get_param(param_blocks, "Ranger_Inactive RB", PARAM_CITY_ALIAS.get(city, city), "Inactive Days")

st.markdown('<div class="section-label">판단 흐름</div>', unsafe_allow_html=True)

rb_action = None
lb_action = None

with st.container(border=True):
    st.markdown("**1단계 · RB Creation**")
    if creation is not None and creation_nat is not None:
        if creation < creation_nat:
            st.write(f"Creation {creation:.1f}% < 전국 {creation_nat:.1f}% → 낮음 (인액티브 기준 {ranger_inactive or '-'}일)")
            if tpvd is not None and tpvd_nat is not None and tpvd < tpvd_nat:
                st.write("TPVD도 낮음 → threshold 조정 검토 대상")
            else:
                st.write("TPVD는 양호 → threshold 조정보다 전체 분석 계속 진행")
        else:
            st.write(f"Creation {creation:.1f}% ≥ 전국 {creation_nat:.1f}% → 정상")
    else:
        st.write("데이터 없음")

with st.container(border=True):
    st.markdown("**2단계 · 레인저 RB 활동량 · Effect**")
    if rb_dv_ranger is not None and rb_dv_ranger < RB_RATE_LOW_THRESHOLD:
        st.write(f"레인저 RB량 {rb_dv_ranger:.1f}로 매우 낮음 → effect 판단 불가, 양부터 확보 필요")
        rb_action = ("레인저 RB 인센티브 (활동량 확보) + 다음 주기 effect 재확인", "amber")
    elif effect_ranger is not None and effect_ranger_nat is not None:
        if effect_ranger >= effect_ranger_nat:
            st.write(f"RB effect {effect_ranger:.2f} ≥ 전국 {effect_ranger_nat:.2f} → 효과 있음")
            if rb_dv_ranger is not None and rb_dv_ranger_nat is not None and rb_dv_ranger < rb_dv_ranger_nat:
                rb_action = ("레인저 RB 인센티브 후보 확정", "green")
            else:
                rb_action = ("RB 유지 (이미 양호)", "gray")
        else:
            st.write(f"RB effect {effect_ranger:.2f} < 전국 {effect_ranger_nat:.2f} → 효과 낮음")
            rb_action = ("RB 인센티브 대상 아님 — 위치·density 등 원인조사 필요", "red")
    else:
        st.write("effect 데이터 없음")

with st.container(border=True):
    st.markdown("**3단계 · RDV & LB 판단**")
    if rdv_val is not None:
        if rdv_val < RDV_THRESHOLD:
            st.write(f"RDV {rdv_val:.0f}% < 기준 {RDV_THRESHOLD:.0f}% → 미달")
            lb_action = ("레인저 LB 인센티브 검토", "green")
        else:
            st.write(f"RDV {rdv_val:.0f}% ≥ 기준 {RDV_THRESHOLD:.0f}% → 충족")
            lb_action = ("LB 액션 불필요", "gray")
    else:
        st.write("RDV 데이터 없음")


# ══════════════════════════════════════════════════════
# 최종 Action
# ══════════════════════════════════════════════════════
st.markdown('<div class="section-label">최종 Action</div>', unsafe_allow_html=True)

def action_box(text, level):
    st.markdown(f'<div class="action-{level}">{text}</div>', unsafe_allow_html=True)

col_rb, col_lb = st.columns(2)
with col_rb:
    st.markdown("**RB**")
    if rb_action:
        action_box(rb_action[0], rb_action[1])
    else:
        action_box("판단 불가 (데이터 부족)", "gray")
with col_lb:
    st.markdown("**LB**")
    if lb_action:
        action_box(lb_action[0], lb_action[1])
    else:
        action_box("판단 불가 (데이터 부족)", "gray")

st.markdown("---")
st.caption(f"판단 기준: RDV {RDV_THRESHOLD:.0f}%, 레인저 RB량 {RB_RATE_LOW_THRESHOLD} 미만 시 양부족으로 처리 (코드 상단에서 조정 가능)")
