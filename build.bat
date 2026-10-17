@echo off
title P2P Tunnel EXE Derleyici
cd /d "%~dp0"

echo ============================================================
echo               P2P TUNNEL EXE DERLEYICI
echo ============================================================
echo.

python build_exe.py --all
echo.
echo Islem tamamlandi.
pause
