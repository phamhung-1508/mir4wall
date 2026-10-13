import sys
import re
import ctypes
from ctypes import wintypes
import traceback

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, 
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QScrollArea, QComboBox, QFrame
)
from PyQt5.QtCore import Qt, QTimer
import win32gui
import win32con

# Nạp thư viện DWM của Windows
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except Exception:
    dwmapi = None

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]

class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wintypes.DWORD),
        ("rcTarget", RECT),
        ("rcSource", RECT),
        ("opacity", ctypes.c_byte),
        ("fVisible", wintypes.BOOL),
        ("fSourceClientAreaOnly", wintypes.BOOL),
    ]

DWM_TNP_RECTTARGET = 0x00000002
DWM_TNP_VISIBLE = 0x00000008
DWM_TNP_SOURCECLIENTAREAONLY = 0x00000010


class ThumbnailCard(QFrame):
    def __init__(self, hwnd, title, index, thumb_w, thumb_h, parent=None):
        super().__init__(parent)
        self.hwnd = hwnd
        self.game_title = title
        self.index = index
        self.thumb_id = wintypes.HANDLE()
        self.thumb_w = thumb_w
        self.thumb_h = thumb_h

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            ThumbnailCard {
                background-color: #1f1f23;
                border: 2px solid #38383e;
                border-radius: 6px;
            }
            ThumbnailCard:hover {
                border: 2px solid #ff7b00;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self.header_label = QLabel(f" {self.game_title} ")
        self.header_label.setFixedHeight(22)
        self.header_label.setStyleSheet("""
            color: #ffffff;
            font-weight: bold;
            font-size: 11px;
            background-color: #2b2b36;
            border-radius: 3px;
        """)
        layout.addWidget(self.header_label)

        self.thumb_area = QWidget()
        self.thumb_area.setFixedSize(self.thumb_w, self.thumb_h)
        self.thumb_area.setStyleSheet("background-color: #000000;")
        layout.addWidget(self.thumb_area)

    def set_display_size(self, width, height):
        self.thumb_w = width
        self.thumb_h = height
        self.thumb_area.setFixedSize(self.thumb_w, self.thumb_h)
        self.update_thumbnail_position()

    def showEvent(self, event):
        super().showEvent(event)
        self.register_thumbnail()

    def register_thumbnail(self):
        if not dwmapi or self.thumb_id:
            return
        try:
            dest_hwnd = int(self.thumb_area.winId())
            hr = dwmapi.DwmRegisterThumbnail(dest_hwnd, self.hwnd, ctypes.byref(self.thumb_id))
            if hr == 0:
                self.update_thumbnail_position()
        except Exception:
            pass

    def update_thumbnail_position(self):
        if dwmapi and self.thumb_id:
            try:
                props = DWM_THUMBNAIL_PROPERTIES()
                props.dwFlags = DWM_TNP_RECTTARGET | DWM_TNP_VISIBLE | DWM_TNP_SOURCECLIENTAREAONLY
                props.fVisible = True
                props.fSourceClientAreaOnly = True
                props.rcTarget = RECT(0, 0, self.thumb_w, self.thumb_h)
                dwmapi.DwmUpdateThumbnailProperties(self.thumb_id, ctypes.byref(props))
            except Exception:
                pass

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activate_window()

    def activate_window(self):
        try:
            if win32gui.IsWindow(self.hwnd):
                win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                user32 = ctypes.windll.user32
                current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                window_thread = user32.GetWindowThreadProcessId(self.hwnd, None)
                user32.AttachThreadInput(current_thread, window_thread, True)
                win32gui.SetForegroundWindow(self.hwnd)
                win32gui.BringWindowToTop(self.hwnd)
                user32.AttachThreadInput(current_thread, window_thread, False)
        except Exception:
            try:
                win32gui.SetForegroundWindow(self.hwnd)
            except Exception:
                pass

    def closeEvent(self, event):
        self.unregister_thumbnail()
        super().closeEvent(event)

    def unregister_thumbnail(self):
        if dwmapi and self.thumb_id:
            try:
                dwmapi.DwmUnregisterThumbnail(self.thumb_id)
            except Exception:
                pass
            self.thumb_id = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mir4 Window Wall Manager [Mir4G 1-50]")
        self.resize(1280, 720)
        self.setStyleSheet("background-color: #121214; color: #ececed;")

        self.current_w = 320
        self.current_h = 180
        self.current_cols = 4
        self.cards = {}

        self.init_ui()

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.scan_windows)
        self.auto_refresh_timer.start(4000)

        self.scan_windows()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.refresh_btn = QPushButton("Làm mới ngay (F5)")
        self.refresh_btn.setFixedHeight(30)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6600; color: white; font-weight: bold;
                padding: 0 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #ff8533; }
        """)
        self.refresh_btn.clicked.connect(self.scan_windows)
        toolbar.addWidget(self.refresh_btn)

        toolbar.addWidget(QLabel("Độ phân giải:"))
        self.res_combo = QComboBox()
        self.res_combo.setFixedHeight(30)
        self.res_combo.setStyleSheet("background-color: #242429; color: white; border-radius: 4px; padding: 2px 8px;")
        self.res_options = {
            "Rất nhỏ (240x135)": (240, 135),
            "Tiêu chuẩn (320x180)": (320, 180),
            "Trung bình (400x225)": (400, 225),
            "Lớn (480x270)": (480, 270),
            "Rất lớn (640x360)": (640, 360)
        }
        for label in self.res_options.keys():
            self.res_combo.addItem(label)
        self.res_combo.setCurrentText("Tiêu chuẩn (320x180)")
        self.res_combo.currentIndexChanged.connect(self.on_resolution_change)
        toolbar.addWidget(self.res_combo)

        toolbar.addWidget(QLabel("Số cột:"))
        self.col_combo = QComboBox()
        self.col_combo.setFixedHeight(30)
        self.col_combo.setStyleSheet("background-color: #242429; color: white; border-radius: 4px; padding: 2px 8px;")
        for c in range(2, 9):
            self.col_combo.addItem(f"{c} Cột", c)
        self.col_combo.setCurrentIndex(2)
        self.col_combo.currentIndexChanged.connect(self.on_columns_change)
        toolbar.addWidget(self.col_combo)

        toolbar.addStretch()

        self.status_label = QLabel("Đang chờ quét...")
        self.status_label.setStyleSheet("color: #00e676; font-weight: bold;")
        toolbar.addWidget(self.status_label)

        main_layout.addLayout(toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #292930; background-color: #121214; }")

        self.scroll_widget = QWidget()
        self.grid_layout = QGridLayout(self.scroll_widget)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll_area.setWidget(self.scroll_widget)
        main_layout.addWidget(self.scroll_area)

    def on_resolution_change(self):
        text = self.res_combo.currentText()
        w, h = self.res_options[text]
        self.current_w, self.current_h = w, h
        for card in self.cards.values():
            card.set_display_size(w, h)

    def on_columns_change(self):
        self.current_cols = self.col_combo.currentData()
        self.relayout_cards()

    def relayout_cards(self):
        sorted_cards = sorted(self.cards.values(), key=lambda card: card.index)
        for idx, card in enumerate(sorted_cards):
            r = idx // self.current_cols
            c = idx % self.current_cols
            self.grid_layout.addWidget(card, r, c)

    def scan_windows(self):
        found_windows = []
        pattern = re.compile(r"^mir4g\[(\d+)\]", re.IGNORECASE)

        def enum_cb(hwnd, extra):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).strip()
                    match = pattern.match(title)
                    if match:
                        idx = int(match.group(1))
                        if 1 <= idx <= 50:
                            found_windows.append((idx, hwnd, title))
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass

        found_windows.sort(key=lambda x: x[0])
        current_hwnds = {hwnd for _, hwnd, _ in found_windows}

        for hwnd in list(self.cards.keys()):
            if hwnd not in current_hwnds:
                card = self.cards.pop(hwnd)
                card.unregister_thumbnail()
                card.setParent(None)
                card.deleteLater()

        needs_relayout = False
        for idx, hwnd, title in found_windows:
            if hwnd not in self.cards:
                card = ThumbnailCard(hwnd, title, idx, self.current_w, self.current_h)
                self.cards[hwnd] = card
                needs_relayout = True

        if needs_relayout or len(self.cards) != self.grid_layout.count():
            self.relayout_cards()

        self.status_label.setText(f"Tìm thấy: {len(self.cards)} / 50 cửa sổ")


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        print("\n=== CO LOI XAY RA KHI KHOI DONG ===")
        traceback.print_exc()
        input("\nNhan phim Enter de thoat...")
