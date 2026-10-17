#!/usr/bin/env bash
# ==============================================================================
# P2P Tunnel - Linux Kurulum ve Ortam Hazirlayici
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "          P2P TUNNEL - LINUX KURULUM BETIGI"
echo "============================================================"
echo ""

# 1. Python 3 Kontrolu
if ! command -v python3 &>/dev/null; then
    echo "[-] HATA: python3 bulunamadi!"
    echo "    Lutfen sisteminize Python 3 yukleyin:"
    echo "    Debian/Ubuntu: sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip"
    echo "    RHEL/CentOS  : sudo dnf install -y python3 python3-pip"
    echo "    Arch Linux   : sudo pacman -S python python-pip"
    exit 1
fi

PY_VER=$(python3 --version 2>&1)
echo "[*] Bulunan Python: $PY_VER"

# python3-venv modulu kontrolu
if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "[-] HATA: 'python3 -m venv' modulu yuklu degil!"
    echo "    Debian/Ubuntu icin: sudo apt-get install -y python3-venv"
    exit 1
fi

# 2. Sanal Ortam (.venv)
if [ ! -d ".venv" ] || [ ! -f ".venv/bin/activate" ]; then
    echo "[*] Sanal ortam (.venv) olusturuluyor..."
    python3 -m venv .venv
    echo "[+] Sanal ortam basariyla olusturuldu."
else
    echo "[*] Mevcut sanal ortam (.venv) algilandi."
fi

# 3. Sanal Ortami Aktif Et
# shellcheck disable=SC1091
source .venv/bin/activate

# 4. Argumanlari ve Kurulum Modunu Cozumle
REQ_FILE=""
CLI_PANEL_MODE=""

for arg in "$@"; do
    case "$arg" in
        --headless)
            REQ_FILE="requirements-headless.txt"
            ;;
        --gui)
            REQ_FILE="requirements.txt"
            ;;
        --dev)
            REQ_FILE="requirements-dev.txt"
            ;;
        --mazipanel)
            CLI_PANEL_MODE="mazipanel"
            ;;
        --standalone)
            CLI_PANEL_MODE="standalone"
            ;;
    esac
done

if [ -z "$REQ_FILE" ]; then
    # Eger ekransiz bir oturumdaysa (SSH vb.) veya otomatik bayrak verildiyse varsayilan headless olsun
    if [ -n "$CLI_PANEL_MODE" ] || [ ! -t 0 ] || { [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; }; then
        echo "[*] Grafik arayuz (DISPLAY) bulunamadi veya otomatik kurulum secildi, sunucu/headless modu aktif."
        REQ_FILE="requirements-headless.txt"
    else
        echo "Kurulum modunu secin:"
        echo "  [1] Sunucu / Headless (Yonetim Paneli + KCP Tunel, GUI yok) - [Varsayilan]"
        echo "  [2] Standart Istemci (GUI + Tunel - X11/PyQt6 gerektirir)"
        echo "  [3] Gelistirici / Derleme (PyInstaller, R2 Deploy)"
        echo ""
        read -r -p "Seciminiz (1/2/3) [1]: " SECIM
        case "$SECIM" in
            2) REQ_FILE="requirements.txt" ;;
            3) REQ_FILE="requirements-dev.txt" ;;
            *) REQ_FILE="requirements-headless.txt" ;;
        esac
    fi
fi

echo ""
echo "[*] pip guncelleniyor..."
pip install --upgrade pip --quiet

echo "[*] Bagimliliklar yukleniyor ($REQ_FILE)..."
pip install -r "$REQ_FILE"
echo "[+] Bagimliliklar basariyla kuruldu."
echo ""

# 5. Ornek Konfigurasyon Dosyalarini Kopyala
mkdir -p config

if [ ! -f "config/server_config.json" ]; then
    if [ -f "config/server_config.json.example" ]; then
        cp "config/server_config.json.example" "config/server_config.json"
        chmod 600 "config/server_config.json"
        echo "[+] config/server_config.json ornek sablondan olusturuldu (izin: 600)."
        echo "    Lutfen kendi sunucu bilgilerinizi duzenleyin."
    fi
else
    echo "[*] Mevcut config/server_config.json korundu."
fi

# 6. maziPanel Algilama ve Yonetim Paneli Modu Secimi
MAZIPANEL_DETECTED=0
if [ -d "/mazideveloper" ] || [ -d "../Panel" ] || [ -f "/etc/systemd/system/mazipanel.service" ]; then
    MAZIPANEL_DETECTED=1
elif command -v systemctl &>/dev/null; then
    if systemctl --user list-unit-files 2>/dev/null | grep -qi "mazipanel" || systemctl list-unit-files 2>/dev/null | grep -qi "mazipanel"; then
        MAZIPANEL_DETECTED=1
    fi
fi

PANEL_MODE="standalone"
if [ -n "$CLI_PANEL_MODE" ]; then
    PANEL_MODE="$CLI_PANEL_MODE"
    echo "[*] Yonetim paneli modu CLI parametresi ile ayarlandi: $PANEL_MODE"
elif [ -t 0 ]; then
    echo ""
    if [ "$MAZIPANEL_DETECTED" -eq 1 ]; then
        echo "[*] Ipucu: Sisteminizde maziPanel kurulumu tespit edildi."
    else
        echo "[*] Ipucu: Sisteminizde maziPanel tespit edilmedi (varsayilan: kendi web paneli)."
    fi
    read -r -p "Yönetim için maziPanel kullanıyor musunuz? (E = maziPanel üzerinden yönet, H = P2P Tunnel'ın kendi web panelini kur) [E/H]: " PANEL_SECIM
    case "$PANEL_SECIM" in
        [EeYy]*|[Ee][Vv][Ee][Tt])
            PANEL_MODE="mazipanel"
            ;;
        [HhNn]*|[Hh][Aa][Yy][Iiı][Rr])
            PANEL_MODE="standalone"
            ;;
        *)
            if [ "$MAZIPANEL_DETECTED" -eq 1 ]; then
                PANEL_MODE="mazipanel"
            else
                PANEL_MODE="standalone"
            fi
            ;;
    esac
else
    if [ "$MAZIPANEL_DETECTED" -eq 1 ]; then
        PANEL_MODE="mazipanel"
    else
        PANEL_MODE="standalone"
    fi
fi

PANEL_MODE="$PANEL_MODE" python3 -c '
import json, os
mode = os.environ.get("PANEL_MODE", "standalone")
paths = ["config/server_config.json"]
try:
    from core.paths import get_server_config_path
    sys_cfg = get_server_config_path()
    if os.path.exists(sys_cfg) and os.path.abspath(sys_cfg) != os.path.abspath(paths[0]):
        paths.append(sys_cfg)
except Exception:
    pass
for cfg_path in paths:
    data = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data["panel_mode"] = mode
    os.makedirs(os.path.dirname(os.path.abspath(cfg_path)), exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
'
echo "[+] Yonetim paneli modu kaydedildi: $PANEL_MODE"

if [ "$REQ_FILE" = "requirements-dev.txt" ]; then
    if [ ! -f "config/r2_config.json" ] && [ -f "config/r2_config.json.example" ]; then
        cp "config/r2_config.json.example" "config/r2_config.json"
        chmod 600 "config/r2_config.json"
        echo "[+] config/r2_config.json ornek sablondan olusturuldu (izin: 600)."
    fi
fi

echo ""
echo "============================================================"
echo "               KURULUM BASARIYLA TAMAMLANDI!"
echo "============================================================"
echo ""
echo "Programlari calistirmak icin:"
echo "  - Sunucu Daemon : .venv/bin/python run_server.py"
echo "  - Headless Client: .venv/bin/python client_headless.py"
if [ "$REQ_FILE" = "requirements.txt" ]; then
    echo "  - GUI Istemci   : .venv/bin/python run_client.py"
fi
echo ""
