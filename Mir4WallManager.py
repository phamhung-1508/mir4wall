import sys
import re
import ctypes
from ctypes import wintypes
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, 
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QScrollArea, QComboBox, QFrame
)
from PyQt5.QtCore import Qt, QTimer
import win32gui
import win32con

# Khai báo Windows DWM Thumbnail API
dwmapi = ctypes.WinDLL("dwmapi")

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
    """Khung chứa tiêu đề và vùng chiếu hình thu nhỏ của cửa sổ game"""
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

        # Thanh tiêu đề hiển thị tên cửa sổ
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

        # Vùng chứa DWM thumbnail
        self.thumb_area = QWidget()
        self.thumb_area.setFixedSize(self.thumb_w, self.thumb_h)
        self.thumb_area.setStyleSheet("background-color: #0b0b0e;")
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
        if not self.thumb_id:
            dest_hwnd = int(self.thumb_area.winId())
            hr = dwmapi.DwmRegisterThumbnail(dest_hwnd, self.hwnd, ctypes.byref(self.thumb_id))
            if hr == 0:
                self.update_thumbnail_position()

    def update_thumbnail_position(self):
        if self.thumb_id:
            props = DWM_THUMBNAIL_PROPERTIES()
            props.dwFlags = DWM_TNP_RECTTARGET | DWM_TNP_VISIBLE | DWM_TNP_SOURCECLIENTAREAONLY
            props.fVisible = True
            props.fSourceClientAreaOnly = True
            props.rcTarget = RECT(0, 0, self.thumb_w, self.thumb_h)
            dwmapi.DwmUpdateThumbnailProperties(self.thumb_id, ctypes.byref(props))

    def mouseDoubleClickEvent(self, event):
        """Kích hoạt và đưa cửa sổ game thật lên trước khi click đúp"""
        if event.button() == Qt.LeftButton:
            self.activate_window()

    def activate_window(self):
        if win32gui.IsWindow(self.hwnd):
            # Khôi phục nếu cửa sổ đang bị Minimize
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            # Cho phép và kích hoạt đưa lên foreground
            ctypes.windll.user32.AllowSetForegroundWindow(ctypes.c_uint(-1))
            win32gui.SetForegroundWindow(self.hwnd)

    def closeEvent(self, event):
        self.unregister_thumbnail()
        super().closeEvent(event)

    def unregister_thumbnail(self):
        if self.thumb_id:
            dwmapi.DwmUnregisterThumbnail(self.thumb_id)
            self.thumb_id = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mir4 Window Wall Manager [Mir4G 1-50]")
        self.resize(1300, 750)
        self.setStyleSheet("background-color: #121214; color: #ececed;")

        # Thiết lập mặc định: 320x180 (16:9) và 4 cột
        self.current_w = 320
        self.current_h = 180
        self.current_cols = 4
        self.cards = {}

        self.init_ui()

        # Tự động quét lại cửa sổ mỗi 5 giây
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.scan_windows)
        self.auto_refresh_timer.start(5000)

        # Quét lần đầu
        self.scan_windows()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Toolbar
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

        # Tùy chọn độ phân giải
        toolbar.addWidget(QLabel("Độ phân giải:"))
        self.res_combo = QComboBox()
        self.res_combo.setFixedHeight(30)
        self