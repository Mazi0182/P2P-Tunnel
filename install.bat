@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title P2P Tunnel - Kurulum ve Ortam Hazirlayici
cd /d "%~dp0"

echo ============================================================
echo           P2P TUNNEL - KURULUM VE ORTAM HAZIRLAYICI
echo ============================================================
echo.

:: 1. Python Varlik Kontrolu
set "PY_CMD="
python --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PY_CMD=python"
) else (
    py -3 --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY_CMD=py -3"
    )
)

if "%PY_CMD%"=="" (
    echo [-] HATA: Python 3 bulunamadi!
    echo     Lutfen https://www.python.org/downloads/ adresinden Python 3.9+ indirin.
    echo     Kurulum sirasinda "Add Python to PATH" secenegini isaretlemeyi unutmayin.
    echo.
    pause
    exit /b 1
)

echo [*] Kullanilan Python surumu:
%PY_CMD% --version
echo.

:: 2. Sanal Ortam (.venv) Yonetimi
if not exist ".venv\Scripts\activate.bat" (
    echo [*] Sanal ortam [.venv] olusturuluyor...
    %PY_CMD% -m venv .venv
    if !errorlevel! neq 0 (
        echo [-] HATA: Sanal ortam [.venv] olusturulamadi!
        pause
        exit /b 1
    )
    echo [+] Sanal ortam basariyla olusturuldu.
) else (
    echo [*] Mevcut sanal ortam [.venv] algilandi.
)
echo.

:: 3. Sanal Ortami Aktif Et
call .venv\Scripts\activate.bat
if !errorlevel! neq 0 (
    echo [-] HATA: Sanal ortam aktif edilemedi!
    pause
    exit /b 1
)

:: 4. Argumanlari ve Kurulum Modunu Cozumle
set "REQ_FILE="
set "CLI_PANEL_MODE="

for %%A in (%*) do (
    if /i "%%~A"=="--headless" set "REQ_FILE=requirements-headless.txt"
    if /i "%%~A"=="--dev" set "REQ_FILE=requirements-dev.txt"
    if /i "%%~A"=="--full" set "REQ_FILE=requirements.txt"
    if /i "%%~A"=="--mazipanel" set "CLI_PANEL_MODE=mazipanel"
    if /i "%%~A"=="--standalone" set "CLI_PANEL_MODE=standalone"
)

if not "!REQ_FILE!"=="" goto :INSTALL_DEPS
if not "!CLI_PANEL_MODE!"=="" (
    set "REQ_FILE=requirements-headless.txt"
    goto :INSTALL_DEPS
)

:: Interaktif Menu
echo Kurulum modunu secin:
echo   [1] Standart Istemci (GUI + Tunel) - [Varsayilan]
echo   [2] Sunucu / Headless (Yonetim Paneli + KCP Tunel, GUI yok)
echo   [3] Gelistirici / Derleme (PyInstaller, R2 Auto-Deploy)
echo.
set /p SECIM="Seciminiz (1/2/3) [1]: "

if "%SECIM%"=="2" (
    set "REQ_FILE=requirements-headless.txt"
) else if "%SECIM%"=="3" (
    set "REQ_FILE=requirements-dev.txt"
) else (
    set "REQ_FILE=requirements.txt"
)

:INSTALL_DEPS
echo.
echo [*] pip guncelleniyor...
python -m pip install --upgrade pip --quiet

echo [*] Bagimliliklar yukleniyor [!REQ_FILE!]...
python -m pip install -r !REQ_FILE!
if !errorlevel! neq 0 (
    echo [-] HATA: Paketler yuklenirken bir sorun olustu!
    pause
    exit /b 1
)
echo [+] Bagimliliklar basariyla kuruldu.
echo.

:: 5. Ornek Konfigurasyon Dosyalarini Kopyala
if not exist "config" mkdir config

if not exist "config\server_config.json" (
    if exist "config\server_config.json.example" (
        copy /y "config\server_config.json.example" "config\server_config.json" >nul
        echo [+] config\server_config.json ornek sablondan olusturuldu.
        echo     Lutfen kendi sunucu bilgilerinizi guncelleyin.
    )
) else (
    echo [*] Mevcut config\server_config.json korundu.
)

:: 6. maziPanel Algilama ve Yonetim Paneli Modu Secimi
set "MAZIPANEL_DETECTED=0"
if exist "..\Panel" set "MAZIPANEL_DETECTED=1"
if exist "C:\mazideveloper" set "MAZIPANEL_DETECTED=1"

set "PANEL_MODE=standalone"
if not "!CLI_PANEL_MODE!"=="" (
    set "PANEL_MODE=!CLI_PANEL_MODE!"
    echo [*] Yonetim paneli modu CLI parametresi ile ayarlandi: !PANEL_MODE!
    goto :SAVE_PANEL_MODE
)

echo.
if "!MAZIPANEL_DETECTED!"=="1" (
    echo [*] Ipucu: Sisteminizde maziPanel dizini [..\Panel] tespit edildi.
    set "PANEL_MODE=mazipanel"
) else (
    echo [*] Ipucu: Sisteminizde maziPanel tespit edilmedi.
    set "PANEL_MODE=standalone"
)

set "PANEL_SECIM="
set /p PANEL_SECIM="Yönetim için maziPanel kullanıyor musunuz? (E = maziPanel üzerinden yönet, H = P2P Tunnel'ın kendi web panelini kur) [E/H]: "

if /i "!PANEL_SECIM!"=="E" set "PANEL_MODE=mazipanel"
if /i "!PANEL_SECIM!"=="EVET" set "PANEL_MODE=mazipanel"
if /i "!PANEL_SECIM!"=="Y" set "PANEL_MODE=mazipanel"
if /i "!PANEL_SECIM!"=="YES" set "PANEL_MODE=mazipanel"
if /i "!PANEL_SECIM!"=="H" set "PANEL_MODE=standalone"
if /i "!PANEL_SECIM!"=="HAYIR" set "PANEL_MODE=standalone"
if /i "!PANEL_SECIM!"=="N" set "PANEL_MODE=standalone"
if /i "!PANEL_SECIM!"=="NO" set "PANEL_MODE=standalone"

:SAVE_PANEL_MODE
python -c "import json, os; mode = os.environ.get('PANEL_MODE', 'standalone').strip(); paths = [r'config\server_config.json']; exec('try:\n from core.paths import get_server_config_path\n p = get_server_config_path()\n if os.path.exists(p) and os.path.abspath(p) != os.path.abspath(paths[0]): paths.append(p)\nexcept Exception: pass'); [ (lambda cp: (lambda d: (d.update({'panel_mode': mode}), os.makedirs(os.path.dirname(os.path.abspath(cp)), exist_ok=True), open(cp, 'w', encoding='utf-8').write(json.dumps(d, indent=2, ensure_ascii=False))))(json.load(open(cp, 'r', encoding='utf-8')) if os.path.exists(cp) else {}))(cp) for cp in paths ]"
echo [+] Yonetim paneli modu kaydedildi: !PANEL_MODE!

if "!REQ_FILE!"=="requirements-dev.txt" (
    if not exist "config\r2_config.json" (
        if exist "config\r2_config.json.example" (
            copy /y "config\r2_config.json.example" "config\r2_config.json" >nul
            echo [+] config\r2_config.json ornek sablondan olusturuldu.
        )
    )
)

echo.
echo ============================================================
echo                  KURULUM BASARIYLA TAMAMLANDI!
echo ============================================================
echo.
echo Programlari calistirmak icin:
echo   - GUI Istemci  : .venv\Scripts\python run_client.py
echo   - Sunucu Daemon: .venv\Scripts\python run_server.py
echo   - Headless     : .venv\Scripts\python client_headless.py
echo.
if "!CLI_PANEL_MODE!"=="" pause

