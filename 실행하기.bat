@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo ========================================
echo   모임결정 웹 프로그램 실행 준비
echo ========================================
echo.

set "PYTHON_COMMAND="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_COMMAND=py -3"

if not defined PYTHON_COMMAND (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_COMMAND=python"
)

if not defined PYTHON_COMMAND (
    echo [오류] Python이 설치되어 있지 않거나 PATH에 등록되지 않았습니다.
    echo.
    echo Python 3.11 이상을 설치한 뒤 다시 실행해 주세요.
    echo 설치 주소: https://www.python.org/downloads/
    echo 설치 화면에서 "Add Python to PATH"를 반드시 체크해 주세요.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 프로젝트 전용 Python 환경을 생성합니다...
    call %PYTHON_COMMAND% -m venv .venv
    if errorlevel 1 goto :failed
) else (
    echo [1/3] 기존 프로젝트 환경을 사용합니다.
)

echo [2/3] 필요한 패키지를 확인하고 설치합니다...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

echo [3/3] 웹 서버를 실행합니다.
echo 브라우저가 자동으로 열리지 않으면 http://localhost:5000 에 접속하세요.
echo 서버를 종료하려면 이 창에서 Ctrl+C를 누르세요.
echo.
".venv\Scripts\python.exe" app.py

echo.
echo 서버가 종료되었습니다.
pause
exit /b 0

:failed
echo.
echo [오류] 설치 또는 실행 준비 중 문제가 발생했습니다.
echo 인터넷 연결과 Python 설치 상태를 확인한 뒤 다시 실행해 주세요.
echo.
pause
exit /b 1
