import sys
import os
import re
import json
import subprocess
import time
import winreg
import ctypes
import psutil

# Thư viện đồ họa Win32
import win32gui
import win32ui
import win32con
import win32console

# Ẩn màn hình đen Console
try:
    hwnd_console = win32console.GetConsoleWindow()
    if hwnd_console:
        win32gui.ShowWindow(hwnd_console, win32con.SW_HIDE)
except Exception:
    pass

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QGridLayout, QPushButton, QLabel, QLineEdit, 
    QFileDialog, QCheckBox, QFrame, QMessageBox,
    QTabWidget, QScrollArea, QComboBox, QSlider
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap, QPainter, QIcon

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(get_base_dir(), "boot_config.json")
REG_STARTUP_KEY = "Mir4_Master_Hub_PhamHung"


def is_process_running(exe_path):
    """Kiểm tra tiến trình đang chạy an toàn"""
    if not exe_path or not os.path.exists(exe_path):
        return False
    target_abs = os.path.abspath(exe_path).lower()
    target_name = os.path.basename(exe_path).lower()

    try:
        for proc in psutil.process_iter(['exe', 'name']):
            try:
                p_exe = proc.info.get('exe')
                if p_exe and os.path.abspath(p_exe).lower() == target_abs:
                    return True
                p_name = proc.info.get('name')
                if p_name and p_name.lower() == target_name:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return False


def kill_process_by_path(exe_path):
    """Dừng tiến trình khi bấm nút Dừng"""
    if not exe_path or not os.path.exists(exe_path):
        return False
    target_abs = os.path.abspath(exe_path).lower()
    target_name = os.path.basename(exe_path).lower()
    killed = False

    try:
        for proc in psutil.process_iter(['exe', 'name']):
            try:
                p_exe = proc.info.get('exe')
                p_name = proc.info.get('name')
                if (p_exe and os.path.abspath(p_exe).lower() == target_abs) or (p_name and p_name.lower() == target_name):
                    proc.kill()
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return killed


def launch_like_desktop(exe_path):
    """Khởi động file chuẩn xác 100% giống như click chuột ngoài desktop"""
    if not exe_path or not os.path.exists(exe_path):
        return False
    
    abs_path = os.path.abspath(exe_path)
    working_dir = os.path.dirname(abs_path)

    # 1. os.startfile (Chuẩn nhất của Windows)
    try:
        os.chdir(working_dir)
        os.startfile(abs_path)
        return True
    except Exception:
        pass

    # 2. ShellExecuteW
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(None, "open", abs_path, None, working_dir, 1)
        if ret > 32:
            return True
    except Exception:
        pass

    # 3. Subprocess
    try:
        subprocess.Popen([abs_path], cwd=working_dir, shell=False)
        return True
    except Exception:
        return False


# ==========================================================
#                   MODULE TAB 2: BỨC TƯỜNG GAME
# ==========================================================

def capture_window_pixmap(hwnd, target_w, target_h):
    try:
        if not win32gui.IsWindow(hwnd):
            return None

        cl_left, cl_top, cl_right, cl_bot = win32gui.GetClientRect(hwnd)
        w = cl_right - cl_left
        h = cl_bot - cl_top

        if w <= 0 or h <= 0:
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]

        if w <= 0 or h <= 0:
            return None

        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()

        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)

        res = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
        if res == 0:
            res = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
            if res == 0:
                saveDC.BitBlt((0, 0), (w, h), mfcDC, (0, 0), win32con.SRCCOPY)

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
    def __init__(self, hwnd, title, index, parent=None):
        super().__init__(parent)
        self.hwnd = hwnd
        self.game_title = title
        self.index = index
        self.target_w = 320
        self.target_h = 180
        self.current_pixmap = None

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

    def set_card_size(self, width, height):
        self.target_w = width
        self.target_h = height
        self.setFixedSize(self.target_w + 4, self.target_h + 4)
        self.update()

    def refresh_screen(self):
        pix = capture_window_pixmap(self.hwnd, self.target_w, self.target_h)
        if pix and not pix.isNull():
            self.current_pixmap = pix
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.current_pixmap and not self.current_pixmap.isNull():
            painter = QPainter(self)
            x = (self.width() - self.current_pixmap.width()) // 2
            y = (self.height() - self.current_pixmap.height()) // 2
            painter.drawPixmap(x, y, self.current_pixmap)

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


# ==========================================================
#                   CỬA SỔ CHÍNH MASTER APP
# ==========================================================

class MasterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mir4 Master Hub - Quản Lý Auto & Bức Tường Game [PHAMHUNG]")
        self.resize(1340, 860)
        self.setStyleSheet("""
            QMainWindow { background-color: #121214; }
            QWidget { color: #ececed; font-family: Segoe UI, sans-serif; }
            QTabWidget::pane { border: 1px solid #2e2e38; background-color: #121214; }
            QTabBar::tab {
                background: #1a1a1e; color: #888; font-weight: bold; font-size: 13px;
                padding: 10px 25px; border-top-left-radius: 6px; border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected { background: #ff6600; color: white; }
            QMessageBox { background-color: #1e1e24; }
            QMessageBox QLabel { color: #ffffff; font-size: 13px; font-weight: bold; }
            QMessageBox QPushButton { 
                background-color: #ff6600; color: white; font-weight: bold; 
                min-width: 80px; height: 28px; border-radius: 4px; 
            }
            QMessageBox QPushButton:hover { background-color: #ff8533; }
        """)

        if os.path.exists("app_icon.ico"):
            self.setWindowIcon(QIcon("app_icon.ico"))

        # Cấu hình lưu trữ mặc định
        self.config = {
            "qt_path": "",
            "tinker_path": "",
            "other_path": "",
            "auto_start_tools": True,
            "auto_recover_crash": True
        }
        self.load_config()

        # Biến điều khiển Watchdog và Cooldown chống spam
        self.is_waiting_30s = False
        self.last_launch_time = {}

        # Biến điều khiển Wall Manager
        self.current_cols = 4
        self.cards = {}
        self.auto_scale = True
        self.fixed_w = 320
        self.fixed_h = 180
        self.current_fps = 30

        self.init_ui()

        # Timers Tab 2 (Bức Tường Game)
        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self.update_frames)

        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_windows)
        self.scan_timer.start(5000)

        # Timer Watchdog Tab 1 (Quét mỗi 5 giây)
        self.watchdog_timer = QTimer(self)
        self.watchdog_timer.timeout.connect(self.watchdog_check_and_recover)
        self.watchdog_timer.start(5000)

        # Quét trạng thái giao diện lần đầu
        QTimer.singleShot(300, self.check_app_status_ui)

        # Tự động kích hoạt các Tool nếu cấu hình có bật
        if self.config.get("auto_start_tools", True):
            self.status_boot_label.setText("Tự động kích hoạt: Khởi động QT trước, chờ 30s kích hoạt 2 tool còn lại...")
            QTimer.singleShot(1500, self.start_sequence_flow)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # ================= TAB 1: QUẢN LÝ AUTO =================
        tab_boot = QWidget()
        tab_boot_layout = QVBoxLayout(tab_boot)
        tab_boot_layout.setContentsMargins(20, 15, 20, 15)
        tab_boot_layout.setSpacing(12)

        # Khung chứa 3 đường dẫn Tool
        box_frame = QFrame()
        box_frame.setStyleSheet("background-color: #1a1a1e; border: 1px solid #2e2e38; border-radius: 8px;")
        box_layout = QVBoxLayout(box_frame)
        box_layout.setContentsMargins(18, 12, 18, 12)
        box_layout.setSpacing(10)

        # 1. Tool QT
        h_qt_head = QHBoxLayout()
        lbl_qt = QLabel("1. Phần mềm QT (Ưu tiên chạy trước):")
        lbl_qt.setStyleSheet("border: none; font-weight: bold; color: #00e5ff; font-size: 13px;")
        h_qt_head.addWidget(lbl_qt)
        self.badge_qt = QLabel("⚪ Đang kiểm tra...")
        self.badge_qt.setStyleSheet("border: none; font-size: 11px; font-weight: bold; color: #888;")
        h_qt_head.addWidget(self.badge_qt)
        h_qt_head.addStretch()
        box_layout.addLayout(h_qt_head)

        h_qt = QHBoxLayout()
        self.txt_qt = QLineEdit(self.config.get("qt_path", ""))
        self.txt_qt.setPlaceholderText("Đường dẫn file QT (.exe)...")
        self.txt_qt.setStyleSheet("background-color: #242429; color: white; border: 1px solid #444; border-radius: 4px; padding: 6px;")
        self.txt_qt.textChanged.connect(self.save_config)
        h_qt.addWidget(self.txt_qt)

        btn_browse_qt = QPushButton("Chọn file...")
        btn_browse_qt.setFixedHeight(30)
        btn_browse_qt.setStyleSheet("background-color: #383842; color: white; border-radius: 4px; padding: 0 10px;")
        btn_browse_qt.clicked.connect(lambda: self.browse_target_file(self.txt_qt))
        h_qt.addWidget(btn_browse_qt)

        btn_run_qt = QPushButton("Chạy QT")
        btn_run_qt.setFixedHeight(30)
        btn_run_qt.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; border-radius: 4px; padding: 0 12px;")
        btn_run_qt.clicked.connect(lambda: self.manual_launch_single(self.txt_qt.text().strip(), "QT"))
        h_qt.addWidget(btn_run_qt)
        box_layout.addLayout(h_qt)

        # 2. Tool TINKER
        h_tinker_head = QHBoxLayout()
        lbl_tinker = QLabel("2. Phần mềm TINKER (Chạy sau QT 30s):")
        lbl_tinker.setStyleSheet("border: none; font-weight: bold; color: #00e676; font-size: 13px;")
        h_tinker_head.addWidget(lbl_tinker)
        self.badge_tinker = QLabel("⚪ Đang kiểm tra...")
        self.badge_tinker.setStyleSheet("border: none; font-size: 11px; font-weight: bold; color: #888;")
        h_tinker_head.addWidget(self.badge_tinker)
        h_tinker_head.addStretch()
        box_layout.addLayout(h_tinker_head)

        h_tinker = QHBoxLayout()
        self.txt_tinker = QLineEdit(self.config.get("tinker_path", ""))
        self.txt_tinker.setPlaceholderText("Đường dẫn file TINKER (.exe)...")
        self.txt_tinker.setStyleSheet("background-color: #242429; color: white; border: 1px solid #444; border-radius: 4px; padding: 6px;")
        self.txt_tinker.textChanged.connect(self.save_config)
        h_tinker.addWidget(self.txt_tinker)

        btn_browse_tinker = QPushButton("Chọn file...")
        btn_browse_tinker.setFixedHeight(30)
        btn_browse_tinker.setStyleSheet("background-color: #383842; color: white; border-radius: 4px; padding: 0 10px;")
        btn_browse_tinker.clicked.connect(lambda: self.browse_target_file(self.txt_tinker))
        h_tinker.addWidget(btn_browse_tinker)

        btn_run_tinker = QPushButton("Chạy Tinker")
        btn_run_tinker.setFixedHeight(30)
        btn_run_tinker.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; border-radius: 4px; padding: 0 12px;")
        btn_run_tinker.clicked.connect(lambda: self.manual_launch_single(self.txt_tinker.text().strip(), "TINKER"))
        h_tinker.addWidget(btn_run_tinker)
        box_layout.addLayout(h_tinker)

        # 3. Tool Khác
        h_other_head = QHBoxLayout()
        lbl_other = QLabel("3. Tool Khác (Chạy cùng lúc với Tinker sau 30s):")
        lbl_other.setStyleSheet("border: none; font-weight: bold; color: #e040fb; font-size: 13px;")
        h_other_head.addWidget(lbl_other)
        self.badge_other = QLabel("⚪ Đang kiểm tra...")
        self.badge_other.setStyleSheet("border: none; font-size: 11px; font-weight: bold; color: #888;")
        h_other_head.addWidget(self.badge_other)
        h_other_head.addStretch()
        box_layout.addLayout(h_other_head)

        h_other = QHBoxLayout()
        self.txt_other = QLineEdit(self.config.get("other_path", ""))
        self.txt_other.setPlaceholderText("Đường dẫn Tool thứ 3 (.exe)...")
        self.txt_other.setStyleSheet("background-color: #242429; color: white; border: 1px solid #444; border-radius: 4px; padding: 6px;")
        self.txt_other.textChanged.connect(self.save_config)
        h_other.addWidget(self.txt_other)

        btn_browse_other = QPushButton("Chọn file...")
        btn_browse_other.setFixedHeight(30)
        btn_browse_other.setStyleSheet("background-color: #383842; color: white; border-radius: 4px; padding: 0 10px;")
        btn_browse_other.clicked.connect(lambda: self.browse_target_file(self.txt_other))
        h_other.addWidget(btn_browse_other)

        btn_run_other = QPushButton("Chạy Tool Khác")
        btn_run_other.setFixedHeight(30)
        btn_run_other.setStyleSheet("background-color: #7b1fa2; color: white; font-weight: bold; border-radius: 4px; padding: 0 12px;")
        btn_run_other.clicked.connect(lambda: self.manual_launch_single(self.txt_other.text().strip(), "Tool Khác"))
        h_other.addWidget(btn_run_other)
        box_layout.addLayout(h_other)

        tab_boot_layout.addWidget(box_frame)

        # Tùy chọn tự động
        opts_layout = QVBoxLayout()
        opts_layout.setSpacing(6)

        h_check1 = QHBoxLayout()
        self.chk_startup = QCheckBox("Tự khởi động App Hub cùng Windows")
        self.chk_startup.setChecked(self.is_startup_registered())
        self.chk_startup.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")
        self.chk_startup.stateChanged.connect(self.toggle_windows_startup)
        h_check1.addWidget(self.chk_startup)

        self.chk_auto_start = QCheckBox("Tự khởi động các Tool đã lưu (QT trước, 30s sau mở 2 Tool còn lại)")
        self.chk_auto_start.setChecked(self.config.get("auto_start_tools", True))
        self.chk_auto_start.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")
        self.chk_auto_start.stateChanged.connect(self.save_config)
        h_check1.addWidget(self.chk_auto_start)
        opts_layout.addLayout(h_check1)

        self.chk_auto_recover = QCheckBox("🛡️ Giám sát & Tự động mở lại Tool nếu 1 trong các Tool bị tắt")
        self.chk_auto_recover.setChecked(self.config.get("auto_recover_crash", True))
        self.chk_auto_recover.setStyleSheet("color: #ffaa00; font-weight: bold; font-size: 13px;")
        self.chk_auto_recover.stateChanged.connect(self.save_config)
        opts_layout.addWidget(self.chk_auto_recover)

        tab_boot_layout.addLayout(opts_layout)

        # 2 Nút điều khiển: Khởi chạy tất cả / Dừng tất cả
        h_btns = QHBoxLayout()
        h_btns.setSpacing(12)

        self.btn_start_all = QPushButton("🚀 KHỞI CHẠY TẤT CẢ TOOL (QT TRƯỚC 30S)")
        self.btn_start_all.setFixedHeight(42)
        self.btn_start_all.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff6600, stop:1 #ff8533);
                color: white; font-size: 13px; font-weight: bold; border-radius: 6px;
            }
            QPushButton:hover { background: #ff944d; }
        """)
        self.btn_start_all.clicked.connect(self.on_btn_start_all_clicked)
        h_btns.addWidget(self.btn_start_all)

        self.btn_stop_all = QPushButton("🛑 DỪNG TẤT CẢ TOOL")
        self.btn_stop_all.setFixedHeight(42)
        self.btn_stop_all.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #c62828, stop:1 #e53935);
                color: white; font-size: 13px; font-weight: bold; border-radius: 6px;
            }
            QPushButton:hover { background: #ef5350; }
        """)
        self.btn_stop_all.clicked.connect(self.on_btn_stop_all_clicked)
        h_btns.addWidget(self.btn_stop_all)

        tab_boot_layout.addLayout(h_btns)

        self.status_boot_label = QLabel("Hệ thống quản lý Auto đang sẵn sàng.")
        self.status_boot_label.setAlignment(Qt.AlignCenter)
        self.status_boot_label.setStyleSheet("color: #00e676; font-size: 13px; font-weight: bold;")
        tab_boot_layout.addWidget(self.status_boot_label)

        tab_boot_layout.addStretch()
        self.tabs.addTab(tab_boot, "⚙️ QUẢN LÝ AUTO")

        # ================= TAB 2: TƯỜNG GAME =================
        tab_wall = QWidget()
        tab_wall_layout = QVBoxLayout(tab_wall)
        tab_wall_layout.setContentsMargins(5, 5, 5, 5)
        tab_wall_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        self.refresh_btn = QPushButton("Làm mới ngay (F5)")
        self.refresh_btn.setFixedHeight(30)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6600; color: white; font-weight: bold;
                padding: 0 14px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #ff8533; }
        """)
        self.refresh_btn.clicked.connect(self.scan_windows)
        toolbar.addWidget(self.refresh_btn)

        toolbar.addWidget(QLabel("Độ phân giải:"))
        self.res_combo = QComboBox()
        self.res_combo.setFixedHeight(28)
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

        toolbar.addWidget(QLabel("Số cột:"))
        self.col_combo = QComboBox()
        self.col_combo.setFixedHeight(28)
        self.col_combo.setStyleSheet("background-color: #242429; color: white; border-radius: 4px; padding: 2px 8px;")
        for c in range(1, 9):
            self.col_combo.addItem(f"{c} Cột", c)
        self.col_combo.setCurrentIndex(3)
        self.col_combo.currentIndexChanged.connect(self.on_columns_change)
        toolbar.addWidget(self.col_combo)

        toolbar.addWidget(QLabel("Tốc độ FPS:"))
        self.fps_slider = QSlider(Qt.Horizontal)
        self.fps_slider.setRange(0, 60)
        self.fps_slider.setValue(30)
        self.fps_slider.setFixedWidth(150)
        self.fps_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #2b2b36; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #ff6600; border-radius: 3px; }
            QSlider::handle:horizontal {
                background: #ffffff; border: 2px solid #ff6600; width: 14px;
                margin-top: -5px; margin-bottom: -5px; border-radius: 7px;
            }
        """)
        self.fps_slider.valueChanged.connect(self.on_fps_slider_changed)
        toolbar.addWidget(self.fps_slider)

        self.fps_value_label = QLabel("30 FPS")
        self.fps_value_label.setStyleSheet("color: #ffaa00; font-weight: bold; min-width: 75px;")
        toolbar.addWidget(self.fps_value_label)

        toolbar.addStretch()

        self.status_wall_label = QLabel("Đang chờ quét...")
        self.status_wall_label.setStyleSheet("color: #00e676; font-weight: bold;")
        toolbar.addWidget(self.status_wall_label)

        tab_wall_layout.addLayout(toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #292930; background-color: #121214; }")

        self.scroll_widget = QWidget()
        self.grid_layout = QGridLayout(self.scroll_widget)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll_area.setWidget(self.scroll_widget)
        tab_wall_layout.addWidget(self.scroll_area, 1)

        self.tabs.addTab(tab_wall, "🖥️ TƯỜNG GAME")

        main_layout.addWidget(self.tabs, 1)

        # ================= FOOTER QUẢNG CÁO =================
        self.ad_banner = QFrame()
        self.ad_banner.setFixedHeight(72)
        self.ad_banner.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #18090a, stop:0.5 #200f12, stop:1 #18090a);
                border: 2px solid #ff2a2a; border-radius: 8px;
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
                color: #ffeb3b; font-size: 16px; font-weight: 900;
                padding: 0 25px; border: 2px solid #ffe600; border-radius: 6px;
                letter-spacing: 1px;
            }
        """)
        ad_layout.addWidget(gold_badge)
        main_layout.addWidget(self.ad_banner)

    # ================= LOGIC QUẢN LÝ AUTO =================

    def browse_target_file(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file ứng dụng", "", "Executable Files (*.exe *.bat *.py);;All Files (*.*)"
        )
        if path:
            norm_path = os.path.normpath(path)
            line_edit.setText(norm_path)
            self.save_config()
            self.check_app_status_ui()

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.config.update(data)
            except Exception:
                pass

    def save_config(self):
        try:
            self.config["qt_path"] = self.txt_qt.text().strip()
            self.config["tinker_path"] = self.txt_tinker.text().strip()
            self.config["other_path"] = self.txt_other.text().strip()
            self.config["auto_start_tools"] = self.chk_auto_start.isChecked()
            self.config["auto_recover_crash"] = self.chk_auto_recover.isChecked()

            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def update_badge_ui(self, badge, is_on, is_warning=False, warning_text=""):
        if is_warning:
            badge.setText(f"⚠️ {warning_text}")
            badge.setStyleSheet("border: none; font-size: 11px; font-weight: bold; color: #ffab00;")
        elif is_on:
            badge.setText("🟢 ĐANG CHẠY (ONLINE)")
            badge.setStyleSheet("border: none; font-size: 11px; font-weight: bold; color: #00e676;")
        else:
            badge.setText("🔴 ĐÃ DỪNG (OFFLINE)")
            badge.setStyleSheet("border: none; font-size: 11px; font-weight: bold; color: #ff5252;")

    def check_app_status_ui(self):
        qt_on = is_process_running(self.txt_qt.text().strip())
        self.update_badge_ui(self.badge_qt, qt_on)

        tinker_on = is_process_running(self.txt_tinker.text().strip())
        self.update_badge_ui(self.badge_tinker, tinker_on)

        other_on = is_process_running(self.txt_other.text().strip())
        self.update_badge_ui(self.badge_other, other_on)

        return qt_on, tinker_on, other_on

    def manual_launch_single(self, path, name):
        self.save_config()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Lỗi", f"Đường dẫn file {name} không tồn tại!")
            return

        if is_process_running(path):
            QMessageBox.information(self, "Thông báo", f"{name} đã được khởi chạy từ trước!")
            return

        if launch_like_desktop(path):
            self.last_launch_time[name] = time.time()
            self.status_boot_label.setText(f"Khởi chạy {name} thành công.")
            QMessageBox.information(self, "Thành công", f"Khởi chạy {name} thành công!")
            QTimer.singleShot(1500, self.check_app_status_ui)
        else:
            QMessageBox.critical(self, "Lỗi", f"Không thể khởi động file {name}!")

    def start_sequence_flow(self):
        """Khởi động QT trước, chờ đúng 30 giây rồi mở 2 Tool còn lại"""
        qt_path = self.txt_qt.text().strip()
        tinker_path = self.txt_tinker.text().strip()
        other_path = self.txt_other.text().strip()

        # 1. Mở QT nếu chưa chạy
        if qt_path and os.path.exists(qt_path):
            if not is_process_running(qt_path):
                launch_like_desktop(qt_path)
                self.last_launch_time["QT"] = time.time()
                self.status_boot_label.setText("Đã bật QT. Đang đếm lùi 30 giây để bật TINKER và Tool Khác...")
            else:
                self.status_boot_label.setText("QT đã hoạt động. Chờ 30 giây kích hoạt 2 tool còn lại...")
        else:
            self.status_boot_label.setText("Chưa cài đường dẫn QT. Chờ 30 giây kiểm tra các tool còn lại...")

        self.is_waiting_30s = True
        self.btn_start_all.setEnabled(False)

        # 2. Hẹn giờ 30 giây bật TINKER và Tool Khác
        def run_remaining_tools():
            self.is_waiting_30s = False
            self.btn_start_all.setEnabled(True)

            launched_names = []
            if tinker_path and os.path.exists(tinker_path) and not is_process_running(tinker_path):
                launch_like_desktop(tinker_path)
                self.last_launch_time["TINKER"] = time.time()
                launched_names.append("TINKER")

            if other_path and os.path.exists(other_path) and not is_process_running(other_path):
                launch_like_desktop(other_path)
                self.last_launch_time["Tool Khác"] = time.time()
                launched_names.append("Tool Khác")

            if launched_names:
                msg = f"Đã khởi chạy: {', '.join(launched_names)} sau 30 giây!"
            else:
                msg = "Hoàn tất chu kỳ 30 giây. Các tool đã ở trạng thái chạy!"
            self.status_boot_label.setText(msg)
            self.check_app_status_ui()

        QTimer.singleShot(30000, run_remaining_tools)

    def on_btn_start_all_clicked(self):
        self.save_config()
        self.start_sequence_flow()
        QMessageBox.information(
            self, "Khởi chạy theo chu kỳ",
            "Đã gửi lệnh bật QT!\nHệ thống sẽ đếm lùi đúng 30 giây để tiếp tục bật TINKER và Tool Khác."
        )

    def on_btn_stop_all_clicked(self):
        stopped = []
        for path, name in [
            (self.txt_qt.text().strip(), "QT"),
            (self.txt_tinker.text().strip(), "TINKER"),
            (self.txt_other.text().strip(), "Tool Khác")
        ]:
            if path and is_process_running(path):
                if kill_process_by_path(path):
                    stopped.append(name)

        self.check_app_status_ui()
        if stopped:
            self.status_boot_label.setText(f"Đã dừng: {', '.join(stopped)}")
            QMessageBox.information(self, "Thông báo", f"Đã dừng các tiến trình: {', '.join(stopped)}")
        else:
            self.status_boot_label.setText("Không có tool nào đang chạy để dừng.")
            QMessageBox.information(self, "Thông báo", "Hiện tại không có tool nào đang chạy!")

    def watchdog_check_and_recover(self):
        """Tự động kiểm tra và mở lại tool nếu bị tắt (Kèm Cooldown chống mở đè)"""
        if self.is_waiting_30s or not self.chk_auto_recover.isChecked():
            return

        now = time.time()
        for path, name, badge in [
            (self.txt_qt.text().strip(), "QT", self.badge_qt),
            (self.txt_tinker.text().strip(), "TINKER", self.badge_tinker),
            (self.txt_other.text().strip(), "Tool Khác", self.badge_other)
        ]:
            if path and os.path.exists(path):
                if not is_process_running(path):
                    # Cooldown 15s tránh spam mở lại liên tục khi app đang load
                    if now - self.last_launch_time.get(name, 0) > 15:
                        self.update_badge_ui(badge, False, is_warning=True, warning_text="BỊ TẮT! ĐANG MỞ LẠI...")
                        self.status_boot_label.setText(f"Cảnh báo: Phát hiện {name} bị tắt! Đang tự động mở lại...")
                        launch_like_desktop(path)
                        self.last_launch_time[name] = now

    # ================= KHỞI ĐỘNG CÙNG WINDOWS =================

    def get_startup_bat_path(self):
        startup_dir = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
        return os.path.join(startup_dir, "Mir4_Master_Hub.bat")

    def is_startup_registered(self):
        if os.path.exists(self.get_startup_bat_path()):
            return True
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, REG_STARTUP_KEY)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def toggle_windows_startup(self, state):
        target_exe = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        target_dir = os.path.dirname(os.path.abspath(target_exe))
        bat_file = self.get_startup_bat_path()
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        if state == Qt.Checked:
            try:
                with open(bat_file, "w", encoding="utf-8") as f:
                    f.write(f'@echo off\ncd /d "{target_dir}"\nstart "" "{target_exe}"\n')
            except Exception:
                pass

            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, REG_STARTUP_KEY, 0, winreg.REG_SZ, f'"{target_exe}"')
                winreg.CloseKey(key)
            except Exception:
                pass

            self.status_boot_label.setText("Đã kích hoạt tự khởi động Hub cùng Windows.")
        else:
            if os.path.exists(bat_file):
                try:
                    os.remove(bat_file)
                except Exception:
                    pass

            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, REG_STARTUP_KEY)
                winreg.CloseKey(key)
            except Exception:
                pass

            self.status_boot_label.setText("Đã tắt tự khởi động Hub cùng Windows.")

    # ================= LOGIC TAB 2: BỨC TƯỜNG GAME =================

    def on_tab_changed(self, index):
        """Khi ở Tab 1 (Auto) thì DỪNG vẽ Wall để CPU về 0%. Sang Tab 2 mới vẽ."""
        if index == 1:
            if self.current_fps > 0 and not self.render_timer.isActive():
                interval = max(16, int(1000 / self.current_fps))
                self.render_timer.start(interval)
            self.scan_windows()
        else:
            self.render_timer.stop()

    def changeEvent(self, event):
        """Khi ẩn hoặc thu nhỏ App thì dừng render để tiết kiệm CPU"""
        super().changeEvent(event)
        if self.isMinimized():
            self.render_timer.stop()
        elif self.isVisible() and self.tabs.currentIndex() == 1 and self.current_fps > 0:
            if not self.render_timer.isActive():
                interval = max(16, int(1000 / self.current_fps))
                self.render_timer.start(interval)

    def on_fps_slider_changed(self, value):
        self.current_fps = value
        if value == 0:
            self.fps_value_label.setText("0 FPS (Tạm dừng)")
            self.render_timer.stop()
        else:
            self.fps_value_label.setText(f"{value} FPS")
            interval = max(16, int(1000 / value))
            self.render_timer.setInterval(interval)
            if self.tabs.currentIndex() == 1 and not self.render_timer.isActive():
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
        if self.tabs.currentIndex() != 1:
            return

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

        self.status_wall_label.setText(f"Tìm thấy: {len(self.cards)} / 50 cửa sổ")

    def update_frames(self):
        if self.tabs.currentIndex() != 1 or not self.isVisible() or self.isMinimized() or not self.cards:
            return

        scroll_y = self.scroll_area.verticalScrollBar().value()
        viewport_h = self.scroll_area.viewport().height()
        view_top = scroll_y - 50
        view_bottom = scroll_y + viewport_h + 50

        for card in self.cards.values():
            card_top = card.y()
            card_bottom = card_top + card.height()
            if card_bottom >= view_top and card_top <= view_bottom:
                card.refresh_screen()


# ==========================================================
#                   ĐIỂM KHỞI CHẠY (MAIN)
# ==========================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MasterApp()
    window.show()
    sys.exit(app.exec_())
