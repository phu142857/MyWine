import os
import sys
import time
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QLineEdit, QPushButton, QLabel, QMessageBox, QGroupBox, QCheckBox
)

from Xlib import X, Xutil, display
from Xlib.ext import xtest


class EmbedHost(QWidget):
    """
    Naked native X11 host filling the main window viewport.
    No floating chrome — Wine is reparented directly here at (0,0).
    """

    def __init__(self, x_display=None, parent=None):
        super().__init__(parent)
        self.x_display = x_display
        self.foreign_win_id = None
        self.aspect = None  # (w, h) locked aspect of embedded app; None = stretch fill

        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background-color: #101010;")
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._geom_lock = QTimer(self)
        self._geom_lock.setInterval(250)
        self._geom_lock.timeout.connect(self.sync_foreign_geometry)

    def _x(self, win_id: int):
        return self.x_display.create_resource_object("window", win_id)

    def host_xid(self) -> int:
        return int(self.winId())

    def host_pixel_size(self) -> tuple[int, int]:
        try:
            g = self._x(self.host_xid()).get_geometry()
            if g.width > 0 and g.height > 0:
                return int(g.width), int(g.height)
        except Exception as err:
            print(f"[WARN] host get_geometry: {err}")
        dpr = self.devicePixelRatioF()
        return (
            max(1, int(round(self.width() * dpr))),
            max(1, int(round(self.height() * dpr))),
        )

    def _frame_extents(self, win_id: int) -> tuple[int, int, int, int]:
        try:
            atom = self.x_display.intern_atom("_NET_FRAME_EXTENTS")
            prop = self._x(win_id).get_full_property(atom, X.AnyPropertyType)
            if prop and prop.value and len(prop.value) >= 4:
                extents = tuple(int(prop.value[i]) for i in range(4))
                print(f"[FRAME] LRTB={extents}")
                return extents  # type: ignore[return-value]
        except Exception as err:
            print(f"[FRAME] {err}")
        return 0, 0, 0, 0

    def resolve_client_window(self, win_id: int) -> int:
        """Prefer largest mapped child when win_id is a WM/Wine frame."""
        self._frame_extents(win_id)
        wine = self._x(win_id)
        try:
            children = list(wine.query_tree().children)
        except Exception:
            return win_id

        parent_geom = wine.get_geometry()
        parent_area = max(1, parent_geom.width * parent_geom.height)
        best_id, best_area = win_id, 0

        for child in children:
            try:
                cg = child.get_geometry()
                if child.get_attributes().map_state != X.IsViewable:
                    continue
                area = cg.width * cg.height
                if area > best_area and area >= parent_area * 0.5:
                    best_area = area
                    best_id = child.id
                    print(f"[CLIENT] child={hex(child.id)} {cg.width}x{cg.height} @({cg.x},{cg.y})")
            except Exception:
                continue

        if best_id != win_id:
            print(f"[CLIENT] use {hex(best_id)} instead of frame {hex(win_id)}")
        return best_id

    def _apply_hints(self, win_obj, w: int, h: int):
        win_obj.set_wm_normal_hints(hints={
            "flags": (
                Xutil.PPosition | Xutil.PSize | Xutil.PMinSize
                | Xutil.PMaxSize | Xutil.PWinGravity
            ),
            "x": 0, "y": 0,
            "width": w, "height": h,
            "min_width": w, "min_height": h,
            "max_width": w, "max_height": h,
            "win_gravity": X.NorthWestGravity,
        })

    def configure_foreign(self, w: int, h: int):
        if not self.foreign_win_id or not self.x_display:
            return
        wine = self._x(self.foreign_win_id)
        wine.configure(x=0, y=0, width=w, height=h, border_width=0)
        self._apply_hints(wine, w, h)

    def sync_foreign_geometry(self):
        if not self.foreign_win_id or not self.x_display:
            return
        try:
            host_xid = self.host_xid()
            wine = self._x(self.foreign_win_id)
            if wine.query_tree().parent.id != host_xid:
                wine.reparent(self._x(host_xid), 0, 0)
            w, h = self.host_pixel_size()
            self.configure_foreign(w, h)
            self.x_display.flush()
        except Exception as err:
            print(f"[WARN] sync: {err}")

    def log_geom(self, tag: str):
        if not self.foreign_win_id or not self.x_display:
            return
        try:
            wine = self._x(self.foreign_win_id)
            g = wine.get_geometry()
            parent = wine.query_tree().parent.id
            host = self.host_xid()
            hg = self._x(host).get_geometry()
            ok = "OK" if parent == host and g.x == 0 and g.y == 0 else "BAD"
            print(
                f"[GEOM {tag}] {ok} wine={hex(self.foreign_win_id)} "
                f"xy=({g.x},{g.y}) {g.width}x{g.height} "
                f"parent={hex(parent)} host={hex(host)} {hg.width}x{hg.height}"
            )
        except Exception as err:
            print(f"[GEOM {tag}] {err}")

    def embed(self, win_id: int, lock_aspect: bool = True) -> bool:
        """Reparent Wine into this host and resize 1:1 to host pixels."""
        try:
            if not self.x_display:
                raise RuntimeError("XDisplay unavailable")

            self._geom_lock.stop()
            QApplication.processEvents()

            host_xid = self.host_xid()
            client_id = self.resolve_client_window(win_id)
            self.foreign_win_id = client_id

            # Capture native aspect before we force-fit (for optional letterbox UI later)
            try:
                ng = self._x(client_id).get_geometry()
                if lock_aspect and ng.width > 0 and ng.height > 0:
                    self.aspect = (ng.width, ng.height)
                else:
                    self.aspect = None
            except Exception:
                self.aspect = None

            pw, ph = self.host_pixel_size()
            print(f"[EMBED] host={hex(host_xid)} {pw}x{ph} client={hex(client_id)} aspect={self.aspect}")

            wine = self._x(client_id)
            wine.change_attributes(override_redirect=True)
            wine.reparent(self._x(host_xid), 0, 0)
            self.configure_foreign(pw, ph)
            wine.map()
            wine.change_attributes(override_redirect=True)
            self.x_display.sync()

            self.log_geom("after-reparent")
            self.sync_foreign_geometry()
            self.log_geom("after-sync")

            self._geom_lock.start()
            QTimer.singleShot(0, self.sync_foreign_geometry)
            QTimer.singleShot(100, self.sync_foreign_geometry)
            QTimer.singleShot(300, lambda: self.log_geom("t+300ms"))
            return True
        except Exception as err:
            print(f"[ERROR] embed failed: {err}")
            return False

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        # Keep Wine pixel-perfect with host — 1:1 click mapping, no float panel.
        self.sync_foreign_geometry()


class WineEmbedPoC(QWidget):
    """
    Strategy: no floating window.
    Toolbar on top, EmbedHost fills the rest; Wine is reparented into EmbedHost
    and resized to the host on every layout change.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PoC: Direct Embed (no float) — resize 1:1 into main viewport")
        self.resize(1200, 850)

        self.x_display = self._init_x11_display()
        self.win_id = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # --- Controls ---
        top = QGroupBox("1. Resize on main screen → embed into viewport (no floating panel)")
        top_l = QHBoxLayout(top)

        top_l.addWidget(QLabel("Window ID:"))
        self.win_id_input = QLineEdit()
        self.win_id_input.setPlaceholderText("e.g. 0x3c00009")
        top_l.addWidget(self.win_id_input)

        top_l.addWidget(QLabel("Pre-resize W×H (0 = skip):"))
        self.width_input = QLineEdit("800")
        self.width_input.setFixedWidth(56)
        top_l.addWidget(self.width_input)
        self.height_input = QLineEdit("600")
        self.height_input.setFixedWidth(56)
        top_l.addWidget(self.height_input)

        self.lock_aspect_chk = QCheckBox("Remember aspect")
        self.lock_aspect_chk.setChecked(True)
        self.lock_aspect_chk.setToolTip("Store native aspect after embed (informational); Wine still fills host 1:1.")
        top_l.addWidget(self.lock_aspect_chk)

        self.fit_btn = QPushButton("Fit window to Wine aspect")
        self.fit_btn.setToolTip("Resize this Qt window so the viewport matches stored Wine aspect.")
        self.fit_btn.clicked.connect(self.fit_window_to_aspect)
        top_l.addWidget(self.fit_btn)

        self.process_btn = QPushButton("Embed into main viewport")
        self.process_btn.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        self.process_btn.clicked.connect(self.resize_and_embed)
        top_l.addWidget(self.process_btn)
        root.addWidget(top)

        click = QGroupBox("2. Direct 1:1 click (coords relative to Wine / viewport)")
        click_l = QHBoxLayout(click)
        click_l.addWidget(QLabel("X, Y:"))
        self.click_x_input = QLineEdit("50")
        self.click_x_input.setFixedWidth(48)
        click_l.addWidget(self.click_x_input)
        self.click_y_input = QLineEdit("50")
        self.click_y_input.setFixedWidth(48)
        click_l.addWidget(self.click_y_input)
        self.use_xtest_chk = QCheckBox("XTest")
        self.use_xtest_chk.setChecked(True)
        click_l.addWidget(self.use_xtest_chk)
        self.click_btn = QPushButton("Send Click")
        self.click_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.click_btn.clicked.connect(self.send_direct_click)
        click_l.addWidget(self.click_btn)
        click_l.addStretch()
        root.addWidget(click)

        # --- Main viewport (takes all remaining space) ---
        self.embed_host = EmbedHost(x_display=self.x_display)
        root.addWidget(self.embed_host, stretch=1)

        self.status = QLabel("Viewport ready — paste Wine window id and Embed.")
        self.status.setStyleSheet("color: #aaaaaa;")
        root.addWidget(self.status)

    def _init_x11_display(self):
        name = os.environ.get("DISPLAY")
        if not name:
            print("[ERROR] $DISPLAY not set")
            return None
        try:
            d = display.Display(name)
            print(f"[INFO] XWayland Display: {name}")
            return d
        except Exception as err:
            print(f"[ERROR] XDisplay: {err}")
            return None

    def resize_and_embed(self):
        win_id_str = self.win_id_input.text().strip()
        if not win_id_str:
            QMessageBox.warning(self, "Error", "Please input a Window ID")
            return
        if not self.x_display:
            QMessageBox.critical(self, "Error", "XDisplay unavailable")
            return

        try:
            self.win_id = int(win_id_str, 16) if win_id_str.startswith("0x") else int(win_id_str)
            pre_w = int(self.width_input.text() or "0")
            pre_h = int(self.height_input.text() or "0")

            print("\n=== DIRECT EMBED PIPELINE ===")
            wine = self.x_display.create_resource_object("window", self.win_id)

            # Optional: resize on main screen first (lets Wine GDI/D3D settle)
            if pre_w > 0 and pre_h > 0:
                print(f"[STEP 1] Pre-resize {hex(self.win_id)} -> {pre_w}x{pre_h}")
                wine.configure(width=pre_w, height=pre_h)
                self.x_display.flush()
                QApplication.processEvents()
                time.sleep(0.15)
            else:
                print("[STEP 1] Skip pre-resize")

            # Ensure viewport has a real size, then embed + force Wine = host size
            QApplication.processEvents()
            hw, hh = self.embed_host.width(), self.embed_host.height()
            print(f"[STEP 2] Viewport Qt size {hw}x{hh}")

            print("[STEP 3] Reparent into main EmbedHost")
            ok = self.embed_host.embed(self.win_id, lock_aspect=self.lock_aspect_chk.isChecked())
            if ok and self.embed_host.foreign_win_id:
                self.win_id = self.embed_host.foreign_win_id
                pw, ph = self.embed_host.host_pixel_size()
                self.status.setText(
                    f"Embedded {hex(self.win_id)} @ {pw}x{ph} (1:1 with viewport). "
                    f"Resize the window — Wine follows."
                )
                QMessageBox.information(self, "OK", f"Embedded into main viewport at {pw}x{ph}")
            else:
                QMessageBox.critical(self, "Error", "Embed failed — see terminal logs")
        except Exception as err:
            QMessageBox.critical(self, "Error", str(err))

    def fit_window_to_aspect(self):
        """Resize Qt window so embed_host matches remembered Wine aspect."""
        aspect = self.embed_host.aspect
        if not aspect:
            QMessageBox.information(self, "Aspect", "No aspect stored yet — embed first.")
            return
        aw, ah = aspect
        host = self.embed_host
        # Keep current host width, compute height from aspect (or vice versa if too tall)
        target_h = max(1, int(round(host.width() * ah / aw)))
        delta_h = target_h - host.height()
        self.resize(self.width(), self.height() + delta_h)
        QApplication.processEvents()
        self.embed_host.sync_foreign_geometry()
        print(f"[FIT] aspect {aw}:{ah} -> host {host.width()}x{host.height()}")
        self.status.setText(f"Window fitted to aspect {aw}:{ah}")

    def send_direct_click(self):
        if not self.win_id or not self.x_display:
            QMessageBox.warning(self, "Error", "Not embedded")
            return
        try:
            tx = int(self.click_x_input.text())
            ty = int(self.click_y_input.text())
            wine = self.x_display.create_resource_object("window", self.win_id)
            root = self.x_display.screen().root
            tr = root.translate_coords(wine, tx, ty)
            ax, ay = tr.x, tr.y
            origin = self.embed_host.mapToGlobal(QPoint(0, 0))
            print(f"[CLICK] local({tx},{ty}) root({ax},{ay}) qt_origin({origin.x()},{origin.y()})")

            if self.use_xtest_chk.isChecked():
                xtest.fake_input(self.x_display, X.MotionNotify, x=ax, y=ay)
                xtest.fake_input(self.x_display, X.ButtonPress, detail=1)
                xtest.fake_input(self.x_display, X.ButtonRelease, detail=1)
                self.x_display.flush()
            else:
                wine.send_event(
                    display.event.ButtonPress(
                        detail=1, time=X.CurrentTime, root=root, window=wine, child=X.NONE,
                        root_x=ax, root_y=ay, event_x=tx, event_y=ty, state=0, same_screen=1
                    ),
                    event_mask=X.ButtonPressMask,
                )
                wine.send_event(
                    display.event.ButtonRelease(
                        detail=1, time=X.CurrentTime, root=root, window=wine, child=X.NONE,
                        root_x=ax, root_y=ay, event_x=tx, event_y=ty, state=X.Button1Mask, same_screen=1
                    ),
                    event_mask=X.ButtonReleaseMask,
                )
                self.x_display.flush()
        except Exception as err:
            QMessageBox.critical(self, "Error", str(err))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = WineEmbedPoC()
    win.show()
    sys.exit(app.exec())
