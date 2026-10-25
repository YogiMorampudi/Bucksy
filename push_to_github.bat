@echo off
setlocal
echo =======================================================
echo          Bucksy - Push to GitHub Helper
echo =======================================================
echo.
set "PATH=%LOCALAPPDATA%\Programs\MinGit\cmd;%PATH%"

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git could not be located.
    pause
    exit /b 1
)

echo Checking Git status...
git status
echo.

set /p REPO_URL="Enter your GitHub Repository URL (e.g. https://github.com/USERNAME/bucksy.git): "
if "%REPO_URL%"=="" (
    echo [ERROR] No repository URL entered. Exiting.
    pause
    exit /b 1
)

git remote remove origin 2>nul
git remote add origin %REPO_URL%
git branch -M main

echo.
echo Pushing to GitHub (main branch)...
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo =======================================================
    echo [SUCCESS] Code pushed to GitHub successfully!
    echo Next step: Import this repo into Vercel and set your env vars.
    echo =======================================================
) else (
    echo.
    echo [NOTE] Push completed or prompt required credentials.
)
pause
