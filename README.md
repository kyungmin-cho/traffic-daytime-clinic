> Hackathon prototype, no longer maintained. Write-up: [kyungmin-cho/contests](https://github.com/kyungmin-cho/contests/tree/main/2026-12_traffic-daytime-clinic)

# 낮시간 병·의원 접근성 분석

「AI와 함께하는 교통문제 해결을 위한 데이터 분석 공모전」(한겨레·재단법인 숲과나눔, 2026) 제출 보고서 「출근 시간표로는 보이지 않는 병원 가는 길」의 분석 코드와 파생 결과다.

## 요약

한국교통연구원 국가교통DB(KTDB)의 2023년 교통접근성지표로 전국 3,530개 읍면동에서 가장 가까운 내과 진료 가능 병·의원까지의 대중교통/도보 접근시간을 오전(07~09시)과 낮(12~14시)으로 나눠 비교했다. 낮에 5분 이상 길어지는 곳은 전국의 일부이고 대부분 면 지역이다. 전라북도 243개 읍면동은 낮 악화 여부와 승용차 접근시간으로 나눠 "교통부터 점검할 곳"과 "시설도 함께 볼 곳"을 구분하고, 2023년 12월 주민등록 65세 이상 인구를 붙였다. 부안군 계화면은 KTDB 2024년 3월 GTFS 시각표로 다시 확인했다. 끝으로 낮 버스 1회 증회가 늘리는 배출을 승용차 운행 감소로 상쇄하려면 얼마가 필요한지를 KTDB CO₂ 배출계수로 계산했다.

| 수치 | 값 | 근거표 (`outputs/tables/`) |
| --- | --- | --- |
| 낮 접근시간이 5분 이상 길어진 읍면동(병·의원) | 적어도 438곳 / 3,530곳 (12.4%) | `national_summary.csv` |
| 5분 이상 짧아진 읍면동 | 적어도 244곳 (6.9%) | `national_summary.csv` |
| 오전·낮 모두 정확한 값이 있는 3,345곳의 낮-오전 차이 중위값 | 0.0분 | `national_exact_pairs_summary.csv` |
| 악화 438곳 중 면 지역 | 401곳 (91.6%) | `tail_composition.csv` |
| 전북 악화 읍면동 / 그곳의 65세 이상 주민 | 67/243곳 (27.6%) / 70,374명 | `province_selection.csv`, `headline_metrics.csv` |
| 그중 교통 우선 점검(승용차 15분 미만) | 35곳 / 42,632명 | `local_quadrants.csv` |
| 왕복 20km 증회 1회를 상쇄하는 실제 승용차 운행 감소 | 133.8 차량-km | `headline_metrics.csv`, `carbon_scenarios.csv` |
| 같은 조건에서 전환율 25%일 때 필요한 대상 기존 운행 | 535.2 차량-km | `headline_metrics.csv` |

탄소 시나리오의 기준 가정은 대형 CNG 시내버스 30km/h, 중형 휘발유 승용차 40km/h, 공차·회차 거리 20%다.

## 해석상 주의

- **120분 초과 검열.** 원자료의 `>120.00`은 결측이 아니라 "120분 이상"이다. 지우지 않고 검열 플래그로 남겨 낮-오전 차이의 하한·상한을 둔다. 그래서 악화·개선 수는 "적어도" 그만큼인 보수적 최소치다. 오전·낮 둘 다 검열된 100곳은 변화 없음으로 보지 않는다. 시설수의 `>10`도 같은 방식으로 다룬다.
- **모형값.** 평균접근시간은 집계구 인구로 가중한 모형 최소시간이다. 실제 환자의 이동시간이나 진료 포기를 뜻하지 않는다. 읍면동 단순분포와 KTDB 공식 인구가중 전국값(`official_national_aggregates.csv`)은 구분한다.
- **고령 인구는 거주 규모다.** 65세 이상 인구는 그 읍면동에 사는 사람의 수이지 환자, 버스 이용자, 증회 수혜 인원이 아니다. 30분 접근가능인구 비율 손실을 고령 인구에 곱한 값은 연령에 따라 접근성이 같다고 가정한 대리값이다.
- **연간 감축 톤 수치는 없다.** 탄소 계산은 직접(배기관) CO₂의 조건부 손익분기선(차량-km)이다. 실제 노선·차량·속도·전환율을 관측하지 않았으므로 연간 감축량으로 바꾸지 않는다. 그림 06의 회색 띠는 차종·속도 가정 전체의 범위이지 신뢰구간이 아니다.
- **지역 선택과 분류.** 전북은 후보 세 도(전북·충북·경남) 중 악화 비율이 가장 높아 고른 목적 표집이며 충북(27.5%)과 차이가 작다. 사분면은 점검 우선순위이지 시설 부족이나 배차 원인을 확정하는 분류가 아니다. "낮 악화 미확인"은 접근성이 좋다는 뜻이 아니다. Ward 군집도 비교했지만(`cluster_diagnostics.csv`) 사분면보다 낫다는 근거가 없어 채택하지 않았다.
- **GTFS.** KTDB GTFS는 2024년 3월 평일 모형 시각표다. 2026년 현행 운행이나 정시성 관측이 아니고 방향·목적지 정보가 없다. 노선 계통 하나(창북2 정류장의 600번 한 route_id)만 보면 오전 0건·낮 5건으로 낮이 많아 보이지만, 같은 정류장의 모든 노선을 세면 오전 14건·낮 5건(3건)이고 계화면을 지나는 trip은 오전 19개·낮 10개다. calendar의 전 요일 1은 모형용 고정값이다.
- **인구 결합.** KTDB(통계청 8자리)와 주민등록(행정안전부 10자리) 코드는 2023-12-31 경계 파일로 잇는다. 출장소 62곳의 인구는 부모 읍면동에 더했고(`population_branch_rollup.csv`), 17개 시도 합계가 공식 값과 같은지 검사한다. 전국 미결합 5곳은 주민등록 인구가 없는 철원·고성의 면이다.

## 폴더 구조

```
analysis/
├── Makefile
├── pyproject.toml, uv.lock, .python-version   실행 환경 고정
├── src/
│   ├── data.py       원자료 내려받기·SHA-256 확인, KTDB 의료시설 3종 정규화
│   ├── analysis.py   오전·낮 비교, 인구 결합, 사분면·군집 진단, GTFS 계화면 사례, 탄소 손익분기
│   ├── figures.py    그림 6장(300dpi 원본과 보고서 축소판)
│   └── verify.py     자동 검사 37개와 실행 기록
├── data/
│   ├── README.md                     자료별 출처·URL·기준시점·해시와 받는 법
│   ├── sources.json                  다운로드 주소·양식·SHA-256
│   ├── branch_parent_overrides.csv   이름만으로 부모를 알 수 없는 출장소 3곳의 대응 근거
│   ├── raw/          원자료(커밋 제외)
│   └── processed/    중간 산출(커밋 제외)
└── outputs/
    ├── tables/          결과표(CSV·JSON)
    ├── figures/         그림 01~06, 300dpi 원본
    ├── figures_report/  보고서에 넣은 축소판
    └── qa/              원자료·분석·GTFS 검수 기록, verification.json, run_manifest.json
```

주요 결과표: `headline_metrics.csv`(보고서 핵심 수치와 단위·분모·근거), `key_metrics.csv`, `national_summary.csv`, `national_exact_pairs_summary.csv`, `province_summary.csv`, `local_quadrants.csv`(전북), `threshold_sensitivity.csv`(기준 3/5/10분 × 10/15/20분, 검열 제외), `population_*`(인구 결합 감사), `gtfs_*`, `carbon_scenarios.csv`·`carbon_coefficients.json`.
KTDB 원자료 값을 읍면동 행 단위로 그대로 담은 표(`national_clinic_all.csv`, `worsened_areas.csv`, `improved_areas.csv`, `local_clinic_all.csv`, `medical_all_metrics.csv`)는 실행하면 만들어지지만 저장소에는 올리지 않는다.

## 원자료

원자료는 재배포하지 않는다. 출처, URL, 기준시점, 받는 방법은 [data/README.md](data/README.md)에, 파일별 SHA-256은 [data/sources.json](data/sources.json)에 있다. 모두 `data/raw/`에 둔다.

- KTDB 2023 교통접근성지표 ZIP(`ktdb_2023.zip`, 같은 파일의 중복 목록 `ktdb_2023_duplicate.zip`)
- 행정안전부 2023년 12월 행정동별 5세 단위 주민등록인구 CSV(`mois_202312_age5.csv`)
- KTDB View-T CO₂ 배출계수 설명자료(`Co2quantity.pdf`)
- 2023-12-31 행정동 경계(`boundary_20231231.geojson`, 통계청 경계 기반 민간 보정본 admdongkor)
- KTDB 대중교통 GTFS(2024년 기준, `gtfs_2024.zip`): 직접 링크가 없는 **신청 자료**다. KTDB 누리집 정보공개 → 자료신청 → 교통분석자료 → 교통망GIS DB → 대중교통 → 전국 → 배포년도 2025 → 대중교통GTFS(2024년 기준)를 신청해 받은 ZIP을 `data/raw/gtfs_2024.zip`으로 둔다. sources.json의 링크는 신청 건마다 달라 만료될 수 있다.

`src/data.py`는 없는 파일만 내려받고, 있는 파일은 해시만 확인한다. 해시가 다르면 멈춘다.

## 실행

Python 3.14.7과 [uv](https://docs.astral.sh/uv/)를 쓴다.

```sh
cd analysis
uv sync --frozen
make all                              # 내려받기 → 정리 → 분석 → 그림 → 검사
make analyze figures verify           # 원자료가 data/raw에 이미 있을 때
```

| 단계 | 명령 | 하는 일 |
| --- | --- | --- |
| `make data` | `src/data.py fetch` | 없는 원자료 내려받기, 모든 원자료 SHA-256 확인, KTDB ZIP 풀기 |
| `make prepare` | `src/data.py prepare` | KTDB 의료 3종 정규화(`data/processed/`) |
| `make analyze` | `src/analysis.py` | prepare 후 모든 결과표. GTFS stop_times 약 1.6GB를 압축 상태로 스트리밍한다 |
| `make figures` | `src/figures.py` | `outputs/figures/`와 `outputs/figures_report/`. `make analyze` 결과(`medical_all_metrics.csv` 등)가 필요하다 |
| `make verify` | `src/verify.py` | 검사 37개. 모두 통과하면 `outputs/qa/verification.json`과 `run_manifest.json`(환경·파일 해시)을 쓴다 |

그림은 macOS의 Apple SD Gothic Neo로 그렸다. 다른 OS에서는 한글 글꼴 경로를 `KOREAN_FONT` 환경변수로 지정한다. 글꼴이 다르면 그림 픽셀은 달라질 수 있지만 수치는 같다.
