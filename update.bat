@echo off
rem Daily 9am: rebuild the Naver blog link hub and push to GitHub Pages if anything changed.
chcp 65001 >nul
cd /d "%~dp0"
if not exist logs mkdir logs
set LOG=logs\update.log
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> "%LOG%"
git pull --ff-only -q >> "%LOG%" 2>&1
"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" naver_blog_sitemap.py zerisun88 --out "%TEMP%\naver_blog_out" --hub-dir . --site-url https://imwooha.github.io --blogger https://zerisun.blogspot.com >> "%LOG%" 2>&1
if errorlevel 1 (
  echo FAILED: script error >> "%LOG%"
  exit /b 1
)
git add index.html sitemap.xml robots.txt .nojekyll
git diff --cached --quiet
if errorlevel 1 (
  git -c user.name=imwooha -c user.email=imwooha@gmail.com commit -q -m "Update blog links %date%" >> "%LOG%" 2>&1
  git push -q >> "%LOG%" 2>&1 && echo pushed >> "%LOG%" || echo FAILED: push >> "%LOG%"
) else (
  echo no changes >> "%LOG%"
)
