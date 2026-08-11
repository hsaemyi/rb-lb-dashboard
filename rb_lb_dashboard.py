import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="RB/LB Incentive Dashboard", layout="wide")

SPREADSHEET_ID = "1_0c46TezCR0uFGQ-E9V2ntHO_d5P-faWy-mdJPNdueY"

# ══════════════════════════════════════════════════════
# 판단 기준값 (여기서 조정)
# ══════════════════════════════════════════════════════
RDV_THRESHOLD = 95.0   # RDV 기준(%) - 원래 기준값
GAP_THRESHOLD = 2.0    # creation vs 총수행량 갭 기준(%p)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }

.block-container { padding-top: 2.5rem; max-width: 1180px; }

.app-header { font-size: 22px; font-weight: 700; color: #14141f; letter-spacing: -0.3px; margin-bottom: 2px; }
.app-sub { font-size: 13px; color: #8b8b96; margin-bottom: 28px; }

.section-label { font-size: 11px; font-weight: 600; color: #a0a0ab; text-transform: uppercase; letter-spacing: 0.6px; margin: 28px 0 10px; }

.metric-card {
    background: #ffffff; border-radius: 12px; padding: 14px 16px;
    border: 1px solid #ececf1; box-shadow: 0 1px 2px rgba(20,20,31,0.04);
    margin-bottom: 10px; height: 88px;
}
.label { font-size: 11px; font-weight: 500; color: #9a9aa5; margin-bottom: 5px; letter-spacing: 0.2px; }
.value-main { font-size: 19px; font-weight: 700; color: #14141f; letter-spacing: -0.3px; }
.value-sub { font-size: 11px; color: #b0b0ba; margin-top: 3px; }

.step-box {
    background: #fafafc; border: 1px solid #ececf1; border-radius: 10px;
    padding: 12px 16px; margin-bottom: 8px; font-size: 13px; color: #45454f;
}
.step-box b { color: #14141f; font-weight: 600; }

.action-green, .action-amber, .action-red, .action-gray {
    border-radius: 10px; padding: 13px 16px; margin-bottom: 8px;
    font-weight: 600; font-size: 13.5px; letter-spacing: -0.1px;
}
.action-green { background: #f0faf6; color: #16805a; border: 1px solid #cdeee0; }
.action-amber { background: #fef8ec; color: #b8760a; border: 1px solid #f6e3b8; }
.action-red   { background: #fdf2f2; color: #c23d3d; border: 1px solid #f5c9c9; }
.action-gray  { background: #f7f7f9; color: #6b6b76; border: 1px solid #e6e6ec; }

div[data-testid="stSelectbox"] label { font-size: 12px; font-weight: 500; color: #6b6b76; }
hr { border-color: #ececf1 !important; margin: 24px 0 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="app-header">Rebalancing Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="app-sub">도시 선택 시 RB/LB 판단 로직을 단계별로 계산합니다</div>', unsafe_allow_html=True)


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
        """A열에 라벨(지표명)이 반복되는 블록형 탭 파서.
        header_keyword_col1: 헤더행을 식별할 두 번째 컬럼의 값 (예: 'Region', 'Cityid')
        """
        ws = sh.worksheet(sheet_name)
        rows = ws.get_all_values()
        blocks = {}
        i = 0
        n = len(rows)
        while i < n:
            row = rows[i]
            col_a = row[0].strip() if len(row) > 0 else ""
            col_b = row[1].strip() if len(row) > 1 else ""
            if col_a and col_b == header_keyword_col1:
                # 헤더 행 발견
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
                df = pd.DataFrame(data_rows, columns=header)
                blocks[label] = df
                i = j
            else:
                i += 1
        return blocks

    def parse_single(sheet_name, header_row_idx, start_col_idx):
        """헤더가 한 번만 나오는 단일 표 탭 파서 (RDV용). 1-indexed header_row_idx."""
        ws = sh.worksheet(sheet_name)
        rows = ws.get_all_values()
        header = [c.strip() for c in rows[header_row_idx - 1][start_col_idx:]]
        data_rows = []
        for r in rows[header_row_idx:]:
            sliced = r[start_col_idx:start_col_idx + len(header)]
            if len(sliced) == 0 or all(c.strip() == "" for c in sliced):
                continue
            data_rows.append(sliced + [""] * (len(header) - len(sliced)))
        df = pd.DataFrame(data_rows, columns=header)
        return df

    rdv_df = parse_single("RDV", header_row_idx=2, start_col_idx=2)  # C열=index2, 2행
    creation_blocks = parse_blocks("Creation", header_keyword_col1="Region")
    param_blocks = parse_blocks("LB/RB Parameter Dashboard", header_keyword_col1="Cityid")
    kr_rb_blocks = parse_blocks("KR_RB", header_keyword_col1="Region")

    return rdv_df, creation_blocks, param_blocks, kr_rb_blocks


with st.spinner("Google Sheets에서 데이터 불러오는 중..."):
    try:
        rdv_df, creation_blocks, param_blocks, kr_rb_blocks = load_all()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()


# ══════════════════════════════════════════════════════
# 헬퍼: 특정 블록에서 도시의 특정 주(WK32 등) 값 가져오기
# ══════════════════════════════════════════════════════
def get_val(blocks, metric_name, city, week_col, as_float=True):
    df = blocks.get(metric_name)
    if df is None or df.empty:
        return None
    row = df[df["City"].astype(str).str.strip() == city]
    if row.empty or week_col not in df.columns:
        return None
    raw = str(row.iloc[0][week_col]).strip()
    if raw in ["", "-", "N/A", "#DIV/0!", "No RB"]:
        return None
    raw = raw.replace("%", "").replace(",", "")
    if not as_float:
        return raw
    try:
        return float(raw)
    except:
        return None


def get_total(blocks, metric_name, week_col):
    return get_val(blocks, metric_name, "Total", week_col)


def get_rdv_val(rdv_df, city, week_col):
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
    week_options = ["WK29", "WK30", "WK31", "WK32"]
    week = st.selectbox("Week", week_options, index=len(week_options) - 1)

creation_week_col = "2026-" + week.replace("WK", "W")

st.markdown("---")

# ══════════════════════════════════════════════════════
# 지표 수집
# ══════════════════════════════════════════════════════
creation = get_val(creation_blocks, "RB Creation(RB/DV) - RANGER", city, creation_week_col)
creation_total = get_total(creation_blocks, "RB Creation(RB/DV) - RANGER", creation_week_col)

tpvd = get_val(kr_rb_blocks, "TPVD", city, week)
tpvd_total = get_total(kr_rb_blocks, "TPVD", week)

rb_dv_total_city = get_val(kr_rb_blocks, "RB/DV", city, week)
rb_dv_total_nat = get_total(kr_rb_blocks, "RB/DV", week)

rb_dv_mti = get_val(kr_rb_blocks, "RB/DV_MTI", city, week)
rb_dv_mti_nat = get_total(kr_rb_blocks, "RB/DV_MTI", week)

rb_dv_ranger = get_val(kr_rb_blocks, "RB/DV_RANGER", city, week)
rb_dv_ranger_nat = get_total(kr_rb_blocks, "RB/DV_RANGER", week)

effect_ranger = get_val(kr_rb_blocks, "24H Trips / RB_Ranger", city, week)
effect_ranger_nat = get_total(kr_rb_blocks, "24H Trips / RB_Ranger", week)

rdv = get_rdv_val(rdv_df, city, week)

marshal_inactive = get_param("MARSHAL_INACTIVE DAYS", param_blocks, city, "Inactive Days") if False else get_param(param_blocks, "MARSHAL_INACTIVE DAYS", city, "Inactive Days")
ranger_inactive = get_param(param_blocks, "Ranger_Inactive RB", city, "Inactive Days")


# ══════════════════════════════════════════════════════
# 요약 카드
# ══════════════════════════════════════════════════════
def mcard(col, label, val, sub=""):
    col.markdown(f"""<div class="metric-card">
        <div class="label">{label}</div>
        <div class="value-main">{val}</div>
        <div class="value-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
mcard(c1, "Creation(RB/DV)", f"{creation:.1f}%" if creation is not None else "-", f"전국 {creation_total:.1f}%" if creation_total else "")
mcard(c2, "TPVD", f"{tpvd:.2f}" if tpvd is not None else "-", f"전국 {tpvd_total:.2f}" if tpvd_total else "")
mcard(c3, "RDV(가동률)", f"{rdv:.0f}%" if rdv is not None else "-", f"기준 {RDV_THRESHOLD:.0f}%")
mcard(c4, "레인저 RB effect", f"{effect_ranger:.2f}" if effect_ranger is not None else "-", f"전국 {effect_ranger_nat:.2f}" if effect_ranger_nat else "")

c5, c6, c7 = st.columns(3)
mcard(c5, "RB/DV 총량", f"{rb_dv_total_city:.1f}" if rb_dv_total_city is not None else "-", f"전국 {rb_dv_total_nat:.1f}" if rb_dv_total_nat else "")
mcard(c6, "RB/DV_MTI", f"{rb_dv_mti:.1f}" if rb_dv_mti is not None else "-", f"전국 {rb_dv_mti_nat:.1f}" if rb_dv_mti_nat else "")
mcard(c7, "RB/DV_레인저", f"{rb_dv_ranger:.1f}" if rb_dv_ranger is not None else "-", f"전국 {rb_dv_ranger_nat:.1f}" if rb_dv_ranger_nat else "")

st.markdown("---")

# ══════════════════════════════════════════════════════
# 6단계 판단 로직
# ══════════════════════════════════════════════════════
st.markdown('<div class="section-label">판단 흐름</div>', unsafe_allow_html=True)

def action_box(text, level="gray"):
    cls = {"green": "action-green", "amber": "action-amber", "red": "action-red", "gray": "action-gray"}[level]
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)

rb_actions = []
lb_actions = []

# 1단계: Creation
st.markdown('<div class="step-box"><b>1단계 · RB Creation 확인</b></div>', unsafe_allow_html=True)
if creation is None or creation_total is None:
    st.write("Creation 데이터 없음")
elif creation < creation_total:
    st.write(f"Creation {creation:.1f}% < 전국 {creation_total:.1f}% → 낮음")
    if tpvd is not None and tpvd_total is not None and tpvd < tpvd_total:
        st.write(f"TPVD {tpvd:.2f} < 전국 {tpvd_total:.2f} → 낮음 → 전체 분석 진행")
    else:
        st.write("TPVD는 전국 대비 양호 → threshold 문제 가능성, 전체 분석은 계속 진행")
    ranger_inactive_disp = ranger_inactive if ranger_inactive else "-"
    st.write(f"Ranger 인액티브 기준일: {ranger_inactive_disp}일 (참고: 다수 도시 3일)")
    rb_actions.append(("Threshold(인액티브 기준일) 조정 검토", "amber"))
else:
    st.write(f"Creation {creation:.1f}% ≥ 전국 {creation_total:.1f}% → 정상")

# 2단계: 총 수행량
st.markdown('<div class="step-box"><b>2단계 · 총 RB 수행량 vs Creation 갭</b></div>', unsafe_allow_html=True)
if rb_dv_total_city is not None:
    st.write(f"레인저 {rb_dv_ranger:.1f} (전국 {rb_dv_ranger_nat:.1f}) / MTI {rb_dv_mti:.1f} (전국 {rb_dv_mti_nat:.1f})")

# 3단계 + 4단계: 레인저 RB량/effect
st.markdown('<div class="step-box"><b>3~4단계 · 레인저 RB량 · effect 확인</b></div>', unsafe_allow_html=True)
RB_RATE_LOW_THRESHOLD = 1.0  # 이 미만이면 표본부족으로 판단 (양부터 늘려야 함)
if rb_dv_ranger is not None:
    if rb_dv_ranger < RB_RATE_LOW_THRESHOLD:
        st.write(f"레인저 RB량 {rb_dv_ranger:.1f}로 매우 낮음 → effect 판단 불가, 양부터 확보 필요")
        rb_actions.append(("레인저 RB 인센티브 (활동량 확보 목적) + 다음 주기 effect 재확인", "green"))
    else:
        if effect_ranger is not None and effect_ranger_nat is not None:
            if effect_ranger >= effect_ranger_nat:
                st.write(f"레인저 RB effect {effect_ranger:.2f} ≥ 전국 {effect_ranger_nat:.2f} → 효과 있음")
                if rb_dv_ranger >= rb_dv_ranger_nat:
                    st.write("레인저 RB량도 전국 이상 → 유지")
                    rb_actions.append(("RB 유지 (이미 양호)", "gray"))
                else:
                    rb_actions.append(("레인저 RB 인센티브 후보 확정", "green"))
            else:
                st.write(f"레인저 RB effect {effect_ranger:.2f} < 전국 {effect_ranger_nat:.2f} → 효과 낮음")
                rb_actions.append(("RB 인센티브 대상 아님 — 위치/density 등 원인조사 필요", "red"))
        else:
            st.write("effect 데이터 없음")

# 5단계: LB 판단
st.markdown('<div class="step-box"><b>5단계 · LB 판단 (RDV 기준)</b></div>', unsafe_allow_html=True)
if rdv is not None:
    if rdv < RDV_THRESHOLD:
        st.write(f"RDV {rdv:.0f}% < 기준 {RDV_THRESHOLD:.0f}% → 미달")
        lb_actions.append(("레인저 LB 인센티브 검토", "green"))
    else:
        st.write(f"RDV {rdv:.0f}% ≥ 기준 {RDV_THRESHOLD:.0f}% → 충족")
        lb_actions.append(("LB 액션 불필요", "gray"))
else:
    st.write("RDV 데이터 없음")

st.markdown("---")

# ══════════════════════════════════════════════════════
# 최종 결론
# ══════════════════════════════════════════════════════
st.markdown('<div class="section-label">최종 Action</div>', unsafe_allow_html=True)
colrb, collb = st.columns(2)
with colrb:
    st.markdown("**RB**")
    if rb_actions:
        for text, level in rb_actions:
            action_box(text, level)
    else:
        action_box("판단 불가 (데이터 부족)", "gray")
with collb:
    st.markdown("**LB**")
    if lb_actions:
        for text, level in lb_actions:
            action_box(text, level)
    else:
        action_box("판단 불가 (데이터 부족)", "gray")

st.markdown("---")
st.caption(f"판단 기준: RDV {RDV_THRESHOLD:.0f}%, 레인저 RB량 최소 {RB_RATE_LOW_THRESHOLD} 미만 시 양부족으로 처리. 상단 코드에서 조정 가능.")
