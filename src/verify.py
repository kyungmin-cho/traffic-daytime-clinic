"""보고서 핵심 수치의 독립 집계와 단위·검열·결합 불변조건 검사 37개, 실행 기록.

사용: uv run --frozen python src/verify.py
출력: outputs/qa/verification.json(통과한 검사 목록), outputs/qa/run_manifest.json(실행환경·파일 SHA-256)
검사 하나라도 실패하면 AssertionError로 멈추고 아무것도 쓰지 않는다.
"""

import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from analysis import breakeven, bus_ef, car_ef

ROOT = Path(__file__).resolve().parents[1]
TABLE_DIR = ROOT / "outputs/tables"
QA_DIR = ROOT / "outputs/qa"
PACKAGES = ["pandas", "numpy", "openpyxl", "geopandas", "matplotlib", "scikit-learn", "scipy", "pillow", "requests"]


class Checks:
    def __init__(self):
        self.passed = []

    def __call__(self, name, condition):
        if not condition:
            raise AssertionError(name)
        self.passed.append(name)


def read_table(name):
    return pd.read_csv(TABLE_DIR / f"{name}.csv", dtype={"HDCD": str})


def check_accessibility(check):
    national = read_table("national_clinic_all")
    local = read_table("local_clinic_all")
    both_censored = national.pt_am_censored & national.pt_day_censored
    check(
        "전국3530·전북243 행정단위 중복 없음",
        len(national) == 3530 and national.HDCD.nunique() == 3530 and len(local) == 243 and local.HDCD.nunique() == 243,
    )
    check(
        "검열 시간쌍 분해: 정확3345 + 편측85 + 양측100",
        int(national.exact_pair.sum()) == 3345
        and int(both_censored.sum()) == 100
        and int((national.pt_am_censored ^ national.pt_day_censored).sum()) == 85,
    )
    # 확인된 악화는 낮 하한 - 오전 상한으로 판정한다. 둘 다 검열이면 판정할 수 없다.
    check(
        "검열 구간 판정438 악화244 개선",
        int((national.delta_lower >= 5).sum()) == 438 and int((national.delta_upper <= -5).sum()) == 244,
    )
    check(
        "양측검열 안정·개선·악화 단정 없음",
        not national.loc[both_censored, ["worse5_confirmed", "better5_confirmed"]].any().any(),
    )
    check(
        "정확쌍 387 악화·225 개선",
        int(((national.delta >= 5) & national.exact_pair).sum()) == 387
        and int(((national.delta <= -5) & national.exact_pair).sum()) == 225,
    )
    check(
        "전북 인구243개 전부 결합·65세인구는 총인구 이하",
        local.population.notna().all() and (local.elder65 <= local.population).all(),
    )
    unmatched = national[national.population.isna()]
    check(
        "전국 인구 미결합은 MOIS가 제외한 비거주5면만",
        len(unmatched) == 5 and set(unmatched.HDCD_EMD_NM) == {"근동면", "원동면", "원남면", "임남면", "수동면"},
    )
    quadrants = read_table("local_quadrants")
    check(
        "전북 사분면 수 합계243·고령인구 중복합산 없음",
        sum(local.groupby("quadrant").size()) == 243 and quadrants.elder65_residents.sum() == local.elder65.sum(),
    )
    local_worse = local.delta_lower >= 5
    check(
        "전북 악화67곳 고령거주70374명",
        int(local_worse.sum()) == 67 and local.loc[local_worse, "elder65"].sum() == 70374,
    )

    conservation = read_table("population_conservation_audit")
    branches = read_table("population_branch_rollup")
    check(
        "출장소62개 인구242000·고령38153 누락없이 합산",
        len(branches) == 62 and branches.branch_population.sum() == 242000 and branches.branch_elder65.sum() == 38153,
    )
    check(
        "17시도 총인구·65세이상인구 공식상위행과 각각일치",
        len(conservation) == 17
        and (conservation.population_joined == conservation.population_official).all()
        and (conservation.elder65_joined == conservation.elder65_official).all(),
    )
    check(
        "전국 인구51325329·고령9730411 보존",
        national.population.sum() == 51325329 and national.elder65.sum() == 9730411,
    )
    check("전북 인구1754757·고령423128 보존", local.population.sum() == 1754757 and local.elder65.sum() == 423128)

    for kind in ["coverage", "facilities"]:
        indicator = pd.read_csv(ROOT / f"data/processed/{kind}_medical.csv.gz")
        values = indicator[[f"{kind}_{t}" for t in [15, 30, 45, 60]]]
        check(kind + " 15→60분 누적기회 단조 증가", (np.diff(values.values, axis=1) >= -1e-8).all())


def check_carbon(check):
    # 상쇄선 위에서 버스 배출(g)과 줄어든 승용차 배출(g)이 같아야 한다.
    for service_km, rate, empty_ratio, bus_speed, car_speed in [
        (20, 0.25, 0.2, 30, 40),
        (40, 0.5, 0.5, 20, 50),
        (10, 1, 0, 40, 30),
    ]:
        avoided, eligible = breakeven(service_km, rate, empty_ratio, bus_speed, car_speed)
        check(
            f"탄소 질량수지 L{service_km}",
            np.isclose(eligible * rate * car_ef(car_speed), service_km * (1 + empty_ratio) * bus_ef(bus_speed))
            and np.isclose(avoided, eligible * rate),
        )
    check("전환0 손익분기 무한대", np.isinf(breakeven(20, 0)[1]))
    check("고속65.4 분기", np.isclose(car_ef(65.4), 0.0343 * 65.4**2 - 5.4212 * 65.4 + 339.8479))


def check_raw_hashes(check):
    for spec in json.loads((ROOT / "data/sources.json").read_text())["files"]:
        digest = hashlib.sha256((ROOT / "data/raw" / spec["local_path"]).read_bytes()).hexdigest()
        check("원자료 SHA256 " + spec["local_path"], digest == spec["sha256"])


def check_gtfs(check):
    audit = json.loads((QA_DIR / "gtfs_audit.json").read_text())
    selected = pd.read_csv(ROOT / "data/processed/gtfs_selected_stop.csv")
    check(
        "GTFS 21889865행 검사·계화면40정류장",
        audit["stop_times_rows_scanned"] == 21889865 and audit["gyehwa_stops_in_boundary"] == 40,
    )
    check(
        "GTFS 선택반례: 오전0 낮5 출발기록",
        len(selected) == 13
        and int(((selected.minute >= 420) & (selected.minute < 540)).sum()) == 0
        and int(((selected.minute >= 720) & (selected.minute < 840)).sum()) == 5,
    )
    stops = pd.read_csv(TABLE_DIR / "gtfs_gyehwa_stop_summary.csv", dtype=str)
    changbuk = stops[stops.stop_name == "창북2"]
    check(
        "GTFS 창북2 정류장 전체 노선: 오전14·낮5 / 오전14·낮3",
        sorted(zip(changbuk.am0709.astype(int), changbuk.day1214.astype(int))) == [(14, 3), (14, 5)],
    )
    check(
        "GTFS 계화면 통과 trip: 오전19·낮10",
        audit["area_distinct_trips"]
        == {"distinct_trips_total": 55, "distinct_trips_am0709": 19, "distinct_trips_day1214": 10},
    )


def check_figures(check):
    paths = sorted((ROOT / "outputs/figures").glob("*.png"))
    check("그림6개", len(paths) == 6)
    for path in paths:
        image = Image.open(path)
        dpi_ok = all(abs(x - 300) < 1 for x in image.info["dpi"])
        check(path.name + " 300dpi/가로2900px 이상", dpi_ok and image.width >= 2900)


def write_manifest(verification):
    """실행환경과 코드·설정·산출물 SHA-256을 기록한다(원자료 해시는 data/sources.json)."""
    files = (
        list((ROOT / "data").glob("*.csv"))
        + list((ROOT / "src").glob("*.py"))
        + list((ROOT / "outputs/tables").glob("*"))
        + list((ROOT / "outputs/figures").glob("*.png"))
        + list((ROOT / "outputs/figures_report").glob("*.png"))
        + [ROOT / name for name in ["pyproject.toml", "uv.lock", "Makefile", "README.md"]]
        + [ROOT / "data/sources.json", ROOT / "data/README.md"]
    )
    manifest = {
        "finished_utc": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
        "files": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)},
        "raw_integrity": "data/sources.json",
        "verification": verification,
        "reproduction_entry_point": "make all",
    }
    (QA_DIR / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))


def main():
    check = Checks()
    check_accessibility(check)
    check_carbon(check)
    check_raw_hashes(check)
    check_gtfs(check)
    check_figures(check)
    verification = {"passed": len(check.passed), "checks": check.passed}
    (QA_DIR / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2))
    write_manifest(verification)
    print(f"PASS {len(check.passed)} checks; run_manifest.json written")


if __name__ == "__main__":
    main()
