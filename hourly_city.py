#!/usr/bin/env python3
"""매시간 올림픽공원 일대 기록 (공연이 없는 날 포함, 평소 기준 만들기)

행정안전부 지역축제장 안전관리 매뉴얼의 인파 단계는 '평소(1개월 평균) 대비 몇 %'를 함께 본다.
공연일만 모으면 평소 값이 없어서, 매시간 한 줄씩 남긴다.
  data/hourly/summary_YYYY-MM.csv   collect.py의 summary와 같은 칸(도로·실시간 인구·버스·주차 합계·날씨)
  data/hourly/ppltn_fcst_YYYY-MM.csv 서울시가 내는 앞으로 12시간 인구 예측(우리 예측과 비교용)

  python hourly_city.py --git      (SEOUL_API_KEY 환경변수 필요, 값은 출력하지 않음)
"""
import argparse
import os
import subprocess
import urllib.parse

from collect import PARKING_URL, PLACE, SEOUL_URL, SUMMARY_HEADER, append_csv, fetch_json, now_kst, parse_city

OUT = os.path.join("data", "hourly")
FCST_HEADER = ["수집시각", "인구갱신시각", "예측시각", "예측혼잡도", "예측인구최소", "예측인구최대"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--git", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("SEOUL_API_KEY", "").strip()
    if not key:
        raise SystemExit("SEOUL_API_KEY 환경변수가 없습니다")
    os.makedirs(OUT, exist_ok=True)
    t = now_kst()
    ts = f"{t:%Y-%m-%d %H:%M:%S}"
    d = fetch_json(SEOUL_URL.format(key=key, place=urllib.parse.quote(PLACE)))
    _, summary, _ = parse_city(d, ts)
    summary["수집시각"] = ts
    try:
        p = fetch_json(PARKING_URL)
        summary["주차합계_parking_sum"] = (p[0] if isinstance(p, list) and p else p).get("parking_sum")
    except Exception as e:                       # 주차 API가 안 돼도 나머지는 남긴다
        print("주차 합계 실패:", type(e).__name__)
    append_csv(os.path.join(OUT, f"summary_{t:%Y-%m}.csv"), SUMMARY_HEADER, [[summary.get(h) for h in SUMMARY_HEADER]])
    pp = ((d.get("CITYDATA") or {}).get("LIVE_PPLTN_STTS") or [{}])[0]
    rows = [[ts, pp.get("PPLTN_TIME"), f.get("FCST_TIME"), f.get("FCST_CONGEST_LVL"), f.get("FCST_PPLTN_MIN"), f.get("FCST_PPLTN_MAX")]
            for f in (pp.get("FCST_PPLTN") or [])]
    if rows:
        append_csv(os.path.join(OUT, f"ppltn_fcst_{t:%Y-%m}.csv"), FCST_HEADER, rows)
    print(ts, "인구", summary.get("인구혼잡도"), summary.get("인구최소"), "~", summary.get("인구최대"),
          "주차", summary.get("주차합계_parking_sum"), "예측", len(rows), "줄")
    if a.git:
        for c in (["git", "add", OUT], ["git", "commit", "-m", f"매시간 기록 {t:%m-%d %H시}"],
                  ["git", "pull", "--rebase", "--autostash"], ["git", "push"]):
            subprocess.run(c, check=False)


if __name__ == "__main__":
    main()
