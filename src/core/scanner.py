"""
Mod Scanner
Сканер директории модов Paradox
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ModInfo:
    """Информация о моде"""
    name: str
    path: Path
    version: str = ""
    supported_version: str = ""
    dependencies: List[str] = field(default_factory=list)
    load_order: int = 0
    files: Dict[str, Path] = field(default_factory=dict)
    enabled: bool = True
    
    
@dataclass
class FileConflict:
    """Информация о конфликте файлов"""
    relative_path: str
    mods: List[ModInfo] = field(default_factory=list)
    conflict_type: str = "overwrite"  # overwrite, partial, compatible


@dataclass
class ScanResult:
    """Результат сканирования"""
    mods: List[ModInfo] = field(default_factory=list)
    conflicts: List[FileConflict] = field(default_factory=list)
    total_files: int = 0
    conflicting_files: int = 0


class ModScanner:
    """Сканер директории модов"""
    
    # Расширения файлов для отслеживания
    TRACKED_EXTENSIONS = {'.txt', '.gui', '.gfx', '.asset'}
    
    # Папки для сканирования
    TRACKED_FOLDERS = {
        'common', 'events', 'history', 'localization', 
        'gfx', 'gui', 'interface', 'map_data', 'music', 'sound'
    }
    
    def __init__(self, mods_directory: Path):
        self.mods_directory = Path(mods_directory)
        self.mods: List[ModInfo] = []
        
    def scan_all(self) -> ScanResult:
        """Сканирует все моды в директории"""
        result = ScanResult()
        
        # Находим все папки модов
        for item in self.mods_directory.iterdir():
            if item.is_dir():
                # Проверяем есть ли descriptor.mod
                descriptor = item / "descriptor.mod"
                if descriptor.exists():
                    mod = self._scan_mod(item)
                    if mod:
                        result.mods.append(mod)
                        
        # Ищем конфликты
        result.conflicts = self._find_conflicts(result.mods)
        
        # Считаем статистику
        result.total_files = sum(len(m.files) for m in result.mods)
        result.conflicting_files = len(result.conflicts)
        
        return result
    
    def scan_from_load_order(self, load_order_file: Path) -> ScanResult:
        """
        Сканирует моды на основе файла порядка загрузки
        (dlc_load.json или game_data.json)
        """
        result = ScanResult()
        
        try:
            with open(load_order_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Парсим разные форматы
            if 'enabled_mods' in data:
                # Формат dlc_load.json
                enabled_mods = data['enabled_mods']
            elif 'mods' in data:
                # Другой формат
                enabled_mods = data['mods']
            else:
                enabled_mods = []
                
            for i, mod_path in enumerate(enabled_mods):
                # mod_path может быть относительным или абсолютным
                full_path = self._resolve_mod_path(mod_path)
                if full_path and full_path.exists():
                    mod = self._scan_mod(full_path)
                    if mod:
                        mod.load_order = i
                        result.mods.append(mod)
                        
        except Exception as e:
            print(f"Error reading load order: {e}")
            
        result.conflicts = self._find_conflicts(result.mods)
        result.total_files = sum(len(m.files) for m in result.mods)
        result.conflicting_files = len(result.conflicts)
        
        return result
    
    def _resolve_mod_path(self, mod_path: str) -> Optional[Path]:
        """Разрешает путь к моду"""
        path = Path(mod_path)
        
        # Абсолютный путь
        if path.is_absolute() and path.exists():
            return path
            
        # Относительный от директории модов
        resolved = self.mods_directory / path
        if resolved.exists():
            return resolved
            
        # Пробуем найти по имени
        if path.suffix == '.mod':
            # Это .mod файл, читаем путь из него
            mod_file = self.mods_directory / path
            if mod_file.exists():
                real_path = self._read_mod_path(mod_file)
                if real_path:
                    return real_path
                    
        return None
    
    def _read_mod_path(self, mod_file: Path) -> Optional[Path]:
        """Читает путь к моду из .mod файла"""
        try:
            with open(mod_file, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            match = re.search(r'path\s*=\s*"([^"]+)"', content)
            if match:
                return Path(match.group(1))
        except:
            pass
        return None
    
    def _scan_mod(self, mod_path: Path) -> Optional[ModInfo]:
        """Сканирует один мод"""
        descriptor = mod_path / "descriptor.mod"
        if not descriptor.exists():
            return None
            
        # Парсим descriptor.mod
        try:
            with open(descriptor, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except:
            return None
            
        # Извлекаем информацию
        name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
        version_match = re.search(r'version\s*=\s*"([^"]+)"', content)
        supported_match = re.search(r'supported_version\s*=\s*"([^"]+)"', content)
        
        # Dependencies
        deps = []
        deps_match = re.search(r'dependencies\s*=\s*\{([^}]+)\}', content, re.DOTALL)
        if deps_match:
            deps = re.findall(r'"([^"]+)"', deps_match.group(1))
            
        mod = ModInfo(
            name=name_match.group(1) if name_match else mod_path.name,
            path=mod_path,
            version=version_match.group(1) if version_match else "",
            supported_version=supported_match.group(1) if supported_match else "",
            dependencies=deps
        )
        
        # Сканируем файлы
        mod.files = self._scan_mod_files(mod_path)
        
        return mod
    
    def _scan_mod_files(self, mod_path: Path) -> Dict[str, Path]:
        """Сканирует все релевантные файлы в моде"""
        files = {}
        
        for root, dirs, filenames in os.walk(mod_path):
            root_path = Path(root)
            relative_root = root_path.relative_to(mod_path)
            
            # Проверяем что это отслеживаемая папка
            if relative_root.parts:
                top_folder = relative_root.parts[0]
                if top_folder not in self.TRACKED_FOLDERS and top_folder != '.':
                    continue
                    
            for filename in filenames:
                filepath = root_path / filename
                ext = filepath.suffix.lower()
                
                if ext in self.TRACKED_EXTENSIONS:
                    relative = filepath.relative_to(mod_path)
                    files[str(relative)] = filepath
                    
        return files
    
    def _find_conflicts(self, mods: List[ModInfo]) -> List[FileConflict]:
        """Находит конфликтующие файлы между модами"""
        file_to_mods: Dict[str, List[ModInfo]] = defaultdict(list)
        
        for mod in mods:
            for relative_path in mod.files:
                file_to_mods[relative_path].append(mod)
                
        conflicts = []
        for path, mod_list in file_to_mods.items():
            if len(mod_list) > 1:
                # Сортируем по порядку загрузки
                sorted_mods = sorted(mod_list, key=lambda m: m.load_order)
                
                conflict = FileConflict(
                    relative_path=path,
                    mods=sorted_mods,
                    conflict_type=self._determine_conflict_type(path, sorted_mods)
                )
                conflicts.append(conflict)
                
        return sorted(conflicts, key=lambda c: c.relative_path)
    
    def _determine_conflict_type(self, path: str, mods: List[ModInfo]) -> str:
        """Определяет тип конфликта"""
        # Локализация обычно мержится
        if 'localization' in path:
            return 'compatible'
            
        # GUI часто можно мержить
        if path.endswith('.gui'):
            return 'partial'
            
        # Остальное - перезапись
        return 'overwrite'


def get_paradox_mods_path(game: str = "ck3") -> Optional[Path]:
    """Возвращает путь к локальной папке модов для игры"""
    import platform
    
    system = platform.system()
    
    if system == "Windows":
        docs = Path.home() / "Documents" / "Paradox Interactive"
    elif system == "Linux":
        docs = Path.home() / ".local" / "share" / "Paradox Interactive"
    elif system == "Darwin":  # macOS
        docs = Path.home() / "Documents" / "Paradox Interactive"
    else:
        return None
        
    game_folders = {
        "ck3": "Crusader Kings III",
        "eu4": "Europa Universalis IV",
        "hoi4": "Hearts of Iron IV",
        "stellaris": "Stellaris",
        "vic3": "Victoria 3"
    }
    
    game_folder = game_folders.get(game.lower())
    if game_folder:
        return docs / game_folder / "mod"
        
    return None


def get_all_mods_paths(game: str = "ck3") -> List[Dict[str, any]]:
    """
    Находит все папки с модами: локальную и Steam Workshop.
    Возвращает список словарей с информацией о каждой папке.
    """
    import platform
    
    steam_app_ids = {
        "ck3": "1158310",
        "eu4": "236850",
        "hoi4": "394360",
        "stellaris": "281990",
        "vic3": "529340"
    }
    
    game_key = game.lower()
    steam_app_id = steam_app_ids.get(game_key, "")
    
    results = []
    
    # 1. Локальная папка модов
    local_path = get_paradox_mods_path(game)
    if local_path and local_path.exists():
        mod_count = sum(1 for d in local_path.iterdir() if d.is_dir() and (d / "descriptor.mod").exists())
        if mod_count > 0:
            results.append({
                "path": local_path,
                "type": "local",
                "name": f"Local mods ({mod_count})",
                "count": mod_count
            })
    
    # 2. Steam Workshop
    workshop_paths = _find_steam_workshop_path(steam_app_id)
    for wp in workshop_paths:
        if wp.exists():
            mod_count = sum(1 for d in wp.iterdir() if d.is_dir())
            if mod_count > 0:
                results.append({
                    "path": wp,
                    "type": "workshop", 
                    "name": f"Steam Workshop ({mod_count})",
                    "count": mod_count
                })
    
    return results


def _find_steam_workshop_path(steam_app_id: str) -> List[Path]:
    """Находит папки Steam Workshop для игры"""
    import platform
    
    system = platform.system()
    workshop_paths = []
    
    if system == "Windows":
        # Ищем через реестр и стандартные пути
        steam_paths = []
        
        try:
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
                steam_paths.append(Path(winreg.QueryValueEx(key, "InstallPath")[0]))
                winreg.CloseKey(key)
            except:
                pass
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
                steam_paths.append(Path(winreg.QueryValueEx(key, "InstallPath")[0]))
                winreg.CloseKey(key)
            except:
                pass
        except ImportError:
            pass
        
        # Стандартные пути
        standard = [
            Path(r"C:\Program Files (x86)\Steam"),
            Path(r"C:\Program Files\Steam"),
            Path(r"D:\Steam"),
            Path(r"D:\SteamLibrary"),
            Path(r"E:\Steam"),
            Path(r"E:\SteamLibrary"),
            Path(r"F:\Steam"),
            Path(r"F:\SteamLibrary"),
        ]
        steam_paths.extend(standard)
        
        # Читаем дополнительные библиотеки из libraryfolders.vdf
        for sp in list(steam_paths):
            if sp and sp.exists():
                vdf_path = sp / "steamapps" / "libraryfolders.vdf"
                if vdf_path.exists():
                    steam_paths.extend(_parse_steam_libraries(vdf_path))
        
        # Ищем workshop в каждой библиотеке
        seen = set()
        for sp in steam_paths:
            if sp and sp.exists():
                workshop = sp / "steamapps" / "workshop" / "content" / steam_app_id
                if workshop.exists() and str(workshop) not in seen:
                    workshop_paths.append(workshop)
                    seen.add(str(workshop))
    
    elif system == "Linux":
        home = Path.home()
        steam_paths = [
            home / ".steam" / "steam",
            home / ".local" / "share" / "Steam",
        ]
        
        for sp in list(steam_paths):
            if sp.exists():
                vdf_path = sp / "steamapps" / "libraryfolders.vdf"
                if vdf_path.exists():
                    steam_paths.extend(_parse_steam_libraries(vdf_path))
        
        seen = set()
        for sp in steam_paths:
            if sp and sp.exists():
                workshop = sp / "steamapps" / "workshop" / "content" / steam_app_id
                if workshop.exists() and str(workshop) not in seen:
                    workshop_paths.append(workshop)
                    seen.add(str(workshop))
    
    elif system == "Darwin":
        home = Path.home()
        steam_path = home / "Library" / "Application Support" / "Steam"
        
        if steam_path.exists():
            steam_paths = [steam_path]
            vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
            if vdf_path.exists():
                steam_paths.extend(_parse_steam_libraries(vdf_path))
            
            for sp in steam_paths:
                if sp and sp.exists():
                    workshop = sp / "steamapps" / "workshop" / "content" / steam_app_id
                    if workshop.exists():
                        workshop_paths.append(workshop)
    
    return workshop_paths


def get_game_install_path(game: str = "ck3") -> Optional[Path]:
    """
    Автоопределение пути установки игры.
    Ищет в Steam, GOG, Xbox Game Pass и стандартных путях.
    Возвращает путь к папке game/ внутри установки.
    """
    import platform
    
    system = platform.system()
    
    # Steam App IDs
    steam_app_ids = {
        "ck3": "1158310",
        "eu4": "236850",
        "hoi4": "394360",
        "stellaris": "281990",
        "vic3": "529340"
    }
    
    # Названия папок игр
    game_names = {
        "ck3": "Crusader Kings III",
        "eu4": "Europa Universalis IV", 
        "hoi4": "Hearts of Iron IV",
        "stellaris": "Stellaris",
        "vic3": "Victoria 3"
    }
    
    game_key = game.lower()
    game_name = game_names.get(game_key, "")
    steam_app_id = steam_app_ids.get(game_key, "")
    
    found_paths = []
    
    if system == "Windows":
        found_paths.extend(_find_game_windows(game_name, steam_app_id))
    elif system == "Linux":
        found_paths.extend(_find_game_linux(game_name, steam_app_id))
    elif system == "Darwin":
        found_paths.extend(_find_game_macos(game_name, steam_app_id))
    
    # Проверяем найденные пути
    for path in found_paths:
        game_folder = path / "game"
        if game_folder.exists():
            # Проверяем что это действительно CK3
            if (game_folder / "common").exists() or (game_folder / "events").exists():
                return game_folder
        # Некоторые версии без подпапки game
        if (path / "common").exists():
            return path
    
    return None


def _find_game_windows(game_name: str, steam_app_id: str) -> List[Path]:
    """Поиск игры на Windows"""
    paths = []
    
    # 1. Steam через реестр
    try:
        import winreg
        
        # Ищем путь Steam
        steam_path = None
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
            steam_path = Path(winreg.QueryValueEx(key, "InstallPath")[0])
            winreg.CloseKey(key)
        except:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
                steam_path = Path(winreg.QueryValueEx(key, "InstallPath")[0])
                winreg.CloseKey(key)
            except:
                pass
        
        if steam_path:
            # Ищем библиотеки Steam
            library_paths = [steam_path]
            
            # Читаем libraryfolders.vdf
            vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
            if vdf_path.exists():
                library_paths.extend(_parse_steam_libraries(vdf_path))
            
            # Ищем игру в библиотеках
            for lib_path in library_paths:
                game_path = lib_path / "steamapps" / "common" / game_name
                if game_path.exists():
                    paths.append(game_path)
        
        # 2. GOG через реестр
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                rf"SOFTWARE\WOW6432Node\GOG.com\Games\1158310")  # CK3 GOG ID
            gog_path = Path(winreg.QueryValueEx(key, "path")[0])
            winreg.CloseKey(key)
            if gog_path.exists():
                paths.append(gog_path)
        except:
            pass
            
    except ImportError:
        pass  # winreg не доступен
    
    # 3. Xbox Game Pass
    xbox_paths = [
        Path(r"C:\XboxGames") / game_name / "Content",
        Path.home() / "XboxGames" / game_name / "Content",
    ]
    for p in xbox_paths:
        if p.exists():
            paths.append(p)
    
    # 4. Стандартные пути
    standard_paths = [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common") / game_name,
        Path(r"C:\Program Files\Steam\steamapps\common") / game_name,
        Path(r"D:\Steam\steamapps\common") / game_name,
        Path(r"D:\SteamLibrary\steamapps\common") / game_name,
        Path(r"E:\Steam\steamapps\common") / game_name,
        Path(r"E:\SteamLibrary\steamapps\common") / game_name,
        Path(r"C:\GOG Games") / game_name,
        Path(r"D:\GOG Games") / game_name,
        Path(r"C:\Games") / game_name,
        Path(r"D:\Games") / game_name,
    ]
    
    for p in standard_paths:
        if p.exists() and p not in paths:
            paths.append(p)
    
    return paths


def _find_game_linux(game_name: str, steam_app_id: str) -> List[Path]:
    """Поиск игры на Linux"""
    paths = []
    home = Path.home()
    
    # Steam paths
    steam_paths = [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
    ]
    
    for steam_path in steam_paths:
        if steam_path.exists():
            # Библиотеки Steam
            library_paths = [steam_path]
            
            vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
            if vdf_path.exists():
                library_paths.extend(_parse_steam_libraries(vdf_path))
            
            for lib_path in library_paths:
                game_path = lib_path / "steamapps" / "common" / game_name
                if game_path.exists():
                    paths.append(game_path)
    
    # Proton/Wine prefix
    proton_paths = [
        home / ".steam" / "steam" / "steamapps" / "compatdata" / steam_app_id / "pfx" / "drive_c",
    ]
    for p in proton_paths:
        if p.exists():
            # Ищем внутри prefix
            for subdir in ["Program Files (x86)", "Program Files", "Games"]:
                game_path = p / subdir / game_name
                if game_path.exists():
                    paths.append(game_path)
    
    return paths


def _find_game_macos(game_name: str, steam_app_id: str) -> List[Path]:
    """Поиск игры на macOS"""
    paths = []
    home = Path.home()
    
    # Steam на macOS
    steam_path = home / "Library" / "Application Support" / "Steam"
    if steam_path.exists():
        library_paths = [steam_path]
        
        vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
        if vdf_path.exists():
            library_paths.extend(_parse_steam_libraries(vdf_path))
        
        for lib_path in library_paths:
            game_path = lib_path / "steamapps" / "common" / game_name
            if game_path.exists():
                paths.append(game_path)
    
    # Applications
    app_paths = [
        Path("/Applications") / f"{game_name}.app" / "Contents" / "Resources",
        home / "Applications" / f"{game_name}.app" / "Contents" / "Resources",
    ]
    for p in app_paths:
        if p.exists():
            paths.append(p)
    
    return paths


def _parse_steam_libraries(vdf_path: Path) -> List[Path]:
    """Парсит libraryfolders.vdf для поиска дополнительных библиотек Steam"""
    libraries = []
    
    try:
        with open(vdf_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Простой парсинг VDF - ищем пути
        # Формат: "path"		"D:\\SteamLibrary"
        path_matches = re.findall(r'"path"\s*"([^"]+)"', content)
        for path_str in path_matches:
            # Обработка экранированных путей Windows
            path_str = path_str.replace('\\\\', '\\')
            path = Path(path_str)
            if path.exists():
                libraries.append(path)
                
    except Exception:
        pass
    
    return libraries
