from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QResizeEvent

from embedded_window import EmbeddedWindow

class EmbedHost(QWidget):

    def __init__(self, x11_manager, parent=None):
        super().__init__(parent)
        self.manager = x11_manager
        self.embedded = None
        self.setAttribute(Qt.WA_NativeWindow)

        self.setFocusPolicy(Qt.StrongFocus)

        self.setStyleSheet("background:#101010;")

    @property
    def host_xid(self):
        return int(self.winId())

    def embed(self, embedded_window: EmbeddedWindow):
        self.embedded = embedded_window
        self.manager.reparent_window(embedded_window.win_id, self.host_xid)
        self.sync_geometry()

    def sync_geometry(self):
        if not self.embedded:
            return

        self.manager.configure_embedded_window(self.embedded.win_id, self.width(), self.height())

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.sync_geometry()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        
        if self.embedded:self.manager.set_focus(self.embedded.win_id)
