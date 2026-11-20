"""
'공연·날씨·입출차 연계 방문객 혼잡도 예측'용 외부 자료를 받는다. GitHub Actions(data/visitor-weather 갈래)에서 실행.
  1) 날씨(시간별): Open-Meteo 과거 기상(ERA5 기반, 인증키 없음, CC BY 4.0) — 올림픽공원 좌표
  2) 지하철 일별 역별 승하차: 서울 열린데이터광장 CardSubwayStatsNew (SEOUL_API_KEY) — 올림픽공원 주변 역만
  3) 지하철 월별 시간대별 승하차: 서울 열린데이터광장 CardSubwayTime (SEOUL_API_KEY) — 같은 역
  4) 생활인구 2026년 월별 파일: OA-14991 (인증키 없음) — 올림픽공원 동(11710566)만
인증키는 환경변수로만 받고 출력하지 않는다. 결과: data/visitor_weather/*.csv
"""
import csv
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta

OUT = "data/visitor_weather"
LAT, LON = 37.5207, 127.1214          # 올림픽공원(KSPO DOME 부근)
START = date(2024, 6, 1)
STATIONS = ("올림픽공원", "몽촌토성", "한성백제", "방이", "둔촌오륜")
KEY = os.environ.get("SEOUL_API_KEY", "").strip()
UA = {"User-Agent": "Mozilla/5.0 (olpark-collector)"}
os.makedirs(OUT, exist_ok=True)
log = []


def get(url, data=None, tries=4, timeout=60):
    for t in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:                       # 주소에 키가 있으므로 주소는 출력하지 않는다
            err = type(e).__name__
            time.sleep(5 * (t + 1))
    raise RuntimeError(f"요청 실패({err})")


def weather():
    end = date.today() - timedelta(days=2)
    q = {"latitude": LAT, "longitude": LON, "start_date": START.isoformat(), "end_date": end.isoformat(),
         "hourly": "temperature_2m,apparent_temperature,precipitation,rain,snowfall,relative_humidity_2m,wind_speed_10m,weather_code,cloud_cover",
         "timezone": "Asia/Seoul"}
    j = json.loads(get("https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(q), timeout=180))
    h = j["hourly"]
    cols = list(h.keys())
    with open(f"{OUT}/weather_hourly_openmeteo.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i in range(len(h["time"])):
            w.writerow([h[c][i] for c in cols])
    log.append(f"날씨: {len(h['time'])}시간 ({h['time'][0]} ~ {h['time'][-1]}), 단위 {json.dumps(j.get('hourly_units', {}), ensure_ascii=False)}")


def seoul(service, arg, start=1, end=1000):
    url = f"http://openapi.seoul.go.kr:8088/{KEY}/json/{service}/{start}/{end}/{arg}"
    j = json.loads(get(url))
    body = j.get(service) or {}
    rows = body.get("row") or []
    code = (body.get("RESULT") or j.get("RESULT") or {}).get("CODE", "")
    return rows, code, body.get("list_total_count", 0)


def subway_daily():
    path = f"{OUT}/subway_daily_olpark.csv"
    rows_out, cols, d, miss = [], None, START, []
    last = date.today() - timedelta(days=3)
    while d <= last:
        try:
            rows, code, total = seoul("CardSubwayStatsNew", d.strftime("%Y%m%d"))
            if total > 1000:
                more, _, _ = seoul("CardSubwayStatsNew", d.strftime("%Y%m%d"), 1001, 2000)
                rows += more
        except RuntimeError as e:
            rows, code = [], str(e)
        keep = [r for r in rows if any(s in str(r.get("SBWY_STNS_NM") or r.get("SUB_STA_NM") or "") for s in STATIONS)]
        if not keep:
            miss.append(f"{d}({code or '없음'})")
        for r in keep:
            cols = cols or list(r.keys())
            rows_out.append([r.get(c) for c in cols])
        d += timedelta(days=1)
        time.sleep(0.15)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if cols:
            w.writerow(cols)
            w.writerows(rows_out)
    log.append(f"지하철 일별: {len(rows_out)}줄, 비어 있는 날 {len(miss)}일" + (f" (예: {', '.join(miss[:5])}, 마지막 {miss[-1]})" if miss else ""))


def subway_hourly_month():
    path = f"{OUT}/subway_hourly_month_olpark.csv"
    rows_out, cols, miss = [], None, []
    y, m = START.year, START.month
    today = date.today()
    while (y, m) < (today.year, today.month):
        ym = f"{y}{m:02d}"
        try:
            rows, code, total = seoul("CardSubwayTime", ym)
            if total > 1000:
                more, _, _ = seoul("CardSubwayTime", ym, 1001, 2000)
                rows += more
        except RuntimeError as e:
            rows, code = [], str(e)
        keep = [r for r in rows if any(s in str(r.get("STTN") or r.get("SUB_STA_NM") or "") for s in STATIONS)]
        if not keep:
            miss.append(f"{ym}({code or '없음'})")
        for r in keep:
            cols = cols or list(r.keys())
            rows_out.append([r.get(c) for c in cols])
        m += 1
        if m == 13:
            y, m = y + 1, 1
        time.sleep(0.3)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if cols:
            w.writerow(cols)
            w.writerows(rows_out)
    log.append(f"지하철 월별 시간대: {len(rows_out)}줄, 비어 있는 달 {len(miss)}개" + (f" ({', '.join(miss)})" if miss else ""))


def living_pop_2026():
    path = f"{OUT}/oryun_living_pop_2026.csv"
    header, lines, got, miss = None, [], [], []
    for mm in range(1, 13):
        ym = f"26{mm:02d}"
        data = urllib.parse.urlencode({"infId": "OA-14991", "infSeq": "3", "seq": ym, "seqNo": ""}).encode()
        try:
            b = get("https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false", data=data, tries=2, timeout=300)
            z = zipfile.ZipFile(io.BytesIO(b))
            txt = z.read(z.namelist()[0]).decode("utf-8-sig", errors="replace")
        except Exception:
            miss.append(ym)
            continue
        rows = txt.splitlines()
        header = header or rows[0]
        k = [r for r in rows[1:] if r.replace('"', "").split(",")[2:3] == ["11710566"]]
        lines += k
        got.append(f"{ym}:{len(k)}")
    if header:
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + "\n" + "\n".join(lines) + "\n")
    log.append(f"생활인구 2026: {', '.join(got) or '없음'}; 아직 없음 {', '.join(miss)}")


if __name__ == "__main__":
    for name, fn in (("weather", weather), ("subway_daily", subway_daily), ("subway_hourly_month", subway_hourly_month), ("living_pop_2026", living_pop_2026)):
        if name.startswith("subway") and not KEY:
            log.append(f"{name}: SEOUL_API_KEY 없음 → 건너뜀")
            continue
        try:
            fn()
        except Exception as e:
            log.append(f"{name}: 실패 {type(e).__name__}: {str(e)[:120]}")
    txt = "\n".join(log)
    print(txt)
    open(f"{OUT}/README_fetch_log.txt", "w", encoding="utf-8").write(txt + "\n")
