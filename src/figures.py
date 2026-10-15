"""그림 6장: 300dpi 원본(outputs/figures)과 보고서 축소판(outputs/figures_report).

사용: uv run --frozen python src/figures.py
분석 표(outputs/tables)와 중간 산출(data/processed)만 읽는다. src/analysis.py를 먼저 실행한다.
축소판은 같은 그리기 함수를 report=True로 불러 만든다: 그림 크기 절반(세로는 1.08배 더),
글자 크기 축소, 그림 안 제목·각주 생략(보고서 캡션으로 옮김), 여백을 잘라 저장.
한글 글꼴은 KOREAN_FONT 환경변수로 바꿀 수 있다(기본 macOS Apple SD Gothic Neo).
"""

import json
import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from matplotlib.font_manager import FontProperties, fontManager
from matplotlib.patches import Patch

from analysis import CAR_COEFFICIENTS, breakeven, bus_ef, car_ef

ROOT = Path(__file__).resolve().parents[1]
TABLE_DIR = ROOT / "outputs/tables"
FULL_DIR = ROOT / "outputs/figures"
REPORT_DIR = ROOT / "outputs/figures_report"
FONT_PATH = os.environ.get("KOREAN_FONT", "/System/Library/Fonts/AppleSDGothicNeo.ttc")

BASE_STYLE = {
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
}
REPORT_STYLE = {
    "font.size": 8.5,
    "axes.titlesize": 9.5,
    "axes.labelsize": 8.5,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
}
REPORT_SCALE = 0.5  # 원본 12in 폭 → 6in. 보고서의 12cm 칸에 넣으면 인쇄 배율 약 0.8
REPORT_HEIGHT_STRETCH = 1.08

QUADRANT_COLORS = {
    "교통 우선 점검": "#D25436",
    "교통·시설 함께 점검": "#7953A2",
    "시설 원거리 점검": "#CEA64B",
    "낮 악화 미확인·차 근거리": "#9DAEB3",
}
ROUTE_COLORS = {"600": "#2F5D73", "610": "#C9822B", "620": "#6B8E23", "630": "#8C5A9E"}
RED = "#D25436"
BLUE = "#496E80"
GREEN = "#218B7C"
TEAL = "#168477"
GREY = "#53616A"
HATCH_GREY = "#525E66"  # 지도의 검열 빗금
SOURCE = "자료: KTDB 2023 교통접근성지표(의료·시각표 2024.3), MOIS 주민등록 2023.12 | 분석: src/"

NOTES = {
    "01_national_distribution": SOURCE
    + "analysis.py · 히스토그램은 >120 검열쌍 제외. 악화·개선 확인 수의 분모는 전국 3,530곳.\n"
    "시간 모형값이며 실제 환자 이동·진료 포기를 뜻하지 않음.",
    "02_province_comparison": SOURCE
    + "analysis.py · 분모: 시도 내 전체 읍면동. >120은 하한 120으로 비교하므로 확인 비율은 보수적 최소치.\n"
    "전북·충북의 차이는 작으며 전북 선택은 목적 표집이다. 시도명은 KTDB 2023 표기.",
    "03_local_maps": SOURCE
    + "figures.py · 지도: admdongkor ver20231231(통계청 경계 기반 민간 보정본), EPSG:5179. 지역 결합 243/243.\n"
    "분류 기준 Δ≥5분·낮 승용차 15분. >120은 120으로 표시. 낮 악화 미확인은 양호함을 뜻하지 않음.",
    "04_local_quadrants": SOURCE
    + "analysis.py · 점 크기: 65세 이상 주민등록인구. Δ≥5분·승용차<15분은 교통 우선 점검 후보.\n"
    "옥도·위도는 승용차>120분 검열. 오전·낮 모두 검열되어 Δ도 미식별이며 0은 표시값이다. 모든 243개 관측점 포함.\n"
    "임계값 3/5/10분 × 10/15/20분 민감도는 threshold_sensitivity.csv. 인과적 원인 확정 분류가 아님.",
    "05_case_profiles": SOURCE
    + "figures.py, analysis.py · 내과 진료 가능 병·의원. 시설수는 인구가중 평균이며 >10 검열.\n"
    "GTFS: KTDB 2024.3. 출발기록 최다 정류장의 같은 이름 정류장 2곳, 모든 노선. 방향·목적지 정보 없음.\n"
    "calendar는 모형용 고정값. 실제 2026 운행·정시성 관측값이 아니며, "
    "노선 계통 하나만 고르면 결론이 뒤집힘을 함께 공개.",
    "06_carbon_breakeven": "자료: KTDB View-T CO₂ 계수 표2(2021 승인계수 기반) | 코드: src/analysis.py · "
    "직접 CO₂ 비교, 실제 노선·차량군을 관측한 결과 아님.\n"
    "기준 가정: 대형 CNG 시내버스 30km/h, 중형 휘발유 승용차 40km/h, 오른쪽 공차·회차=영업거리의 20%.\n"
    "실제 감소 V*=L(1+h)EF버스/EF차, 대상 규모 D*=V*/r. r=0이면 유한한 손익분기 없음. "
    "신규 이동은 승용차 대체로 세지 않음.",
}


def read_table(name):
    return pd.read_csv(TABLE_DIR / f"{name}.csv", dtype={"HDCD": str})


def apply_style(report):
    if not Path(FONT_PATH).exists():
        raise RuntimeError("KOREAN_FONT에 한글 TTF/OTF/TTC 경로 지정")
    fontManager.addfont(FONT_PATH)
    plt.rcParams.update({"font.family": FontProperties(fname=FONT_PATH).get_name(), **BASE_STYLE})
    if report:
        plt.rcParams.update(REPORT_STYLE)


def figure_size(width, height, report):
    if report:
        return (width * REPORT_SCALE, height * REPORT_SCALE * REPORT_HEIGHT_STRETCH)
    return (width, height)


def add_title(fig, text, report):
    """원본에만 그림 제목을 넣는다. 축소판의 제목은 보고서 캡션이 맡는다."""
    if not report:
        fig.suptitle(text, x=0.03, ha="left", fontsize=17, y=0.96)


def finish(fig, name, report):
    if report:
        fig.savefig(REPORT_DIR / f"{name}.png", dpi=300, bbox_inches="tight", pad_inches=0.03)
    else:
        fig.text(0.03, 0.025, NOTES[name], ha="left", va="bottom", fontsize=8, color=GREY)
        fig.savefig(FULL_DIR / f"{name}.png", dpi=300)
    plt.close(fig)


def plot_national_distribution(metrics, report):
    """01 전국 읍면동의 낮-오전 시간차 분포(시설 3종)."""
    fig, axes = plt.subplots(1, 3, figsize=figure_size(12, 4.5, report))
    fig.subplots_adjust(left=0.06, right=0.98, bottom=0.23, top=0.78, wspace=0.3)
    for ax, facility in zip(axes, ["병·의원", "종합병원", "공공의료시설"]):
        rows = metrics[metrics.Faci_NM == facility]
        exact = rows[rows.exact_pair]
        ax.hist(exact.delta, bins=np.arange(-85, 91, 5), color=BLUE, edgecolor="white", lw=0.4)
        ax.axvline(5, color=RED, lw=1.3)
        ax.axvline(-5, color=TEAL, lw=1.3)
        ax.set(xlabel="낮 - 오전 접근시간 (분)", title=facility, xlim=(-85, 90))
        ax.set_yscale("symlog", linthresh=10)
        ax.set_ylim(0, 1e5)
        label = (
            f"악화 {rows.worse5_confirmed.sum():,}·개선 {rows.better5_confirmed.sum():,}곳 / {len(rows):,}\n"
            f"막대: 정확한 시간쌍 {len(exact):,}곳"
        )
        ax.text(
            0.03,
            0.97,
            label,
            transform=ax.transAxes,
            va="top",
            fontsize=8 if report else 9,
            bbox={"fc": "white", "ec": "none", "alpha": 0.85, "pad": 1},
        )
    axes[0].set_ylabel("읍면동 수 (10곳 이상 로그 눈금)")
    add_title(fig, "01  낮시간 악화는 전체의 평균보다 분포의 꼬리에 있다", report)
    finish(fig, "01_national_distribution", report)


def plot_province_comparison(provinces, selected_province, report):
    """02 시도별 악화·개선 확인 비율."""
    provinces = provinces.sort_values("worse5_pct")
    fig, ax = plt.subplots(figsize=figure_size(10, 6.8, report))
    fig.subplots_adjust(left=0.16, right=0.95, bottom=0.18, top=0.86)
    y = np.arange(len(provinces))
    colors = [RED if name == selected_province else BLUE for name in provinces.HDCD_SD_NM]
    ax.barh(y, provinces.worse5_pct, color=colors, height=0.35, label="5분 이상 악화 확인")
    ax.barh(y + 0.36, provinces.better5_pct, color=GREEN, height=0.35, label="5분 이상 개선 확인")
    ax.set_yticks(y + 0.18, provinces.HDCD_SD_NM)
    ax.set_xlabel("시도 내 전체 읍면동 대비 비율 (%)")
    ax.set_xlim(0, 35)
    for position, row in zip(y, provinces.itertuples()):
        label = f"{row.worse5_pct:.1f}% ({int(row.worse5_n)}/{int(row.n)})"
        ax.text(row.worse5_pct + 0.4, position, label, va="center", fontsize=9)
    ax.legend(loc="lower right", frameon=False)
    add_title(fig, "02  악화 지역과 개선 지역을 함께 공개한다", report)
    finish(fig, "02_province_comparison", report)


def plot_local_maps(local, report):
    """03 선택 지역의 시간차 지도와 사분면 지도."""
    province = local.HDCD_SD_NM.iloc[0]
    boundary = gpd.read_file(ROOT / "data/raw/boundary_20231231.geojson")
    boundary["HDCD"] = boundary.adm_cd.astype(str)
    areas = boundary.merge(
        local[["HDCD", "delta", "quadrant", "exact_pair"]], on="HDCD", how="inner", validate="one_to_one"
    ).to_crs(5179)
    assert len(areas) == len(local), (len(areas), len(local))

    fig, axes = plt.subplots(1, 2, figsize=figure_size(12, 6.2, report))
    fig.subplots_adjust(left=0.03, right=0.98, bottom=0.22, top=0.83, wspace=0.1)
    areas.plot(
        column="delta",
        ax=axes[0],
        cmap="RdBu_r",
        norm=TwoSlopeNorm(0, -70, 70),
        linewidth=0.15,
        edgecolor="white",
        legend=True,
        legend_kwds={"label": "낮 - 오전 (분)", "shrink": 0.65},
    )
    areas[~areas.exact_pair].plot(ax=axes[0], facecolor="none", edgecolor=HATCH_GREY, linewidth=0.2, hatch="///")
    censored_patch = Patch(facecolor="white", edgecolor=HATCH_GREY, hatch="///", label=">120 검열 포함")
    axes[0].legend(handles=[censored_patch], loc="lower left", frameon=False, fontsize=8)
    for quadrant, color in QUADRANT_COLORS.items():
        areas[areas.quadrant == quadrant].plot(ax=axes[1], color=color, edgecolor="white", linewidth=0.15)
    for ax in axes:
        ax.set_axis_off()
    axes[0].set_title("시간대 차이: 개선(파랑)과 악화(빨강)")
    axes[1].set_title("교통·시설의 우선 점검 유형")
    axes[1].legend(
        handles=[Patch(facecolor=v, label=k) for k, v in QUADRANT_COLORS.items()],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.34 if report else -0.15),
        ncol=2,
        frameon=False,
        fontsize=9,
    )
    add_title(fig, f"03  {province} {len(local)}개 읍면동: 같은 악화에도 점검할 원인은 다르다", report)
    finish(fig, "03_local_maps", report)


def draw_axis_break(ax, x):
    """축 단절 표시(사선 두 개)."""
    for y_pair in [(-0.012, 0.012), (0.988, 1.012)]:
        ax.plot([x - 0.015, x + 0.015], list(y_pair), transform=ax.transAxes, color=GREY, clip_on=False)


def plot_local_quadrants(local, report):
    """04 승용차 접근시간 × 낮 악화 산점도. 120분 초과 지역은 끊긴 오른쪽 축에 둔다."""
    fig, (ax, far) = plt.subplots(
        1, 2, figsize=figure_size(10, 6.4, report), sharey=True, gridspec_kw={"width_ratios": [5, 1]}
    )
    fig.subplots_adjust(left=0.1, right=0.98, bottom=0.25, top=0.83, wspace=0.06)
    # 축을 끊어 120분 초과 도서 지역도 숨기지 않는다.
    in_axes = local.car_day.between(0, 50) | local.car_day.between(115, 125)
    assert in_axes.all(), "단절 구간에 관측점 있음: 축 재설계 필요"
    for quadrant, color in QUADRANT_COLORS.items():
        rows = local[local.quadrant == quadrant]
        for target in [ax, far]:
            target.scatter(
                rows.car_day,
                rows.delta,
                s=15 + rows.elder65 / 25,
                c=color,
                alpha=0.7,
                edgecolors="white",
                lw=0.5,
                label=f"{quadrant} ({len(rows)}곳)",
            )
    ax.axvline(15, color=GREY, ls="--", lw=1)
    for target in [ax, far]:
        target.axhline(5, color=GREY, ls="--", lw=1)
    label_offsets = {"계화면": (-34, 4), "상교동": (6, 4)}
    for name in ["계화면", "동향면", "흥덕면", "상교동"]:
        row = local[local.HDCD_EMD_NM == name].iloc[0]
        ax.annotate(
            name,
            (row.car_day, row.delta),
            xytext=label_offsets.get(name, (6, 4)),
            textcoords="offset points",
            fontsize=8 if report else 10,
        )
    ax.set(ylabel="대중교통 낮 - 오전 접근시간 (분)", xlim=(0, 50), ylim=(-72, 75))
    far.set(xlim=(115, 125), xticks=[120], xticklabels=[">120"])
    far.tick_params(left=False, labelleft=False)
    far.spines["left"].set_visible(False)
    far.annotate(
        "옥도면·위도면\n시간차 미식별", (120, 0), xytext=(0, 22), textcoords="offset points", ha="center", fontsize=8
    )
    draw_axis_break(ax, 1)
    draw_axis_break(far, 0)
    x_label = "승용차 낮시간 접근시간 (분, 50~115 구간 축 단절)"
    fig.text(0.52, 0.09 if report else 0.16, x_label, ha="center", fontsize=11)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    add_title(fig, "04  교통만 먼저 볼 곳과 시설도 함께 볼 곳", report)
    finish(fig, "04_local_quadrants", report)


def plot_area_profile(time_ax, coverage_ax, row, clinic_times, show_labels):
    """사례 지역 하나: 시간대별 접근시간(위)과 허용시간별 접근가능인구 비율(아래)."""
    times = clinic_times[clinic_times.HDCD == row.HDCD]
    for mode, color, label in [("2_PT", RED, "대중교통/도보"), ("1_PC", BLUE, "승용차")]:
        by_zone = times[times.Mode == mode].set_index("Time_Zone").loc[["0_AllDay", "1_T0709", "2_T1214", "3_T1820"]]
        time_ax.plot(range(4), by_zone.minutes, "o-", c=color, label=label)
    time_ax.set_xticks(range(4), ["일평균", "오전", "낮", "저녁"])
    time_ax.set_ylim(0, 125)
    time_ax.set_title(f"{row.HDCD_SGG_NM} {row.HDCD_EMD_NM}\nΔ {row.delta:+.1f}분 · 고령인구 {int(row.elder65):,}명")
    if show_labels:
        time_ax.set_ylabel("가장 가까운 병·의원까지 (분)")
        time_ax.legend(frameon=False, fontsize=9)

    for zone, style, color, label in [("1_T0709", "--", BLUE, "오전"), ("2_T1214", "-", RED, "낮")]:
        values = [row[f"coverage_{t}_2_PT_{zone}"] for t in [15, 30, 45, 60]]
        coverage_ax.plot([15, 30, 45, 60], values, "o", ls=style, c=color, label=label)
    coverage_ax.set(ylim=(-3, 103), xlabel="접근 허용시간 (분)", xticks=[15, 30, 45, 60])
    coverage_ax.legend(frameon=False, fontsize=9)
    if show_labels:
        coverage_ax.set_ylabel("접근가능인구 비율 (%)")
    count = row["facilities_30_2_PT_2_T1214"]
    count_text = ">10" if row["facilities_30_censored_2_PT_2_T1214"] else f"{count:.2f}"
    coverage_ax.text(
        0.03,
        0.94,
        f"낮 30분 내 시설수 {count_text}개",
        transform=coverage_ax.transAxes,
        va="top",
        fontsize=9,
        bbox={"fc": "white", "ec": "none", "alpha": 0.85},
    )


def plot_stop_timetable(ax, report):
    """창북2 정류장(같은 이름 2곳)의 모든 노선 출발기록."""
    departures = pd.read_csv(ROOT / "data/processed/gtfs_selected_stop_all_routes.csv", dtype={"route_short_name": str})
    audit = json.loads((ROOT / "outputs/qa/gtfs_audit.json").read_text())
    selected = audit["selected"]
    stops = audit["selected_stop_all_routes"]
    ax.axvspan(7, 9, alpha=0.13, color=BLUE)
    ax.axvspan(12, 14, alpha=0.15, color=RED)
    for position, stop in enumerate(stops):
        stop_departures = departures[departures.stop_id == stop["stop_id"]]
        for route, rows in stop_departures.groupby("route_short_name"):
            ax.eventplot(
                rows.minute / 60,
                lineoffsets=1.5 - position,
                linelengths=0.6,
                color=ROUTE_COLORS.get(route, "#777777"),
                linewidth=1.2,
            )
    ax.legend(
        handles=[Patch(color=v, label=f"{k}번") for k, v in ROUTE_COLORS.items()],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.62 if report else -0.5),
        ncol=4,
        frameon=False,
        fontsize=8 if report else 9,
    )
    ax.set(
        xlim=(6, 20), ylim=(0.5, 2.45), yticks=[], xticks=range(6, 21), xlabel="2024.3 평일 모형 시각표 출발기록 (시각)"
    )
    ax.set_title(
        f"GTFS 보조 확인: 계화면 {selected['stop_name']} 정류장(같은 이름 2곳) 전체 노선 — "
        f"위 오전 {stops[0]['am0709']}·낮 {stops[0]['day1214']}건, "
        f"아래 오전 {stops[1]['am0709']}·낮 {stops[1]['day1214']}건",
        fontsize=10 if report else 11,
    )
    ax.text(
        0.01,
        0.97,
        f"노선 계통 하나({selected['route_short_name']}번 중 1개 ID)만 보면 "
        f"오전 {selected['am0709']}·낮 {selected['day1214']}건으로 반대로 보인다.",
        transform=ax.transAxes,
        fontsize=8 if report else 9,
        va="top",
    )


def plot_case_profiles(local, report):
    """05 사례 세 곳의 프로필과 GTFS 시각표."""
    fig = plt.figure(figsize=figure_size(12, 10, report))
    grid = fig.add_gridspec(3, 3, height_ratios=[1, 1, 0.65])
    axes = np.array([[fig.add_subplot(grid[i, j]) for j in range(3)] for i in range(2)])
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.16, top=0.88, hspace=0.95 if report else 0.6, wspace=0.24)
    times = pd.read_csv(ROOT / "data/processed/time_medical.csv.gz", dtype={"HDCD": str})
    clinic_times = times[(times.HDCD_Lev == 4) & (times.Faci_NM == "병·의원")]
    for column, name in enumerate(["계화면", "동향면", "흥덕면"]):
        row = local[local.HDCD_EMD_NM == name].iloc[0]
        plot_area_profile(axes[0, column], axes[1, column], row, clinic_times, show_labels=column == 0)
    plot_stop_timetable(fig.add_subplot(grid[2, :]), report)
    add_title(fig, "05  지역 프로필과 원자료 시각표를 함께 확인한다", report)
    finish(fig, "05_case_profiles", report)


def plot_carbon_breakeven(report):
    """06 버스 1회 증회의 탄소 상쇄 조건."""
    fig, axes = plt.subplots(1, 2, figsize=figure_size(12, 5.3, report))
    fig.subplots_adjust(left=0.08, right=0.97, bottom=0.27, top=0.8, wspace=0.28)
    service_km = np.linspace(1, 60, 100)
    for empty_ratio, style in [(0, ":"), (0.2, "-"), (0.5, "--")]:
        avoided = [breakeven(km, 1, empty_ratio)[0] for km in service_km]
        axes[0].plot(service_km, avoided, style, label=f"공차·회차 {empty_ratio:.0%}")
    # 모든 차급·연료와 속도 조합의 시나리오 범위(신뢰구간이 아님)
    ratios = [
        (1 + empty_ratio) * bus_ef(bus_speed) / car_ef(car_speed, kind)
        for kind in CAR_COEFFICIENTS
        for bus_speed in [20, 30, 40]
        for car_speed in [30, 40, 50]
        for empty_ratio in [0, 0.2, 0.5]
    ]
    axes[0].fill_between(
        service_km,
        service_km * min(ratios),
        service_km * max(ratios),
        alpha=0.14,
        color=BLUE,
        label="차종·속도 가정 전체 범위",
    )
    axes[0].set(
        xlabel="증회 1회 왕복 영업거리 L (km)", ylabel="상쇄에 필요한 실제 승용차 감소 (차량-km)", ylim=(0, 1100)
    )
    axes[0].legend(frameon=False, fontsize=9)

    rates = np.linspace(0.1, 1, 100)
    for km in [10, 20, 40]:
        axes[1].plot(rates * 100, [breakeven(km, rate)[1] for rate in rates], label=f"왕복 L={km}km")
    reference = breakeven(20, 1)[0]
    axes[1].axhline(reference, color=GREY, ls=":", label=f"L=20 실제 감소 필요 {reference:.1f} 차량-km")
    axes[1].set(
        xlabel="전환율 r: 대상 기존 차량-km 중 실제 취소 비율 (%)", ylabel="필요한 대상 기존 승용차 규모 (차량-km)"
    )
    axes[1].legend(frameon=False, fontsize=9)
    add_title(fig, "06  한 번 더 운행할 때 탄소가 상쇄되는 조건", report)
    finish(fig, "06_carbon_breakeven", report)


def draw_all(report):
    metrics = read_table("medical_all_metrics")
    local = read_table("local_clinic_all")
    plot_national_distribution(metrics, report)
    plot_province_comparison(read_table("province_summary"), local.HDCD_SD_NM.iloc[0], report)
    plot_local_maps(local, report)
    plot_local_quadrants(local, report)
    plot_case_profiles(local, report)
    plot_carbon_breakeven(report)


def main():
    plt.switch_backend("Agg")
    FULL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for report in [False, True]:
        with plt.rc_context():
            apply_style(report)
            draw_all(report)


if __name__ == "__main__":
    main()
