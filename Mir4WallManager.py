import sys
import os
import re
import ctypes
from ctypes import wintypes
import win32gui
import win32ui
import win32con
import win32console

# Ẩn console đen ngay khi khởi chạy
try:
    hwnd_console = win32console.GetConsoleWindow()
    if hwnd_console:
        win32gui.ShowWindow(hwnd_console, win32con.SW_HIDE)
except Exception:
    pass

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, 
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QScrollArea, QComboBox, QFrame, QSlider, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QImage, QPixmap, QIcon


def capture_window_pixmap(hwnd, target_w, target_h):
    """Chụp trực tiếp bộ đệm đồ họa và co giãn đúng tỉ lệ chuẩn 640x360"""
    try:
        if not win32gui.IsWindow(hwnd):
            return None

        left, top, right, bot = win32gui.GetClientRect(hwnd)
        w = right - left
        h = bot - top

        if w <= 0 or h <= 0:
            return None

        hwndDC = win32gui.GetDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()

        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)

        result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
        if result == 0:
            ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)

        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)

        img = QImage(bmpstr, bmpinfo['bmWidth'], bmpinfo['bmHeight'], QImage.Format_ARGB32)

        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

        pixmap = QPixmap.fromImage(img)
        return pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.FastTransformation)
    except Exception:
        return None


class ThumbnailCard(QFrame):
    """Card hiển thị trực tiếp toàn bộ màn hình game"""
    def __init__(self, hwnd, title, index, parent=None):
        super().__init__(parent)
        self.hwnd = hwnd
        self.game_title = title
        self.index = index
        self.target_w = 320
        self.target_h = 180

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            ThumbnailCard {
                background-color: #000000;
                border: 2px solid #38383e;
                border-radius: 4px;
            }
            ThumbnailCard:hover {
                border: 2px solid #ff7b00;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #000000; border: none;")
        layout.addWidget(self.image_label)

    def set_card_size(self, width, height):
        self.target_w = width
        self.target_h = height
        self.image_label.setFixedSize(self.target_w, self.target_h)
        self.setFixedSize(self.target_w + 4, self.target_h + 4)

    def refresh_screen(self):
        pixmap = capture_window_pixmap(self.hwnd, self.target_w, self.target_h)
        if pixmap and not pixmap.isNull():
            self.image_label.setPixmap(pixmap)

    def mouseDoubleClickEvent(self, event):
        """Click đúp chuột để đưa cửa sổ game thật lên trước"""
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
        self.resize(1340, 800)
        self.setStyleSheet("background-color: #121214; color: #ececed;")

        if os.path.exists("app_icon.ico"):
            self.setWindowIcon(QIcon("app_icon.ico"))

        self.current_cols = 4
        self.cards = {}
        self.auto_scale = True
        self.fixed_w = 320
        self.fixed_h = 180

        self.init_ui()

        # Timer cập nhật khung hình (Mặc định 30 FPS)
        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self.update_frames)
        self.render_timer.start(33)

        # Timer quét phát hiện game mới mở/đóng
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_windows)
        self.scan_timer.start(3000)

        QTimer.singleShot(100, self.scan_windows)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ==================== THANH CÔNG CỤ ====================
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        self.refresh_btn = QPushButton("Làm mới ngay (F5)")
        self.refresh_btn.setFixedHeight(32)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6600; color: white; font-weight: bold;
                padding: 0 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #ff8533; }
        """)
        self.refresh_btn.clicked.connect(self.scan_windows)
        toolbar.addWidget(self.refresh_btn)

        # Lựa chọn Độ phân giải (Khôi phục lại trọn vẹn)
        toolbar.addWidget(QLabel("Độ phân giải:"))
        self.res_combo = QComboBox()
        self.res_combo.setFixedHeight(30)
        self.res_combo.setStyleSheet("background-color: #242429; color: white; border-radius: 4px; padding: 2px 8px;")
        self.res_options = {
            "Tự động (Co giãn theo App)": None,
            "Rất nhỏ (240x135)": (240, 135),
            "Tiêu chuẩn (320x180)": (320, 180),
            "Trung bình (400x225)": (400, 225),
            "Lớn (480x270)": (480, 270),
            "Gốc chuẩn (640x360)": (640, 360)
        }
        for label in self.res_options.keys():
            self.res_combo.addItem(label)
        self.res_combo.setCurrentText("Tự động (Co giãn theo App)")
        self.res_combo.currentIndexChanged.connect(self.on_resolution_change)
        toolbar.addWidget(self.res_combo)

        # Lựa chọn Số cột
        toolbar.addWidget(QLabel("Số cột:"))
        self.col_combo = QComboBox()
        self.col_combo.setFixedHeight(30)
        self.col_combo.setStyleSheet("background-color: #242429; color: white; border-radius: 4px; padding: 2px 8px;")
        for c in range(1, 9):
            self.col_combo.addItem(f"{c} Cột", c)
        self.col_combo.setCurrentIndex(3)  # Mặc định 4 cột
        self.col_combo.currentIndexChanged.connect(self.on_columns_change)
        toolbar.addWidget(self.col_combo)

        # Thanh trượt điều chỉnh FPS (0 - 60 FPS)
        toolbar.addWidget(QLabel("Tốc độ FPS:"))
        self.fps_slider = QSlider(Qt.Horizontal)
        self.fps_slider.setRange(0, 60)
        self.fps_slider.setValue(30)
        self.fps_slider.setFixedWidth(160)
        self.fps_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #2b2b36;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #ff6600;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 2px solid #ff6600;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
        """)
        self.fps_slider.valueChanged.connect(self.on_fps_slider_changed)
        toolbar.addWidget(self.fps_slider)

        self.fps_value_label = QLabel("30 FPS")
        self.fps_value_label.setStyleSheet("color: #ffaa00; font-weight: bold; min-width: 80px;")
        toolbar.addWidget(self.fps_value_label)

        toolbar.addStretch()

        self.status_label = QLabel("Đang chờ quét...")
        self.status_label.setStyleSheet("color: #00e676; font-weight: bold;")
        toolbar.addWidget(self.status_label)

        main_layout.addLayout(toolbar)

        # ==================== KHU VỰC HIỂN THỊ GAME ====================
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #292930; background-color: #121214; }")

        self.scroll_widget = QWidget()
        self.grid_layout = QGridLayout(self.scroll_widget)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll_area.setWidget(self.scroll_widget)
        main_layout.addWidget(self.scroll_area, 1)

        # ==================== BANNER QUẢNG CÁO PHÍA DƯỚI ====================
        self.ad_banner = QFrame()
        self.ad_banner.setFixedHeight(75)
        self.ad_banner.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #18090a, stop:0.5 #200f12, stop:1 #18090a);
                border: 2px solid #ff2a2a;
                border-radius: 8px;
            }
        """)
        ad_layout = QHBoxLayout(self.ad_banner)
        ad_layout.setContentsMargins(20, 5, 20, 5)

        contact_layout = QVBoxLayout()
        contact_layout.setSpacing(2)
        contact_layout.setAlignment(Qt.AlignVCenter)

        lbl_design = QLabel("Design by : <span style='color: #00e5ff; font-weight: bold;'>PHAMHUNG</span>")
        lbl_design.setStyleSheet("border: none; background: transparent; font-size: 13px; font-weight: bold; color: #ff5252;")
        contact_layout.addWidget(lbl_design)

        lbl_zalo = QLabel("ZALO : <span style='color: #ffe600; font-weight: bold;'>0392771558</span>")
        lbl_zalo.setStyleSheet("border: none; background: transparent; font-size: 13px; font-weight: bold; color: #ff5252;")
        contact_layout.addWidget(lbl_zalo)

        lbl_fb = QLabel("FB : <span style='color: #ffffff; font-weight: bold;'>Phạm Văn Hưng</span>")
        lbl_fb.setStyleSheet("border: none; background: transparent; font-size: 13px; font-weight: bold; color: #ff5252;")
        contact_layout.addWidget(lbl_fb)

        ad_layout.addLayout(contact_layout)
        ad_layout.addStretch()

        gold_badge = QLabel("BUY / SELL GOLD MIR4")
        gold_badge.setFixedHeight(46)
        gold_badge.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #801010, stop:1 #d32f2f);
                color: #ffeb3b;
                font-size: 16px;
                font-weight: 900;
                padding: 0 25px;
                border: 2px solid #ffe600;
                border-radius: 6px;
                letter-spacing: 1px;
            }
        """)
        ad_layout.addWidget(gold_badge)

        main_layout.addWidget(self.ad_banner)

    def on_fps_slider_changed(self, value):
        if value == 0:
            self.fps_value_label.setText("0 FPS (Tạm dừng)")
            self.render_timer.stop()
        else:
            self.fps_value_label.setText(f"{value} FPS")
            interval = max(16, int(1000 / value))
            self.render_timer.setInterval(interval)
            if not self.render_timer.isActive():
                self.render_timer.start()

    def on_resolution_change(self):
        text = self.res_combo.currentText()
        val = self.res_options[text]
        if val is None:
            self.auto_scale = True
        else:
            self.auto_scale = False
            self.fixed_w, self.fixed_h = val
        self.update_card_dimensions()

    def on_columns_change(self):
        self.current_cols = self.col_combo.currentData()
        self.relayout_cards()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_scale:
            self.update_card_dimensions()

    def update_card_dimensions(self):
        """Khóa chuẩn tỷ lệ 640x360 cho khung hình"""
        if not self.cards:
            return

        if self.auto_scale:
            viewport_w = self.scroll_area.viewport().width()
            spacing = self.grid_layout.spacing()
            margins = self.grid_layout.contentsMargins().left() + self.grid_layout.contentsMargins().right()
            available_width = viewport_w - margins - ((self.current_cols - 1) * spacing) - 15
            target_w = max(160, int(available_width / self.current_cols))
            target_h = int(target_w * 360 / 640)
        else:
            target_w = self.fixed_w
            target_h = self.fixed_h

        for card in self.cards.values():
            card.set_card_size(target_w, target_h)

    def relayout_cards(self):
        sorted_cards = sorted(self.cards.values(), key=lambda card: card.index)
        for idx, card in enumerate(sorted_cards):
            r = idx // self.current_cols
            c = idx % self.current_cols
            self.grid_layout.addWidget(card, r, c)
        self.update_card_dimensions()

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
                card.setParent(None)
                card.deleteLater()

        needs_relayout = False
        for idx, hwnd, title in found_windows:
            if hwnd not in self.cards:
                card = ThumbnailCard(hwnd, title, idx)
                self.cards[hwnd] = card
                needs_relayout = True

        if needs_relayout:
            self.relayout_cards()

        self.status_label.setText(f"Tìm thấy: {len(self.cards)} / 50 cửa sổ")

    def update_frames(self):
        if not self.isVisible() or self.isMinimized():
            return
            
        viewport_rect = self.scroll_area.viewport().rect()
        for card in self.cards.values():
            card_geo = card.geometry()
            top_left_in_vp = self.scroll_widget.mapTo(self.scroll_area.viewport(), card_geo.topLeft())
            card_rect_in_vp = QRect(top_left_in_vp, card_geo.size())
            
            if viewport_rect.intersects(card_rect_in_vp):
                card.refresh_screen()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
