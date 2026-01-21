"""
Smart Patch Generator
Генератор патчей с сохранением структуры
"""

import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import os

from .smart_merger import (
    StructurePreservingMerger, 
    FileMergeResult,
    read_mod_name,
    read_mod_dependencies,
    validate_mod_compatibility
)
from .structural_merger import StructuralMerger, StructuralMergeResult


@dataclass
class PatchStats:
    """Статистика патча"""
    total_files: int = 0
    merged_files: int = 0
    copied_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PatchProgress:
    """Прогресс генерации"""
    current_file: str = ""
    current_index: int = 0
    total_files: int = 0
    status: str = ""


class SmartPatchGenerator:
    """
    Генератор патчей с умным мержем.
    
    Принцип работы:
    1. База (ванилла или глобальный мод) = структура/скелет файлов
    2. Сабмоды = изменения (дельты) поверх базы
    3. Мерж сохраняет структуру базы, применяя только изменения из сабмодов
    """
    
    # Расширения для мержа (текстовые файлы Paradox)
    MERGEABLE_EXTENSIONS = {'.txt', '.gui', '.gfx'}
    
    # Папки которые содержат мержабельные файлы (ТОЛЬКО логика, НЕ графика)
    MERGEABLE_FOLDERS = {
        'common', 'events', 'history', 'decisions', 'gui', 'interface', 'gfx',
        'scripted_triggers', 'scripted_effects', 'on_actions'
    }
    
    # Папки которые ИГНОРИРУЕМ полностью (звуки, шрифты - не нужны в патче)
    IGNORED_FOLDERS = {
        'fonts', 'music', 'sound', 'tools',
        'dlc', 'dlc_metadata', 'localization', 'map_data',
        'content_source', 'portraits', 'coat_of_arms'
    }
    
    # Расширения которые игнорируем (графика, бинарные файлы)
    IGNORED_EXTENSIONS = {'.dds', '.png', '.jpg', '.jpeg', '.tga', '.bmp', '.wav', '.ogg', '.mp3'}
    
    def __init__(self, progress_callback=None):
        """
        Args:
            progress_callback: функция(PatchProgress) для отчёта о прогрессе
        """
        self.progress_callback = progress_callback
        self.stats = PatchStats()
        
    def generate_patch(
        self,
        base_path: Path,
        base_is_vanilla: bool,
        mod_paths: List[Path],
        output_path: Path,
        patch_name: str = "AutoPatch"
    ) -> PatchStats:
        """
        Генерирует патч.
        
        Args:
            base_path: Путь к базе (игра или глобальный мод)
            base_is_vanilla: True если база - ванильная игра
            mod_paths: Пути к сабмодам в порядке применения
            output_path: Куда сохранить патч
            patch_name: Имя патча
            
        Returns:
            PatchStats со статистикой
        """
        self.stats = PatchStats()
        
        # Проверяем совместимость
        is_valid, messages = validate_mod_compatibility(base_path, base_is_vanilla, mod_paths)
        if not is_valid:
            self.stats.errors.extend([m for m in messages if m.startswith('❌')])
            self.stats.warnings.extend([m for m in messages if m.startswith('⚠️')])
            # Продолжаем с предупреждениями, но не с ошибками
            if self.stats.errors:
                return self.stats
        else:
            self.stats.warnings.extend(messages)
        
        # Создаём выходную директорию
        if output_path.exists():
            shutil.rmtree(output_path)
        output_path.mkdir(parents=True)
        
        # Собираем все файлы из сабмодов
        mod_files = self._collect_mod_files(mod_paths)
        self.stats.total_files = len(mod_files)
        
        self._report_progress("Начинаем мерж...", 0)
        
        # Обрабатываем каждый файл
        merger = StructuralMerger()  # Используем новый глубокий мержер
        
        for i, (relative_path, sources) in enumerate(mod_files.items()):
            self._report_progress(f"Обработка: {relative_path}", i)
            
            # Файл ДОЛЖЕН существовать в базе - иначе пропускаем
            # Уникальные файлы сабмодов загрузит сам сабмод
            base_file = base_path / relative_path
            
            if not base_file.exists():
                self.stats.skipped_files += 1
                continue
            
            # Читаем базу для сравнения
            try:
                with open(base_file, 'r', encoding='utf-8-sig') as f:
                    base_content = f.read()
                base_normalized = self._normalize_content(base_content)
            except Exception:
                base_normalized = None
            
            # Фильтруем: оставляем ТОЛЬКО моды которые ИЗМЕНИЛИ файл
            # Неизменённые копии оригинала игнорируем
            changed_sources = []
            for mod_path, file_path in sources:
                try:
                    with open(file_path, 'r', encoding='utf-8-sig') as f:
                        mod_content = f.read()
                    mod_normalized = self._normalize_content(mod_content)
                    
                    if base_normalized is None or mod_normalized != base_normalized:
                        # Файл изменён - добавляем
                        changed_sources.append((mod_path, file_path))
                except Exception:
                    # Если не смогли прочитать - добавляем на всякий случай
                    changed_sources.append((mod_path, file_path))
            
            # Если никто не изменил файл - пропускаем
            if not changed_sources:
                self.stats.skipped_files += 1
                continue
            
            # Файл есть в базе и изменён - мержим если это мержабельный файл
            if self._is_mergeable(relative_path):
                # changed_sources = [(mod_path, file_path), ...] - только изменённые!
                mod_file_pairs = [(read_mod_name(mod_path), file_path) for mod_path, file_path in changed_sources]
                
                result = merger.merge_file(base_file, mod_file_pairs)
                
                if result.success:
                    # Сохраняем только если есть изменения
                    if result.changes:
                        self._save_file(output_path / relative_path, result.content)
                        self.stats.merged_files += 1
                    else:
                        self.stats.skipped_files += 1
                else:
                    self.stats.errors.append(f"Ошибка мержа {relative_path}: {result.error}")
                    self.stats.failed_files += 1
            else:
                # Не мержабельный файл (но есть в базе) - берём последнюю ИЗМЕНЁННУЮ версию
                _, last_file = changed_sources[-1]
                self._copy_file(last_file, output_path / relative_path)
                self.stats.copied_files += 1
        
        # Генерируем метафайлы
        self._generate_descriptor(output_path, patch_name, mod_paths)
        self._generate_readme(output_path, patch_name, base_path, mod_paths)
        
        self._report_progress("Готово!", self.stats.total_files)
        
        return self.stats
    
    def _collect_mod_files(self, mod_paths: List[Path]) -> Dict[str, List[Tuple[Path, Path]]]:
        """
        Собирает файлы из всех модов.
        Игнорирует графику, звуки и другие не-мержабельные папки.
        
        Returns:
            {relative_path: [(mod_path, file_path), ...]}
        """
        files: Dict[str, List[Tuple[Path, Path]]] = {}
        
        for mod_path in mod_paths:
            for root, dirs, filenames in os.walk(mod_path):
                root_path = Path(root)
                
                # Получаем относительный путь от мода
                try:
                    rel_root = root_path.relative_to(mod_path)
                    top_folder = rel_root.parts[0] if rel_root.parts else ""
                except ValueError:
                    top_folder = ""
                
                # Пропускаем игнорируемые папки
                if top_folder.lower() in {f.lower() for f in self.IGNORED_FOLDERS}:
                    dirs[:] = []  # Не заходим глубже
                    continue
                
                # Пропускаем скрытые папки
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for filename in filenames:
                    filepath = root_path / filename
                    relative = filepath.relative_to(mod_path)
                    relative_str = str(relative)
                    
                    # Пропускаем descriptor.mod и другие метафайлы
                    if filename in ('descriptor.mod', 'thumbnail.png', '.mod'):
                        continue
                    
                    # Пропускаем графику, звуки, шрифты
                    ext = Path(filename).suffix.lower()
                    if ext in self.IGNORED_EXTENSIONS or ext in {'.ttf', '.otf', '.fnt'}:
                        continue
                    
                    if relative_str not in files:
                        files[relative_str] = []
                    files[relative_str].append((mod_path, filepath))
        
        return files
    
    def _is_mergeable(self, relative_path: str) -> bool:
        """Проверяет можно ли мержить файл"""
        path = Path(relative_path)
        
        # Проверяем расширение
        if path.suffix.lower() not in self.MERGEABLE_EXTENSIONS:
            return False
        
        # Проверяем папку
        if path.parts:
            top_folder = path.parts[0].lower()
            
            # Игнорируемые папки
            if top_folder in {f.lower() for f in self.IGNORED_FOLDERS}:
                return False
            
            # Мержабельные папки
            if top_folder not in {f.lower() for f in self.MERGEABLE_FOLDERS}:
                return False
        
        return True
    
    def _save_file(self, path: Path, content: str):
        """Сохраняет файл"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8-sig') as f:
            f.write(content)
    
    def _copy_file(self, source: Path, dest: Path):
        """Копирует файл"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    
    def _normalize_content(self, content: str) -> str:
        """Нормализует контент для сравнения (убирает пробелы, переносы, комментарии)"""
        lines = []
        for line in content.split('\n'):
            # Убираем комментарии
            if '#' in line:
                line = line[:line.index('#')]
            # Убираем пробелы
            line = line.strip()
            if line:
                lines.append(line)
        return ''.join(lines).replace(' ', '').replace('\t', '').replace('\r', '')
    
    def _report_progress(self, status: str, current: int):
        """Отправляет отчёт о прогрессе"""
        if self.progress_callback:
            progress = PatchProgress(
                current_file=status,
                current_index=current,
                total_files=self.stats.total_files,
                status=status
            )
            self.progress_callback(progress)
    
    def _generate_descriptor(self, output_path: Path, patch_name: str, mod_paths: List[Path]):
        """Генерирует descriptor.mod"""
        mod_names = [read_mod_name(p) for p in mod_paths]
        
        content = f'''version="1.0.0"
tags={{
\t"Compatibility"
}}
name="{patch_name}"
supported_version="1.15.*"
'''
        
        (output_path / "descriptor.mod").write_text(content, encoding='utf-8-sig')
        
        # .mod файл для лаунчера — создаётся СНАРУЖИ папки патча
        safe_name = patch_name.replace(" ", "_").replace("+", "_")
        mod_content = content + f'path="mod/{output_path.name}"'
        # Внешний .mod файл рядом с папкой патча
        external_mod_path = output_path.parent / f"{safe_name}.mod"
        external_mod_path.write_text(mod_content, encoding='utf-8-sig')
    
    def _generate_readme(self, output_path: Path, patch_name: str, base_path: Path, mod_paths: List[Path]):
        """Генерирует README"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        base_name = read_mod_name(base_path) if (base_path / "descriptor.mod").exists() else "Vanilla Game"
        mod_names = [read_mod_name(p) for p in mod_paths]
        
        content = f"""# {patch_name}

Auto-generated compatibility patch
Created: {now}

## Base
{base_name}

## Merged Mods
"""
        for name in mod_names:
            content += f"- {name}\n"
        
        content += f"""
## Statistics
- Total files processed: {self.stats.total_files}
- Merged (conflicts resolved): {self.stats.merged_files}
- Copied (mod conflicts): {self.stats.copied_files}
- Skipped (no conflicts): {self.stats.skipped_files}
- Failed: {self.stats.failed_files}

## Installation
Patch is ready to use! Just enable it in launcher BELOW all source mods.

## Load Order
```
{base_name}
"""
        for name in mod_names:
            content += f"{name}\n"
        content += f"{patch_name}  <-- LAST\n```\n"
        
        if self.stats.errors:
            content += "\n## Errors\n"
            for e in self.stats.errors:
                content += f"- {e}\n"
        
        if self.stats.warnings:
            content += "\n## Warnings\n"
            for w in self.stats.warnings:
                content += f"- {w}\n"
        
        (output_path / "README.md").write_text(content, encoding='utf-8')
