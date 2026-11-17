# 올림픽공원 도로·주차 실시간 수집기

KSPO DOME 공연 전후의 주변 도로 정체와 주차장 출차를 5분마다 기록합니다.
한국체육산업개발 2026 공공데이터 활용 경진대회 출품 준비용입니다.

## 모으는 데이터

| 출처 | 내용 | 저장 파일 |
|---|---|---|
| 서울시 실시간 도시데이터(올림픽공원) | 주변 도로 58개 구간의 속도·혼잡 단계 | `roads.csv` |
| 같은 응답 | 지역 평균 속도, 정체 구간 수, 인구, 버스 승하차, 돌발 건수, 날씨 | `summary.csv` |
| 같은 응답 | 사고·통제 등 돌발정보 원문 | `incidents.csv` |
| 한국체육산업개발 실시간 주차현황 | 올림픽공원 주차 합계(`parking_sum`) | `summary.csv`의 `주차합계_parking_sum` |
| 서울시 응답 원문 전체 | 나중에 다시 분석할 때 쓰는 원본 | `raw_citydata.jsonl.gz` |

실행할 때마다 `data/날짜_이름표_시작시각/` 폴더가 하나씩 생깁니다. 오류는 같은 폴더의 `errors.log`에 남습니다.

---

## GitHub에서 쓰는 방법

### 1. 저장소 만들기
1. github.com 로그인 → 오른쪽 위 **+** → **New repository**
2. 이름 예: `olpark-collector`
3. **Public**으로 만드세요.
   - 공개 저장소는 Actions 사용 시간이 무료·무제한입니다.
   - 비공개 저장소는 월 2,000분까지 무료인데, 이번 일정(7회 × 약 350분)은 약 2,450분이라 넘칩니다.
   - 인증키는 아래 3번의 Secret에 넣으므로 공개 저장소여도 노출되지 않습니다.

### 2. 파일 올리기
1. 받은 zip을 풀면 `collect.py`, `README.md`, `.github` 폴더가 있습니다.
2. 새 저장소 화면에서 **uploading an existing file** (또는 **Add file → Upload files**)
3. 세 가지를 **한꺼번에 끌어다 놓고** → **Commit changes**
4. 저장소에 `.github/workflows/collect.yml` 이 보이는지 확인하세요.
   - 안 보이면: **Add file → Create new file** → 파일 이름 칸에 `.github/workflows/collect.yml` 입력 → zip 안의 같은 파일 내용을 붙여넣고 커밋

### 3. 인증키 넣기 (Secret)
1. 저장소 **Settings → Secrets and variables → Actions**
2. **New repository secret**
3. Name: `SEOUL_API_KEY` / Secret: 서울시 열린데이터광장 일반 인증키 → **Add secret**

### 4. 쓰기 권한 확인
**Settings → Actions → General → Workflow permissions** 에서 **Read and write permissions** 선택 후 Save.

### 5. 시험 실행 (꼭 먼저 하세요)
1. 저장소 **Actions** 탭 → 처음이면 **I understand my workflows, go ahead and enable them**
2. 왼쪽 **올림픽공원 도로·주차 수집** → 오른쪽 **Run workflow**
3. minutes `10`, label `test` 그대로 → **Run workflow**
4. 약 15분 뒤 저장소 `data/` 폴더에 `..._test_...` 폴더가 생기면 성공입니다.
5. 확인할 것
   - `roads.csv`에 58줄씩 쌓였는지
   - `summary.csv`의 `주차합계_parking_sum` 칸에 숫자가 있는지
   - `errors.log`가 있다면 내용
     - `도시데이터 실패: ... timed out` 처럼 계속 실패하면 GitHub 서버(해외)에서 서울시 API 접속이 막힌 것일 수 있습니다. 이때는 아래 **윈도우에서 직접 실행**으로 바꾸세요.
     - `INFO-100` 등 인증 오류면 Secret 값을 다시 확인하세요.

### 6. 공연 날 자동 실행
`.github/workflows/collect.yml`의 `schedule`에 일정이 이미 들어 있습니다.

| 날짜 | 공연 | 수집 시작(한국시간) |
|---|---|---|
| 11/20(금) | 로이킴 20:00 | 17:50 |
| 11/21(토) | 로이킴 18:00 | 15:50 |
| 11/22(일) | 로이킴 17:00 | 14:50 |
| 11/26(목) | KSPO돔 공연 없음(금요일 공연과 비교용) | 17:50 |
| 11/27(금) | 조용필 19:00 | 16:50 |
| 11/28(토) | 조용필 18:00 | 15:50 |
| 11/29(일) | 조용필 17:00 | 14:50 |

- 각 실행은 약 5시간 50분 동안 수집합니다.
- 마감 전 주말은 모두 공연이 있어서, 비교용은 평일(목) 저녁으로 잡았습니다. 그날 올림픽홀 등 다른 공연장 행사가 있는지 확인해 두세요.
- **GitHub 예약 실행은 늦게 시작되거나 드물게 건너뛸 수 있습니다.** 공연 날 시작 시각쯤 Actions 탭에서 실행 중인지 확인하고, 안 돌고 있으면 **Run workflow**로 minutes `350`, label `roykim` 등을 넣어 직접 시작하세요.
- 일정이 바뀌면 cron 줄을 고치세요. 시각은 **UTC(한국시간 − 9시간)** 입니다. 예: 한국 11/30 18:00 → `0 9 30 11 *`
- 수집이 다 끝나면 `schedule` 부분을 지우세요. 그대로 두면 내년 같은 날짜에 다시 돕니다.

### 7. 결과 받기
저장소 첫 화면 **Code → Download ZIP** 으로 받거나 `data/` 폴더의 CSV를 내려받아 분석에 쓰면 됩니다.

## 도로 58개 구간 한꺼번에 수집 (`collect_links.py`)

`olpark_links_58.csv`에 적힌 58개 LINK_ID마다 서울시 **실시간 도로 소통 정보** API(`TrafficInfo`)를 불러
구간별 속도·통행시간을 `data/links_날짜.csv`에 한 번에 저장합니다.

- **윈도우**: `run_links.bat`을 더블클릭 → 인증키 붙여넣기 → 수집 시간(1회만이면 `0`, 공연 날은 `350`)
- **명령어**:
  ```
  set SEOUL_API_KEY=여기에_인증키
  python collect_links.py                 (1회)
  python collect_links.py --minutes 350   (5분마다 350분)
  ```
- **GitHub**: 같은 workflow 안에 `links` 작업으로 들어 있어 예약·수동 실행 때 함께 돕니다.
- 저장 항목: 수집시각, LINK_ID, 도로명, 시작·끝 지점, 길이, 속도(km/h), 통행시간(초), 혼잡단계(서울시 기준으로 계산), 결과코드, 응답 원문
- 첫 실행에서 모든 구간이 실패하면 `data/links_errors_날짜.log`를 보세요.
  - `INFO-100`: 인증키 오류
  - 서비스명 오류: 열린데이터광장 "서울시 실시간 도로 소통 정보"의 샘플 URL에 적힌 서비스명으로 `--service 이름`을 붙여 실행
  - `timed out` 반복: 접속 차단(GitHub이면 윈도우에서 실행)

---

## 윈도우에서 직접 실행 (GitHub에서 안 될 때)

1. python.org에서 Python 3 설치. 설치 첫 화면에서 **Add python.exe to PATH** 체크
2. zip을 푼 폴더에서 주소창에 `cmd` 입력 후 엔터
3. 아래 두 줄 실행 (키는 본인 것으로)
   ```
   set SEOUL_API_KEY=여기에_인증키
   python collect.py --minutes 350 --label roykim
   ```
4. 수집 중에는 창을 닫지 말고, **설정 → 시스템 → 전원**에서 절전 모드를 "안 함"으로 바꿔 두세요.
5. 결과는 같은 폴더의 `data\` 아래에 쌓입니다.

시험은 `python collect.py --minutes 10 --label test` 로 하세요.

---

## 주의
- 인증키를 `collect.py`나 다른 파일에 직접 적지 마세요. 공개 저장소에 올라가면 누구나 봅니다.
- 서울시 도로소통 데이터는 5분마다 갱신되므로 더 자주 불러도 같은 값입니다.
- 한국체육산업개발 `parking_sum`이 "주차된 차량 수"인지 "남은 면수"인지는 공식 설명이 없습니다. 공연 후 값이 줄어드는지 늘어나는지로 확인하거나 디지털혁신팀(02-2180-3504)에 문의하세요.
