"""
Smart Block Merger
Умный мерджер с сохранением структуры базового файла
"""

from collections import OrderedDict
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field
from pathlib import Path
import re

from .parser import ParadoxParser, ParadoxSerializer


@dataclass
class BlockChange:
    """Изменение блока"""
    block_name: str
    change_type: str  # 'added', 'modified', 'unchanged'
    source_mod: str
    original_content: Optional[str] = None
    new_content: Optional[str] = None


@dataclass
class FileMergeResult:
    """Результат мержа файла"""
    success: bool
    content: str = ""
    changes: List[BlockChange] = field(default_factory=list)
    error: str = ""
    warnings: List[str] = field(default_factory=list)


class StructurePreservingMerger:
    """
    Мерджер с сохранением структуры базового файла.
    
    Логика:
    1. Парсим базовый файл - это СТРУКТУРА (скелет)
    2. Парсим файл мода - это ИЗМЕНЕНИЯ (дельта)
    3. Для каждого блока в моде:
       - Если блок есть в базе и ИЗМЕНЁН → глубокий мерж содержимого
       - Если блока НЕТ в базе → добавляем в конец
    4. Сохраняем структуру и форматирование базы
    """
    
    def __init__(self):
        self.changes: List[BlockChange] = []
        
    def merge_file(
        self, 
        base_path: Path, 
        mod_paths: List[Tuple[str, Path]],  # [(mod_name, path), ...]
    ) -> FileMergeResult:
        """
        Мержит базовый файл с изменениями из модов.
        
        Приоритеты:
        1. Раскомментирован + изменён → ВЫСШИЙ
        2. Раскомментирован (не изменён) → СРЕДНИЙ
        3. Закомментирован → НИЗШИЙ
        
        Args:
            base_path: Путь к базовому файлу (оригинал)
            mod_paths: Список (имя мода, путь к файлу) в порядке применения
        """
        self.changes = []
        
        try:
            # Читаем базовый файл
            with open(base_path, 'r', encoding='utf-8-sig') as f:
                base_content = f.read()
            
            # Извлекаем блоки из базы
            base_blocks = self._extract_blocks_with_text(base_content)
            base_commented = base_blocks.get('__commented_blocks__', {})
            
            # Собираем ВСЕ версии каждого блока из всех модов
            # {block_name: [(mod_name, text, is_commented, is_modified), ...]}
            all_versions: Dict[str, List[Tuple[str, str, bool, bool]]] = {}
            
            # Добавляем базовые версии для сравнения
            base_normalized = {}
            for name, text in base_blocks.items():
                if not name.startswith('__'):
                    base_normalized[name] = self._normalize(text)
            for name, text in base_commented.items():
                base_normalized[f"#{name}"] = self._normalize(text)
            
            # Собираем версии из всех модов
            for mod_name, mod_path in mod_paths:
                if not mod_path.exists():
                    continue
                    
                with open(mod_path, 'r', encoding='utf-8-sig') as f:
                    mod_content = f.read()
                    
                mod_blocks = self._extract_blocks_with_text(mod_content)
                mod_commented = mod_blocks.get('__commented_blocks__', {})
                
                # Раскомментированные блоки
                for block_name, block_text in mod_blocks.items():
                    if block_name.startswith('__'):
                        continue
                    
                    # Проверяем изменён ли относительно базы
                    normalized = self._normalize(block_text)
                    is_modified = (
                        base_normalized.get(block_name) != normalized and
                        base_normalized.get(f"#{block_name}") != normalized
                    )
                    
                    # Раскомментирование = тоже изменение!
                    was_commented_in_base = block_name in base_commented
                    is_state_change = was_commented_in_base  # Был закомментирован, теперь раскомментирован
                    
                    # КЛЮЧЕВОЕ: неизменённые блоки НЕ участвуют в мерже!
                    # Они не могут "победить" и откатить изменения от других модов
                    # НО: раскомментирование = это изменение состояния
                    if not is_modified and not is_state_change:
                        continue  # Пропускаем неизменённую копию
                    
                    if block_name not in all_versions:
                        all_versions[block_name] = []
                    
                    all_versions[block_name].append((
                        mod_name,
                        block_text,
                        False,  # is_commented = False
                        is_modified or is_state_change  # Изменён ИЛИ раскомментирован
                    ))
                
                # Закомментированные блоки
                for block_name, block_text in mod_commented.items():
                    normalized = self._normalize(block_text)
                    is_modified = (
                        base_normalized.get(block_name) != normalized and
                        base_normalized.get(f"#{block_name}") != normalized
                    )
                    
                    # Для закомментированных: добавляем если изменён ИЛИ если это
                    # комментирование ранее активного блока (смена состояния)
                    was_uncommented_in_base = block_name in base_blocks
                    
                    if not is_modified and not was_uncommented_in_base:
                        continue  # Пропускаем неизменённый закомментированный блок
                    
                    if block_name not in all_versions:
                        all_versions[block_name] = []
                    
                    all_versions[block_name].append((
                        mod_name,
                        block_text,
                        True,  # is_commented = True
                        is_modified
                    ))
            
            # Определяем результат для каждого блока
            result_blocks = {}
            result_commented = {}
            
            # Сначала копируем базу
            for name, text in base_blocks.items():
                if not name.startswith('__'):
                    result_blocks[name] = text
            for name, text in base_commented.items():
                result_commented[name] = text
            
            # Применяем изменения по приоритету
            for block_name, versions in all_versions.items():
                # Определяем что было в базе
                was_in_base = block_name in base_blocks
                was_commented_in_base = block_name in base_commented
                
                # Фильтруем только изменённые версии
                modified_versions = [(m, t, c, mod) for m, t, c, mod in versions if mod]
                
                if not modified_versions:
                    continue  # Никто не менял - пропускаем
                
                # Сортируем по приоритету (приоритет закодирован в порядке добавления)
                # Берём "победителя" для определения состояния (комментирован/раскомментирован)
                winner = self._pick_winner(versions)
                mod_name, block_text, is_commented, is_modified = winner
                
                if is_commented:
                    # Победитель закомментирован
                    if was_in_base:
                        # Был раскомментирован → закомментировать
                        del result_blocks[block_name]
                        result_commented[block_name] = block_text
                        self.changes.append(BlockChange(
                            block_name=block_name,
                            change_type='commented',
                            source_mod=mod_name
                        ))
                    elif was_commented_in_base:
                        # Был закомментирован → обновить если изменён
                        if is_modified:
                            result_commented[block_name] = block_text
                            self.changes.append(BlockChange(
                                block_name=block_name,
                                change_type='modified_commented',
                                source_mod=mod_name
                            ))
                    else:
                        # Новый закомментированный
                        result_commented[block_name] = block_text
                        self.changes.append(BlockChange(
                            block_name=block_name,
                            change_type='added_commented',
                            source_mod=mod_name
                        ))
                else:
                    # Победитель раскомментирован
                    if was_commented_in_base:
                        # Был закомментирован → раскомментировать + глубокий мерж
                        if block_name in result_commented:
                            del result_commented[block_name]
                        
                        # Глубокий мерж всех версий
                        mod_texts = [(m, t) for m, t, c, _ in modified_versions if not c]
                        if mod_texts:
                            merged = self._deep_merge_blocks(block_text, mod_texts)
                            result_blocks[block_name] = merged
                        else:
                            result_blocks[block_name] = block_text
                        
                        change_type = 'uncommented_modified' if is_modified else 'uncommented'
                        self.changes.append(BlockChange(
                            block_name=block_name,
                            change_type=change_type,
                            source_mod=mod_name
                        ))
                    elif was_in_base:
                        # Был раскомментирован → ГЛУБОКИЙ МЕРЖ всех версий
                        base_text = base_blocks[block_name]
                        mod_texts = [(m, t) for m, t, c, _ in modified_versions if not c]
                        
                        if mod_texts:
                            merged = self._deep_merge_blocks(base_text, mod_texts)
                            result_blocks[block_name] = merged
                            self.changes.append(BlockChange(
                                block_name=block_name,
                                change_type='deep_merged',
                                source_mod=', '.join(m for m, _ in mod_texts)
                            ))
                        else:
                            result_blocks[block_name] = block_text
                            self.changes.append(BlockChange(
                                block_name=block_name,
                                change_type='modified',
                                source_mod=mod_name
                            ))
                    else:
                        # Новый раскомментированный
                        result_blocks[block_name] = block_text
                        self.changes.append(BlockChange(
                            block_name=block_name,
                            change_type='added',
                            source_mod=mod_name
                        ))
            
            # Собираем результат
            result_blocks['__header__'] = base_blocks.get('__header__', '')
            result_blocks['__commented_blocks__'] = result_commented
            
            result_content = self._assemble_file(result_blocks, base_content)
            
            # Валидация баланса скобок (игнорируем комментарии!)
            open_count = 0
            close_count = 0
            for line in result_content.split('\n'):
                # Убираем комментарии
                if '#' in line:
                    line = line[:line.index('#')]
                open_count += line.count('{')
                close_count += line.count('}')
            
            if open_count != close_count:
                return FileMergeResult(
                    success=False,
                    error=f"Несбалансированные скобки: {{ = {open_count}, }} = {close_count}",
                    warnings=[f"Diff: {open_count - close_count}"]
                )
            
            return FileMergeResult(
                success=True,
                content=result_content,
                changes=self.changes
            )
            
        except Exception as e:
            import traceback
            return FileMergeResult(
                success=False,
                error=f"{str(e)}\n{traceback.format_exc()}"
            )
    
    def _pick_winner(self, versions: List[Tuple[str, str, bool, bool]]) -> Tuple[str, str, bool, bool]:
        """
        Выбирает победителя среди версий блока.
        
        Приоритет:
        1. Раскомментирован + изменён (ВЫСШИЙ)
        2. Раскомментирован (СРЕДНИЙ)
        3. Закомментирован (НИЗШИЙ)
        
        При равном приоритете - последний в списке (последний мод)
        
        Returns: (mod_name, text, is_commented, is_modified)
        """
        # Сортируем по приоритету
        def priority(v):
            mod_name, text, is_commented, is_modified = v
            if not is_commented and is_modified:
                return 3  # Высший
            elif not is_commented:
                return 2  # Средний
            else:
                return 1  # Низший
        
        # Находим максимальный приоритет
        max_priority = max(priority(v) for v in versions)
        
        # Берём последнюю версию с максимальным приоритетом
        for v in reversed(versions):
            if priority(v) == max_priority:
                return v
        
        return versions[-1]  # fallback
    
    def _extract_blocks_with_text(self, content: str) -> Dict[str, str]:
        """
        Извлекает блоки верхнего уровня с их оригинальным текстом.
        Включает закомментированные блоки с префиксом '#'
        
        Возвращает: {block_name: raw_text}
        Для закомментированных: {'#block_name': raw_text}
        """
        blocks = OrderedDict()
        blocks['__header__'] = ""  # Комментарии и namespace в начале
        blocks['__commented_blocks__'] = {}  # {block_name: raw_text} для закомментированных
        
        lines = content.split('\n')
        current_block_name = None
        current_block_lines = []
        current_is_commented = False
        brace_depth = 0
        header_lines = []
        in_header = True
        
        for line in lines:
            stripped = line.strip()
            
            # Считаем скобки (игнорируя закомментированные)
            line_for_braces = line
            if '#' in line:
                comment_pos = line.find('#')
                # Для закомментированных БЛОКОВ - считаем всю строку
                # Для обычных блоков или вне блоков - игнорируем комментарии
                if current_is_commented:
                    line_for_braces = line  # Считаем всё в закомментированном блоке
                elif current_block_name is not None:
                    # Внутри активного блока - игнорируем комментарии
                    line_for_braces = line[:comment_pos]
                elif stripped.startswith('#'):
                    # Вне блока, строка-комментарий - может быть начало закомм. блока
                    line_for_braces = line
                else:
                    # Вне блока, комментарий в конце строки
                    line_for_braces = line[:comment_pos]
            
            open_braces = line_for_braces.count('{')
            close_braces = line_for_braces.count('}')
            
            if current_block_name is None:
                # Ищем начало обычного блока: name = { или scripted_effect name = {
                # Поддерживаем имена с цифрами, пробелами, двоеточиями, точками
                # Примеры: gondor.0120, 5120, 4035.1.1, scripted_effect name, title:c_xxx
                match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:\s]*?)\s*=\s*\{', stripped)
                if match:
                    in_header = False
                    current_block_name = match.group(1).strip()
                    current_block_lines = [line]
                    current_is_commented = False
                    brace_depth = open_braces - close_braces
                    
                    if brace_depth == 0:
                        # Однострочный блок
                        blocks[current_block_name] = line
                        current_block_name = None
                        current_block_lines = []
                    continue
                
                # Ищем начало ЗАКОММЕНТИРОВАННОГО блока: #name = { или # name = {
                commented_match = re.match(r'^#\s*([a-zA-Z0-9_][a-zA-Z0-9_\.:\s]*?)\s*=\s*\{', stripped)
                if commented_match:
                    in_header = False
                    current_block_name = commented_match.group(1).strip()
                    current_block_lines = [line]
                    current_is_commented = True
                    brace_depth = stripped.count('{') - stripped.count('}')
                    
                    if brace_depth == 0:
                        # Однострочный закомментированный блок
                        blocks['__commented_blocks__'][current_block_name] = line
                        current_block_name = None
                        current_block_lines = []
                        current_is_commented = False
                    continue
                
                if in_header:
                    header_lines.append(line)
                elif stripped and not stripped.startswith('#'):
                    # Простое присваивание вне блока (namespace = xxx, etc)
                    simple_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_]*)\s*=\s*(.+)$', stripped)
                    if simple_match:
                        key = simple_match.group(1)
                        blocks[key] = line
            else:
                # Внутри блока
                current_block_lines.append(line)
                
                if current_is_commented:
                    # Для закомментированного блока считаем скобки из всей строки
                    brace_depth += stripped.count('{') - stripped.count('}')
                else:
                    brace_depth += open_braces - close_braces
                
                if brace_depth <= 0:
                    # Блок закончился
                    block_text = '\n'.join(current_block_lines)
                    
                    if current_is_commented:
                        blocks['__commented_blocks__'][current_block_name] = block_text
                    else:
                        blocks[current_block_name] = block_text
                    
                    current_block_name = None
                    current_block_lines = []
                    current_is_commented = False
                    brace_depth = 0
        
        # Если остался незакрытый блок
        if current_block_name and current_block_lines:
            block_text = '\n'.join(current_block_lines)
            if current_is_commented:
                blocks['__commented_blocks__'][current_block_name] = block_text
            else:
                blocks[current_block_name] = block_text
            
        blocks['__header__'] = '\n'.join(header_lines)
        
        return blocks
    
    def _normalize(self, text: str) -> str:
        """Нормализует текст для сравнения (убирает пробелы, комментарии)"""
        # Убираем комментарии
        lines = []
        for line in text.split('\n'):
            # Убираем комментарии в конце строки
            if '#' in line:
                line = line[:line.index('#')]
            line = line.strip()
            if line:
                lines.append(line)
        return ''.join(lines).replace(' ', '').replace('\t', '')
    
    def _assemble_file(self, blocks: Dict[str, str], original_content: str) -> str:
        """Собирает файл из блоков, сохраняя порядок оригинала"""
        result_lines = []
        
        # Получаем закомментированные блоки
        commented_blocks = blocks.get('__commented_blocks__', {})
        
        # Добавляем header (namespace, комментарии в начале)
        if '__header__' in blocks and blocks['__header__'].strip():
            result_lines.append(blocks['__header__'])
            result_lines.append('')
        
        # Добавляем блоки
        added_blocks = set(['__header__', '__commented_blocks__'])
        added_commented = set()
        
        # Сначала пытаемся сохранить порядок из оригинала
        original_blocks = self._extract_blocks_with_text(original_content)
        original_commented = original_blocks.get('__commented_blocks__', {})
        
        # Обрабатываем раскомментированные блоки из оригинала
        for block_name in original_blocks:
            if block_name.startswith('__'):
                continue
            
            # Проверяем: может блок теперь закомментирован?
            if block_name in commented_blocks:
                # Был раскомментирован, теперь закомментирован
                result_lines.append(commented_blocks[block_name])
                result_lines.append('')
                added_commented.add(block_name)
            elif block_name in blocks:
                # Остался раскомментированным
                result_lines.append(blocks[block_name])
                result_lines.append('')
            added_blocks.add(block_name)
        
        # Обрабатываем закомментированные блоки из оригинала
        for block_name in original_commented:
            if block_name in added_commented:
                continue  # Уже добавили
            
            # Проверяем: может блок теперь раскомментирован?
            if block_name in blocks and block_name not in added_blocks:
                # Был закомментирован, теперь раскомментирован
                result_lines.append(blocks[block_name])
                result_lines.append('')
                added_blocks.add(block_name)
            elif block_name in commented_blocks:
                # Остался закомментированным
                result_lines.append(commented_blocks[block_name])
                result_lines.append('')
            added_commented.add(block_name)
        
        # Добавляем новые раскомментированные блоки в конец
        for block_name, block_text in blocks.items():
            if block_name not in added_blocks and not block_name.startswith('__'):
                result_lines.append(block_text)
                result_lines.append('')
        
        # Добавляем новые закомментированные блоки в конец
        for block_name, block_text in commented_blocks.items():
            if block_name not in added_commented:
                result_lines.append(block_text)
                result_lines.append('')
        
        return '\n'.join(result_lines).strip() + '\n'
    
    def _deep_merge_blocks(self, base_text: str, mod_texts: List[Tuple[str, str]]) -> str:
        """
        Глубоко мержит содержимое блоков.
        Мержит списки on_actions, events - добавляя уникальные элементы.
        
        Args:
            base_text: Текст базового блока
            mod_texts: [(mod_name, block_text), ...] отсортированные по приоритету
        
        Returns:
            Смерженный текст блока
        """
        result = base_text
        
        # Паттерны и имена списков для мержа
        list_configs = [
            ('on_actions', r'on_actions\s*=\s*\{([^}]*)\}'),
            ('events', r'events\s*=\s*\{([^}]*)\}'),
        ]
        
        # Собираем уникальные элементы из всех модов для каждого списка
        for list_name, pattern in list_configs:
            base_match = re.search(pattern, result, re.DOTALL)
            if not base_match:
                continue
            
            base_list_content = base_match.group(1)
            base_items = self._extract_list_items(base_list_content)
            all_items = list(base_items)  # Начинаем с базы
            
            # Собираем уникальные элементы из всех модов
            for mod_name, mod_text in mod_texts:
                mod_match = re.search(pattern, mod_text, re.DOTALL)
                if mod_match:
                    mod_list_content = mod_match.group(1)
                    mod_items = self._extract_list_items(mod_list_content)
                    
                    for item in mod_items:
                        if item not in all_items:
                            all_items.append(item)
            
            # Если есть новые элементы - обновляем список
            if len(all_items) > len(base_items):
                # Формируем новый список
                if '\n' in base_list_content:
                    # Многострочный формат
                    new_content = '\n' + '\n'.join(f'\t\t{item}' for item in all_items) + '\n\t'
                else:
                    # Однострочный формат
                    new_content = ' ' + ' '.join(all_items) + ' '
                
                # Заменяем список в результате
                result = re.sub(
                    pattern,
                    f'{list_name} = {{{new_content}}}',
                    result,
                    count=1
                )
        
        return result
    
    def _extract_list_items(self, content: str) -> List[str]:
        """Извлекает элементы списка из содержимого блока"""
        items = []
        
        # Убираем комментарии
        lines = content.split('\n')
        clean_content = ""
        for line in lines:
            if '#' in line:
                line = line[:line.index('#')]
            clean_content += line + " "
        
        # Разбиваем по пробелам
        tokens = clean_content.split()
        for token in tokens:
            token = token.strip()
            if token and token not in ('{', '}'):
                items.append(token)
        
        return items


def read_mod_dependencies(mod_path: Path) -> List[str]:
    """Читает dependencies из descriptor.mod"""
    descriptor = mod_path / "descriptor.mod"
    if not descriptor.exists():
        return []
        
    try:
        with open(descriptor, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            
        # Ищем блок dependencies = { ... }
        match = re.search(r'dependencies\s*=\s*\{([^}]*)\}', content, re.DOTALL)
        if match:
            deps_content = match.group(1)
            # Извлекаем строки в кавычках
            return re.findall(r'"([^"]+)"', deps_content)
    except:
        pass
        
    return []


def read_mod_name(mod_path: Path) -> str:
    """Читает имя мода из descriptor.mod"""
    descriptor = mod_path / "descriptor.mod"
    if not descriptor.exists():
        return mod_path.name
        
    try:
        with open(descriptor, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        match = re.search(r'name\s*=\s*"([^"]+)"', content)
        if match:
            return match.group(1)
    except:
        pass
        
    return mod_path.name


def validate_mod_compatibility(base_path: Path, base_is_vanilla: bool, mod_paths: List[Path]) -> Tuple[bool, List[str]]:
    """
    Проверяет совместимость модов с базой.
    
    Returns:
        (is_valid, list_of_errors_or_warnings)
    """
    errors = []
    warnings = []
    
    if base_is_vanilla:
        base_name = "vanilla"
    else:
        base_name = read_mod_name(base_path)
    
    for mod_path in mod_paths:
        mod_name = read_mod_name(mod_path)
        deps = read_mod_dependencies(mod_path)
        
        if base_is_vanilla:
            # База - ванилла, мод не должен иметь зависимостей от других модов
            if deps:
                errors.append(
                    f"❌ Мод '{mod_name}' требует '{deps[0]}' как зависимость.\n"
                    f"   Выберите этот мод как базу, а не ванильную игру."
                )
        else:
            # База - глобальный мод
            if deps:
                # Проверяем что зависимость совпадает с базой
                base_name_lower = base_name.lower()
                found_match = False
                for dep in deps:
                    if dep.lower() in base_name_lower or base_name_lower in dep.lower():
                        found_match = True
                        break
                
                if not found_match:
                    warnings.append(
                        f"⚠️ Мод '{mod_name}' зависит от '{deps[0]}',\n"
                        f"   но выбрана база '{base_name}'. Проверьте совместимость."
                    )
            else:
                # Мод без зависимостей - возможно это не сабмод
                warnings.append(
                    f"⚠️ Мод '{mod_name}' не указывает зависимости.\n"
                    f"   Возможно это самостоятельный мод, а не сабмод."
                )
    
    is_valid = len(errors) == 0
    return is_valid, errors + warnings
