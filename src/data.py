"""원자료 내려받기·해시 확인(fetch)과 KTDB 의료시설 3종 정규화(prepare).

사용:
    uv run --frozen python src/data.py            # fetch 후 prepare
    uv run --frozen python src/data.py fetch [--refresh]
    uv run --frozen python src/data.py prepare

fetch는 data/sources.json에 고정한 SHA-256과 다른 파일을 받으면 멈춘다.
prepare는 `>120`(시간)·`>10`(시설수) 표시를 결측으로 지우지 않고 우측 검열 플래그로 남긴다.
"""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import openpyxl
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data/raw"
PROCESSED_DIR = ROOT / "data/processed"
QA_DIR = ROOT / "outputs/qa"

# 행정안전부 CSV는 페이지를 먼저 연 세션으로 공개 다운로드 양식을 POST해야 받을 수 있다.
MOIS_PAGE_URL = "https://jumin.mois.go.kr/ageStatMonth.do"

# KTDB 엑셀 파일 번호와 지표 종류
KTDB_INDICATORS = [("01", "time"), ("02", "coverage"), ("03", "facilities")]
OPPORTUNITY_MINUTES = [15, 30, 45, 60]
MEDICAL_FACILITY = "의료시설"
KEY_COLUMNS = ["HDCD", "Region", "HDCD_Lev", "Faci_CD", "Time_Zone", "Mode"]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- fetch


def download(session, spec):
    """sources.json 항목 하나를 받는다. POST 항목은 MOIS 다운로드 양식이다."""
    if spec.get("method") == "POST":
        session.get(MOIS_PAGE_URL, timeout=90).raise_for_status()
        response = session.post(spec["url"], data=spec["form"], headers={"Referer": MOIS_PAGE_URL}, timeout=180)
    else:
        response = session.get(spec["url"], timeout=180)
    response.raise_for_status()
    return response.content


def extract_ktdb_zip():
    """KTDB ZIP을 data/raw/ktdb/에 푼다. 파일명은 cp949로 저장되어 있다."""
    with ZipFile(RAW_DIR / "ktdb_2023.zip") as archive:
        for info in archive.infolist():
            name = info.filename
            try:
                name = name.encode("cp437").decode("cp949")
            except UnicodeError:
                pass
            target = RAW_DIR / "ktdb" / Path(name).name
            target.parent.mkdir(exist_ok=True)
            if not target.exists():
                target.write_bytes(archive.read(info))


def fetch(refresh=False):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    specs = json.loads((ROOT / "data/sources.json").read_text())["files"]
    session = requests.Session()
    for spec in specs:
        path = RAW_DIR / spec["local_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if spec.get("manual"):
            if not path.exists():
                raise FileNotFoundError(f"{path.name}: 신청 자료라 직접 받아 data/raw/에 둘 것 ({spec['procedure']})")
        elif refresh or not path.exists():
            temporary = path.with_suffix(path.suffix + ".download")
            temporary.write_bytes(download(session, spec))
            if sha256(temporary) != spec["sha256"]:
                raise RuntimeError(
                    f"{path.name}: 다운로드 해시 변경. .download를 검토한 뒤 sources.json을 명시적으로 갱신할 것"
                )
            temporary.replace(path)
        if sha256(path) != spec["sha256"]:
            raise RuntimeError(f"{path.name}: 해시 불일치")
        print(f"OK {path.name} {spec['sha256']}", flush=True)
    extract_ktdb_zip()
    # 자료목록 9번과 10번은 같은 ZIP이어야 한다.
    assert sha256(RAW_DIR / "ktdb_2023.zip") == sha256(RAW_DIR / "ktdb_2023_duplicate.zip")


# ---------------------------------------------------------------- prepare


def read_indicator_sheet(prefix, kind):
    """KTDB 지표 엑셀의 두 번째 시트에서 의료시설 행만 읽고 전체 시트의 검수 정보를 함께 돌려준다."""
    path = next((RAW_DIR / "ktdb").glob(prefix + "*.xlsx"))
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows_iter = workbook.worksheets[1].iter_rows(values_only=True)
    # 01은 다섯째 줄이 열 이름, 02·03은 그 아래 보조 머리글이 한 줄 더 있다.
    for _ in range(5):
        header = next(rows_iter)
    if prefix != "01":
        next(rows_iter)
    if kind == "time":
        value_columns = ["minutes"]
    else:
        value_columns = [f"{kind}_{t}" for t in OPPORTUNITY_MINUTES]
    columns = list(header[:15]) + value_columns

    medical_rows = []
    row_count = 0
    missing_cells = 0
    levels = set()
    facilities = set()
    for row in rows_iter:
        if row[0] is None:
            continue
        row_count += 1
        levels.add(row[3])
        facilities.add(row[12])
        missing_cells += sum(value in (None, "N/A") for value in row[15:])
        if row[11] == MEDICAL_FACILITY:
            medical_rows.append(row)
    workbook.close()

    audit = {
        "all_rows": row_count,
        "medical_rows": len(medical_rows),
        "missing_value_cells_all_facilities": missing_cells,
        "facilities": sorted(facilities),
        "levels": sorted(levels),
        "schema": columns,
    }
    return pd.DataFrame(medical_rows, columns=columns), audit


def normalize_indicator(table, kind):
    """`>` 표시를 검열 플래그로 분리하고 값의 범위·단조성을 검사한다."""
    value_columns = list(table.columns[15:])
    table["HDCD"] = table.HDCD.astype(str)
    table["HDCD_Lev"] = table.HDCD_Lev.astype(int)
    assert not table.duplicated(KEY_COLUMNS).any()
    for column in value_columns:
        if kind in ("time", "facilities"):
            table[column + "_censored"] = table[column].astype(str).str.startswith(">")
        table[column] = pd.to_numeric(table[column].astype(str).str.replace(">", "", regex=False), errors="coerce")

    values = table[value_columns]
    if kind == "time":
        assert table.minutes.between(0, 120).all()
    elif kind == "coverage":
        assert values.apply(lambda x: x.between(0, 100)).all().all()
    else:
        assert values.apply(lambda x: x.between(0, 10)).all().all()
    if kind != "time":
        # 15→60분 누적 기회는 줄어들 수 없다.
        assert (np.diff(values.values, axis=1) >= -1e-8).all()
    return table


def prepare():
    PROCESSED_DIR.mkdir(exist_ok=True)
    QA_DIR.mkdir(parents=True, exist_ok=True)
    source_audit = {}
    for prefix, kind in KTDB_INDICATORS:
        table, audit = read_indicator_sheet(prefix, kind)
        table = normalize_indicator(table, kind)
        table.to_csv(PROCESSED_DIR / f"{kind}_medical.csv.gz", index=False)
        source_audit[kind] = audit
        print(kind, audit, flush=True)
    (QA_DIR / "source_audit.json").write_text(json.dumps(source_audit, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", nargs="?", choices=["fetch", "prepare"], help="생략하면 둘 다 실행")
    parser.add_argument("--refresh", action="store_true", help="있는 파일도 다시 내려받기")
    args = parser.parse_args()
    if args.step in (None, "fetch"):
        fetch(refresh=args.refresh)
    if args.step in (None, "prepare"):
        prepare()


if __name__ == "__main__":
    main()
