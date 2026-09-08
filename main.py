import sys

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout)
from embedded_window import EmbeddedWindow
from embed_host import EmbedHost
from control_panel import ControlPanel
from x11_manager import X11WindowManager

class MainWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.resize(1200, 800)
        self.manager = (X11WindowManager())

        self.controls = (ControlPanel())

        self.embed_host = (EmbedHost(self.manager))

        root = QVBoxLayout(self)

        root.addWidget(self.controls)

        root.addWidget(self.embed_host, stretch=1)

        self.controls.embed_button.clicked.connect(self.embed_clicked)

    def embed_clicked(self):
        text = (self.controls.window_id.text().strip())

        if not text:
            return

        win_id = (int(text, 16) if text.startswith("0x") else int(text))
        _, _, w, h = (self.manager.get_geometry(win_id))

        embedded = EmbeddedWindow(win_id=win_id, native_width=w, native_height=h)

        self.embed_host.embed(embedded)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    
    win.show()
  
    sys.exit(app.exec())
