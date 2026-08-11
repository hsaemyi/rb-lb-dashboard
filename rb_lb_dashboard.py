import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Rebalancing Dashboard", layout="wide")

st.markdown("""
<style>
.result-card {
    background: #f0f7ff; border-radius: 10px;
    padding: 14px 18px; border: 1px solid #c0d8f0; margin-bottom: 8px;
}
.metric-card {
    background: #f8f9fa; border-radius: 10px;
    padding: 14px 18px; border: 1px solid #e0e0e0; margin-bottom: 8px;
}
.result-header {
    background: #1a1a2e; color: white; padding: 12px 20px;
    border-radius: 8px; font-weight: 700; font-size: 18px; margin: 16px 0 12px;
}
.sub-step-header {
    background: #f5f5f5; color: #2d2d2d; padding: 9px 16px;
    border-radius: 8px; font-weight: 600; font-size: 14px;
    border: 1px solid #bbb; margin: 20px 0 12px;
}
.label { font-size: 12px; color: #666; margin-bottom: 4px; }
.value-main { font-size: 22px; font-weight: 600; color: #1a1a2e; }
.value-sub { font-size: 13px; color: #444; margin-top: 2px; }
.delta-pos { color: #1D9E75; font-weight: 600; font-size: 13px; }
.delta-neg { color: #E24B4A; font-weight: 600; font-size: 13px; }
.delta-neu { color: #888; font-size: 13px; }
</style>
""", unsafe_allow_html=True)

st.title("Rebalancing Dashboard")
st.caption("Google Sheets-Linked | RB/LB Incentive Decision Support")

SPREADSHEET_ID = "1_0c46TezCR0uFGQ-E9V2ntHO_d5P-faWy-mdJPNdueY"

RDV_THRESHOLD = 95.0
RB_RATE_LOW_THRESHOLD = 1.0


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


with st.spinner("Loading data from Google Sheets..."):
    try:
        rdv_df, creation_blocks, param_blocks, kr_rb_blocks = load_all()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()


# ══════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════
def get_val(blocks, metric_name, city, week_col):
    df = blocks.get(metric_name)
    if df is None or df.empty or "City" not in df.columns:
        return None
    row = df[df["City"].astype(str).str.strip() == city]
    if row.empty or week_col not in df.columns:
        return None
    raw = str(row.iloc[0][week_col]).strip()
    if raw in ["", "-", "N/A", "#DIV/0!", "No RB"]:
        return None
    raw = raw.replace("%", "").replace(",", "")
    try:
        return float(raw)
    except:
        return None


def get_total(blocks, metric_name, week_col):
    return get_val(blocks, metric_name, "Total", week_col)


def get_rdv_val(rdv_df, city, week_col):
    if "City / Geo" not in rdv_df.columns:
        return None
    row = rdv_df[rdv_df["City / Geo"].astype(str).str.strip() == city]
    if row.empty or week_col not in rdv_df.columns:
        return None
    raw = str(row.iloc[0][week_col]).strip().replace("%", "")
    try:
        return float(raw)
    except:
        return None


def get_param(param_blocks, metric_name, city, col_name):
    df = param_blocks.get(metric_name)
    if df is None or df.empty or "Cityname" not in df.columns:
        return None
    row = df[df["Cityname"].astype(str).str.strip() == city]
    if row.empty or col_name not in df.columns:
        return None
    val = str(row.iloc[0][col_name]).strip()
    return val if val else None


def delta_badge(cur, ref, higher_is_better=True, fmt="{:.2f}", suffix=""):
    if cur is None or ref is None:
        return ""
    diff = cur - ref
    good = (diff >= 0) if higher_is_better else (diff <= 0)
    cls = "delta-pos" if good else "delta-neg"
    sign = "+" if diff >= 0 else ""
    return f'<span class="{cls}">({sign}{fmt.format(diff)}{suffix} vs 전국)</span>'


# ══════════════════════════════════════════════════════
# 도시 / 주 선택
# ══════════════════════════════════════════════════════
all_cities = sorted(set(
    kr_rb_blocks.get("RB/DV", pd.DataFrame(columns=["City"]))["City"].astype(str).str.strip().tolist()
))
all_cities = [c for c in all_cities if c and c != "Total"]

st.markdown("---")
col1, col2 = st.columns(2)
with col1:
    default_idx = all_cities.index("Songpa") if "Songpa" in all_cities else 0
    city = st.selectbox("City", all_cities, index=default_idx)
with col2:
    week_options = ["WK29", "WK30", "WK31", "WK32"]
    week = st.selectbox("Week", week_options, index=len(week_options) - 1)

creation_week_col = "2026-" + week.replace("WK", "W")

# ══════════════════════════════════════════════════════
# 지표 수집
# ══════════════════════════════════════════════════════
creation = get_val(creation_blocks, "RB Creation(RB/DV) - RANGER", city, creation_week_col)
creation_nat = get_total(creation_blocks, "RB Creation(RB/DV) - RANGER", creation_week_col)
tpvd = get_val(kr_rb_blocks, "TPVD", city, week)
tpvd_nat = get_total(kr_rb_blocks, "TPVD", week)
rb_dv_total = get_val(kr_rb_blocks, "RB/DV", city, week)
rb_dv_total_nat = get_total(kr_rb_blocks, "RB/DV", week)
rb_dv_mti = get_val(kr_rb_blocks, "RB/DV_MTI", city, week)
rb_dv_mti_nat = get_total(kr_rb_blocks, "RB/DV_MTI", week)
rb_dv_ranger = get_val(kr_rb_blocks, "RB/DV_RANGER", city, week)
rb_dv_ranger_nat = get_total(kr_rb_blocks, "RB/DV_RANGER", week)
effect_ranger = get_val(kr_rb_blocks, "24H Trips / RB_Ranger", city, week)
effect_ranger_nat = get_total(kr_rb_blocks, "24H Trips / RB_Ranger", week)
rdv = get_rdv_val(rdv_df, city, week)
ranger_inactive = get_param(param_blocks, "Ranger_Inactive RB", city, "Inactive Days")
marshal_inactive = get_param(param_blocks, "Marshal_Inactive RB", city, "Inactive Days")


# ══════════════════════════════════════════════════════
# Week's Metrics
# ══════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Week's Metrics")

def mcard(col, label, val, sub="", wow_html=""):
    col.markdown(f"""<div class="metric-card">
        <div class="label">{label}</div>
        <div class="value-main">{val} {wow_html}</div>
        <div class="value-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

r1c1, r1c2, r1c3, r1c4 = st.columns(4)
mcard(r1c1, "Creation (RB/DV)", f"{creation:.1f}%" if creation is not None else "-",
      f"전국 {creation_nat:.1f}%" if creation_nat is not None else "",
      delta_badge(creation, creation_nat, higher_is_better=True, fmt="{:.1f}", suffix="%p"))
mcard(r1c2, "TPVD", f"{tpvd:.2f}" if tpvd is not None else "-",
      f"전국 {tpvd_nat:.2f}" if tpvd_nat is not None else "",
      delta_badge(tpvd, tpvd_nat, higher_is_better=True))
mcard(r1c3, "RDV (가동률)", f"{rdv:.0f}%" if rdv is not None else "-", f"기준 {RDV_THRESHOLD:.0f}%",
      delta_badge(rdv, RDV_THRESHOLD, higher_is_better=True, fmt="{:.0f}", suffix="%p"))
mcard(r1c4, "레인저 RB Effect", f"{effect_ranger:.2f}" if effect_ranger is not None else "-",
      f"전국 {effect_ranger_nat:.2f}" if effect_ranger_nat is not None else "",
      delta_badge(effect_ranger, effect_ranger_nat, higher_is_better=True))

r2c1, r2c2, r2c3 = st.columns(3)
mcard(r2c1, "RB/DV 총량", f"{rb_dv_total:.1f}" if rb_dv_total is not None else "-",
      f"전국 {rb_dv_total_nat:.1f}" if rb_dv_total_nat is not None else "",
      delta_badge(rb_dv_total, rb_dv_total_nat, higher_is_better=True))
mcard(r2c2, "RB/DV_MTI", f"{rb_dv_mti:.1f}" if rb_dv_mti is not None else "-",
      f"전국 {rb_dv_mti_nat:.1f}" if rb_dv_mti_nat is not None else "",
      delta_badge(rb_dv_mti, rb_dv_mti_nat, higher_is_better=True))
mcard(r2c3, "RB/DV_레인저", f"{rb_dv_ranger:.1f}" if rb_dv_ranger is not None else "-",
      f"전국 {rb_dv_ranger_nat:.1f}" if rb_dv_ranger_nat is not None else "",
      delta_badge(rb_dv_ranger, rb_dv_ranger_nat, higher_is_better=True))


# ══════════════════════════════════════════════════════
# STEP 1. Creation & Threshold
# ══════════════════════════════════════════════════════
st.markdown("---")
st.markdown('<div class="result-header">STEP 1. Creation & Threshold</div>', unsafe_allow_html=True)

creation_low = creation is not None and creation_nat is not None and creation < creation_nat
tpvd_low = tpvd is not None and tpvd_nat is not None and tpvd < tpvd_nat

col_cur, col_ref = st.columns(2)
col_cur.markdown(f"""<div class="result-card">
    <div class="label">{city} Creation</div>
    <div class="value-main">{creation:.1f}%</div>
    <div class="value-sub">인액티브 기준 — Ranger {ranger_inactive or '-'}일 · Marshal {marshal_inactive or '-'}일</div>
</div>""" if creation is not None else """<div class="result-card">Creation 데이터 없음</div>""", unsafe_allow_html=True)
col_ref.markdown(f"""<div class="result-card">
    <div class="label">전국 평균</div>
    <div class="value-main">{creation_nat:.1f}%</div>
    <div class="value-sub">참고 도시 다수 인액티브 기준 3일</div>
</div>""" if creation_nat is not None else """<div class="result-card">-</div>""", unsafe_allow_html=True)

st.markdown('<div class="sub-step-header">판단</div>', unsafe_allow_html=True)
if creation_low:
    if tpvd_low:
        st.markdown('<span class="delta-neg">Creation 낮음 + TPVD 낮음 → Threshold(인액티브 기준일) 조정 검토 대상</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="delta-neu">Creation 낮음이지만 TPVD는 전국 이상 → Threshold 즉시 조정 대상은 아니나 전체 분석 계속 진행</span>', unsafe_allow_html=True)
else:
    st.markdown('<span class="delta-pos">Creation 정상 범위</span>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# STEP 2. 레인저 RB 활동량 · Effect
# ══════════════════════════════════════════════════════
st.markdown('<div class="result-header">STEP 2. 레인저 RB 활동량 · Effect</div>', unsafe_allow_html=True)

col_cur, col_ref = st.columns(2)
col_cur.markdown(f"""<div class="result-card">
    <div class="label">레인저 RB/DV</div>
    <div class="value-main">{rb_dv_ranger:.1f}</div>
    <div class="value-sub">MTI {rb_dv_mti:.1f} (전국 {rb_dv_mti_nat:.1f})</div>
</div>""" if rb_dv_ranger is not None else """<div class="result-card">데이터 없음</div>""", unsafe_allow_html=True)
col_ref.markdown(f"""<div class="result-card">
    <div class="label">전국 평균</div>
    <div class="value-main">{rb_dv_ranger_nat:.1f}</div>
</div>""" if rb_dv_ranger_nat is not None else """<div class="result-card">-</div>""", unsafe_allow_html=True)

st.markdown('<div class="sub-step-header">판단</div>', unsafe_allow_html=True)
rb_action = None
if rb_dv_ranger is not None and rb_dv_ranger < RB_RATE_LOW_THRESHOLD:
    st.markdown(f'<span class="delta-neg">레인저 RB량 {rb_dv_ranger:.1f}로 매우 낮음 → effect 판단 불가, 양부터 확보 필요</span>', unsafe_allow_html=True)
    rb_action = ("레인저 RB 인센티브 (활동량 확보) + 다음 주기 effect 재확인", "amber")
elif effect_ranger is not None and effect_ranger_nat is not None:
    if effect_ranger >= effect_ranger_nat:
        st.markdown(f'<span class="delta-pos">RB effect {effect_ranger:.2f} ≥ 전국 {effect_ranger_nat:.2f} → 효과 있음</span>', unsafe_allow_html=True)
        if rb_dv_ranger is not None and rb_dv_ranger_nat is not None and rb_dv_ranger < rb_dv_ranger_nat:
            rb_action = ("레인저 RB 인센티브 후보 확정", "green")
        else:
            rb_action = ("RB 유지 (이미 양호)", "gray")
    else:
        st.markdown(f'<span class="delta-neg">RB effect {effect_ranger:.2f} < 전국 {effect_ranger_nat:.2f} → 효과 낮음</span>', unsafe_allow_html=True)
        rb_action = ("RB 인센티브 대상 아님 — 위치·density 등 원인조사 필요", "red")
else:
    st.markdown('<span class="delta-neu">effect 데이터 없음</span>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# STEP 3. RDV & LB 판단
# ══════════════════════════════════════════════════════
st.markdown('<div class="result-header">STEP 3. RDV & LB 판단</div>', unsafe_allow_html=True)

col_cur, col_ref = st.columns(2)
col_cur.markdown(f"""<div class="result-card">
    <div class="label">{city} RDV</div>
    <div class="value-main">{rdv:.0f}%</div>
</div>""" if rdv is not None else """<div class="result-card">RDV 데이터 없음</div>""", unsafe_allow_html=True)
col_ref.markdown(f"""<div class="result-card">
    <div class="label">기준</div>
    <div class="value-main">{RDV_THRESHOLD:.0f}%</div>
</div>""", unsafe_allow_html=True)

st.markdown('<div class="sub-step-header">판단</div>', unsafe_allow_html=True)
lb_action = None
if rdv is not None:
    if rdv < RDV_THRESHOLD:
        st.markdown(f'<span class="delta-neg">RDV {rdv:.0f}% < 기준 {RDV_THRESHOLD:.0f}% → 미달</span>', unsafe_allow_html=True)
        lb_action = ("레인저 LB 인센티브 검토", "green")
    else:
        st.markdown(f'<span class="delta-pos">RDV {rdv:.0f}% ≥ 기준 {RDV_THRESHOLD:.0f}% → 충족</span>', unsafe_allow_html=True)
        lb_action = ("LB 액션 불필요", "gray")
else:
    st.markdown('<span class="delta-neu">RDV 데이터 없음</span>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# STEP 4. Result Summary
# ══════════════════════════════════════════════════════
st.markdown('<div class="sub-step-header">STEP 4 · Result Summary</div>', unsafe_allow_html=True)

bullets = []
if creation_low:
    bullets.append(f"Creation {creation:.1f}%로 전국({creation_nat:.1f}%) 대비 낮음 — 인액티브 기준일 조정 검토")
if rb_action:
    bullets.append(f"RB: {rb_action[0]}")
if lb_action:
    bullets.append(f"LB: {lb_action[0]}")
if not bullets:
    bullets.append("판단할 데이터가 부족합니다")

bullet_html = "".join([
    f"<div style='display:flex;gap:8px;margin-bottom:6px;'>"
    f"<span style='color:#1F3864;font-weight:700;'>•</span>"
    f"<span style='font-size:13px;color:#1a1a2e;'>{b}</span></div>"
    for b in bullets
])
st.markdown(f"""
<div style="background:#f8f9fa;border:1px solid #e0e0e0;border-radius:10px;padding:16px 20px;margin-bottom:8px;">
    <div style="font-size:13px;font-weight:700;color:#1F3864;margin-bottom:10px;">📌 Result Summary</div>
    {bullet_html}
</div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# 최종 Action
# ══════════════════════════════════════════════════════
st.markdown('<div class="sub-step-header">최종 Action</div>', unsafe_allow_html=True)

action_colors = {
    "green": ("#e8f5e9", "#81c784", "#1D9E75"),
    "amber": ("#fff8e1", "#ffe082", "#E07B00"),
    "red":   ("#ffebee", "#e57373", "#E24B4A"),
    "gray":  ("#f5f5f5", "#ccc", "#666"),
}

def action_card(col, title, action):
    if action is None:
        bg, border, txt = action_colors["gray"]
        text = "판단 불가 (데이터 부족)"
    else:
        text, level = action
        bg, border, txt = action_colors[level]
    col.markdown(f"""<div style="background:{bg};border:1px solid {border};border-radius:10px;
        padding:14px 18px;">
        <div style="font-size:12px;color:#666;margin-bottom:4px;">{title}</div>
        <div style="font-size:15px;font-weight:700;color:{txt};">{text}</div>
    </div>""", unsafe_allow_html=True)

col_rb, col_lb = st.columns(2)
action_card(col_rb, "RB", rb_action)
action_card(col_lb, "LB", lb_action)

st.markdown("---")
st.caption(f"판단 기준: RDV {RDV_THRESHOLD:.0f}%, 레인저 RB량 {RB_RATE_LOW_THRESHOLD} 미만 시 양부족으로 처리 (코드 상단에서 조정 가능)")
