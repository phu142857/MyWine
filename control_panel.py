from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QGroupBox
)


class ControlPanel(QGroupBox):

    def __init__(self):
        super().__init__("Wine Embed")
        layout = QHBoxLayout(self)
        layout.addWidget(QLabel("Window ID:"))
        self.window_id = QLineEdit()
        layout.addWidget(self.window_id)
        self.embed_button = QPushButton("Embed")
        layout.addWidget(self.embed_button)
