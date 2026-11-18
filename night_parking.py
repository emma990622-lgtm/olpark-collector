#!/usr/bin/env python3
"""새벽 공원 주차 합계 기록 (하루 한 번)

한국체육산업개발 실시간 주차현황(parking_sum)은 출차 기록이 없는 장기 주차 차량까지 세어서
실제보다 많게 나온다(공공데이터포털 설명: "장기 주차인 경우 종료일이 표기되지 않아 실제 주차대수가 정확하지 않을 수 있음").
2024년 7월 입출차 기록으로 보면 새벽 4시 반에 실제로 서 있는 차는 약 60대(30~136대)인데,
2026-11-18 00:33 실시간 값은 1,085대였다. 그래서 매일 새벽 값을 남겨 두고, 웹에서
'실시간 값 − (새벽 값 − 60)'으로 실제에 가까운 대수를 계산한다.

  python night_parking.py --git
"""
import argparse
import csv
import os
import subprocess

from collect import PARKING_URL, fetch_json, now_kst

OUT = os.path.join("data", "parking_night.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--git", action="store_true")
    a = ap.parse_args()
    p = fetch_json(PARKING_URL)
    x = p[0] if isinstance(p, list) and p else p
    s = x.get("parking_sum")
    t = now_kst()
    new = not os.path.exists(OUT)
    with open(OUT, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "time", "parking_sum"])
        w.writerow([f"{t:%Y-%m-%d}", f"{t:%H:%M}", s])
    print(f"{t:%Y-%m-%d %H:%M} parking_sum={s}")
    if a.git:
        for c in (["git", "add", OUT], ["git", "commit", "-m", f"새벽 주차 합계 {t:%m-%d}"],
                  ["git", "pull", "--rebase", "--autostash"], ["git", "push"]):
            subprocess.run(c, check=False)


if __name__ == "__main__":
    main()
