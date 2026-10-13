import sys
import re
import ctypes
from ctypes import wintypes
import win32gui
import win32con
import win32console

# 1. ẨN NGAY CỬA SỔ CMD KHI VỪA KHỞI CHẠY
try:
    hwnd_console = win32console.GetConsoleWindow()
    if hwnd_console:
        win32gui.ShowWindow(hwnd_console, win32con.SW_HIDE)
except Exception:
    pass

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, 
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QScrollArea, QComboBox, QFrame
)
from PyQt5.QtCore import Qt, QTimer, QPoint

# Nạp Windows DWM Thumbnail API
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
DWM_TNP_OPACITY = 0x00000004
DWM_TNP_SOURCECLIENTAREAONLY = 0x00000010


class ThumbnailCard(QFrame):
    """Thẻ chứa thông tin và vị trí placeholder cho 1 cửa sổ game"""
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
                background-color: #1a1a1e;
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

        # Thanh tiêu đề thẻ
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

        # Vùng chừa chỗ cho DWM vẽ đè lên
        self.screen_placeholder = QWidget()
        self.screen_placeholder.setFixedSize(self.thumb_w, self.thumb_h)
        self.screen_placeholder.setStyleSheet("background-color: #000000;")
        layout.addWidget(self.screen_placeholder)

    def set_display_size(self, width, height):
        self.thumb_w = width
        self.thumb_h = height
        self.screen_placeholder.setFixedSize(self.thumb_w, self.thumb_h)

    def mouseDoubleClickEvent(self, event):
        """Click đúp chuột để đưa cửa sổ game thật lên tương tác"""
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mir4 Window Wall Manager [Mir4G 1-50]")
        self.resize(1340, 750)
        self.setStyleSheet("background-color: #121214; color: #ececed;")

        self.current_w = 320
        self.current_h = 180
        self.current_cols = 4
        self.cards = {}

        self.init_ui()

        # Timer liên tục cập nhật vị trí thumbnail và quét cửa sổ mới
        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self.update_all_thumbnails)
        self.sync_timer.start(50)  # Cập nhật mượt mà khi cuộn hoặc co giãn

        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_windows)
        self.scan_timer.start(3000)

        QTimer.singleShot(200, self.scan_windows)

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

        # Khu vực cuộn
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #292930; background-color: #121214; }")
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.update_all_thumbnails)
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self.update_all_thumbnails)

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
        self.update_all_thumbnails()

    def on_columns_change(self):
        self.current_cols = self.col_combo.currentData()
        self.relayout_cards()

    def relayout_cards(self):
        sorted_cards = sorted(self.cards.values(), key=lambda card: card.index)
        for idx, card in enumerate(sorted_cards):
            r = idx // self.current_cols
            c = idx % self.current_cols
            self.grid_layout.addWidget(card, r, c)
        self.update_all_thumbnails()

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

        # Dọn dẹp card của cửa sổ đã tắt
        for hwnd in list(self.cards.keys()):
            if hwnd not in current_hwnds:
                card = self.cards.pop(hwnd)
                if card.thumb_id:
                    dwmapi.DwmUnregisterThumbnail(card.thumb_id)
                card.setParent(None)
                card.deleteLater()

        # Thêm card mới
        main_hwnd = int(self.winId())
        needs_relayout = False

        for idx, hwnd, title in found_windows:
            if hwnd not in self.cards:
                card = ThumbnailCard(hwnd, title, idx, self.current_w, self.current_h)
                # Đăng ký trực tiếp với Top-Level MainWindow
                hr = dwmapi.DwmRegisterThumbnail(main_hwnd, hwnd, ctypes.byref(card.thumb_id))
                self.cards[hwnd] = card
                needs_relayout = True

        if needs_relayout:
            self.relayout_cards()

        self.status_label.setText(f"Tìm thấy: {len(self.cards)} / 50 cửa sổ")
        self.update_all_thumbnails()

    def update_all_thumbnails(self):
        """Chiếu hình ảnh từng game chính xác vào ô màn hình tương ứng trên cửa sổ chính"""
        if not self.isVisible():
            return

        viewport = self.scroll_area.viewport()
        vp_top_left = viewport.mapTo(self, QPoint(0, 0))
        vp_rect = RECT(
            vp_top_left.x(),
            vp_top_left.y(),
            vp_top_left.x() + viewport.width(),
            vp_top_left.y() + viewport.height()
        )

        for card in self.cards.values():
            if not card.thumb_id:
                continue

            # Tính tọa độ của vùng màn hình con đối với cửa sổ chính MainWindow
            screen_pos = card.screen_placeholder.mapTo(self, QPoint(0, 0))
            left = screen_pos.x()
            top = screen_pos.y()
            right = left + card.thumb_w
            bottom = top + card.thumb_h

            props = DWM_THUMBNAIL_PROPERTIES()
            
            # Kiểm tra nếu ô màn hình bị cuộn ra khỏi vùng nhìn thấy
            if right < vp_rect.left or left > vp_rect.right or bottom < vp_rect.top or top > vp_rect.bottom:
                props.dwFlags = DWM_TNP_VISIBLE
                props.fVisible = False
            else:
                # Cắt bớt phần hiển thị nếu card bị cuộn dở dang
                clamped_left = max(left, vp_rect.left)
                clamped_top = max(top, vp_rect.top)
                clamped_right = min(right, vp_rect.right)
                clamped_bottom = min(bottom, vp_rect.bottom)

                props.dwFlags = (
                    DWM_TNP_RECTTARGET | 
                    DWM_TNP_VISIBLE | 
                    DWM_TNP_OPACITY | 
                    DWM_TNP_SOURCECLIENTAREAONLY
                )
                props.fVisible = True
                props.opacity = 255
                props.fSourceClientAreaOnly = True
                props.rcTarget = RECT(clamped_left, clamped_top, clamped_right, clamped_bottom)

            try:
                dwmapi.DwmUpdateThumbnailProperties(card.thumb_id, ctypes.byref(props))
            except Exception:
                pass

    def closeEvent(self, event):
        for card in self.cards.values():
            if card.thumb_id:
                try:
                    dwmapi.DwmUnregisterThumbnail(card.thumb_id)
                except Exception:
                    pass
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
