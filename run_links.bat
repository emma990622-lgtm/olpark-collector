@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 올림픽공원 주변 도로 58개 구간 수집
echo.
if "%SEOUL_API_KEY%"=="" set /p SEOUL_API_KEY=서울시 일반 인증키를 붙여넣고 엔터: 
set /p MIN=몇 분 동안 수집할까요? (1회만이면 0, 공연 날은 350): 
if "%MIN%"=="" set MIN=0
python collect_links.py --minutes %MIN%
echo.
echo 결과는 data 폴더의 links_날짜.csv 에 있습니다.
pause
