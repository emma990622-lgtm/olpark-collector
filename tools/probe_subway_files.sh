#!/bin/bash
# OA-12914(지하철 일별 역별 승하차 월별 파일) 내려받는 방법 찾기용: 페이지 HTML을 저장한다.
set +e
mkdir -p data/visitor_weather/probe
curl -sS -L -A "Mozilla/5.0" "https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do" -o data/visitor_weather/probe/page.html
grep -oE "(downloadFile|fn_?[A-Za-z]*[Dd]own[A-Za-z]*)\([^)]*\)" data/visitor_weather/probe/page.html | sort | uniq -c | head -60 > data/visitor_weather/probe/calls.txt
grep -oE "[a-zA-Z/_.]*(down|Down)[a-zA-Z/_.]*\.do" data/visitor_weather/probe/page.html | sort | uniq -c >> data/visitor_weather/probe/calls.txt
grep -n -iE "seq|infSeq|fileNm|CARD_SUBWAY" data/visitor_weather/probe/page.html | head -80 > data/visitor_weather/probe/grep.txt
# 생활인구와 같은 대용량 파일 경로 시도
for s in 1 2; do for q in 202301 2301 1; do
  curl -sS -L -A "Mozilla/5.0" -e "https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do" -X POST \
    "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false" \
    --data-urlencode "infId=OA-12914" --data-urlencode "infSeq=$s" --data-urlencode "seq=$q" --data-urlencode "seqNo=" -o t.bin
  echo "bigfile infSeq=$s seq=$q -> $(stat -c%s t.bin) bytes $(head -c 60 t.bin | tr -dc '[:print:]' | head -c 60)" >> data/visitor_weather/probe/try.txt
done; done
wc -c data/visitor_weather/probe/*
