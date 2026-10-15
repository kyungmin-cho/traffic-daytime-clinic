"""낮시간 의료 접근성 분석: 오전·낮 시간쌍 비교, 인구 결합, 사분면·군집 진단,
GTFS 계화면 사례, 버스 1회 증회의 탄소 손익분기.

사용: uv run --frozen python src/analysis.py
입력: data/processed/*_medical.csv.gz(src/data.py prepare), data/raw의 경계·주민등록·GTFS
출력: outputs/tables/, outputs/qa/analysis_audit.json·gtfs_audit.json
"""

import json
import re
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import RobustScaler, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data/raw"
PROCESSED_DIR = ROOT / "data/processed"
TABLE_DIR = ROOT / "outputs/tables"
QA_DIR = ROOT / "outputs/qa"

# 판정 기준(분). 공식 기준이 아니라 분석상 선택이며 민감도 표에서 3/5/10, 10/15/20으로 바꿔 본다.
DELTA_THRESHOLD = 5
CAR_THRESHOLD = 15
TIME_CAP = 120  # KTDB 평균접근시간 상한. `>120`은 우측 검열값
TOLERANCE = 1e-8

CLINIC = "병·의원"
LOCAL_CANDIDATES = ["전라북도", "경상남도", "충청북도"]
EMD_META = ["HDCD", "HDCD_SD_NM", "HDCD_SGG_NM", "HDCD_EMD_NM", "Faci_NM"]
TIME_PAIR_COLUMNS = {"2_PT_1_T0709": "pt_am", "2_PT_2_T1214": "pt_day", "1_PC_2_T1214": "car_day"}

TRANSPORT_FIRST = "교통 우선 점검"
TRANSPORT_AND_FACILITY = "교통·시설 함께 점검"
FACILITY_FAR = "시설 원거리 점검"
NOT_WORSE_CAR_NEAR = "낮 악화 미확인·차 근거리"

CLUSTER_SEED = 20261015
CLUSTER_SUBSAMPLES = 30
CLUSTER_SUBSAMPLE_SHARE = 0.8

GTFS_PREFIX = "202403_GTFS_DataSet/"
GTFS_STOP_TIMES_ROWS = 21889865
GYEHWA_ADM_CD = "35580340"  # 부안군 계화면
# 원산·신수 출장소를 KTDB 통계지역으로 합산한 근거가 되는 정류장과 그 위치의 행정동 코드
BRANCH_EVIDENCE_STOPS = {"BS_KOTI_BOR_56611": "34030330", "SS_ACC2_39004380": "38060510"}
AM_WINDOW = (420, 540)  # 07:00~09:00 (자정부터 분)
DAY_WINDOW = (720, 840)  # 12:00~14:00

# KTDB View-T Co2quantity.pdf 표2(인쇄 3쪽/PDF 4쪽)의 Tier3 속도식, g/차량-km.
# 저속 y = a*v**b, 고속(65.4km/h 이상) y = c*v**2 + d*v + e. 값: (a, b, c, d, e)
CAR_COEFFICIENTS = {
    "경형 휘발유": (1065.1722, -0.5889, 0.0225, -3.3075, 212.8460),
    "경형 LPG": (989.9413, -0.5937, 0.0172, -2.3601, 167.3842),
    "소형 휘발유": (1256.0382, -0.5914, 0.0252, -3.7270, 245.9051),
    "소형 경유": (1037.3974, -0.5800, 0.0133, -1.3612, 129.4859),
    "소형 LPG": (1223.8670, -0.6046, 0.0188, -2.7902, 203.7804),
    "중형 휘발유": (1446.3728, -0.5793, 0.0343, -5.4212, 339.8479),
    "중형 경유": (1153.5685, -0.5507, 0.0226, -3.0857, 225.8804),
    "중형 LPG": (1513.8104, -0.6075, 0.0245, -3.6654, 257.7428),
    "중형 HEV": (211.9807, -0.1884, 0.0205, -2.8635, 190.4598),
    "대형 휘발유": (2022.6604, -0.6183, 0.0374, -5.9783, 385.8791),
    "대형 경유": (1149.2206, -0.5313, 0.0246, -3.3168, 239.5643),
    "대형 LPG": (1967.2719, -0.6616, 0.0295, -4.6079, 301.8248),
    "대형 HEV": (522.2199, -0.3855, 0.0164, -2.1338, 176.8101),
}
BUS_COEFFICIENTS = (5054.5880, -0.4910)  # 대형 CNG 시내버스 y = a*v**b
SPEED_BREAKPOINT = 65.4
CO2_SOURCE_URL = "https://viewt.ktdb.go.kr/cong/pdf/Co2quantity.pdf"


def save_table(table, name):
    table.to_csv(TABLE_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


# ================================================================ 시간쌍 요약


def summarize(group):
    """읍면동 묶음의 낮시간 시간과 낮-오전 차이(delta) 분포."""
    delta = group.delta
    return pd.Series(
        {
            "n": len(group),
            "median_day": group.pt_day.median(),
            "mean_day": group.pt_day.mean(),
            "median_delta": delta.median(),
            "mean_delta": delta.mean(),
            "q01": delta.quantile(0.01),
            "q05": delta.quantile(0.05),
            "q25": delta.quantile(0.25),
            "q75": delta.quantile(0.75),
            "q90": delta.quantile(0.9),
            "q95": delta.quantile(0.95),
            "q99": delta.quantile(0.99),
            "min_delta": delta.min(),
            "max_delta": delta.max(),
            "worse5_n": (delta >= 5).sum(),
            "worse5_pct": (delta >= 5).mean() * 100,
            "worse10_pct": (delta >= 10).mean() * 100,
            "better5_n": (delta <= -5).sum(),
            "better5_pct": (delta <= -5).mean() * 100,
            "day60_pct": (group.pt_day >= 60).mean() * 100,
            "cap_either_n": ((group.pt_day >= TIME_CAP - TOLERANCE) | (group.pt_am >= TIME_CAP - TOLERANCE)).sum(),
        }
    )


def summarize_by(table, key):
    return table.groupby(key).apply(summarize, include_groups=False).reset_index()


def normalize_name(name):
    """KTDB 2023과 MOIS 2023-12의 시도명·'제N동' 표기 차이를 맞춘다."""
    name = name.replace("강원특별자치도", "강원도").replace("전북특별자치도", "전라북도")
    return re.sub(r"제(?=\d+동)", "", name)


def classify_quadrant(table, delta_threshold=DELTA_THRESHOLD, car_threshold=CAR_THRESHOLD):
    """낮 악화(delta)와 낮 승용차 접근시간으로 점검 우선순위를 나눈다. 원인 판정이 아니다."""
    worse = table.delta >= delta_threshold
    car_far = table.car_day >= car_threshold
    return np.select(
        [worse & ~car_far, worse & car_far, ~worse & car_far],
        [TRANSPORT_FIRST, TRANSPORT_AND_FACILITY, FACILITY_FAR],
        default=NOT_WORSE_CAR_NEAR,
    )


def build_time_pairs(time):
    """읍면동(HDCD_Lev=4)×시설 단위로 수단·시간대별 시간을 펼치고 오전·낮 차이와 검열 구간을 만든다."""
    emd = time[time.HDCD_Lev == 4].copy()
    pairs = emd.pivot(index=EMD_META, columns=["Mode", "Time_Zone"], values="minutes")
    pairs.columns = [f"{mode}_{zone}" for mode, zone in pairs.columns]
    pairs = pairs.reset_index().rename(columns=TIME_PAIR_COLUMNS)

    flags = emd.pivot(index=EMD_META, columns=["Mode", "Time_Zone"], values="minutes_censored")
    flags.columns = [f"censored_{mode}_{zone}" for mode, zone in flags.columns]
    pairs = pairs.merge(flags.reset_index(), on=EMD_META, validate="one_to_one")
    pairs["pt_am_censored"] = pairs["censored_2_PT_1_T0709"]
    pairs["pt_day_censored"] = pairs["censored_2_PT_2_T1214"]
    pairs["exact_pair"] = ~(pairs.pt_am_censored | pairs.pt_day_censored)
    pairs["delta"] = pairs.pt_day - pairs.pt_am

    # `>120`은 실제값이 120 이상이라는 뜻이다. 오전이 검열되면 차이의 하한이, 낮이 검열되면 상한이 없다.
    pairs["delta_lower"] = np.where(pairs.pt_am_censored, -np.inf, pairs.delta)
    pairs["delta_upper"] = np.where(pairs.pt_day_censored, np.inf, pairs.delta)
    pairs["worse5_confirmed"] = pairs.delta_lower >= DELTA_THRESHOLD
    pairs["better5_confirmed"] = pairs.delta_upper <= -DELTA_THRESHOLD
    pairs["full_name"] = pairs[EMD_META[1:4]].agg(" ".join, axis=1)
    assert len(pairs) == 3530 * 3 and pairs[["pt_am", "pt_day", "car_day"]].notna().all().all()
    return pairs


def attach_opportunities(pairs):
    """접근가능인구비율(coverage)과 접근가능시설수(facilities)를 같은 읍면동·시설 행에 붙인다."""
    for kind in ["coverage", "facilities"]:
        indicator = pd.read_csv(PROCESSED_DIR / f"{kind}_medical.csv.gz", dtype={"HDCD": str})
        indicator = indicator[indicator.HDCD_Lev == 4]
        value_columns = [c for c in indicator if c.startswith(kind + "_")]
        wide = indicator.pivot(index=["HDCD", "Faci_NM"], columns=["Mode", "Time_Zone"], values=value_columns)
        wide.columns = [f"{column}_{mode}_{zone}" for column, mode, zone in wide.columns]
        pairs = pairs.merge(wide.reset_index(), on=["HDCD", "Faci_NM"], validate="one_to_one")
    return pairs


# ================================================================ 인구 결합


def load_code_crosswalk():
    """KTDB는 통계청 8자리, MOIS는 10자리 코드다. 2023-12-31 경계 속성으로 두 코드를 잇는다."""
    with open(RAW_DIR / "boundary_20231231.geojson") as file:
        boundary = json.load(file)
    crosswalk = pd.DataFrame([feature["properties"] for feature in boundary["features"]])
    crosswalk = crosswalk[["adm_cd", "adm_cd2", "adm_nm"]]
    assert not crosswalk.adm_cd.duplicated().any() and not crosswalk.adm_cd2.duplicated().any()
    return crosswalk


def load_population():
    """MOIS 2023-12 5세 단위 주민등록인구. 총인구와 65세 이상을 만든다."""
    population = pd.read_csv(RAW_DIR / "mois_202312_age5.csv", encoding="cp949", dtype=str)
    population["mois_code"] = population["행정구역"].str.extract(r"\((\d{10})\)")[0]
    population["pop_name"] = (
        population["행정구역"]
        .str.replace(r"\s*\(\d+\)", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    count_columns = population.columns[1:24]
    for column in count_columns:
        population[column] = pd.to_numeric(population[column].str.replace(",", "", regex=False), errors="raise")
    # 첫 열은 총인구, 셋째 열부터 연령대별 인구
    assert (population[count_columns[2:]].sum(axis=1) == population[count_columns[0]]).all()
    elder_columns = [c for c in count_columns if re.search(r"_(65|70|75|80|85|90|95|100)", c)]
    population["population"] = population[count_columns[0]]
    population["elder65"] = population[elder_columns].sum(axis=1)
    population["norm_name"] = population.pop_name.map(normalize_name)
    return population


def attach_population(pairs, crosswalk, population):
    """코드 교차표로 인구를 붙이고, 경계 파일에 없는 코드는 전체 이름이 정확히 같을 때만 보완한다."""
    population_columns = ["mois_code", "pop_name", "population", "elder65"]
    pairs = pairs.merge(crosswalk, left_on="HDCD", right_on="adm_cd", how="left", validate="many_to_one")
    pairs = pairs.merge(
        population[population_columns], left_on="adm_cd2", right_on="mois_code", how="left", validate="many_to_one"
    )
    pairs["join_method"] = np.where(pairs.population.notna(), "20231231_boundary_code", "unmatched")
    for index in pairs.index[pairs.population.isna()]:
        hits = population[population.norm_name == normalize_name(pairs.loc[index, "full_name"])]
        if len(hits) == 1:
            for column in population_columns:
                pairs.loc[index, column] = hits.iloc[0][column]
            pairs.loc[index, "join_method"] = "exact_full_name"
    return pairs


def find_branch_parents(pairs, population):
    """MOIS 출장소 62곳의 부모 읍면동을 찾는다.

    출장소 인구는 본소와 따로 집계되므로 본소 코드만 결합하면 전국 242,000명이 빠진다.
    이름에 부모 읍·면이 있으면 그것을, 없으면 data/branch_parent_overrides.csv의 근거를 쓴다.
    """
    overrides = pd.read_csv(
        ROOT / "data/branch_parent_overrides.csv",
        dtype={"branch_code": str, "parent_code": str, "ktdb_hdcd": str},
    )
    override_by_code = overrides.set_index("branch_code").to_dict("index")
    emd_population = population[~population.mois_code.str.endswith("00000")].copy()
    joined_codes = set(pairs.mois_code.dropna())

    rows = []
    for branch in emd_population[emd_population.pop_name.str.endswith("출장소")].itertuples():
        if branch.mois_code in override_by_code:
            override = override_by_code[branch.mois_code]
            parent_code = override["parent_code"]
            method = "documented_override"
            evidence = override["evidence_url"]
        else:
            match = re.match(r"^(.*[읍면])[^읍면]*출장소$", branch.pop_name)
            if match is None:
                raise ValueError(f"출장소 부모 식별 실패: {branch.pop_name}")
            parent = emd_population[emd_population.norm_name == normalize_name(match[1])]
            if len(parent) != 1:
                raise ValueError(f"출장소 부모 중복/누락: {branch.pop_name}")
            parent_code = parent.iloc[0].mois_code
            method = "explicit_parent_in_MOIS_name"
            evidence = "mois_202312_age5.csv 행정구역 이름"
        assert parent_code in joined_codes, (branch.pop_name, parent_code)
        rows.append(
            {
                "branch_code": branch.mois_code,
                "branch_name": branch.pop_name,
                "parent_code": parent_code,
                "branch_population": branch.population,
                "branch_elder65": branch.elder65,
                "method": method,
                "evidence": evidence,
            }
        )
    branches = pd.DataFrame(rows)
    assert len(branches) == 62 and not branches.branch_code.duplicated().any()
    return branches


def add_branch_population(pairs, branches):
    totals = branches.groupby("parent_code")[["branch_population", "branch_elder65"]].sum().reset_index()
    pairs = pairs.merge(totals, left_on="mois_code", right_on="parent_code", how="left", validate="many_to_one")
    pairs["population_base"] = pairs.population
    pairs["elder65_base"] = pairs.elder65
    pairs["branch_population"] = pairs.branch_population.fillna(0)
    pairs["branch_elder65"] = pairs.branch_elder65.fillna(0)
    pairs["population"] = pairs.population + pairs.branch_population
    pairs["elder65"] = pairs.elder65 + pairs.branch_elder65
    return pairs


def audit_population_conservation(pairs, population):
    """결합 인구의 시도 합계가 MOIS 17개 시도 공식 행과 같아야 한다(중복 합산·누락 금지)."""
    joined = pairs[pairs.Faci_NM == CLINIC].copy()
    joined["norm_province"] = joined.HDCD_SD_NM.map(normalize_name)
    sums = joined.groupby("norm_province")[["population", "elder65"]].sum()
    official = population[population.mois_code.str.endswith("00000000")].set_index("norm_name")
    conservation = sums.join(official[["population", "elder65"]], lsuffix="_joined", rsuffix="_official")
    conservation = conservation.reset_index()
    assert (conservation.population_joined == conservation.population_official).all()
    assert (conservation.elder65_joined == conservation.elder65_official).all()
    return conservation


def add_coverage_loss(pairs):
    """30분 접근가능인구비율의 오전→낮 손실과, 65세 이상 인구에 곱한 대리값(연령 균등 가정)."""
    pairs["elder_share"] = pairs.elder65 / pairs.population
    pairs["cov30_am"] = pairs["coverage_30_2_PT_1_T0709"]
    pairs["cov30_day"] = pairs["coverage_30_2_PT_2_T1214"]
    pairs["cov30_loss_pp"] = pairs.cov30_am - pairs.cov30_day
    pairs["elder_cov30_net_loss_proxy"] = pairs.elder65 * pairs.cov30_loss_pp / 100
    pairs["elder_cov30_positive_loss_proxy"] = pairs.elder65 * pairs.cov30_loss_pp.clip(lower=0) / 100
    pairs["quadrant"] = classify_quadrant(pairs)
    return pairs


# ================================================================ 전국·지역 결과


def tail_composition(clinic):
    """악화 지역(delta≥5)이 면·군에 얼마나 몰려 있는가."""
    tail = clinic[clinic.delta >= 5]
    is_myeon = tail.HDCD_EMD_NM.str.endswith("면")
    is_gun = tail.HDCD_SGG_NM.str.endswith("군")
    rows = []
    for category, mask in [("면", is_myeon), ("군", is_gun), ("군의 면", is_gun & is_myeon)]:
        rows.append(
            {"category": category, "n": int(mask.sum()), "denominator": len(tail), "percent": mask.mean() * 100}
        )
    return pd.DataFrame(rows)


def threshold_sensitivity(clinic, local, selected):
    """기준(Δ 3/5/10분 × 승용차 10/15/20분)과 120분 검열 제외 여부를 바꿔 교통 우선 후보를 다시 센다."""
    rows = []
    for scope, group in [("전국", clinic), (selected, local)]:
        baseline = set(group.loc[(group.delta >= 5) & (group.car_day < 15), "HDCD"])
        for exclude_cap in [False, True]:
            if exclude_cap:
                uncapped = (group.pt_am < TIME_CAP - TOLERANCE) & (group.pt_day < TIME_CAP - TOLERANCE)
                subset = group[uncapped]
            else:
                subset = group
            for delta_threshold in [3, 5, 10]:
                for car_threshold in [10, 15, 20]:
                    candidates = set(
                        subset.loc[(subset.delta >= delta_threshold) & (subset.car_day < car_threshold), "HDCD"]
                    )
                    union = candidates | baseline
                    rows.append(
                        {
                            "scope": scope,
                            "exclude_cap": exclude_cap,
                            "delta_threshold": delta_threshold,
                            "car_threshold": car_threshold,
                            "n": len(subset),
                            "transport_n": len(candidates),
                            "candidate_jaccard": len(candidates & baseline) / len(union) if union else 1,
                            "worse_pct": (subset.delta >= delta_threshold).mean() * 100,
                        }
                    )
    return pd.DataFrame(rows)


def quadrant_table(local):
    rows = []
    for name, group in local.groupby("quadrant"):
        rows.append(
            {
                "quadrant": name,
                "n": len(group),
                "population_matched_n": int(group.population.notna().sum()),
                "elder65_residents": group.elder65.sum(min_count=1),
                "median_delta": group.delta.median(),
                "median_car": group.car_day.median(),
                "median_pt_day": group.pt_day.median(),
                "median_cov30_day": group.cov30_day.median(),
                "elder_cov30_net_loss_proxy": group.elder_cov30_net_loss_proxy.sum(min_count=1),
                "elder_cov30_positive_loss_proxy": group.elder_cov30_positive_loss_proxy.sum(min_count=1),
            }
        )
    return pd.DataFrame(rows)


def ward_labels(features, k):
    return AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(features)


def cluster_diagnostics(local):
    """Ward 군집을 사분면의 대안으로 비교한다.

    외부 정답이 없으므로 군집이 정책상 더 낫다고 판정하지 않는다(adopted=False).
    """
    features = [c for c in local if re.match(r"[12]_[A-Z]+_", c)] + ["pt_am", "pt_day", "car_day"]
    assert len(features) == 8, features
    values = local[features].values
    baseline = set(local.loc[(local.delta >= 5) & (local.car_day < 15), "HDCD"])
    assignments = local[["HDCD", "full_name", "quadrant"]].copy()
    rng = np.random.default_rng(CLUSTER_SEED)
    sample_size = int(CLUSTER_SUBSAMPLE_SHARE * len(values))

    results = []
    for scaling, scaler in [("standard", StandardScaler()), ("robust", RobustScaler())]:
        scaled = scaler.fit_transform(values)
        for k in [3, 4, 5]:
            labels = ward_labels(scaled, k)
            # 낮 악화 중위값 ≥5분이고 승용차 중위값 <15분인 군집을 교통 우선 후보로 본다.
            candidates = []
            for label in np.unique(labels):
                members = local.iloc[np.where(labels == label)[0]]
                if members.delta.median() >= 5 and members.car_day.median() < 15:
                    candidates.extend(members.HDCD)
            candidates = set(candidates)
            union = candidates | baseline
            overlap = len(candidates & baseline) / len(union) if union else 1

            stability = []
            for _ in range(CLUSTER_SUBSAMPLES):
                index = np.sort(rng.choice(len(values), sample_size, replace=False))
                rescaled = scaler.__class__().fit_transform(values[index])
                stability.append(adjusted_rand_score(labels[index], ward_labels(rescaled, k)))

            results.append(
                {
                    "scaling": scaling,
                    "k": k,
                    "silhouette": silhouette_score(scaled, labels),
                    "ari_vs_quadrants": adjusted_rand_score(local.quadrant, labels),
                    "candidate_n": len(candidates),
                    "baseline_n": len(baseline),
                    "candidate_jaccard": overlap,
                    "subsample_ari_median": np.median(stability),
                    "subsample_ari_min": np.min(stability),
                    "adopted": False,
                }
            )
            assignments[f"{scaling}_k{k}"] = labels
    return pd.DataFrame(results), assignments


def run_accessibility():
    time = pd.read_csv(PROCESSED_DIR / "time_medical.csv.gz", dtype={"HDCD": str})
    pairs = build_time_pairs(time)
    save_table(summarize_by(pairs, "Faci_NM"), "national_summary")
    # 공식 전국 집계(인구가중)는 읍면동 단순분포와 따로 공개한다.
    save_table(time[(time.HDCD_Lev == 0) & (time.Region_NM == "전체")], "official_national_aggregates")

    pairs = attach_opportunities(pairs)
    population = load_population()
    pairs = attach_population(pairs, load_code_crosswalk(), population)
    branches = find_branch_parents(pairs, population)
    save_table(branches, "population_branch_rollup")
    pairs = add_branch_population(pairs, branches)
    save_table(audit_population_conservation(pairs, population), "population_conservation_audit")
    crosswalk_columns = [
        "HDCD",
        "full_name",
        "adm_cd2",
        "mois_code",
        "pop_name",
        "population_base",
        "elder65_base",
        "branch_population",
        "branch_elder65",
        "population",
        "elder65",
        "join_method",
    ]
    save_table(pairs[crosswalk_columns].drop_duplicates(), "population_crosswalk_audit")
    pairs = add_coverage_loss(pairs)

    clinic = pairs[pairs.Faci_NM == CLINIC].copy()
    provinces = summarize_by(clinic, "HDCD_SD_NM").sort_values("worse5_pct", ascending=False)
    save_table(provinces, "province_summary")
    save_table(summarize_by(pairs[pairs.exact_pair], "Faci_NM"), "national_exact_pairs_summary")
    # 후보 세 도 중 악화 비율이 가장 높은 곳을 분석 지역으로 고른다(목적 표집).
    candidates = provinces[provinces.HDCD_SD_NM.isin(LOCAL_CANDIDATES)].copy()
    save_table(candidates, "province_selection")
    selected = candidates.iloc[0].HDCD_SD_NM
    local = clinic[clinic.HDCD_SD_NM == selected].copy()

    save_table(clinic.sort_values("delta", ascending=False), "national_clinic_all")
    save_table(clinic[clinic.delta <= -5].sort_values("delta"), "improved_areas")
    save_table(clinic[clinic.delta >= 5].sort_values("delta", ascending=False), "worsened_areas")
    save_table(tail_composition(clinic), "tail_composition")
    save_table(threshold_sensitivity(clinic, local, selected), "threshold_sensitivity")
    save_table(quadrant_table(local), "local_quadrants")
    save_table(local, "local_clinic_all")
    diagnostics, assignments = cluster_diagnostics(local)
    save_table(diagnostics, "cluster_diagnostics")
    save_table(assignments, "cluster_assignments")
    save_table(pairs, "medical_all_metrics")

    audit = {
        "ktdb_emd_n": clinic.HDCD.nunique(),
        "matched_n": int(clinic.population.notna().sum()),
        "unmatched": clinic.loc[clinic.population.isna(), ["HDCD", "full_name"]].to_dict("records"),
        "selected_province": selected,
        "local_n": len(local),
        "local_matched_n": int(local.population.notna().sum()),
        "national_worse_elder_residents": float(clinic.loc[clinic.delta >= 5, "elder65"].sum()),
        "local_worse_elder_residents": float(local.loc[local.delta >= 5, "elder65"].sum()),
    }
    write_json(QA_DIR / "analysis_audit.json", audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


# ================================================================ GTFS 계화면 사례
# KTDB 2024-03 GTFS로 계화면 정류장 시각표 공급을 보조 확인한다.
# KTDB의 route_type=0은 시내·농어촌버스다(표준 GTFS의 0과 다름).
# calendar의 전요일 1은 모형용 고정값이라 실제 매일 운행으로 해석하지 않는다.


def clock_minutes(text):
    hours, minutes, seconds = text.split(":")
    return int(hours) * 60 + int(minutes) + int(seconds) / 60


def in_window(minutes, window):
    return (minutes >= window[0]) & (minutes < window[1])


def check_branch_evidence(stops, boundary):
    """예외 출장소 두 곳의 지리 통합 근거: 근거 정류장이 KTDB 부모 읍면동 경계 안에 있다."""
    evidence = gpd.sjoin(
        stops[stops.stop_id.isin(BRANCH_EVIDENCE_STOPS)],
        boundary[["adm_cd", "adm_nm", "geometry"]],
        how="left",
        predicate="intersects",
    )
    assert len(evidence) == 2
    assert all(str(row.adm_cd) == BRANCH_EVIDENCE_STOPS[row.stop_id] for row in evidence.itertuples())
    columns = ["stop_id", "stop_name", "stop_lat", "stop_lon", "adm_cd", "adm_nm"]
    evidence[columns].to_csv(TABLE_DIR / "branch_geographic_evidence.csv", index=False, encoding="utf-8-sig")


def scan_stop_times(archive, stop_ids):
    """약 1.6GB stop_times를 압축 스트림으로 읽어 해당 정류장의 승차 가능 기록만 모은다."""
    parts = []
    total = 0
    reader = pd.read_csv(archive.open(GTFS_PREFIX + "stop_times.txt"), dtype=str, chunksize=500000)
    for chunk in reader:
        total += len(chunk)
        hit = chunk[chunk.stop_id.isin(stop_ids) & (chunk.pickup_type == "0")]
        if len(hit):
            parts.append(hit.copy())
    assert total == GTFS_STOP_TIMES_ROWS, total
    if not parts:
        raise RuntimeError("계화면 승차가능 stop_times 없음")
    return pd.concat(parts, ignore_index=True), total


def summarize_stop_routes(departures):
    rows = []
    for (stop_id, route_id), group in departures.groupby(["stop_id", "route_id"]):
        minutes = group.minute.sort_values().values
        ordered = group.sort_values("minute")
        rows.append(
            {
                "stop_id": stop_id,
                "route_id": route_id,
                "stop_name": group.stop_name.iloc[0],
                "route_short_name": group.route_short_name.iloc[0],
                "daily_departures": len(group),
                "am0709": int(in_window(group.minute, AM_WINDOW).sum()),
                "day1214": int(in_window(group.minute, DAY_WINDOW).sum()),
                "first_departure": ordered.departure_time.iloc[0],
                "last_departure": ordered.departure_time.iloc[-1],
                "max_gap_minutes": float(pd.Series(minutes).diff().max()) if len(minutes) > 1 else None,
            }
        )
    summary = pd.DataFrame(rows)
    return summary.sort_values(["daily_departures", "stop_id", "route_id"], ascending=[False, True, True])


def route_order(name):
    return (len(name), name)


def run_gtfs_case():
    path = RAW_DIR / "gtfs_2024.zip"
    if not path.exists():
        raise FileNotFoundError("GTFS 원자료를 먼저 받아야 함; 집계 접근성 본체는 이 파일에 의존하지 않음")
    boundary = gpd.read_file(RAW_DIR / "boundary_20231231.geojson")
    gyehwa = boundary.loc[boundary.adm_cd.astype(str) == GYEHWA_ADM_CD].geometry.iloc[0]
    archive = ZipFile(path)

    stops = pd.read_csv(archive.open(GTFS_PREFIX + "stops.txt"), dtype={"stop_id": str})
    stops = gpd.GeoDataFrame(stops, geometry=gpd.points_from_xy(stops.stop_lon, stops.stop_lat), crs=4326)
    local_stops = stops[stops.geometry.covered_by(gyehwa)].copy()
    stop_ids = set(local_stops.stop_id)
    assert stop_ids, "계화면 정류장 없음"
    check_branch_evidence(stops, boundary)

    trips = pd.read_csv(archive.open(GTFS_PREFIX + "trips.txt"), dtype=str)
    routes = pd.read_csv(archive.open(GTFS_PREFIX + "routes.txt"), dtype=str)
    bus_routes = routes[routes.route_type == "0"]
    trips = trips[trips.route_id.isin(bus_routes.route_id)]

    stop_times, rows_scanned = scan_stop_times(archive, stop_ids)
    departures = (
        stop_times.merge(trips, on="trip_id", how="inner", validate="many_to_one")
        .merge(local_stops.drop(columns="geometry"), on="stop_id", validate="many_to_one")
        .merge(bus_routes[["route_id", "route_short_name"]], on="route_id", validate="many_to_one")
    )
    departures["minute"] = departures.departure_time.map(clock_minutes)
    departures = departures.drop_duplicates(["stop_id", "route_id", "trip_id", "departure_time"])
    departures.to_csv(PROCESSED_DIR / "gtfs_gyehwa_departures.csv.gz", index=False)

    route_summary = summarize_stop_routes(departures)
    route_summary.to_csv(TABLE_DIR / "gtfs_gyehwa_stop_route_summary.csv", index=False, encoding="utf-8-sig")

    # 출발기록이 가장 많은 정류장·노선을 고른다. 큰 공백을 골라내지 않는 기술적 표집이다.
    chosen = route_summary.iloc[0]
    selected = departures[(departures.stop_id == chosen.stop_id) & (departures.route_id == chosen.route_id)]
    selected = selected.sort_values("minute")
    selected.to_csv(PROCESSED_DIR / "gtfs_selected_stop.csv", index=False)
    hourly = [
        {"hour": hour, "departures": int(((selected.minute >= 60 * hour) & (selected.minute < 60 * (hour + 1))).sum())}
        for hour in range(30)
    ]
    pd.DataFrame(hourly).to_csv(TABLE_DIR / "gtfs_selected_hourly.csv", index=False, encoding="utf-8-sig")

    # 노선 계통 하나만 보면 같은 정류장의 다른 계통(같은 600번의 다른 route_id, 610 등)이 빠진다.
    # 정류장 단위(모든 노선)와 계화면 전체(서로 다른 trip 수)로 다시 센다.
    departures["am"] = in_window(departures.minute, AM_WINDOW)
    departures["day"] = in_window(departures.minute, DAY_WINDOW)
    stop_summary = (
        departures.groupby(["stop_id", "stop_name"])
        .agg(
            daily_departures=("trip_id", "size"),
            routes=("route_short_name", lambda names: "·".join(sorted(set(names), key=route_order))),
            am0709=("am", "sum"),
            day1214=("day", "sum"),
        )
        .reset_index()
        .sort_values(["daily_departures", "stop_id"], ascending=[False, True])
    )
    stop_summary.to_csv(TABLE_DIR / "gtfs_gyehwa_stop_summary.csv", index=False, encoding="utf-8-sig")
    same_name = departures[departures.stop_name == chosen.stop_name].sort_values("minute")
    same_name.drop(columns=["am", "day"]).to_csv(PROCESSED_DIR / "gtfs_selected_stop_all_routes.csv", index=False)

    area_trips = {
        "distinct_trips_total": int(departures.trip_id.nunique()),
        "distinct_trips_am0709": int(departures[departures.am].trip_id.nunique()),
        "distinct_trips_day1214": int(departures[departures.day].trip_id.nunique()),
    }
    chosen_stop_columns = ["stop_id", "routes", "daily_departures", "am0709", "day1214"]
    chosen_stops = stop_summary[stop_summary.stop_name == chosen.stop_name][chosen_stop_columns].to_dict("records")
    audit = {
        "download_label": "대중교통GTFS(2024년 기준)",
        "reference": "2024년3월 평일, 내부202403폴더와설명서10쪽 확인",
        "stop_times_rows_scanned": rows_scanned,
        "gyehwa_stops_in_boundary": len(local_stops),
        "gyehwa_boardable_bus_departure_rows": len(departures),
        "stop_route_pairs": len(route_summary),
        "selection_rule": "daily_departures 최대, 동률은 stop_id·route_id 오름차순",
        "selected": chosen.to_dict(),
        "selection_effect": (
            "선택 계통(600 중 한 route_id)만 보면 오전0·낮5지만, "
            "같은 이름 정류장의 모든 노선을 세면 아래 selected_stop_all_routes처럼 오전이 더 많다"
        ),
        "selected_stop_all_routes": chosen_stops,
        "area_distinct_trips": area_trips,
        "limitations": [
            (
                "route_id는 노선번호와 1:1이 아님(600번이 여러 route_id로 나뉨); "
                "노선 계통 하나로 정류장 공급을 대표하지 않음"
            ),
            "방향·목적지 필드 없음; 실제 방향별 배차 간격으로 단정하지 않음",
            "calendar 전요일1과2017~2030은 설명서상고정값; 실제일요일운행증거아님",
            "2024년3월 평일 모델용 시각표,2026현행운행/정시성 관측아님",
            "의료기관까지의 연결·환승·통행거리·차종미확인; 증회효과 재계산 안 함",
        ],
    }
    write_json(QA_DIR / "gtfs_audit.json", audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


# ================================================================ 탄소 손익분기
# 직접(배기관) CO2만 비교한다. 승객-km나 CO2eq로 바꾸지 않는다.


def car_ef(speed, kind="중형 휘발유"):
    """승용차 배출계수(g/차량-km)."""
    if np.any(np.asarray(speed) <= 0):
        raise ValueError("속도는 양수여야 함")
    a, b, c, d, e = CAR_COEFFICIENTS[kind]
    v = np.asarray(speed)
    return np.where(v < SPEED_BREAKPOINT, a * v**b, c * v * v + d * v + e)


def bus_ef(speed):
    """대형 CNG 시내버스 배출계수(g/차량-km)."""
    if np.any(np.asarray(speed) <= 0):
        raise ValueError("속도는 양수여야 함")
    a, b = BUS_COEFFICIENTS
    return a * np.asarray(speed) ** b


def breakeven(service_km, conversion_rate, empty_ratio=0.2, bus_speed=30, car_speed=40, car="중형 휘발유"):
    """버스 1회 증회(왕복 영업거리 L, 공차·회차 비율 h)의 배출을 상쇄하는 승용차 운행 규모.

    돌려주는 값: (실제로 취소되어야 하는 승용차 차량-km V*, 전환율 r일 때 필요한 대상 기존 운행 D* = V*/r)
    """
    if service_km <= 0 or not 0 <= conversion_rate <= 1 or empty_ratio < 0:
        raise ValueError("시나리오 범위 오류")
    avoided = service_km * (1 + empty_ratio) * bus_ef(bus_speed) / car_ef(car_speed, car)
    eligible = float(avoided / conversion_rate) if conversion_rate > 0 else float("inf")
    return float(avoided), eligible


def run_carbon_scenarios():
    rows = []
    for car in CAR_COEFFICIENTS:
        for bus_speed in [20, 30, 40]:
            for car_speed in [30, 40, 50]:
                for empty_ratio in [0, 0.2, 0.5]:
                    for service_km in [10, 20, 40, 60]:
                        for rate in [0, 0.1, 0.25, 0.5, 0.75, 1]:
                            avoided, eligible = breakeven(service_km, rate, empty_ratio, bus_speed, car_speed, car)
                            rows.append(
                                {
                                    "car": car,
                                    "bus_speed": bus_speed,
                                    "car_speed": car_speed,
                                    "empty_ratio": empty_ratio,
                                    "roundtrip_service_km": service_km,
                                    "conversion_rate": rate,
                                    "bus_g_per_vehicle_km": float(bus_ef(bus_speed)),
                                    "car_g_per_vehicle_km": float(car_ef(car_speed, car)),
                                    "avoided_car_vehicle_km_needed": avoided,
                                    "eligible_baseline_vehicle_km_needed": eligible,
                                }
                            )
    save_table(pd.DataFrame(rows), "carbon_scenarios")
    coefficients = {
        "source": CO2_SOURCE_URL,
        "source_table": "표2, 인쇄3쪽 / PDF4쪽",
        "cars": CAR_COEFFICIENTS,
        "city_bus_CNG": list(BUS_COEFFICIENTS),
        "speed_breakpoint_kmh": SPEED_BREAKPOINT,
        "scope": "tailpipe CO2, g/vehicle-km",
    }
    write_json(TABLE_DIR / "carbon_coefficients.json", coefficients)


# ================================================================ 보고서 핵심표


HEADLINE_COLUMNS = ["scope", "metric", "value", "unit", "source_file", "code", "denominator"]


def write_key_tables():
    """보고서 본문 수치의 근거표. 저장된 표를 다시 읽어 만든다."""
    national = pd.read_csv(TABLE_DIR / "national_summary.csv")
    local = pd.read_csv(TABLE_DIR / "local_clinic_all.csv")
    avoided, eligible = breakeven(20, 0.25)
    worse = local[local.delta >= 5]
    transport_first = local[local.quadrant == TRANSPORT_FIRST]

    # (범위, 지표, 값, 단위, 근거표, 계산 코드, 분모·단서)
    rows = []
    for facility, row in national.set_index("Faci_NM").iterrows():
        for metric, unit in [("worse5_n", "곳"), ("worse5_pct", "%"), ("better5_n", "곳"), ("better5_pct", "%")]:
            rows.append(
                (
                    "전국 " + facility,
                    metric,
                    row[metric],
                    unit,
                    "national_summary.csv",
                    "src/analysis.py:summarize",
                    "전국3530읍면동; 검열아래확인가능최소",
                )
            )
    rows += [
        ("전북 병·의원", "악화지역65세이상거주", worse.elder65.sum(), "명", "local_clinic_all.csv",
         "src/analysis.py:add_branch_population", "악화67읍면동; 실제환자아님"),
        ("전북 병·의원", "교통우선지역65세이상거주", transport_first.elder65.sum(), "명", "local_quadrants.csv",
         "src/analysis.py:classify_quadrant", "교통우선35읍면동"),
        ("전북 병·의원", "30분접근기회순손실대리값", local.elder_cov30_net_loss_proxy.sum(), "명상당",
         "local_clinic_all.csv", "src/analysis.py:add_coverage_loss", "지역내연령균등접근성가정"),
        ("시나리오 L20km/r25%", "실제승용차취소필요", avoided, "차량-km", "carbon_scenarios.csv",
         "src/analysis.py:breakeven", "CNG버스30/중형휘발유차40kmh;공차20%"),
        ("시나리오 L20km/r25%", "대상기존승용차운행규모", eligible, "차량-km", "carbon_scenarios.csv",
         "src/analysis.py:breakeven", "전환25%;관측값아님"),
    ]  # fmt: skip
    headline = pd.DataFrame(rows, columns=HEADLINE_COLUMNS)
    headline["source_file"] = "outputs/tables/" + headline.source_file
    order = ["scope", "metric", "value", "unit", "denominator", "source_file", "code"]
    save_table(headline[order], "headline_metrics")

    key_columns = ["Faci_NM", "n", "worse5_n", "worse5_pct", "better5_n", "better5_pct"]
    save_table(national[key_columns].copy(), "key_metrics")


def main():
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    QA_DIR.mkdir(parents=True, exist_ok=True)
    run_accessibility()
    run_carbon_scenarios()
    run_gtfs_case()
    write_key_tables()


if __name__ == "__main__":
    main()
