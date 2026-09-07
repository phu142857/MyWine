import os
import sys
import time
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QWindow, QResizeEvent, QMouseEvent, QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QPushButton, QLabel, QMessageBox, QGroupBox,
    QGraphicsDropShadowEffect, QFrame, QCheckBox
)

# X11/XWayland interface library
from Xlib import X, display
from Xlib.ext import xtest


class FloatingContainer(QFrame):
    """
    A floating overlay panel that lives inside the main Qt window.
    Hosts embedded foreign QWindow and manages internal active geometry.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.SubWindow)
        self.setStyleSheet("""
            FloatingContainer {
                background-color: #252526;
                border: 2px solid #007acc;
                border-radius: 8px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        self.drag_position = QPoint()
        self.is_dragging = False
        self.foreign_qwindow = None
        self.embedded_qt_container = None

        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        self.main_layout.setSpacing(4)

        # Header Bar
        self.header = QFrame()
        self.header.setFixedHeight(30)
        self.header.setStyleSheet("background-color: #333333; border-radius: 4px;")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 0, 8, 0)

        self.title_label = QLabel("Floating Wine Panel (Drag Here)")
        self.title_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        header_layout.addWidget(self.title_label)

        self.main_layout.addWidget(self.header)

        # Embedded Content Area
        self.content_area = QWidget()
        self.content_area.setStyleSheet("background-color: #1e1e1e;")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        self.main_layout.addWidget(self.content_area)

    def attach_foreign_window(self, win_id: int):
        """Safely attaches foreign X11 window into container."""
        try:
            if self.embedded_qt_container:
                self.content_layout.removeWidget(self.embedded_qt_container)
                self.embedded_qt_container.deleteLater()
                self.embedded_qt_container = None

            self.foreign_qwindow = QWindow.fromWinId(win_id)
            if not self.foreign_qwindow:
                raise ValueError(f"Cannot resolve QWindow for WinID: {hex(win_id)}")

            self.embedded_qt_container = QWidget.createWindowContainer(self.foreign_qwindow, self.content_area)
            self.embedded_qt_container.setFocusPolicy(Qt.StrongFocus)
            
            self.content_layout.addWidget(self.embedded_qt_container)
            self.embedded_qt_container.show()
            self.foreign_qwindow.setGeometry(0, 0, self.content_area.width(), self.content_area.height())
            return True

        except Exception as err:
            print(f"[ERROR] Failed to attach foreign window: {err}")
            return False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_dragging and event.buttons() == Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_position
            if self.parent():
                parent_rect = self.parent().rect()
                new_x = max(0, min(new_pos.x(), parent_rect.width() - self.width()))
                new_y = max(0, min(new_pos.y(), parent_rect.height() - self.height()))
                self.move(new_x, new_y)
            else:
                self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.is_dragging = False

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self.foreign_qwindow and self.embedded_qt_container:
            self.foreign_qwindow.setGeometry(0, 0, self.content_area.width(), self.content_area.height())


class WineAutoClickerPoC(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PoC: Strategy 2 - Main Resize First then Embed (Niri / XWayland)")
        self.resize(1200, 850)

        # Connect to active XWayland display session dynamically
        self.x_display = self._init_x11_display()
        self.win_id = None

        self.init_ui()

        # Create Floating Overlay Panel
        self.floating_panel = FloatingContainer(self)
        self.floating_panel.setGeometry(50, 200, 800, 636) # 600 content + 30 header + 6 padding
        self.floating_panel.show()

    def _init_x11_display(self):
        """Connects to active XWayland display session managed by Niri."""
        display_name = os.environ.get("DISPLAY")
        if not display_name:
            print("[ERROR] $DISPLAY variable is not set by Niri compositor!")
            return None

        try:
            x_disp = display.Display(display_name)
            print(f"[INFO] Successfully connected to active XWayland Display: {display_name}")
            return x_disp
        except Exception as err:
            print(f"[ERROR] Failed to connect to XDisplay '{display_name}': {err}")
            return None

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Top Control Bar: Window ID & Target Dimension Input ---
        top_box = QGroupBox("1. Strategy: Resize Wine App at Main Screen -> Embed")
        top_layout = QHBoxLayout(top_box)
        
        top_layout.addWidget(QLabel("Window ID:"))
        self.win_id_input = QLineEdit()
        self.win_id_input.setPlaceholderText("e.g. 0x3c00009")
        top_layout.addWidget(self.win_id_input)

        top_layout.addWidget(QLabel("Target Width:"))
        self.width_input = QLineEdit("800")
        self.width_input.setFixedWidth(60)
        top_layout.addWidget(self.width_input)

        top_layout.addWidget(QLabel("Target Height:"))
        self.height_input = QLineEdit("600")
        self.height_input.setFixedWidth(60)
        top_layout.addWidget(self.height_input)

        self.process_btn = QPushButton("Resize on Main & Embed Window")
        self.process_btn.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        self.process_btn.clicked.connect(self.resize_main_and_embed)
        top_layout.addWidget(self.process_btn)

        main_layout.addWidget(top_box)

        # --- Background Auto-Click Controls (Direct 1:1 Mapping) ---
        click_box = QGroupBox("2. Direct 1:1 Background Auto-Click (No Coordinate Scaling Required)")
        click_layout = QHBoxLayout(click_box)

        click_layout.addWidget(QLabel("Target Coordinates (X, Y):"))
        self.click_x_input = QLineEdit("50")
        self.click_x_input.setFixedWidth(50)
        click_layout.addWidget(self.click_x_input)

        self.click_y_input = QLineEdit("50")
        self.click_y_input.setFixedWidth(50)
        click_layout.addWidget(self.click_y_input)

        self.use_xtest_chk = QCheckBox("Use XTest Fake Input")
        self.use_xtest_chk.setChecked(True)
        click_layout.addWidget(self.use_xtest_chk)

        self.click_btn = QPushButton("Send Direct Click")
        self.click_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.click_btn.clicked.connect(self.send_direct_click)
        click_layout.addWidget(self.click_btn)

        main_layout.addWidget(click_box)

        main_layout.addStretch()

    def resize_main_and_embed(self):
        """
        New Strategy Pipeline:
        1. Resize target Wine window on Main Screen (Native X11 Level)
        2. Wait for Wine/X11 to flush & layout
        3. Adjust Floating Container size to match
        4. Reparent/Attach Window into Container
        """
        win_id_str = self.win_id_input.text().strip()
        if not win_id_str:
            QMessageBox.warning(self, "Error", "Please input a valid Window ID!")
            return

        try:
            target_w = int(self.width_input.text())
            target_h = int(self.height_input.text())
            self.win_id = int(win_id_str, 16) if win_id_str.startswith("0x") else int(win_id_str)

            if not self.x_display:
                QMessageBox.critical(self, "Error", "XDisplay is unavailable!")
                return

            print(f"\n=== STRATEGY 2 PIPELINE START ===")
            print(f"[STEP 1] Resizing Native X11 Window {hex(self.win_id)} to ({target_w}x{target_h}) on Main Screen...")
            
            # Send native X11 configure request to resize window BEFORE reparenting
            win_obj = self.x_display.create_resource_object('window', self.win_id)
            win_obj.configure(width=target_w, height=target_h)
            self.x_display.flush()

            # Process Qt events to let X11 & Wine handle geometry layout changes
            QApplication.processEvents()
            time.sleep(0.15) # Brief pause to allow Wine GDI/DirectX to re-render layout

            # Step 2: Adjust Floating Container to hold exact content area + header/padding
            # Header = 30px, Top/Bottom Margins = 6 + 6 = 12px, Borders = 4px -> Height Offset = 42px
            container_w = target_w + 12
            container_h = target_h + 42
            self.floating_panel.resize(container_w, container_h)
            print(f"[STEP 2] Adjusted Floating Panel Outer Container to ({container_w}x{container_h})")

            # Step 3: Embed Foreign Window into Container
            print(f"[STEP 3] Reparenting/Attaching Foreign Window into Qt Container...")
            success = self.floating_panel.attach_foreign_window(self.win_id)

            if success:
                QMessageBox.information(
                    self, "Success", 
                    f"Successfully resized Native Window to {target_w}x{target_h} on Main Screen and embedded into Panel!"
                )
            else:
                QMessageBox.critical(self, "Error", f"Failed to attach window {hex(self.win_id)}.")

        except Exception as err:
            QMessageBox.critical(self, "Error", f"Execution failed: {str(err)}")

    def send_direct_click(self):
        """Dispatches mouse click with direct 1:1 coordinate mapping based on live container root location."""
        if not self.win_id or not self.x_display:
            QMessageBox.warning(self, "Error", "Window not embedded or XDisplay unavailable!")
            return

        try:
            target_x = int(self.click_x_input.text())
            target_y = int(self.click_y_input.text())

            # Fetch the precise root position of embedded_qt_container (Excludes Header 30px & Margins)
            content_win_id = int(self.floating_panel.embedded_qt_container.winId())
            qt_container_x11 = self.x_display.create_resource_object('window', content_win_id)
            root_win = self.x_display.screen().root

            # Query dynamic root offset (Handles panel dragging anywhere on screen)
            translated = qt_container_x11.translate_coordinates(root_win, 0, 0)
            abs_root_x = translated.x + target_x
            abs_root_y = translated.y + target_y

            print(f"[CLICK DEBUG] Local Target : ({target_x}, {target_y})")
            print(f"[CLICK DEBUG] Root Container: ({translated.x}, {translated.y})")
            print(f"[CLICK DEBUG] Final Root Target: ({abs_root_x}, {abs_root_y})")

            # Dispatch Event
            if self.use_xtest_chk.isChecked():
                xtest.fake_input(self.x_display, X.MotionNotify, x=abs_root_x, y=abs_root_y)
                xtest.fake_input(self.x_display, X.ButtonPress, detail=1)
                xtest.fake_input(self.x_display, X.ButtonRelease, detail=1)
                self.x_display.flush()
                print(f"[XTEST SUCCESS] Injected 1:1 hardware click at Root({abs_root_x}, {abs_root_y})")
            else:
                window_obj = self.x_display.create_resource_object('window', self.win_id)
                press_event = display.event.ButtonPress(
                    detail=1, time=X.CurrentTime, root=root_win, window=window_obj, child=X.NONE,
                    root_x=abs_root_x, root_y=abs_root_y, event_x=target_x, event_y=target_y,
                    state=0, same_screen=1
                )
                release_event = display.event.ButtonRelease(
                    detail=1, time=X.CurrentTime, root=root_win, window=window_obj, child=X.NONE,
                    root_x=abs_root_x, root_y=abs_root_y, event_x=target_x, event_y=target_y,
                    state=X.Button1Mask, same_screen=1
                )
                window_obj.send_event(press_event, event_mask=X.ButtonPressMask)
                window_obj.send_event(release_event, event_mask=X.ButtonReleaseMask)
                self.x_display.flush()
                print(f"[XSendEvent SUCCESS] Sent 1:1 synthetic click at Local({target_x}, {target_y})")

        except Exception as err:
            QMessageBox.critical(self, "Error", f"Failed to dispatch click: {str(err)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = WineAutoClickerPoC()
    win.show()
    sys.exit(app.exec())