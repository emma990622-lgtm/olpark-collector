#!/usr/bin/env python3
"""올림픽공원 주변 도로·주차 실시간 수집기

5분마다 아래 두 API를 불러 CSV로 쌓습니다. 파이썬 표준 라이브러리만 씁니다(설치할 패키지 없음).
  1) 서울시 실시간 도시데이터(올림픽공원): 주변 도로 58개 구간 속도, 지역 평균, 인구, 돌발정보
  2) 한국체육산업개발 실시간 주차현황: 올림픽공원 주차 합계(parking_sum)
  3) 서울시 공영주차장 실시간 정보(GetParkingInfo): 송파구·강동구 공영주차장 빈자리
     → 공원 안 주차장과 '조금 먼 주차장'을 비교하기 위한 자료

사용 예)
  python collect.py --minutes 350              # 350분 동안 5분마다 수집
  python collect.py --minutes 10 --label test  # 10분 시험 수집
  python collect.py --minutes 350 --git        # GitHub Actions용: 30분마다 저장소에 커밋

서울시 인증키는 환경변수 SEOUL_API_KEY 로 넘깁니다(코드에 적지 마세요).
"""
import argparse
import csv
import datetime as dt
import gzip
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

KST = dt.timezone(dt.timedelta(hours=9))
PLACE = "올림픽공원"
SEOUL_URL = "http://openapi.seoul.go.kr:8088/{key}/json/citydata/1/5/{place}"
PARKING_URL = "https://www.ksponco.or.kr/online/main/parkingorsApi.do?apiKey=PARKING21803504"
LOT_URL = "http://openapi.seoul.go.kr:8088/{key}/json/GetParkingInfo/{a}/{b}/{addr}"
LOT_GUS = ["송파구", "강동구"]      # 올림픽공원이 걸쳐 있는 자치구
INTERVAL_MIN = 5          # 도로소통 갱신 주기(5분)에 맞춤
COMMIT_EVERY = 6          # --git 사용 시 6회(약 30분)마다 커밋

# 날짜(한국시간) → 폴더 이름표. 일정이 바뀌면 여기만 고치면 됩니다.
EVENTS = {
    "2026-11-20": "baseline_fri", # 공식 일정상 로이킴은 21·22일만 → 공연 없는 금요일(비교용)
    "2026-11-21": "roykim",       # 로이킴 18:00
    "2026-11-22": "roykim",       # 로이킴 17:00
    "2026-11-26": "baseline",     # KSPO돔 공연 없는 평일 저녁(금요일 공연과 비교용)
    "2026-11-27": "choyongpil",   # 조용필 19:00 (+올림픽홀 다이나믹듀오 20:00)
    "2026-11-28": "choyongpil",   # 조용필 18:00 (+다이나믹듀오 18:00)
    "2026-11-29": "choyongpil",   # 조용필 17:00 (+다이나믹듀오 17:00)
}


def now_kst():
    return dt.datetime.now(KST)


def fetch_json(url, timeout=20, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "olpark-collector/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            return json.loads(raw.decode("utf-8"))
        except Exception as e:  # 네트워크 오류·형식 오류 모두 재시도
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}")


def append_csv(path, header, rows):
    if not rows:
        return
    new = not os.path.exists(path)
    # 엑셀에서 한글이 깨지지 않도록 새 파일에만 BOM을 붙입니다.
    with open(path, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerows(rows)


def log_error(outdir, msg):
    line = f"{now_kst():%Y-%m-%d %H:%M:%S} {msg}"
    print("[오류]", line, file=sys.stderr)
    with open(os.path.join(outdir, "errors.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


ROAD_HEADER = ["수집시각", "도로갱신시각", "LINK_ID", "도로명", "시작지점", "끝지점",
               "길이_m", "속도_kmh", "혼잡단계"]
SUMMARY_HEADER = ["수집시각", "도로갱신시각", "지역평균속도_kmh", "지역도로혼잡", "구간수",
                  "정체구간수", "서행구간수", "원활구간수",
                  "인구갱신시각", "인구혼잡도", "인구최소", "인구최대",
                  "버스30분승차최소", "버스30분하차최소", "돌발건수",
                  "주차합계_parking_sum", "기온", "강수형태",
                  # 11/20 추가: 올림픽공원 일대 실시간 인구의 연령·성별 비율(%) — 공연 관객 구성 추정 확인용(olpark-traffic scripts/15)
                  "인구비율_0~9세", "인구비율_10대", "인구비율_20대", "인구비율_30대", "인구비율_40대",
                  "인구비율_50대", "인구비율_60대", "인구비율_70대이상", "남성비율", "여성비율",
                  "상주인구비율", "비상주인구비율"]
INCIDENT_HEADER = ["수집시각", "내용_json"]


LOT_HEADER = ["수집시각", "주차장코드", "주차장명", "주소", "주차장종류", "실시간제공",
              "총면수", "현재주차대수", "현재주차갱신시각", "평일운영시작", "평일운영종료",
              "주말운영시작", "주말운영종료", "기본요금", "기본시간_분", "추가요금", "추가시간_분",
              "위도", "경도", "원문_json"]
_LOT_FILTER_OK = None   # 주소 조건 검색이 되는지(첫 호출에서 판단)


def _lot_rows(d):
    g = d.get("GetParkingInfo") or {}
    res = g.get("RESULT") or d.get("RESULT") or {}
    code = res.get("CODE") or res.get("RESULT.CODE")
    return g.get("row") or [], int(g.get("list_total_count") or 0), code


def fetch_lots(key):
    """송파구·강동구 공영주차장 실시간 정보. 주소 조건 검색이 안 되면 전체를 받아 주소로 거른다."""
    global _LOT_FILTER_OK
    rows = []
    if _LOT_FILTER_OK is not False:
        for gu in LOT_GUS:
            d = fetch_json(LOT_URL.format(key=key, a=1, b=1000, addr=urllib.parse.quote(gu)))
            r, _, code = _lot_rows(d)
            rows += [x for x in r if gu in str(x.get("ADDR", ""))]
        if rows or _LOT_FILTER_OK:
            _LOT_FILTER_OK = True
            return rows
        _LOT_FILTER_OK = False
    a, total = 1, None
    while total is None or a <= total:
        d = fetch_json(LOT_URL.format(key=key, a=a, b=a + 999, addr="").rstrip("/"))
        r, total, code = _lot_rows(d)
        if not r:
            break
        rows += [x for x in r if any(gu in str(x.get("ADDR", "")) for gu in LOT_GUS)]
        a += 1000
    return rows


def lot_csv_rows(rows, ts):
    g = lambda x, k: x.get(k, "")
    return [[ts, g(x, "PKLT_CD"), g(x, "PKLT_NM"), g(x, "ADDR"), g(x, "PKLT_TYPE"),
             g(x, "PRK_STTS_YN"), g(x, "TPKCT"), g(x, "NOW_PRK_VHCL_CNT"),
             g(x, "NOW_PRK_VHCL_UPDT_TM"), g(x, "WD_OPER_BGNG_TM"), g(x, "WD_OPER_END_TM"),
             g(x, "WE_OPER_BGNG_TM"), g(x, "WE_OPER_END_TM"), g(x, "BSC_PRK_CRG"),
             g(x, "BSC_PRK_HR"), g(x, "ADD_PRK_CRG"), g(x, "ADD_PRK_HR"), g(x, "LAT"),
             g(x, "LOT"), json.dumps(x, ensure_ascii=False)] for x in rows]


def parse_city(d, ts):
    """서울시 실시간 도시데이터 응답 → (도로행들, 요약행 일부, 돌발행들)"""
    c = d.get("CITYDATA") or {}
    road = c.get("ROAD_TRAFFIC_STTS") or {}
    avg = road.get("AVG_ROAD_DATA") or {}
    links = road.get("ROAD_TRAFFIC_STTS") or []
    road_time = avg.get("ROAD_TRAFFIC_TIME", "")
    road_rows = [[ts, road_time, r.get("LINK_ID"), r.get("ROAD_NM"), r.get("START_ND_NM"),
                  r.get("END_ND_NM"), r.get("DIST"), r.get("SPD"), r.get("IDX")] for r in links]
    cnt = {"정체": 0, "서행": 0, "원활": 0}
    for r in links:
        if r.get("IDX") in cnt:
            cnt[r["IDX"]] += 1
    pp = (c.get("LIVE_PPLTN_STTS") or [{}])[0]
    bus = c.get("LIVE_BUS_PPLTN") or {}
    acc = c.get("ACDNT_CNTRL_STTS") or []
    w = (c.get("WEATHER_STTS") or [{}])[0]
    summary = {
        "도로갱신시각": road_time,
        "지역평균속도_kmh": avg.get("ROAD_TRAFFIC_SPD"),
        "지역도로혼잡": avg.get("ROAD_TRAFFIC_IDX"),
        "구간수": len(links),
        "정체구간수": cnt["정체"], "서행구간수": cnt["서행"], "원활구간수": cnt["원활"],
        "인구갱신시각": pp.get("PPLTN_TIME"), "인구혼잡도": pp.get("AREA_CONGEST_LVL"),
        "인구최소": pp.get("AREA_PPLTN_MIN"), "인구최대": pp.get("AREA_PPLTN_MAX"),
        "버스30분승차최소": bus.get("BUS_30WTHN_GTON_PPLTN_MIN"),
        "버스30분하차최소": bus.get("BUS_30WTHN_GTOFF_PPLTN_MIN"),
        "돌발건수": len(acc),
        "기온": w.get("TEMP"), "강수형태": w.get("PRECPT_TYPE"),
        "남성비율": pp.get("MALE_PPLTN_RATE"), "여성비율": pp.get("FEMALE_PPLTN_RATE"),
        "상주인구비율": pp.get("RESNT_PPLTN_RATE"), "비상주인구비율": pp.get("NON_RESNT_PPLTN_RATE"),
    }
    for k, lab in [("0", "0~9세"), ("10", "10대"), ("20", "20대"), ("30", "30대"), ("40", "40대"),
                   ("50", "50대"), ("60", "60대"), ("70", "70대이상")]:
        summary["인구비율_" + lab] = pp.get("PPLTN_RATE_" + k)
    incident_rows = [[ts, json.dumps(a, ensure_ascii=False)] for a in acc]
    return road_rows, summary, incident_rows


def git_commit(outdir, final=False):
    msg = f"수집 {os.path.basename(outdir)} {now_kst():%m-%d %H:%M}" + (" (완료)" if final else "")
    cmds = [["git", "add", outdir],
            ["git", "commit", "-m", msg],
            ["git", "pull", "--rebase", "--autostash"],
            ["git", "push"]]
    for c in cmds:
        r = subprocess.run(c, capture_output=True, text=True)
        if r.returncode != 0 and c[1] != "commit":  # 바뀐 게 없으면 commit은 실패해도 괜찮음
            print("[git]", " ".join(c), r.stderr.strip(), file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="올림픽공원 도로·주차 실시간 수집")
    ap.add_argument("--minutes", type=int, default=350, help="수집할 시간(분). GitHub Actions는 최대 350 권장")
    ap.add_argument("--label", default="", help="폴더 이름표(비우면 날짜로 자동 지정)")
    ap.add_argument("--outdir", default="data", help="저장 폴더")
    ap.add_argument("--git", action="store_true", help="30분마다 저장소에 커밋·푸시(GitHub Actions용)")
    ap.add_argument("--test-file", help="API 대신 저장해 둔 도시데이터 JSON으로 1회 시험")
    a = ap.parse_args()

    key = os.environ.get("SEOUL_API_KEY", "").strip()
    if not key and not a.test_file:
        sys.exit("환경변수 SEOUL_API_KEY 가 비어 있습니다. README의 설정 방법을 보세요.")

    start = now_kst()
    label = a.label.strip() or EVENTS.get(f"{start:%Y-%m-%d}", "etc")
    outdir = os.path.join(a.outdir, f"{start:%Y-%m-%d}_{label}_{start:%H%M}")
    os.makedirs(outdir, exist_ok=True)
    print(f"저장 폴더: {outdir} / {a.minutes}분 동안 {INTERVAL_MIN}분 간격 수집")

    city_url = SEOUL_URL.format(key=key, place=urllib.parse.quote(PLACE))
    end = start + dt.timedelta(minutes=a.minutes)
    n = 0
    while True:
        ts = f"{now_kst():%Y-%m-%d %H:%M:%S}"
        summary = {}
        # 1) 서울시 실시간 도시데이터
        try:
            if a.test_file:
                d = json.load(open(a.test_file, encoding="utf-8"))
            else:
                d = fetch_json(city_url)
            res = (d.get("RESULT") or {})
            code = res.get("RESULT.CODE") or res.get("CODE")
            if code and code != "INFO-000":
                raise RuntimeError(f"서울시 API 응답 {code}: {res.get('RESULT.MESSAGE') or res.get('MESSAGE')}")
            road_rows, summary, inc_rows = parse_city(d, ts)
            append_csv(os.path.join(outdir, "roads.csv"), ROAD_HEADER, road_rows)
            append_csv(os.path.join(outdir, "incidents.csv"), INCIDENT_HEADER, inc_rows)
            with gzip.open(os.path.join(outdir, "raw_citydata.jsonl.gz"), "at", encoding="utf-8") as g:
                g.write(json.dumps({"ts": ts, "data": d}, ensure_ascii=False) + "\n")
        except Exception as e:
            log_error(outdir, f"도시데이터 실패: {e}")
        # 2) 한국체육산업개발 실시간 주차 합계
        if not a.test_file:
            try:
                p = fetch_json(PARKING_URL)
                summary["주차합계_parking_sum"] = (p[0] if isinstance(p, list) and p else p).get("parking_sum")
            except Exception as e:
                log_error(outdir, f"주차 실패: {e}")
        # 3) 서울시 공영주차장 실시간(송파·강동) - 15분마다(5분 수집 3번에 1번)
        if not a.test_file and n % 3 == 0:
            try:
                lots = fetch_lots(key)
                append_csv(os.path.join(outdir, "parking_lots.csv"), LOT_HEADER, lot_csv_rows(lots, ts))
                if not lots:
                    log_error(outdir, "공영주차장: 송파·강동 주차장을 찾지 못함")
            except Exception as e:
                log_error(outdir, f"공영주차장 실패: {e}")
        append_csv(os.path.join(outdir, "summary.csv"), SUMMARY_HEADER,
                   [[ts] + [summary.get(h, "") for h in SUMMARY_HEADER[1:]]])
        n += 1
        print(f"{ts} #{n} 평균 {summary.get('지역평균속도_kmh')}km/h "
              f"정체 {summary.get('정체구간수')}곳 주차합계 {summary.get('주차합계_parking_sum')}")

        if a.git and n % COMMIT_EVERY == 0:
            git_commit(outdir)
        if a.test_file:
            break
        # 다음 5분 정각(00, 05, 10 ...)까지 대기
        t = now_kst()
        nxt = (t.replace(second=0, microsecond=0)
               + dt.timedelta(minutes=INTERVAL_MIN - t.minute % INTERVAL_MIN))
        if nxt > end:
            break
        time.sleep(max(1, (nxt - now_kst()).total_seconds()))

    if a.git:
        git_commit(outdir, final=True)
    print(f"끝. {n}회 수집 → {outdir}")


if __name__ == "__main__":
    main()
