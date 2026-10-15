# 데이터 출처 및 재현 절차

원자료는 `data/raw/`, 중간 결과는 `data/processed/`에 로컬 저장하며 `.gitignore`로 커밋에서 제외한다. 모든 실제 다운로드의 SHA-256·용량·POST 인자는 [sources.json](sources.json)에 고정했다. 다운로드 일자: 2026-10-15(Asia/Seoul).

## 다운로드

```sh
cd analysis
uv sync --frozen
uv run --frozen python src/data.py fetch
```

`src/data.py fetch`는 파일이 있으면 해시를 검증하고 없으면 내려받는다. `--refresh`는 재다운로드하며 제공 파일이 바뀌어 해시가 다르면 중단한다. 출처와 변경 내용을 검토하기 전 해시를 임의 갱신하지 않는다.

## 2023년 교통접근성지표 ZIP(자료목록9번)
- 제공처: 한국교통연구원 국가교통DB
- URL: https://www.ktdb.go.kr/www/fileDownTrnsport.do?idx=48612&fileTy=2&fileNo=7
- 기준시점: 2023-12 통계; 대중교통 시각표 및 의료시설 2024-03
- 로컬명: `ktdb_2023.zip` · 85,353,004 bytes
- SHA-256: `692292315c0cf0c0b3b123e22da83a56107beb680652af59c837f8dae8de5049`

## 동일 ZIP 자료목록10번(중복 검증)
- 제공처: 한국교통연구원 국가교통DB
- URL: https://www.ktdb.go.kr/www/fileDownTrnsport.do?idx=48612&fileTy=2&fileNo=8
- 기준시점: 위와 동일
- 로컬명: `ktdb_2023_duplicate.zip` · 85,353,004 bytes
- SHA-256: `692292315c0cf0c0b3b123e22da83a56107beb680652af59c837f8dae8de5049`

## 행정동별 연령별 인구현황 2023년12월 전체읍면동 계 5세
- 제공처: 행정안전부 주민등록 인구통계
- URL: https://jumin.mois.go.kr/downloadCsvAge.do?searchYearMonth=month&xlsStats=3
- 기준시점: 2023-12-31 월말, 거주자·거주불명자·재외국민 포함; 외국인 제외
- 로컬명: `mois_202312_age5.csv` · 726,053 bytes
- SHA-256: `52438430615d6b620cd2471d8c6b44892c14909b952182e0ae8d54a6c6f6622a`

## View-T 이산화탄소(CO2) 배출계수 설명자료
- 제공처: 한국교통연구원 KTDB View-T
- URL: https://viewt.ktdb.go.kr/cong/pdf/Co2quantity.pdf
- 기준시점: 2021 승인 국가계수 활용, 문서의 구축연도2019~2024; 2023 차량군 실측계수 아님
- 로컬명: `Co2quantity.pdf` · 1,298,850 bytes
- SHA-256: `30fe9fd5c4d051d561676bf584322703132df1ffdebcfe971399ce4a0bc4583c`

## HangJeongDong_ver20231231.geojson
- 제공처: vuski/admdongkor(현 schwa456/hangjeongdong), 통계청 경계 기반 민간 보정
- URL: https://raw.githubusercontent.com/vuski/admdongkor/7360288277dfd12d74e54b959c59bdd66f852e3a/ver20231231/HangJeongDong_ver20231231.geojson
- 기준시점: ver20231231, 고정 커밋7360288277dfd12d74e54b959c59bdd66f852e3a
- 로컬명: `boundary_20231231.geojson` · 34,650,471 bytes
- SHA-256: `6916df854f1c49ce56cd280f5dc633ef89931ef02db845624ce886d49a23d528`

## 대중교통GTFS(2024년 기준), 202403_GTFS_DataSet
- 제공처: 한국교통연구원 KTDB, 공개 교통분석자료 신청(직접 링크 없음)
- 기준시점: 2024년3월 평일, 2025년배포 항목. calendar값은모형용 고정코딩
- 로컬명: `gtfs_2024.zip` · 214,689,001 bytes
- SHA-256: `9419e9fa1a86ac9344e50322feefeacdc96f1601708985dbd45571eb69f60f94`

## 수동 다운로드와 정의

- KTDB: [교통접근성지표 페이지](https://www.ktdb.go.kr/www/selectTrnsportTreeView.do?idx=46126&key=30) → 2023년 교통접근성지표 ZIP. 자료목록 9·10번(fileNo7·8)은 모두 다운로드하여 바이트·SHA-256 동일함을 확인했다. ZIP 내부 00 통계기획서, 01 평균접근시간, 02 접근가능인구비율, 03 접근가능시설수의 해시도 sources.json에 기록했다.
- 통계 기준은 2023년12월, 대중교통은 익년3월(2024-03). 기획서 인쇄1쪽은 시설을 기준시점 또는 익년3~4월로 총괄하며, 인쇄6쪽 표1은 **의료시설=익년3월(2024-03)**, 교육시설=익년4월로 구체화한다. 보고서에는 총괄 정의와 의료 세부시점을 함께 쓴다. 2025년6월 통계 공지는 확인했으나 현재 자료 페이지의 공개 ZIP 목록은 2016~2023이다. 이번 결과는 2023 통계로 고정한다.
- MOIS: [행정동별 연령별 인구](https://jumin.mois.go.kr/ageStatMonth.do) → 월간 2023년12월~2023년12월 → 등록 전체 → 계 → 5세/0~100세 이상 → 전체읍면동현황 → csv. 페이지의 공개 formXlsDown 양식 POST를 그대로 재현했다. encoding=cp949. 총 3,878행은 시도·시군구 등 상위행도 포함하므로 모두 합산하지 않는다. 65~69세부터100세 이상까지 더한다.
- 출장소62개는 본소에 포함되지 않은 별도 인구이므로 KTDB 읍면동으로 합산한다. 이름에 부모가 명시된59곳과 근거를 남긴 예외3곳의 전수 대응표는 outputs/tables/population_branch_rollup.csv다. data/branch_parent_overrides.csv는 수작업 공간 대응표이며 원자료가 아니다. 원산·신수는 주민등록 기관의 소속 변경이 아니라 KTDB 통계경계에 맞추는 지리 합산이다. 원산출장소·신수도 GTFS 좌표와 경계 포함관계도 검증하고, 삼랑진임천은 밀양시 공식 소개로 확인했다. 인구 합계는17개 시도별 공식행과 일치한다.
- MOIS의 주민등록 전체는 거주자·거주불명자·재외국민 포함, 외국인 제외. 이 인구는 KTDB 집계구 가중인구와 동일 분모라고 가정하지 않는다.
- 경계: 공식 원본을 직접 받은 것이 아니라 통계청 경계를 수정한 민간 배포본이다. ver20231231의 고정 커밋을 사용했고, 사용 버전·수정 이력·권리 안내는 [저장소](https://github.com/vuski/admdongkor/tree/7360288277dfd12d74e54b959c59bdd66f852e3a)에서 확인한다. 지도는 시각화 보조이며 공간 면적 가중 계산을 하지 않는다. SGIS 8자리→MOIS10자리 교차표로도 사용했다. 전북 243/243 지도 결합, 전국 인구 3525/3530 결합 및 이름 보완4건은 crosswalk audit에 공개한다.
- 사용·재배포: 다운로드 가능과 원자료 재배포 허용은 별개다. 원자료 ZIP·XLSX·CSV·경계·PDF를 Git에 올리지 않는다. 원자료 값을 읍면동 행 단위로 그대로 담은 파생표(`national_clinic_all.csv`, `worsened_areas.csv`, `improved_areas.csv`, `local_clinic_all.csv`, `medical_all_metrics.csv`)도 저장소에 올리지 않으며, 실행하면 만들어진다.

## GTFS 신청·수령

- 2026-10-15 공개 교통분석자료 신청에서 교통망GIS DB→대중교통→전국→배포년도2025→대중교통GTFS(2024년기준)를 선택했다. 신청 후 받은 다운로드 링크는 신청 건마다 다르고 만료되므로, 재현하려면 같은 항목을 신청해 받은 ZIP을 `data/raw/gtfs_2024.zip`으로 둔다. SHA-256으로 같은 파일인지 확인한다.
- ZIP214,689,001bytes의 stop_times21,889,865행(약1.64GB 비압축)을 압축 스트림으로 읽고 계화면만 추출한다. 전체 stop_times를 디스크에 풀지 않는다. 설명서 PDF와 내부 폴더는2024-03 평일을 확인해 준다. GTFS에도 접근성 본체와 같은2024-03 시점을 사용한다.
- calendar의 전요일1과2017~2030은 고정 코딩이며 실제 운행기간이 아니다. route_type0이 버스라는 KTDB 고유 정의를 적용한다. 방향·headsign·shapes·차종이 없어 실제 의료 연결 운행계획은 별도 확인해야 한다.

## 값 검수

- 각 엑셀의 관측행은349,976행, 의료3종은95,448행이다. HDCD_Lev=4만 읍면동이며0~3의 전국·시도·시군구·하위구 집계와 섞지 않는다. 3530×3시설×4시간대×2수단=84,720 읍면동 의료 관측.
- 01은 헤더5행 다음부터, 02·03은 추가 보조헤더1행 뒤부터 읽는다. 시간대 일평균06~20, 오전07~09, 낮12~14, 저녁18~20. 수단2_PT는 대중교통/도보 결합이며 순수 버스시간이 아니다.
- `N/A`와 `>120.00`을 구분한다. 전체시설의 시간 N/A20셀, 비율·시설수 N/A각80셀은 원자료 전체의 검사 결과다. 본 분석의 의료 읍면동 쌍은 결측 없이 시간 초과 검열만 있다. 상세 검사 outputs/qa/source_audit.json.
- 03의 `>10.00`은 인구가중 접근가능시설수의 상한 초과이며 정확한10이 아니다. `_censored` 열로 유지하고 10은 그림·수치 비교의 하한값으로만 쓴다. 15/30/45/60분 누적값 단조성과 범위 검사를 수행했다.
- 평균시간은 가장 인접한 내과 진료 가능 병·의원 등으로 가는 모형 최소시간의 집계구 인구 가중값이다. 시설수는 지역 내 전체 병원 수가 아니라 주어진 시간 안에 접근 가능한 시설의 인구가중 수이며10 초과 검열이다.
