"""
P2P Tunnel In-Window Server Configuration Page.
Embedded inside the main window's AnimatedStack with downward-opening dropdown,
minimal parenthetical-free labels, 180Hz animations, and immediate persistence on server deletion.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)

from core.invite import normalize_server_key
from client.gui.widgets import (
    AnimatedButton, AnimatedLineEdit, DownwardDropdown, HighHzAnimator, ease_out_cubic
)


class ServerConfigPage(QWidget):
    """
    In-window page for adding, editing, selecting, and deleting server profiles.
    Emits:
    - `saved(name, code, admin_key, saved_servers)` when 'Kaydet' is clicked.
    - `servers_updated(name, code, admin_key, saved_servers)` immediately when 'Sil' is clicked.
    - `cancelled()` when 'Geri' or 'Vazgeç' is clicked.
    """
    saved = pyqtSignal(str, str, str, list)
    servers_updated = pyqtSignal(str, str, str, list)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageConfig")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.saved_servers = []
        self._admin_expanded = False
        self._theme = "dark"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # 1. Top Navigation Row
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.btn_back = AnimatedButton("← Geri", variant="subtle", radius=8, font_size=12, padding="5px 12px", parent=self)
        self.btn_back.clicked.connect(self.cancelled.emit)
        top_row.addWidget(self.btn_back)

        lbl_title = QLabel("Sunucu Ayarları", self)
        lbl_title.setObjectName("PageTitle")
        top_row.addWidget(lbl_title)
        top_row.addStretch()
        layout.addLayout(top_row)

        # 2. Form Card
        form_card = QFrame(self)
        form_card.setObjectName("FormCard")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(16, 16, 16, 16)
        form_layout.setSpacing(10)

        # Saved Servers Selector (Strictly Downward Dropdown)
        lbl_saved = QLabel("KAYITLI SUNUCULAR", form_card)
        lbl_saved.setObjectName("SectionHeader")
        form_layout.addWidget(lbl_saved)

        saved_row = QHBoxLayout()
        saved_row.setSpacing(8)

        self.combo_servers = DownwardDropdown(form_card)
        self.combo_servers.currentIndexChanged.connect(self._on_combo_changed)

        self.btn_delete = AnimatedButton("Sil", variant="danger", radius=8, font_size=12, padding="6px 12px", parent=form_card)
        self.btn_delete.setFixedSize(54, 36)
        self.btn_delete.clicked.connect(self._on_delete_selected_server)

        saved_row.addWidget(self.combo_servers, 1)
        saved_row.addWidget(self.btn_delete)
        form_layout.addLayout(saved_row)

        # Subtle Divider
        self.div = QFrame(form_card)
        self.div.setObjectName("FormDivider")
        self.div.setFixedHeight(1)
        form_layout.addWidget(self.div)

        # Server Name Input
        lbl_name = QLabel("SUNUCU ADI", form_card)
        lbl_name.setObjectName("SectionHeader")
        form_layout.addWidget(lbl_name)

        self.input_name = AnimatedLineEdit(form_card)
        self.input_name.setPlaceholderText("Örn: Oyun Sunucusu")
        self.input_name.setFixedHeight(36)
        self.input_name.returnPressed.connect(self._on_save_clicked)
        form_layout.addWidget(self.input_name)

        # Server Code Input
        lbl_code = QLabel("BAĞLANTI KODU", form_card)
        lbl_code.setObjectName("SectionHeader")
        form_layout.addWidget(lbl_code)

        self.input_code = AnimatedLineEdit(form_card)
        self.input_code.setPlaceholderText("Örn: A1B2-C3D4")
        self.input_code.setFixedHeight(36)
        self.input_code.returnPressed.connect(self._on_save_clicked)
        form_layout.addWidget(self.input_code)

        # Admin Key Collapsible Section (Animated Reveal)
        admin_header_row = QHBoxLayout()
        self.btn_toggle_admin = QPushButton("Yönetici Anahtarı ▸", form_card)
        self.btn_toggle_admin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_admin.setFixedHeight(22)
        self.btn_toggle_admin.clicked.connect(self._toggle_admin_field)
        admin_header_row.addWidget(self.btn_toggle_admin)
        admin_header_row.addStretch()
        form_layout.addLayout(admin_header_row)

        self.input_admin_key = AnimatedLineEdit(form_card)
        self.input_admin_key.setPlaceholderText("Yönetici anahtarı")
        self.input_admin_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_admin_key.setFixedHeight(0)
        self.input_admin_key.setVisible(False)
        self.input_admin_key.returnPressed.connect(self._on_save_clicked)
        form_layout.addWidget(self.input_admin_key)

        self._admin_anim = HighHzAnimator(duration_ms=170, easing=ease_out_cubic, parent=self)
        self._admin_anim.valueChanged.connect(self._on_admin_anim_step)
        self._admin_anim.finished.connect(self._on_admin_anim_done)

        layout.addWidget(form_card)
        layout.addStretch()

        # 3. Bottom Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.btn_cancel = AnimatedButton("Vazgeç", variant="subtle", radius=9, font_size=12, padding="8px 16px", parent=self)
        self.btn_cancel.setFixedHeight(38)
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = AnimatedButton("Kaydet", variant="dark", radius=9, font_size=12, padding="8px 22px", parent=self)
        self.btn_save.setFixedHeight(38)
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)
        self.set_theme(self._theme)

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        for btn in (self.btn_back, self.btn_delete, self.btn_cancel, self.btn_save):
            btn.set_theme(self._theme)
        for inp in (self.input_name, self.input_code, self.input_admin_key):
            inp.set_theme(self._theme)
        self.combo_servers.set_theme(self._theme)

        if self._theme == "dark":
            self.btn_toggle_admin.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    color: #8e8e99;
                    font-size: 11.5px;
                    font-weight: 700;
                    text-align: left;
                    padding: 0px;
                }
                QPushButton:hover {
                    color: #f4f4f6;
                }
            """)
        else:
            self.btn_toggle_admin.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    color: #52525b;
                    font-size: 11.5px;
                    font-weight: 700;
                    text-align: left;
                    padding: 0px;
                }
                QPushButton:hover {
                    color: #141417;
                }
            """)

    def _on_admin_anim_step(self, val: float):
        self.input_admin_key.setFixedHeight(int(val))

    def _on_admin_anim_done(self):
        if not self._admin_expanded:
            self.input_admin_key.setVisible(False)

    def load_data(
        self,
        saved_servers: list,
        current_name: str,
        current_code: str,
        current_admin_key: str,
    ):
        clean_curr_code = normalize_server_key(current_code)
        self.saved_servers = []
        for s in (saved_servers or []):
            item = dict(s)
            if item.get("code"):
                item["code"] = normalize_server_key(item["code"])
            self.saved_servers.append(item)

        self.input_name.setText(current_name)
        self.input_code.setText(clean_curr_code)
        self.input_admin_key.setText(current_admin_key)

        has_admin = bool((current_admin_key or "").strip())
        self._admin_expanded = has_admin
        self._admin_anim.stop()
        if has_admin:
            self.input_admin_key.setVisible(True)
            self.input_admin_key.setFixedHeight(36)
            self.btn_toggle_admin.setText("Yönetici Anahtarı ▾")
        else:
            self.input_admin_key.setFixedHeight(0)
            self.input_admin_key.setVisible(False)
            self.btn_toggle_admin.setText("Yönetici Anahtarı ▸")

        self._populate_combo(select_code=clean_curr_code)

    def _toggle_admin_field(self):
        self._admin_expanded = not self._admin_expanded
        if self._admin_expanded:
            self.input_admin_key.setVisible(True)
            self.btn_toggle_admin.setText("Yönetici Anahtarı ▾")
            self._admin_anim.start(float(self.input_admin_key.height()), 36.0)
            self.input_admin_key.setFocus()
        else:
            self.btn_toggle_admin.setText("Yönetici Anahtarı ▸")
            self._admin_anim.start(float(self.input_admin_key.height()), 0.0)

    def _populate_combo(self, select_code: str = ""):
        self.combo_servers.blockSignals(True)
        self.combo_servers.clear()
        self.combo_servers.addItem("+ Yeni Sunucu Ekle")

        selected_idx = 0
        for i, s in enumerate(self.saved_servers):
            s_name = s.get("name") or "Sunucu"
            s_code = normalize_server_key(s.get("code") or "")
            self.combo_servers.addItem(f"{s_name}  •  {s_code}" if s_code else s_name)
            if select_code and s_code == select_code:
                selected_idx = i + 1

        self.combo_servers.setCurrentIndex(selected_idx)
        self.combo_servers.blockSignals(False)
        self.btn_delete.setEnabled(selected_idx > 0)

    def _on_combo_changed(self, index: int):
        if index <= 0:
            self.input_name.clear()
            self.input_code.clear()
            self.input_admin_key.clear()
            self.input_code.setFocus()
            self.btn_delete.setEnabled(False)
        else:
            server = self.saved_servers[index - 1]
            self.input_name.setText(server.get("name", ""))
            self.input_code.setText(normalize_server_key(server.get("code", "")))
            admin_val = server.get("admin_key", "")
            self.input_admin_key.setText(admin_val)
            if admin_val and not self._admin_expanded:
                self._toggle_admin_field()
            self.btn_delete.setEnabled(True)

    def _on_delete_selected_server(self):
        index = self.combo_servers.currentIndex()
        if index > 0 and (index - 1) < len(self.saved_servers):
            del self.saved_servers[index - 1]
            if self.saved_servers:
                next_idx = min(index - 1, len(self.saved_servers) - 1)
                chosen = self.saved_servers[next_idx]
                c_name = chosen.get("name", "")
                c_code = normalize_server_key(chosen.get("code", ""))
                c_admin = chosen.get("admin_key", "")
                self._populate_combo(select_code=c_code)
                self.input_name.setText(c_name)
                self.input_code.setText(c_code)
                self.input_admin_key.setText(c_admin)
                self.servers_updated.emit(c_name, c_code, c_admin, self.saved_servers)
            else:
                self._populate_combo()
                self._on_combo_changed(0)
                self.servers_updated.emit("", "", "", [])

    def _on_save_clicked(self):
        code = normalize_server_key(self.input_code.text().strip())
        name = self.input_name.text().strip()
        admin_key = self.input_admin_key.text().strip() if self._admin_expanded else ""

        if not code:
            if not self.saved_servers:
                self.saved.emit("", "", "", [])
                return
            first = self.saved_servers[0]
            self.saved.emit(
                first.get("name", ""),
                normalize_server_key(first.get("code", "")),
                first.get("admin_key", ""),
                self.saved_servers,
            )
            return

        if not name:
            name = "Oyun Sunucusu"

        updated = False
        for s in self.saved_servers:
            if normalize_server_key(s.get("code", "")) == code:
                s["name"] = name
                s["code"] = code
                s["admin_key"] = admin_key
                updated = True
                break
        if not updated:
            self.saved_servers.append({
                "name": name,
                "code": code,
                "admin_key": admin_key,
            })

        self.saved.emit(name, code, admin_key, self.saved_servers)
