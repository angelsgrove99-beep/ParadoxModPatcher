"""
Main Window v2 with i18n support
Главное окно с поддержкой локализации
"""

import sys
import os
import json
from pathlib import Path
from typing import List, Optional, Dict

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QProgressBar, QTextEdit, QSplitter,
    QGroupBox, QCheckBox, QComboBox, QMessageBox,
    QStatusBar, QMenuBar, QMenu, QAction, QRadioButton,
    QButtonGroup, QFrame, QScrollArea, QInputDialog,
    QApplication, QActionGroup, QDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QFont, QColor, QIcon

try:
    from ..core.scanner import ModScanner, ModInfo, get_paradox_mods_path, get_game_install_path, get_all_mods_paths
    from ..core.smart_merger import read_mod_name, read_mod_dependencies, validate_mod_compatibility
    from ..core.smart_patch_generator import SmartPatchGenerator, PatchStats, PatchProgress
    from ..i18n import tr, i18n, LANGUAGES
    from ..version import __version__
except ImportError:
    from core.scanner import ModScanner, ModInfo, get_paradox_mods_path, get_game_install_path, get_all_mods_paths
    from core.smart_merger import read_mod_name, read_mod_dependencies, validate_mod_compatibility
    from core.smart_patch_generator import SmartPatchGenerator, PatchStats, PatchProgress
    from i18n import tr, i18n, LANGUAGES
    from version import __version__


class ScanThread(QThread):
    finished = pyqtSignal(list)
    progress = pyqtSignal(str)
    
    def __init__(self, mods_paths: List[Path]):
        super().__init__()
        self.mods_paths = mods_paths if isinstance(mods_paths, list) else [mods_paths]
        
    def run(self):
        self.progress.emit(tr("scanning"))
        all_mods = []
        seen_paths = set()
        
        for mods_path in self.mods_paths:
            if mods_path.exists():
                scanner = ModScanner(mods_path)
                result = scanner.scan_all()
                for mod in result.mods:
                    # Избегаем дубликатов по пути
                    if str(mod.path) not in seen_paths:
                        all_mods.append(mod)
                        seen_paths.add(str(mod.path))
        
        self.finished.emit(all_mods)


class PatchThread(QThread):
    finished = pyqtSignal(object)
    progress = pyqtSignal(str, int, int)
    
    def __init__(self, base_path: Path, base_is_vanilla: bool, mod_paths: List[Path], 
                 output_path: Path, patch_name: str):
        super().__init__()
        self.base_path = base_path
        self.base_is_vanilla = base_is_vanilla
        self.mod_paths = mod_paths
        self.output_path = output_path
        self.patch_name = patch_name
        
    def run(self):
        def progress_callback(p: PatchProgress):
            self.progress.emit(p.status, p.current_index, p.total_files)
        
        generator = SmartPatchGenerator(progress_callback)
        stats = generator.generate_patch(
            self.base_path, self.base_is_vanilla, self.mod_paths,
            self.output_path, self.patch_name
        )
        self.finished.emit(stats)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings("ParadoxModPatcher", "PMP")
        
        # Загружаем сохранённый язык
        saved_lang = self.settings.value("language", "")
        if saved_lang and saved_lang in LANGUAGES:
            i18n.current_language = saved_lang
        
        self.setWindowTitle(f"{tr('window_title')} v{__version__}")
        self.setMinimumSize(900, 700)
        
        self.all_mods: List[ModInfo] = []
        self.base_path: Optional[Path] = None
        self.base_is_vanilla = False
        self._mod_changes_cache: Dict[tuple, bool] = {}
        self._base_files_cache: Dict[str, set] = {}
        
        self.init_ui()
        self.init_menu()
        
        # Автозапуск сканирования всех папок при старте
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self.scan_all_mods)
        
        auto_profile = self.get_profiles_dir() / "_autosave.json"
        if auto_profile.exists():
            self.load_profile(str(auto_profile))
    
    def closeEvent(self, event):
        self.auto_save_profile()
        event.accept()
    
    def auto_save_profile(self):
        profile_data = {
            "mods_path": self.mods_path_label.text(),
            "base_is_vanilla": self.vanilla_radio.isChecked(),
            "base_mod_name": self.base_mod_label.text() if self.mod_radio.isChecked() else "",
            "vanilla_path": self.vanilla_path_label.text(),
            "selected_mods": [],
            "patch_name": self.patch_name_edit.currentText()
        }
        
        for i in range(self.selected_list.count()):
            item = self.selected_list.item(i)
            mod = item.data(Qt.UserRole)
            if mod:
                profile_data["selected_mods"].append(mod.name)
        
        auto_profile = self.get_profiles_dir() / "_autosave.json"
        try:
            with open(auto_profile, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        
        # === Step 1 ===
        self.mods_group = QGroupBox(tr("step1_title"))
        mods_layout = QHBoxLayout(self.mods_group)
        
        self.mods_path_label = QLabel(tr("searching"))
        self.mods_path_label.setStyleSheet("padding: 5px; background: #f0f0f0; border-radius: 3px;")
        mods_layout.addWidget(self.mods_path_label, 1)
        
        self.refresh_btn = QPushButton(tr("refresh"))
        self.refresh_btn.setToolTip(tr("refresh_tooltip"))
        self.refresh_btn.clicked.connect(self.scan_all_mods)
        mods_layout.addWidget(self.refresh_btn)
        
        # Сохраняем пути к папкам
        self.all_mods_paths = []  # Все папки для сканирования
        self.local_mods_path = None  # Локальная папка для создания патча
        
        layout.addWidget(self.mods_group)
        
        # === Step 2 ===
        self.base_group = QGroupBox(tr("step2_title"))
        base_layout = QVBoxLayout(self.base_group)
        
        radio_layout = QHBoxLayout()
        self.base_button_group = QButtonGroup()
        
        self.vanilla_radio = QRadioButton(tr("vanilla_game"))
        self.vanilla_radio.toggled.connect(self.on_base_type_changed)
        self.base_button_group.addButton(self.vanilla_radio)
        radio_layout.addWidget(self.vanilla_radio)
        
        self.mod_radio = QRadioButton(tr("global_mod"))
        self.mod_radio.toggled.connect(self.on_base_type_changed)
        self.base_button_group.addButton(self.mod_radio)
        radio_layout.addWidget(self.mod_radio)
        
        # Виджет выбора глобального мода: лейбл + кнопка
        self.base_mod_label = QLabel("")
        self.base_mod_label.setStyleSheet("padding: 5px; background: #f0f0f0; border-radius: 3px;")
        self.base_mod_label.setMinimumWidth(250)
        radio_layout.addWidget(self.base_mod_label, 1)
        
        self.base_mod_btn = QPushButton("...")
        self.base_mod_btn.setFixedWidth(40)
        self.base_mod_btn.setEnabled(False)
        self.base_mod_btn.setToolTip(tr("select_base_mod"))
        self.base_mod_btn.clicked.connect(self.select_base_mod)
        radio_layout.addWidget(self.base_mod_btn)
        
        # Данные о выбранном моде
        self.base_mod_data = []  # [(name, path), ...]
        self.base_mod_index = -1
        
        base_layout.addLayout(radio_layout)
        
        self.vanilla_path_widget = QWidget()
        vanilla_path_layout = QHBoxLayout(self.vanilla_path_widget)
        vanilla_path_layout.setContentsMargins(0, 0, 0, 0)
        
        self.game_folder_label = QLabel(tr("game_folder"))
        vanilla_path_layout.addWidget(self.game_folder_label)
        self.vanilla_path_label = QLabel(tr("not_selected"))
        self.vanilla_path_label.setStyleSheet("padding: 5px; background: #f0f0f0; border-radius: 3px;")
        vanilla_path_layout.addWidget(self.vanilla_path_label, 1)
        
        self.vanilla_browse_btn = QPushButton(tr("browse"))
        self.vanilla_browse_btn.clicked.connect(self.browse_vanilla_folder)
        vanilla_path_layout.addWidget(self.vanilla_browse_btn)
        
        self.vanilla_auto_btn = QPushButton(tr("auto"))
        self.vanilla_auto_btn.setToolTip(tr("auto_game_tooltip"))
        self.vanilla_auto_btn.clicked.connect(self.auto_detect_game)
        vanilla_path_layout.addWidget(self.vanilla_auto_btn)
        
        self.vanilla_path_widget.setVisible(False)
        base_layout.addWidget(self.vanilla_path_widget)
        
        layout.addWidget(self.base_group)
        
        # === Step 3 ===
        self.mods_select_group = QGroupBox(tr("step3_title"))
        mods_select_layout = QHBoxLayout(self.mods_select_group)
        
        left_layout = QVBoxLayout()
        self.available_label = QLabel(tr("available_mods"))
        left_layout.addWidget(self.available_label)
        self.available_list = QListWidget()
        self.available_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.available_list.itemDoubleClicked.connect(self.add_selected_mods)
        left_layout.addWidget(self.available_list)
        mods_select_layout.addLayout(left_layout, 1)
        
        middle_btns_layout = QVBoxLayout()
        middle_btns_layout.addStretch()
        
        self.add_btn = QPushButton("→")
        self.add_btn.setFixedWidth(40)
        self.add_btn.setToolTip(tr("add_tooltip"))
        self.add_btn.clicked.connect(self.add_selected_mods)
        middle_btns_layout.addWidget(self.add_btn)
        
        self.add_all_btn = QPushButton("⇒")
        self.add_all_btn.setFixedWidth(40)
        self.add_all_btn.setToolTip(tr("add_all_tooltip"))
        self.add_all_btn.clicked.connect(self.add_all_mods)
        middle_btns_layout.addWidget(self.add_all_btn)
        
        self.remove_btn = QPushButton("←")
        self.remove_btn.setFixedWidth(40)
        self.remove_btn.setToolTip(tr("remove_tooltip"))
        self.remove_btn.clicked.connect(self.remove_selected_mods)
        middle_btns_layout.addWidget(self.remove_btn)
        
        self.remove_all_btn = QPushButton("⇐")
        self.remove_all_btn.setFixedWidth(40)
        self.remove_all_btn.setToolTip(tr("remove_all_tooltip"))
        self.remove_all_btn.clicked.connect(self.remove_all_mods)
        middle_btns_layout.addWidget(self.remove_all_btn)
        
        middle_btns_layout.addStretch()
        mods_select_layout.addLayout(middle_btns_layout)
        
        right_layout = QVBoxLayout()
        self.apply_order_label = QLabel(tr("apply_order"))
        right_layout.addWidget(self.apply_order_label)
        self.selected_list = QListWidget()
        self.selected_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.selected_list.itemDoubleClicked.connect(self.remove_selected_mods)
        right_layout.addWidget(self.selected_list)
        
        order_btns_layout = QHBoxLayout()
        
        self.up_btn = QPushButton(tr("move_up"))
        self.up_btn.clicked.connect(self.move_up)
        order_btns_layout.addWidget(self.up_btn)
        
        self.down_btn = QPushButton(tr("move_down"))
        self.down_btn.clicked.connect(self.move_down)
        order_btns_layout.addWidget(self.down_btn)
        
        order_btns_layout.addStretch()
        
        self.selected_count_label = QLabel(tr("selected_count", 0))
        order_btns_layout.addWidget(self.selected_count_label)
        
        right_layout.addLayout(order_btns_layout)
        mods_select_layout.addLayout(right_layout, 1)
        
        layout.addWidget(self.mods_select_group, 1)
        
        # === Log ===
        self.log_group = QGroupBox(tr("log_title"))
        log_layout = QVBoxLayout(self.log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(self.log_group)
        
        # === Bottom ===
        bottom_layout = QHBoxLayout()
        
        self.patch_name_label = QLabel(tr("patch_name"))
        bottom_layout.addWidget(self.patch_name_label)
        self.patch_name_edit = QComboBox()
        self.patch_name_edit.setEditable(True)
        self.patch_name_edit.addItems(["AutoPatch", "Compatibility Patch", "My Patch"])
        self.patch_name_edit.setMinimumWidth(200)
        bottom_layout.addWidget(self.patch_name_edit)
        
        bottom_layout.addStretch()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumWidth(200)
        self.progress_bar.setVisible(False)
        bottom_layout.addWidget(self.progress_bar)
        
        self.generate_btn = QPushButton(tr("create_patch"))
        self.generate_btn.setStyleSheet("""
            QPushButton { font-size: 14px; font-weight: bold; padding: 10px 25px;
                background: #4CAF50; color: white; border: none; border-radius: 5px; }
            QPushButton:hover { background: #45a049; }
            QPushButton:disabled { background: #cccccc; }
        """)
        self.generate_btn.clicked.connect(self.generate_patch)
        self.generate_btn.setEnabled(False)
        bottom_layout.addWidget(self.generate_btn)
        
        layout.addLayout(bottom_layout)
        self.statusBar().showMessage(tr("ready_status"))
    
    def init_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu(tr("menu_file"))
        
        save_action = QAction(tr("menu_save_profile"), self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_profile)
        file_menu.addAction(save_action)
        
        load_action = QAction(tr("menu_load_profile"), self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.load_profile)
        file_menu.addAction(load_action)
        
        self.recent_profiles_menu = file_menu.addMenu(tr("menu_recent"))
        self.update_recent_profiles_menu()
        
        file_menu.addSeparator()
        
        exit_action = QAction(tr("menu_exit"), self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Language menu
        self.language_menu = menubar.addMenu(tr("menu_language"))
        self.lang_action_group = QActionGroup(self)
        self.lang_action_group.setExclusive(True)
        
        for lang_code, lang_name in LANGUAGES.items():
            action = QAction(lang_name, self)
            action.setCheckable(True)
            action.setData(lang_code)
            if lang_code == i18n.current_language:
                action.setChecked(True)
            action.triggered.connect(lambda checked, code=lang_code: self.change_language(code))
            self.lang_action_group.addAction(action)
            self.language_menu.addAction(action)
        
        # Help menu
        help_menu = menubar.addMenu(tr("menu_help"))
        
        doc_action = QAction(tr("menu_documentation"), self)
        doc_action.setShortcut("F1")
        doc_action.triggered.connect(self.show_documentation)
        help_menu.addAction(doc_action)
        
        help_menu.addSeparator()
        
        about_action = QAction(tr("menu_about"), self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def change_language(self, lang_code: str):
        if lang_code == i18n.current_language:
            return
        
        i18n.current_language = lang_code
        self.settings.setValue("language", lang_code)
        self.retranslate_ui()
        self.log(tr("lang_restart"), "info")
    
    def retranslate_ui(self):
        self.setWindowTitle(f"{tr('window_title')} v{__version__}")
        
        self.mods_group.setTitle(tr("step1_title"))
        self.base_group.setTitle(tr("step2_title"))
        self.mods_select_group.setTitle(tr("step3_title"))
        self.log_group.setTitle(tr("log_title"))
        
        self.refresh_btn.setText(tr("refresh"))
        self.refresh_btn.setToolTip(tr("refresh_tooltip"))
        
        self.vanilla_radio.setText(tr("vanilla_game"))
        self.mod_radio.setText(tr("global_mod"))
        self.game_folder_label.setText(tr("game_folder"))
        self.vanilla_browse_btn.setText(tr("browse"))
        self.vanilla_auto_btn.setText(tr("auto"))
        self.vanilla_auto_btn.setToolTip(tr("auto_game_tooltip"))
        
        self.available_label.setText(tr("available_mods"))
        self.apply_order_label.setText(tr("apply_order"))
        self.add_btn.setToolTip(tr("add_tooltip"))
        self.add_all_btn.setToolTip(tr("add_all_tooltip"))
        self.remove_btn.setToolTip(tr("remove_tooltip"))
        self.remove_all_btn.setToolTip(tr("remove_all_tooltip"))
        self.up_btn.setText(tr("move_up"))
        self.down_btn.setText(tr("move_down"))
        self.update_selected_count()
        
        self.patch_name_label.setText(tr("patch_name"))
        self.generate_btn.setText(tr("create_patch"))
        self.statusBar().showMessage(tr("ready_status"))
        
        self.menuBar().clear()
        self.init_menu()
    
    def log(self, message: str, level: str = "info"):
        colors = {"info": "#000000", "success": "#4CAF50", "warning": "#FF9800", "error": "#f44336"}
        color = colors.get(level, "#000000")
        self.log_text.append(f'<span style="color: {color}">{message}</span>')
    
    def browse_mods_folder(self):
        """Добавить кастомную папку к сканированию"""
        path = QFileDialog.getExistingDirectory(self, tr("select_mods_folder"))
        if path:
            path = Path(path)
            if path not in self.all_mods_paths:
                self.all_mods_paths.append(path)
            self.scan_all_mods()
    
    def scan_all_mods(self):
        """Сканирование всех папок с модами"""
        # Находим все папки
        paths_info = get_all_mods_paths("ck3")
        
        self.all_mods_paths = []
        self.local_mods_path = None
        
        for p in paths_info:
            self.all_mods_paths.append(p["path"])
            if p["type"] == "local":
                self.local_mods_path = p["path"]
        
        # Если локальная не найдена, пробуем получить стандартный путь
        if not self.local_mods_path:
            self.local_mods_path = get_paradox_mods_path("ck3")
            if self.local_mods_path and not self.local_mods_path.exists():
                self.local_mods_path.mkdir(parents=True, exist_ok=True)
        
        if not self.all_mods_paths:
            self.mods_path_label.setText(tr("mods_folder_not_found"))
            self.log(tr("mods_folder_not_found"), "error")
            return
        
        # Обновляем UI - показываем что нашли
        summary_parts = []
        total_mods = 0
        for p in paths_info:
            summary_parts.append(f"{p['name']}")
            total_mods += p['count']
        
        self.mods_path_label.setText(" + ".join(summary_parts))
        self.log(f"✓ {tr('found_folders')}: {len(self.all_mods_paths)}, {tr('total_mods')}: {total_mods}", "success")
        
        # Запускаем сканирование
        self.scan_mods()
    
    def browse_vanilla_folder(self):
        path = QFileDialog.getExistingDirectory(self, tr("select_game_folder"))
        if path:
            self.vanilla_path_label.setText(path)
            self.base_path = Path(path)
            self.update_generate_button()
    
    def auto_detect_game(self):
        """Автоопределение пути к игре CK3"""
        path = get_game_install_path("ck3")
        if path and path.exists():
            self.vanilla_path_label.setText(str(path))
            self.base_path = path
            self.update_generate_button()
            self._mod_changes_cache.clear()
            self.refresh_available_list()
            self.log(f"✓ {tr('game_found')}: {path}", "success")
        else:
            QMessageBox.warning(self, tr("not_found"), tr("game_not_found"))
    
    def scan_mods(self):
        if not self.all_mods_paths:
            QMessageBox.warning(self, tr("error"), tr("select_folder_error"))
            return
        
        self.log(tr("scanning"), "info")
        self.statusBar().showMessage(tr("scanning"))
        
        self.scan_thread = ScanThread(self.all_mods_paths)
        self.scan_thread.finished.connect(self.on_scan_finished)
        self.scan_thread.start()
    
    def on_scan_finished(self, mods: List[ModInfo]):
        self.all_mods = mods
        
        # Обновляем данные для выбора глобального мода
        self.base_mod_data = [(mod.name, mod.path) for mod in sorted(mods, key=lambda m: m.name.lower())]
        self.base_mod_index = 0 if self.base_mod_data else -1
        if self.base_mod_data:
            self.base_mod_label.setText(self.base_mod_data[0][0])
            self.on_base_mod_changed(0)
        else:
            self.base_mod_label.setText("")
        
        self.refresh_available_list()
        self.log(tr("found_mods", len(mods)), "success")
        self.statusBar().showMessage(tr("found_mods", len(mods)))
    
    def refresh_available_list(self):
        self.available_list.clear()
        
        base_path = None
        if self.mod_radio.isChecked():
            if self.base_mod_index >= 0 and self.base_mod_index < len(self.base_mod_data):
                base_path = self.base_mod_data[self.base_mod_index][1]
        elif self.vanilla_radio.isChecked():
            vanilla_text = self.vanilla_path_label.text()
            if vanilla_text and vanilla_text != tr("not_selected"):
                base_path = Path(vanilla_text)
        
        selected_paths = set()
        for i in range(self.selected_list.count()):
            item = self.selected_list.item(i)
            mod = item.data(Qt.UserRole)
            selected_paths.add(mod.path)
        
        base_files = set()
        base_path_str = str(base_path) if base_path else ""
        
        if base_path and Path(base_path).exists():
            if base_path_str in self._base_files_cache:
                base_files = self._base_files_cache[base_path_str]
            else:
                self.statusBar().showMessage(tr("analyzing_base"))
                QApplication.processEvents()
                base_files = self._collect_base_files(Path(base_path))
                self._base_files_cache[base_path_str] = base_files
        
        skipped_empty = 0
        checked = 0
        
        for mod in sorted(self.all_mods, key=lambda m: m.name.lower()):
            if base_path and mod.path == base_path:
                continue
            if mod.path in selected_paths:
                continue
            
            if base_files:
                cache_key = (str(mod.path), base_path_str)
                
                if cache_key in self._mod_changes_cache:
                    has_changes = self._mod_changes_cache[cache_key]
                else:
                    checked += 1
                    if checked % 5 == 0:
                        self.statusBar().showMessage(tr("checking_mods", checked))
                        QApplication.processEvents()
                    
                    has_changes = self._mod_has_changes(mod, base_files, Path(base_path))
                    self._mod_changes_cache[cache_key] = has_changes
                
                if not has_changes:
                    skipped_empty += 1
                    continue
            
            item = QListWidgetItem(f"{mod.name} ({tr('files_count', len(mod.files))})")
            item.setData(Qt.UserRole, mod)
            
            deps = read_mod_dependencies(mod.path)
            if deps:
                item.setToolTip(tr("depends_on", ', '.join(deps)))
            
            self.available_list.addItem(item)
        
        if skipped_empty > 0:
            self.log(tr("hidden_mods", skipped_empty), "info")
        
        self.statusBar().showMessage(tr("available_count", self.available_list.count()))
    
    def _collect_base_files(self, base_path: Path) -> set:
        files = set()
        mergeable_folders = {'common', 'events', 'history', 'decisions', 'gui', 'interface', 'gfx',
                           'scripted_triggers', 'scripted_effects', 'on_actions'}
        
        for folder in mergeable_folders:
            folder_path = base_path / folder
            if folder_path.exists():
                for root, dirs, filenames in os.walk(folder_path):
                    for filename in filenames:
                        if filename.endswith(('.txt', '.gui', '.gfx')):
                            filepath = Path(root) / filename
                            relative = filepath.relative_to(base_path)
                            files.add(str(relative))
        return files
    
    def _mod_has_changes(self, mod: 'ModInfo', base_files: set, base_path: Path) -> bool:
        mod_path = Path(mod.path)
        mod_files_set = set(mod.files.keys())
        common_files = mod_files_set & base_files
        
        if not common_files:
            return False
        
        for mod_file in common_files:
            base_file = base_path / mod_file
            mod_file_path = mod_path / mod_file
            
            if base_file.exists() and mod_file_path.exists():
                try:
                    with open(base_file, 'r', encoding='utf-8-sig') as f:
                        base_content = f.read()
                    with open(mod_file_path, 'r', encoding='utf-8-sig') as f:
                        mod_content = f.read()
                    
                    if self._quick_normalize(base_content) != self._quick_normalize(mod_content):
                        return True
                except Exception:
                    return True
        return False
    
    def _quick_normalize(self, content: str) -> str:
        lines = []
        for line in content.split('\n'):
            if '#' in line:
                line = line[:line.index('#')]
            line = line.strip()
            if line:
                lines.append(line)
        return ''.join(lines).replace(' ', '').replace('\t', '')
    
    def on_base_type_changed(self):
        is_vanilla = self.vanilla_radio.isChecked()
        self.vanilla_path_widget.setVisible(is_vanilla)
        self.base_mod_btn.setEnabled(not is_vanilla)
        self.base_is_vanilla = is_vanilla
        
        if is_vanilla:
            vanilla_text = self.vanilla_path_label.text()
            if vanilla_text and vanilla_text != tr("not_selected"):
                self.base_path = Path(vanilla_text)
            else:
                self.base_path = None
        else:
            if self.base_mod_index >= 0 and self.base_mod_index < len(self.base_mod_data):
                self.base_path = self.base_mod_data[self.base_mod_index][1]
        
        self._mod_changes_cache.clear()
        self.refresh_available_list()
        self.update_generate_button()
    
    def on_base_mod_changed(self, index):
        if index >= 0 and index < len(self.base_mod_data):
            self.base_mod_index = index
            self.base_path = self.base_mod_data[index][1]
            self._mod_changes_cache.clear()
            self.refresh_available_list()
            self.update_generate_button()
    
    def select_base_mod(self):
        """Диалог выбора глобального мода"""
        if not self.base_mod_data:
            QMessageBox.warning(self, tr("error"), tr("scan_mods_first"))
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("select_base_mod"))
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        
        list_widget = QListWidget()
        for name, path in self.base_mod_data:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, path)
            item.setToolTip(str(path))
            list_widget.addItem(item)
        
        if self.base_mod_index >= 0:
            list_widget.setCurrentRow(self.base_mod_index)
        list_widget.itemDoubleClicked.connect(dialog.accept)
        layout.addWidget(list_widget)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        if dialog.exec_() == QDialog.Accepted and list_widget.currentItem():
            idx = list_widget.currentRow()
            self.base_mod_index = idx
            self.base_mod_label.setText(self.base_mod_data[idx][0])
            self.on_base_mod_changed(idx)
    
    def add_selected_mods(self):
        for item in self.available_list.selectedItems():
            mod = item.data(Qt.UserRole)
            new_item = QListWidgetItem(f"{mod.name} ({tr('files_count', len(mod.files))})")
            new_item.setData(Qt.UserRole, mod)
            self.selected_list.addItem(new_item)
        
        self.refresh_available_list()
        self.update_selected_count()
        self.update_generate_button()
    
    def add_all_mods(self):
        for i in range(self.available_list.count()):
            item = self.available_list.item(i)
            mod = item.data(Qt.UserRole)
            new_item = QListWidgetItem(f"{mod.name} ({tr('files_count', len(mod.files))})")
            new_item.setData(Qt.UserRole, mod)
            self.selected_list.addItem(new_item)
        
        self.refresh_available_list()
        self.update_selected_count()
        self.update_generate_button()
    
    def remove_selected_mods(self):
        for item in self.selected_list.selectedItems():
            self.selected_list.takeItem(self.selected_list.row(item))
        
        self.refresh_available_list()
        self.update_selected_count()
        self.update_generate_button()
    
    def remove_all_mods(self):
        self.selected_list.clear()
        self.refresh_available_list()
        self.update_selected_count()
        self.update_generate_button()
    
    def move_up(self):
        current_row = self.selected_list.currentRow()
        if current_row > 0:
            item = self.selected_list.takeItem(current_row)
            self.selected_list.insertItem(current_row - 1, item)
            self.selected_list.setCurrentRow(current_row - 1)
    
    def move_down(self):
        current_row = self.selected_list.currentRow()
        if current_row < self.selected_list.count() - 1:
            item = self.selected_list.takeItem(current_row)
            self.selected_list.insertItem(current_row + 1, item)
            self.selected_list.setCurrentRow(current_row + 1)
    
    def update_selected_count(self):
        self.selected_count_label.setText(tr("selected_count", self.selected_list.count()))
    
    def update_generate_button(self):
        self.generate_btn.setEnabled(self.base_path is not None and self.selected_list.count() > 0)
    
    def generate_patch(self):
        if not self.base_path:
            QMessageBox.warning(self, tr("error"), tr("select_base_error"))
            return
        
        if self.selected_list.count() == 0:
            QMessageBox.warning(self, tr("error"), tr("select_mods_error"))
            return
        
        patch_name = self.patch_name_edit.currentText() or "AutoPatch"
        safe_patch_name = patch_name.replace(" ", "_").replace("+", "_")
        
        # Используем локальную папку модов для создания патча
        if self.local_mods_path and self.local_mods_path.exists():
            output_path = self.local_mods_path / safe_patch_name
        else:
            # Fallback - спросить пользователя
            base_output = QFileDialog.getExistingDirectory(self, tr("select_output"))
            if not base_output:
                return
            output_path = Path(base_output) / safe_patch_name
        
        mod_paths = []
        for i in range(self.selected_list.count()):
            item = self.selected_list.item(i)
            mod = item.data(Qt.UserRole)
            mod_paths.append(Path(mod.path))
        
        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.patch_thread = PatchThread(
            self.base_path, self.base_is_vanilla, mod_paths, output_path, patch_name
        )
        self.patch_thread.progress.connect(self.on_patch_progress)
        self.patch_thread.finished.connect(self.on_patch_finished)
        self.patch_thread.start()
    
    def on_patch_progress(self, message: str, current: int, total: int):
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))
        self.statusBar().showMessage(message)
    
    def on_patch_finished(self, stats: PatchStats):
        self.generate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if stats.errors:
            for e in stats.errors:
                self.log(e, "error")
        
        for w in stats.warnings:
            self.log(w, "warning")
        
        if stats.failed_files == 0:
            self.log(tr("patch_success_log", stats.merged_files, stats.skipped_files), "success")
            QMessageBox.information(self, tr("done"),
                tr("patch_created", stats.merged_files, stats.copied_files, 
                   stats.skipped_files, stats.failed_files))
        else:
            self.log(tr("patch_errors_log"), "warning")
            QMessageBox.warning(self, tr("done_with_errors"),
                tr("patch_created_errors", stats.merged_files, stats.copied_files,
                   stats.skipped_files, stats.failed_files))
    
    def show_about(self):
        QMessageBox.about(self, tr("about_title"), tr("about_text"))
    
    def show_documentation(self):
        """Открыть документацию на текущем языке"""
        import webbrowser
        import tempfile
        
        # Определяем путь к документации
        lang = i18n.current_language
        
        # Ищем файл документации
        possible_paths = [
            # При запуске из исходников
            Path(__file__).parent.parent.parent / "resources" / "docs" / f"README_{lang}.md",
            Path(__file__).parent.parent.parent / "resources" / "docs" / "README_en.md",
            # При запуске из exe (PyInstaller)
            Path(sys.executable).parent / "resources" / "docs" / f"README_{lang}.md",
            Path(sys.executable).parent / "resources" / "docs" / "README_en.md",
            # Альтернативный путь для PyInstaller
            Path(getattr(sys, '_MEIPASS', '')) / "resources" / "docs" / f"README_{lang}.md" if hasattr(sys, '_MEIPASS') else None,
            Path(getattr(sys, '_MEIPASS', '')) / "resources" / "docs" / "README_en.md" if hasattr(sys, '_MEIPASS') else None,
        ]
        
        doc_path = None
        for p in possible_paths:
            if p and p.exists():
                doc_path = p
                break
        
        if doc_path:
            # Конвертируем markdown в простой HTML и открываем в браузере
            try:
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Простая конвертация markdown в HTML
                html = self._markdown_to_html(content)
                
                # Сохраняем во временный файл и открываем
                with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
                    f.write(html)
                    temp_path = f.name
                
                webbrowser.open(f'file://{temp_path}')
                
            except Exception as e:
                self.log(f"Error opening documentation: {e}", "error")
        else:
            QMessageBox.warning(self, tr("error"), tr("doc_not_found"))
    
    def _markdown_to_html(self, md: str) -> str:
        """Простая конвертация markdown в HTML"""
        import re
        
        html = md
        
        # Заголовки
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # Жирный и курсив
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        # Код
        html = re.sub(r'```(\w*)\n(.*?)```', r'<pre><code>\2</code></pre>', html, flags=re.DOTALL)
        html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
        
        # Ссылки
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        
        # Списки
        html = re.sub(r'^\- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        
        # Горизонтальная линия
        html = re.sub(r'^---$', r'<hr>', html, flags=re.MULTILINE)
        
        # Параграфы
        html = re.sub(r'\n\n', r'</p><p>', html)
        
        # Таблицы - простая обработка
        lines = html.split('\n')
        in_table = False
        result = []
        for line in lines:
            if '|' in line and not line.strip().startswith('<'):
                if not in_table:
                    result.append('<table border="1" cellpadding="5" cellspacing="0">')
                    in_table = True
                if line.strip().startswith('|--') or line.strip().startswith('| --'):
                    continue  # Пропускаем разделитель таблицы
                cells = [c.strip() for c in line.split('|')[1:-1]]
                result.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
            else:
                if in_table:
                    result.append('</table>')
                    in_table = False
                result.append(line)
        if in_table:
            result.append('</table>')
        html = '\n'.join(result)
        
        # Оборачиваем в HTML документ
        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Paradox Mod Patcher - Documentation</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
               max-width: 900px; margin: 40px auto; padding: 20px; line-height: 1.6; }}
        h1, h2, h3 {{ color: #333; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
        table {{ border-collapse: collapse; margin: 15px 0; }}
        td, th {{ padding: 8px 12px; border: 1px solid #ddd; }}
        a {{ color: #0066cc; }}
        hr {{ border: none; border-top: 1px solid #ddd; margin: 30px 0; }}
        li {{ margin: 5px 0; }}
    </style>
</head>
<body>
<p>{html}</p>
</body>
</html>'''
    
    def get_profiles_dir(self) -> Path:
        profiles_dir = Path.home() / ".paradox_mod_patcher" / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        return profiles_dir
    
    def save_profile(self):
        profile_data = {
            "mods_path": self.mods_path_label.text(),
            "base_is_vanilla": self.vanilla_radio.isChecked(),
            "base_mod_name": self.base_mod_label.text() if self.mod_radio.isChecked() else "",
            "vanilla_path": self.vanilla_path_label.text(),
            "selected_mods": [],
            "patch_name": self.patch_name_edit.currentText()
        }
        
        for i in range(self.selected_list.count()):
            item = self.selected_list.item(i)
            mod = item.data(Qt.UserRole)
            profile_data["selected_mods"].append(mod.name)
        
        name, ok = QInputDialog.getText(self, tr("save_profile_title"), tr("profile_name_prompt"),
                                        text=self.patch_name_edit.currentText())
        
        if ok and name:
            profile_path = self.get_profiles_dir() / f"{name}.json"
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=2)
            
            self.add_recent_profile(str(profile_path))
            self.log(tr("profile_saved", name), "success")
    
    def load_profile(self, profile_path: str = None):
        if not profile_path:
            profile_path, _ = QFileDialog.getOpenFileName(
                self, tr("load_profile_title"), str(self.get_profiles_dir()), "JSON files (*.json)")
        
        if not profile_path or not Path(profile_path).exists():
            return
        
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
            
            mods_path = profile_data.get("mods_path", "")
            if mods_path and mods_path != tr("not_selected"):
                self.mods_path_label.setText(mods_path)
            
            if mods_path and Path(mods_path).exists():
                self.scan_mods()
                if hasattr(self, 'scan_thread'):
                    self.scan_thread.wait()
            
            if profile_data.get("base_is_vanilla"):
                self.vanilla_radio.setChecked(True)
                vanilla_path = profile_data.get("vanilla_path", "")
                if vanilla_path:
                    self.vanilla_path_label.setText(vanilla_path)
                    self.base_path = Path(vanilla_path)
            else:
                self.mod_radio.setChecked(True)
                base_mod_name = profile_data.get("base_mod_name", "")
                if base_mod_name:
                    # Ищем мод по имени в списке
                    for idx, (name, path) in enumerate(self.base_mod_data):
                        if name == base_mod_name:
                            self.base_mod_index = idx
                            self.base_mod_label.setText(name)
                            self.on_base_mod_changed(idx)
                            break
            
            self.selected_list.clear()
            for mod_name in profile_data.get("selected_mods", []):
                for mod in self.all_mods:
                    if mod.name == mod_name:
                        item = QListWidgetItem(f"{mod.name} ({tr('files_count', len(mod.files))})")
                        item.setData(Qt.UserRole, mod)
                        self.selected_list.addItem(item)
                        break
            
            self.refresh_available_list()
            self.update_selected_count()
            self.update_generate_button()
            
            patch_name = profile_data.get("patch_name", "")
            if patch_name:
                self.patch_name_edit.setCurrentText(patch_name)
            
            self.add_recent_profile(profile_path)
            self.log(tr("profile_loaded", Path(profile_path).stem), "success")
            
        except Exception as e:
            self.log(tr("profile_load_error", str(e)), "error")
    
    def add_recent_profile(self, profile_path: str):
        recent = self.settings.value("recent_profiles", [])
        if isinstance(recent, str):
            recent = [recent] if recent else []
        
        if profile_path in recent:
            recent.remove(profile_path)
        recent.insert(0, profile_path)
        recent = recent[:10]
        
        self.settings.setValue("recent_profiles", recent)
        self.update_recent_profiles_menu()
    
    def update_recent_profiles_menu(self):
        self.recent_profiles_menu.clear()
        
        recent = self.settings.value("recent_profiles", [])
        if isinstance(recent, str):
            recent = [recent] if recent else []
        
        if not recent:
            action = QAction(tr("menu_empty"), self)
            action.setEnabled(False)
            self.recent_profiles_menu.addAction(action)
            return
        
        for profile_path in recent:
            if Path(profile_path).exists():
                name = Path(profile_path).stem
                action = QAction(name, self)
                action.setData(profile_path)
                action.triggered.connect(lambda checked, p=profile_path: self.load_profile(p))
                self.recent_profiles_menu.addAction(action)
