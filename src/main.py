#!/usr/bin/env python3
"""
Paradox Mod Patcher
Автоматический генератор патчей совместимости для модов Paradox

Поддерживаемые игры:
- Crusader Kings 3
- Europa Universalis 4
- Hearts of Iron 4
- Stellaris
- Victoria 3
"""

import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """Точка входа приложения"""
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    
    # Высокое DPI
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("Paradox Mod Patcher")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("ParadoxModPatcher")
    
    # Стиль
    app.setStyle("Fusion")
    
    # Шрифт
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    # Стили
    app.setStyleSheet("""
        QMainWindow {
            background: #f5f5f5;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #cccccc;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QListWidget, QTreeWidget, QListView {
            border: 1px solid #cccccc;
            border-radius: 3px;
            background: white;
        }
        QListWidget::item:selected, QTreeWidget::item:selected, QListView::item:selected {
            background: #0078d4;
            color: white;
        }
        QListWidget::item:hover, QTreeWidget::item:hover, QListView::item:hover {
            background: #e5f3ff;
        }
        QListWidget::item:selected:hover, QTreeWidget::item:selected:hover, QListView::item:selected:hover {
            background: #0078d4;
            color: white;
        }
        QPushButton {
            padding: 5px 15px;
            border: 1px solid #cccccc;
            border-radius: 3px;
            background: white;
        }
        QPushButton:hover {
            background: #e5e5e5;
            border-color: #999999;
        }
        QPushButton:pressed {
            background: #d0d0d0;
        }
        QComboBox {
            padding: 5px;
            border: 1px solid #cccccc;
            border-radius: 3px;
            background: white;
        }
        QComboBox QAbstractItemView {
            border: 1px solid #cccccc;
            background: white;
            selection-background-color: #0078d4;
            selection-color: white;
        }
        QComboBox QAbstractItemView::item:hover {
            background: #e5f3ff;
        }
        QProgressBar {
            border: 1px solid #cccccc;
            border-radius: 3px;
            text-align: center;
        }
        QProgressBar::chunk {
            background: #4CAF50;
        }
    """)
    
    # Главное окно
    try:
        from gui.main_window import MainWindow
    except ImportError:
        from src.gui.main_window import MainWindow
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
