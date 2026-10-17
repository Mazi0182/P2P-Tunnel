<div align="center">
  <img src="assets/app_icon.png" alt="P2P Tunnel" width="110" height="110" />
  <h1>P2P Tunnel</h1>
  <p><b>CGNAT Arkasından Port Açmadan ve Statik IP Gerektirmeden Doğrudan Uçtan Uca P2P Tünelleme</b></p>

  [![Protocol](https://img.shields.io/badge/Protokol-KCP%20Fast%20ARQ-18181b.svg)](https://github.com/skywind3000/kcp)
  [![Encryption](https://img.shields.io/badge/%C5%9Eifreleme-ChaCha20--Poly1305-27272a.svg)](https://en.wikipedia.org/wiki/ChaCha20-Poly1305)
  [![Python](https://img.shields.io/badge/Python-3.9%2B-3f3f46.svg)](https://www.python.org/)
  [![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-52525b.svg)](#kurulum)
</div>

---

## Genel Bakış

İnternet servis sağlayıcılarının kullandığı **CGNAT (Carrier-Grade NAT)** altyapısı, ev interneti üzerinden dış dünyaya port yönlendirmeyi (Port Forwarding) engeller. Merkezi VPN veya uzak aktarım (relay) sunucuları ise trafiği üçüncü bir noktadan dolaştırdığı için gecikmeyi (ping) artırır ve bant genişliğini kısıtlar.

**P2P Tunnel**, STUN ve şifreli sinyalleşme üzerinden **UDP Hole Punching** gerçekleştirerek istemci ile sunucu arasında doğrudan uçtan uca bağlantı kurar. Yerel ağda çalışan TCP servislerini port açmaya veya statik IP adresine ihtiyaç duymadan düşük gecikmeyle dış ağa ulaştırır.

---

## Ekran Görüntüleri

<div align="center">

### İstemci Masaüstü Arayüzü

<table>
  <tr>
    <td align="center">
      <b>Ana Ekran</b><br/><br/>
      <img width="260" alt="Ana Ekran" src="https://github.com/user-attachments/assets/dbc4454c-ac47-4139-9f77-ad346ebbf743" />
    </td>
    <td align="center">
      <b>Sunucular Sekmesi</b><br/><br/>
      <img width="260" alt="Sunucular Sekmesi" src="https://github.com/user-attachments/assets/8202c180-c97d-404a-b3dd-14170a4e02e0" />
    </td>
    <td align="center">
      <b>Bağlantı Sonrası Ekranı</b><br/><br/>
      <img width="260" alt="Bağlantı Sonrası Ekranı" src="https://github.com/user-attachments/assets/43323421-fa3e-4e97-8aaf-ada7d5fd03fd" />
    </td>
  </tr>
</table>

<br/>

### maziPanel Üzerindeki P2P Tünel Kontrol Paneli

<img width="900" alt="maziPanel P2P Tünel Kontrol Paneli" src="https://github.com/user-attachments/assets/ae29e21e-4939-4cdc-8e88-91819687ff3e" />

</div>

---

## Temel Özellikler

- **Doğrudan NAT Delme (UDP Hole Punching):** STUN uç nokta keşfi ve şifreli HTTPS sinyalleşmesi ile CGNAT arkasındaki iki cihazı aracı sunucu olmadan doğrudan eşleştirir.
- **KCP Fast ARQ Aktarım Katmanı:** UDP üzerinde güvenilir, sıralı ve düşük gecikmeli paket iletimi sağlar.
- **ChaCha20-Poly1305 AEAD Şifreleme:** Tüm tünel paketleri donanım hızlandırmalı olarak şifrelenir ve rastgele paket dolgusu (padding) ile DPI filtrelerine karşı korunur.
- **Sunucu Tarafından Belirlenen Servis Portu ve Bağlantı Adresi:**
  - Sunucu sahibi, paylaşılacak hedef TCP portunu (varsayılan `25565`) ve istemcilere gösterilecek bağlantı adresini (ör. `baglanti.localhost`) sunucu yapılandırmasından veya Web Yönetim Paneli üzerinden belirler.
  - Bağlantı kurulduğunda bu adres otomatik olarak istemci ekranına iletilir ve tek tıkla kopyalanabilir.
- **Rol Tabanlı Port İzolasyonu (ACL):**
  - **Oyuncu (`Role.PLAYER`):** Yalnızca sunucu sahibinin izin verdiği servis portuna erişebilir; diğer tüm yerel portlar güvenlik katmanında engellenir.
  - **Yönetici (`Role.ADMIN`):** Doğrulanan yönetici anahtarıyla SSH (`22`) ve yönetim paneline güvenli erişim sağlar.
- **Yerel Web Yönetim Paneli & maziPanel Entegrasyonu:** Harici web kütüphanesi gerektirmeyen, saf `asyncio` tabanlı bağımsız kontrol paneli (`http://127.0.0.1:9090`) veya entegre **maziPanel** arayüzü üzerinden aktif istemcileri, gecikme değerlerini, izin verilen servis portunu ve donanım kimliği (HWID) izinlerini yönetme imkanı sunar.

---

## Nasıl Çalışır?

Normal şartlarda standart internet bağlantılarında (özellikle CGNAT altyapısında) modem ve internet sağlayıcısının güvenlik duvarı, dışarıdan sunucuya doğrudan gelen tüm bağlantı isteklerini reddeder. Çünkü dışarıdan gelen paketin içeride hangi cihaza gideceğini bilmez ve güvenlik nedeniyle kapıyı kapalı tutar.

Ancak içerideki bir cihaz dışarıdaki bir adrese UDP paketi gönderdiğinde, modem ve operatör **"içerideki cihaz dışarıya bir soru sordu, birazdan aynı yerden cevabı gelecek"** diyerek güvenlik duvarında geçici bir dönüş kapısı (boşluk) açar. **P2P Tunnel** tam olarak bu davranışı kullanır:

```text
  [ İstemci (Oyuncu) ]                                                [ Sunucu ]
           |                                                              |
           |  1. STUN ile kendi dış IP ve port numarasını öğrenir         |
           |  2. Şifreli sinyalleşme ile adresleri birbirine haber verir  |
           |                                                              |
  =========|====================[ CGNAT / Güvenlik Duvarı ]===============|=========
           |                                                              |
           |  3. Dışarıya UDP paketi atar    3. Dışarıya UDP paketi atar  |
           |     (Duvar geçici boşluk açar)     (Duvar geçici boşluk açar)|
           |                 \                           /                |
           |              [ Açık Kapı ]         [ Açık Kapı ]             |
           |                     \                   /                    |
           |                      v                 v                     |
           |  4. Karşılıklı paketler açılan boşluktan içeri girer         |
           |     ve iki cihaz doğrudan UDP üzerinden el sıkışır           |
           |                                                              |
           +<=================[ Doğrudan Şifreli Tünel ]=================>+
                         (Aracı sunucu yok, doğrudan bağlantı)
```

1. **Dış Kapı Numaralarını Öğrenme (STUN):** Hem sunucu hem de bağlanacak oyuncu, internetteki genel bir STUN sunucusuna *"Beni dışarıdan hangi IP ve port numarasıyla görüyorsun?"* diye sorar. Böylece iki taraf da kendi dış kapı adresini öğrenir.
2. **Adresleri Haberdar Etme (Sinyalleşme):** Sunucu ve istemci, öğrendikleri bu dış IP ve port bilgilerini şifreli bir haberleşme kanalı üzerinden birbirine iletir. Artık iki taraf da karşısındakinin dış dünyadaki adresini bilmektedir.
3. **Aynı Anda Paket Gönderip Kapıyı Aralama (UDP Hole Punching):** İki cihaz aynı anda birbirinin dış adresine ardı ardına küçük UDP paketleri göndermeye başlar. İki taraf da dışarıya istek attığı için her iki tarafın modemi ve CGNAT güvenlik duvarı, karşıdan gelecek paketler için geçici birer kapı aralar.
4. **Doğrudan El Sıkışma ve Tünel:** Karşılıklı atılan paketler bu aralanan kapılardan içeri girer ve iki cihaz birbiriyle doğrudan el sıkışır. Bağlantı kurulduktan sonra aracı hiçbir sunucu kalmaz; veriler ve oyun paketleri doğrudan iki bilgisayar arasında şifreli olarak akar. Bağlantı açık kaldığı sürece düzenli sinyaller gönderilerek bu kapının kapanması engellenir.

---

## Kurulum

### Gereksinimler
- Python 3.9 veya üzeri

### Windows
```cmd
git clone https://github.com/Mazi0182/P2P-Tunnel.git
cd P2P-Tunnel
install.bat
```

### Linux (Headless Sunucu)
```bash
git clone https://github.com/Mazi0182/P2P-Tunnel.git
cd P2P-Tunnel
chmod +x install.sh
./install.sh
```

### Manuel Kurulum
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
pip install -r requirements.txt

# Linux (Sunucu / Headless)
source .venv/bin/activate
pip install -r requirements-headless.txt
```

---

## Kullanım

### 1. Sunucuyu Başlatma
Örnek yapılandırma dosyasını kopyalayın ve sunucuyu çalıştırın:
```bash
cp config/server_config.json.example config/server_config.json
python run_server.py
```
Sunucu başlatıldığında konsolda paylaşabileceğiniz **Bağlantı Kodu (`XXXX-YYYY`)** ve yerel **Web Yönetim Paneli (`http://127.0.0.1:9090`)** bilgileri görüntülenir.

### 2. İstemci ile Bağlanma
```bash
# Masaüstü Arayüzü (Windows)
python run_client.py

# Konsol (Headless) Modu
python client_headless.py --code XXXX-YYYY
```
1. İstemci arayüzünde **Sunucular** sekmesinden sunucu bağlantı kodunu ekleyin ve seçin.
2. Ana ekrandaki anahtara tıklayarak bağlantıyı başlatın.
3. Bağlantı kurulduğunda ekranda beliren sunucu adresini kopyalayarak doğrudan bağlanın.

---

## Proje Yapısı

```text
P2P-Tunnel/
├── assets/                  # Uygulama simgeleri
├── client/
│   ├── client_core.py       # İstemci tünel yönetimi ve yerel TCP vekilleri
│   └── gui/                 # PyQt6 yerel Windows masaüstü arayüzü
├── config/
│   └── server_config.json.example  # Örnek sunucu yapılandırma şablonu
├── core/
│   ├── crypto.py            # ChaCha20-Poly1305 şifreleme ve anahtar türetimi
│   ├── hwid.py              # Donanım kimliği (HWID) doğrulama
│   ├── identity.py          # İstemci kimlik yönetimi
│   ├── invite.py            # Sunucu davet kodu çözümleyici
│   ├── kcp.py               # KCP Fast ARQ protokol katmanı
│   ├── logger.py            # Log yönetimi
│   ├── paths.py             # Platform bağımsız dosya yolu yöneticisi
│   ├── protocol.py          # Çerçeveleme ve komut protokolü
│   ├── puncher.py           # UDP Hole Punching motoru
│   ├── signaling.py         # Şifreli sinyalleşme istemcisi
│   ├── stun.py              # STUN dış IP/Port keşif modülü
│   ├── tunnel.py            # Çift yönlü çoklamalı P2P tünel çekirdeği
│   ├── updater.py           # Otomatik sürüm kontrol ve güncelleme modülü
│   └── version_info.py      # Windows PE sürüm bilgisi oluşturucu
├── server/
│   ├── acl.py               # Rol tabanlı erişim kontrolü ve port güvenlik duvarı
│   ├── ban_manager.py       # HWID yasaklama yöneticisi
│   ├── history_manager.py   # Bağlantı geçmişi yöneticisi
│   ├── server_daemon.py     # Çoklu istemci destekli sunucu servisi
│   ├── version_manager.py   # Sunucu sürüm kontrol yöneticisi
│   └── web_panel.py         # Yerel HTTP web yönetim paneli
├── signaling_server/
│   └── rendezvous.py        # Özel UDP sinyalleşme sunucusu
├── build.bat                # EXE derleme başlatıcısı
├── build_exe.py             # PyInstaller derleme betiği
├── client_headless.py       # Konsol tabanlı istemci
├── install.bat              # Windows kurulum betiği
├── install.sh               # Linux kurulum betiği
├── run_client.py            # İstemci başlatıcısı
└── run_server.py            # Sunucu başlatıcısı
```
