#!/usr/bin/env python3
"""올림픽공원 주변 도로 58개 구간 한꺼번에 수집 (서울시 실시간 도로소통정보)

olpark_links_58.csv 에 적힌 LINK_ID마다 서울시 '실시간 도로 소통 정보' API(TrafficInfo)를 불러
구간별 속도·통행시간을 한 번에 CSV로 저장합니다. 파이썬 표준 라이브러리만 씁니다.

사용 예)
  python collect_links.py                      # 58개 구간 1회 수집
  python collect_links.py --minutes 350        # 350분 동안 5분마다 반복 수집
  python collect_links.py --minutes 350 --git  # GitHub Actions용: 30분마다 커밋

서울시 인증키는 환경변수 SEOUL_API_KEY 로 넘깁니다(코드에 적지 마세요).
"""
import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

KST = dt.timezone(dt.timedelta(hours=9))
BASE = "http://openapi.seoul.go.kr:8088/{key}/xml/{service}/1/5/{link_id}"
INTERVAL_MIN = 5
COMMIT_EVERY = 6
HERE = os.path.dirname(os.path.abspath(__file__))

HEADER = ["수집시각", "LINK_ID", "도로명", "시작지점", "끝지점", "길이_m",
          "속도_kmh", "통행시간_초", "혼잡단계_계산", "결과코드", "응답원문"]


def now_kst():
    return dt.datetime.now(KST)


def load_links(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or "LINK_ID" not in rows[0]:
        sys.exit(f"{path} 에 LINK_ID 열이 없습니다.")
    return rows


def level(spd):
    """서울시 일반도로 표출 기준: 15 이하 정체, 15~25 서행, 25 이상 원활"""
    try:
        v = float(spd)
    except (TypeError, ValueError):
        return ""
    return "정체" if v <= 15 else ("서행" if v < 25 else "원활")


def fetch_link(key, service, link_id, timeout=15, tries=3):
    """한 구간 호출 → (결과코드, row dict). 실패하면 예외."""
    url = BASE.format(key=key, service=service, link_id=link_id)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "olpark-collector/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            return parse_xml(body)
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}")


def parse_xml(body):
    root = ET.fromstring(body)
    code_el = root.find(".//RESULT/CODE")
    if code_el is None:
        code_el = root.find(".//CODE")
    code = (code_el.text or "").strip() if code_el is not None else ""
    row_el = root.find(".//row")
    row = {c.tag: (c.text or "").strip() for c in row_el} if row_el is not None else {}
    if not row and code and code != "INFO-000":
        msg_el = root.find(".//MESSAGE")
        raise RuntimeError(f"{code} {msg_el.text if msg_el is not None else ''}".strip())
    return code, row


def append_rows(path, rows):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
        w.writerows(rows)


def git_commit(paths, msg):
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return
    subprocess.run(["git", "add"] + paths, capture_output=True)
    subprocess.run(["git", "commit", "-m", msg], capture_output=True)
    for _ in range(3):  # 다른 수집 작업과 동시에 올릴 때 충돌하면 다시 시도
        subprocess.run(["git", "pull", "--rebase", "--autostash"], capture_output=True)
        if subprocess.run(["git", "push"], capture_output=True).returncode == 0:
            return
        time.sleep(5)
    print("[git] push 실패", file=sys.stderr)


def collect_once(key, service, links, out_csv, err_log, pause):
    ts = f"{now_kst():%Y-%m-%d %H:%M:%S}"
    rows, fails = [], 0
    for ln in links:
        lid = ln["LINK_ID"].strip()
        try:
            code, row = fetch_link(key, service, lid)
            spd = row.get("prcs_spd") or row.get("PRCS_SPD") or ""
            trv = row.get("prcs_trv_time") or row.get("PRCS_TRV_TIME") or ""
            rows.append([ts, lid, ln.get("도로명", ""), ln.get("시작지점", ""), ln.get("끝지점", ""),
                         ln.get("길이(m)", ""), spd, trv, level(spd), code,
                         json.dumps(row, ensure_ascii=False)])
        except Exception as e:
            fails += 1
            rows.append([ts, lid, ln.get("도로명", ""), ln.get("시작지점", ""), ln.get("끝지점", ""),
                         ln.get("길이(m)", ""), "", "", "", "실패", str(e)[:200]])
            with open(err_log, "a", encoding="utf-8") as f:
                f.write(f"{ts} LINK_ID {lid}: {e}\n")
        time.sleep(pause)
    append_rows(out_csv, rows)
    lv = [r[8] for r in rows]
    print(f"{ts} {len(rows)}개 구간 · 정체 {lv.count('정체')} 서행 {lv.count('서행')} "
          f"원활 {lv.count('원활')} · 실패 {fails}")
    return fails


def main():
    ap = argparse.ArgumentParser(description="올림픽공원 주변 도로 58개 구간 한꺼번에 수집")
    ap.add_argument("--links", default=os.path.join(HERE, "olpark_links_58.csv"), help="구간 목록 CSV")
    ap.add_argument("--minutes", type=int, default=0, help="반복 수집 시간(분). 0이면 1회만")
    ap.add_argument("--outdir", default="data", help="저장 폴더")
    ap.add_argument("--service", default="TrafficInfo", help="서울시 API 서비스명(샘플 URL과 다르면 바꾸기)")
    ap.add_argument("--pause", type=float, default=0.2, help="구간 사이 대기(초)")
    ap.add_argument("--git", action="store_true", help="30분마다 저장소에 커밋·푸시(GitHub Actions용)")
    a = ap.parse_args()

    key = os.environ.get("SEOUL_API_KEY", "").strip()
    if not key:
        sys.exit("환경변수 SEOUL_API_KEY 가 비어 있습니다. README의 설정 방법을 보세요.")
    links = load_links(a.links)

    start = now_kst()
    os.makedirs(a.outdir, exist_ok=True)
    out_csv = os.path.join(a.outdir, f"links_{start:%Y-%m-%d}.csv")   # 하루 한 파일에 이어서 저장
    err_log = os.path.join(a.outdir, f"links_errors_{start:%Y-%m-%d}.log")
    print(f"{len(links)}개 구간 → {out_csv}")

    end = start + dt.timedelta(minutes=a.minutes)
    n = 0
    while True:
        fails = collect_once(key, a.service, links, out_csv, err_log, a.pause)
        n += 1
        if n == 1 and fails == len(links):
            print("모든 구간이 실패했습니다. 오류 기록을 보세요:", err_log, file=sys.stderr)
            print("(인증키, 서비스명, 해외 접속 차단 여부를 확인하세요)", file=sys.stderr)
        if a.git and n % COMMIT_EVERY == 0:
            git_commit([out_csv, err_log], f"도로 58구간 {now_kst():%m-%d %H:%M}")
        t = now_kst()
        nxt = (t.replace(second=0, microsecond=0)
               + dt.timedelta(minutes=INTERVAL_MIN - t.minute % INTERVAL_MIN))
        if a.minutes <= 0 or nxt > end:
            break
        time.sleep(max(1, (nxt - now_kst()).total_seconds()))

    if a.git:
        git_commit([out_csv, err_log], f"도로 58구간 {now_kst():%m-%d %H:%M} (완료)")
    print(f"끝. {n}회 수집 → {out_csv}")


if __name__ == "__main__":
    main()
