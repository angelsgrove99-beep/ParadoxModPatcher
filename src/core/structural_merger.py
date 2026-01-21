"""
Structural Merger - Полноценный структурный мерж Paradox файлов

Принцип работы:
1. Парсим файлы в структуру (понимаем вложенность)
2. Для каждого блока определяем стратегию по правилам Paradox
3. ACCUMULATE_LIST - накапливаем элементы (on_actions, events)
4. REPLACE_WHOLE - берём целиком из мода (события, триггеры, эффекты)
5. RECURSIVE - мержим рекурсивно (on_action контейнеры)

ВАЖНО: Не мержим внутренности событий, триггеров, эффектов!
Событие - атомарная единица. Либо из базы, либо целиком из мода.
"""

import re
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

from .paradox_rules import (
    get_merge_strategy, 
    MergeStrategy,
    TopLevelStrategy,
    is_safe_to_accumulate,
    is_event_block,
    is_date_block,
    is_safe_to_add_child,
    is_top_level_atomic,
    get_file_context,
    get_top_level_strategy,
    SAFE_LIST_BLOCKS,
    NO_MERGE_BLOCKS,
    StructureValidator
)


@dataclass
class ParsedBlock:
    """Распарсенный блок"""
    name: str
    full_text: str  # Полный текст включая name = { ... }
    inner_text: str  # Только содержимое между { }
    start_line: int
    end_line: int
    indent: str
    is_commented: bool = False
    # Дети группируются по имени, но сохраняем ВСЕ блоки с одинаковым именем
    # if[0], if[1], if[2] - все сохранены в списке
    children: Dict[str, List['ParsedBlock']] = field(default_factory=dict)
    list_items: List[str] = field(default_factory=list)  # Для списков типа on_actions
    properties: Dict[str, str] = field(default_factory=dict)  # name = value
    
    def get_child(self, name: str, index: int = 0) -> Optional['ParsedBlock']:
        """Получить дочерний блок по имени и индексу"""
        if name in self.children and index < len(self.children[name]):
            return self.children[name][index]
        return None
    
    def get_all_children(self, name: str) -> List['ParsedBlock']:
        """Получить все дочерние блоки с данным именем"""
        return self.children.get(name, [])
    
    def add_child(self, child: 'ParsedBlock'):
        """Добавить дочерний блок"""
        if child.name not in self.children:
            self.children[child.name] = []
        self.children[child.name].append(child)
    
    def child_count(self, name: str) -> int:
        """Количество дочерних блоков с данным именем"""
        return len(self.children.get(name, []))


@dataclass 
class MergeChange:
    """Описание изменения"""
    path: str  # on_game_start.on_actions
    change_type: str  # added_item, added_block, modified, etc.
    mod_name: str
    content: str


@dataclass
class StructuralMergeResult:
    """Результат мержа"""
    success: bool
    content: str = ""
    error: str = ""
    changes: List[MergeChange] = field(default_factory=list)


class StructuralMerger:
    """Полноценный структурный мержер"""
    
    def __init__(self):
        self.changes: List[MergeChange] = []
    
    def merge_file(self, base_path: Path, mod_paths: List[Tuple[str, Path]]) -> StructuralMergeResult:
        """
        Мержит файл структурно.
        
        Args:
            base_path: Путь к базовому файлу
            mod_paths: [(mod_name, path), ...] в порядке приоритета
        """
        self.changes = []
        
        try:
            # Читаем базу
            with open(base_path, 'r', encoding='utf-8-sig') as f:
                base_content = f.read()
            
            # Читаем моды
            mod_contents = []
            for mod_name, mod_path in mod_paths:
                with open(mod_path, 'r', encoding='utf-8-sig') as f:
                    mod_contents.append((mod_name, f.read()))
            
            return self.merge_contents(base_content, mod_contents)
            
        except Exception as e:
            return StructuralMergeResult(
                success=False,
                error=f"Ошибка чтения файла: {str(e)}"
            )
    
    def merge_contents(self, base_content: str, mod_contents: List[Tuple[str, str]], filename: str = "") -> StructuralMergeResult:
        """Мержит содержимое файлов с учётом правил Paradox"""
        try:
            # Нормализуем
            base_content = base_content.replace('\r\n', '\n')
            mod_contents = [(name, content.replace('\r\n', '\n')) for name, content in mod_contents]
            
            # Парсим базу
            base_blocks = self._parse_top_level_blocks(base_content)
            
            # Парсим моды и собираем изменения
            all_changes: Dict[str, List[Tuple[str, str, Any]]] = {}  # block_name -> [(mod_name, change_type, parsed)]
            
            for mod_name, mod_content in mod_contents:
                mod_blocks = self._parse_top_level_blocks(mod_content)
                
                for block_name, mod_block in mod_blocks.items():
                    if block_name.startswith('__'):
                        continue
                    
                    base_block = base_blocks.get(block_name)
                    
                    if base_block is None:
                        # Новый блок
                        if block_name not in all_changes:
                            all_changes[block_name] = []
                        all_changes[block_name].append((mod_name, 'new', mod_block))
                    else:
                        # Существующий блок - проверяем изменения
                        if self._blocks_differ(base_block, mod_block):
                            if block_name not in all_changes:
                                all_changes[block_name] = []
                            all_changes[block_name].append((mod_name, 'modified', mod_block))
            
            # Применяем изменения к базе
            result_content = base_content
            
            for block_name, changes in all_changes.items():
                base_block = base_blocks.get(block_name)
                
                # Определяем стратегию ВЕРХНЕГО УРОВНЯ
                top_strategy = get_top_level_strategy(block_name, filename)
                
                if base_block is None:
                    # === НОВЫЙ БЛОК ===
                    # Уникальные блоки ВСЕГДА накапливаются (независимо от типа)
                    last_mod_name, _, last_mod_block = changes[-1]
                    result_content = result_content.rstrip() + '\n\n' + last_mod_block.full_text
                    self.changes.append(MergeChange(
                        path=block_name,
                        change_type='added_unique_block',
                        mod_name=last_mod_name,
                        content=block_name
                    ))
                
                elif top_strategy == TopLevelStrategy.ATOMIC_ACCUMULATE:
                    # === АТОМАРНЫЙ БЛОК (событие, decision, trait) ===
                    # Одинаковые блоки: берём целиком из последнего мода
                    # Внутренности НЕ мержим
                    last_mod_name, _, last_mod_block = changes[-1]
                    result_content = result_content.replace(
                        base_block.full_text,
                        last_mod_block.full_text,
                        1
                    )
                    self.changes.append(MergeChange(
                        path=block_name,
                        change_type='replaced_atomic',
                        mod_name=last_mod_name,
                        content=block_name
                    ))
                
                elif top_strategy == TopLevelStrategy.MERGEABLE_CONTAINER:
                    # === КОНТЕЙНЕР (on_action, scripted_effect) ===
                    # Мержим внутренности по правилам
                    mod_blocks_list = [(name, block) for name, _, block in changes]
                    merged_text = self._deep_merge_block(base_block, mod_blocks_list)
                    result_content = result_content.replace(base_block.full_text, merged_text, 1)
                
                else:
                    # Fallback - атомарный
                    last_mod_name, _, last_mod_block = changes[-1]
                    result_content = result_content.replace(
                        base_block.full_text,
                        last_mod_block.full_text,
                        1
                    )
                    self.changes.append(MergeChange(
                        path=block_name,
                        change_type='replaced_fallback',
                        mod_name=last_mod_name,
                        content=block_name
                    ))
            
            # Валидация результата
            validator = StructureValidator()
            is_valid, issues = validator.validate(result_content, filename)
            
            # Добавляем предупреждения в changes
            for issue in issues:
                if issue.severity == 'warning':
                    self.changes.append(MergeChange(
                        path=issue.path,
                        change_type='validation_warning',
                        mod_name='',
                        content=issue.message
                    ))
            
            # Проверка баланса скобок
            if not self._validate_braces(result_content):
                open_c, close_c = self._count_braces(result_content)
                return StructuralMergeResult(
                    success=False,
                    error=f"Несбалансированные скобки после мержа: {{ = {open_c}, }} = {close_c}"
                )
            
            return StructuralMergeResult(
                success=True,
                content=result_content,
                changes=self.changes
            )
            
        except Exception as e:
            import traceback
            return StructuralMergeResult(
                success=False,
                error=f"Ошибка мержа: {str(e)}\n{traceback.format_exc()}"
            )
    
    def _parse_top_level_blocks(self, content: str) -> Dict[str, ParsedBlock]:
        """Парсит блоки верхнего уровня"""
        blocks = {}
        lines = content.split('\n')
        
        i = 0
        header_lines = []
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Пропускаем пустые и комментарии до первого блока
            if not stripped or stripped.startswith('#'):
                if not blocks:  # Ещё не было блоков
                    header_lines.append(line)
                i += 1
                continue
            
            # Ищем начало блока
            # Поддерживаем: name = {, 5120 = {, 1066.1.1 = {
            match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:]*)\s*=\s*\{', stripped)
            if match:
                block_name = match.group(1)
                indent = line[:len(line) - len(line.lstrip())]
                start_line = i
                
                # Находим конец блока
                brace_depth = 0
                block_lines = []
                
                while i < len(lines):
                    block_line = lines[i]
                    block_lines.append(block_line)
                    
                    # Считаем скобки без комментариев
                    line_for_count = block_line
                    if '#' in line_for_count:
                        hash_pos = self._find_comment_start(line_for_count)
                        if hash_pos >= 0:
                            line_for_count = line_for_count[:hash_pos]
                    
                    brace_depth += line_for_count.count('{') - line_for_count.count('}')
                    i += 1
                    
                    if brace_depth <= 0:
                        break
                
                full_text = '\n'.join(block_lines)
                
                # Извлекаем inner_text
                inner_start = full_text.find('{') + 1
                inner_end = full_text.rfind('}')
                inner_text = full_text[inner_start:inner_end] if inner_end > inner_start else ""
                
                block = ParsedBlock(
                    name=block_name,
                    full_text=full_text,
                    inner_text=inner_text,
                    start_line=start_line,
                    end_line=i - 1,
                    indent=indent
                )
                
                # Парсим содержимое блока
                self._parse_block_contents(block)
                
                blocks[block_name] = block
            else:
                i += 1
        
        # Сохраняем header
        if header_lines:
            blocks['__header__'] = ParsedBlock(
                name='__header__',
                full_text='\n'.join(header_lines),
                inner_text='',
                start_line=0,
                end_line=len(header_lines) - 1,
                indent=''
            )
        
        return blocks
    
    def _parse_block_contents(self, block: ParsedBlock):
        """Парсит содержимое блока - находит вложенные блоки, списки, свойства"""
        content = block.inner_text
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            if not stripped or stripped.startswith('#'):
                i += 1
                continue
            
            # Вложенный блок
            match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:]*)\s*=\s*\{(.*)$', stripped)
            if match:
                child_name = match.group(1)
                rest = match.group(2)
                
                # Однострочный блок?
                if rest.rstrip().endswith('}'):
                    # Извлекаем содержимое однострочного блока
                    inner = rest.rstrip()[:-1].strip()
                    
                    child = ParsedBlock(
                        name=child_name,
                        full_text=stripped,
                        inner_text=inner,
                        start_line=i,
                        end_line=i,
                        indent=line[:len(line) - len(stripped)]
                    )
                    
                    # Парсим элементы списка
                    if inner:
                        child.list_items = self._parse_list_items(inner)
                    
                    block.add_child(child)
                    i += 1
                else:
                    # Многострочный блок
                    start_i = i
                    brace_depth = 1
                    child_lines = [line]
                    i += 1
                    
                    while i < len(lines) and brace_depth > 0:
                        child_line = lines[i]
                        child_lines.append(child_line)
                        
                        line_for_count = child_line
                        if '#' in line_for_count:
                            hash_pos = self._find_comment_start(line_for_count)
                            if hash_pos >= 0:
                                line_for_count = line_for_count[:hash_pos]
                        
                        brace_depth += line_for_count.count('{') - line_for_count.count('}')
                        i += 1
                    
                    child_text = '\n'.join(child_lines)
                    inner_start = child_text.find('{') + 1
                    inner_end = child_text.rfind('}')
                    inner_text = child_text[inner_start:inner_end] if inner_end > inner_start else ""
                    
                    child = ParsedBlock(
                        name=child_name,
                        full_text=child_text,
                        inner_text=inner_text,
                        start_line=start_i,
                        end_line=i - 1,
                        indent=line[:len(line) - len(stripped)]
                    )
                    
                    # Рекурсивно парсим
                    self._parse_block_contents(child)
                    
                    # Также извлекаем list_items если это похоже на список
                    child.list_items = self._parse_list_items(inner_text)
                    
                    block.add_child(child)
                continue
            
            # Свойство: name = value
            prop_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:]*)\s*=\s*([^{].*)$', stripped)
            if prop_match:
                prop_name = prop_match.group(1)
                prop_value = prop_match.group(2).strip()
                # Убираем комментарий
                if '#' in prop_value:
                    prop_value = prop_value[:prop_value.index('#')].strip()
                block.properties[prop_name] = prop_value
                i += 1
                continue
            
            # Элемент списка
            item_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:]*)\s*(#.*)?$', stripped)
            if item_match:
                block.list_items.append(item_match.group(1))
            
            i += 1
    
    def _parse_list_items(self, content: str) -> List[str]:
        """Извлекает элементы списка"""
        items = []
        
        # Убираем комментарии
        clean_lines = []
        for line in content.split('\n'):
            if '#' in line:
                hash_pos = self._find_comment_start(line)
                if hash_pos >= 0:
                    line = line[:hash_pos]
            clean_lines.append(line)
        
        clean_content = ' '.join(clean_lines)
        
        # Разбиваем по пробелам, но учитываем вложенные блоки
        depth = 0
        current = ""
        
        for char in clean_content:
            if char == '{':
                depth += 1
                current += char
            elif char == '}':
                depth -= 1
                current += char
            elif char in ' \t\n' and depth == 0:
                if current.strip():
                    # Проверяем что это не свойство (name = value)
                    if '=' not in current or '{' in current:
                        items.append(current.strip())
                    current = ""
            else:
                current += char
        
        if current.strip() and ('=' not in current or '{' in current):
            items.append(current.strip())
        
        # Фильтруем только простые идентификаторы
        result = []
        for item in items:
            # Простой идентификатор или вызов (namespace.event)
            if re.match(r'^[a-zA-Z0-9_][a-zA-Z0-9_\.:]*$', item):
                result.append(item)
        
        return result
    
    def _blocks_differ(self, base: ParsedBlock, mod: ParsedBlock) -> bool:
        """Проверяет отличаются ли блоки"""
        # Нормализуем и сравниваем
        base_norm = self._normalize_content(base.inner_text)
        mod_norm = self._normalize_content(mod.inner_text)
        return base_norm != mod_norm
    
    def _normalize_content(self, content: str) -> str:
        """Нормализует содержимое для сравнения"""
        # Убираем комментарии
        lines = []
        for line in content.split('\n'):
            if '#' in line:
                hash_pos = self._find_comment_start(line)
                if hash_pos >= 0:
                    line = line[:hash_pos]
            line = line.strip()
            if line:
                lines.append(line)
        
        return ' '.join(lines)
    
    def _deep_merge_block(self, base_block: ParsedBlock, mod_blocks: List[Tuple[str, ParsedBlock]], depth: int = 0) -> str:
        """
        Глубокий мерж блока с учётом правил Paradox.
        РЕКУРСИВНО проверяет каждый уровень вложенности.
        
        Поддерживает множественные блоки с одинаковым именем (if, if, if).
        Сопоставление по ИНДЕКСУ: base.if[0] ↔ mod.if[0], base.if[1] ↔ mod.if[1]
        
        ИСКЛЮЧЕНИЕ: GUI контейнеры (texture, environment) - сравниваем по содержимому.
        
        Стратегии:
        - ACCUMULATE_LIST: накапливаем элементы (on_actions, events)
        - REPLACE_WHOLE: берём целиком из мода с наивысшим приоритетом
        - RECURSIVE: мержим рекурсивно (контейнеры) - вызываем себя для детей
        
        Args:
            base_block: Базовый блок
            mod_blocks: Список (mod_name, block) из модов
            depth: Глубина рекурсии (для отладки)
        """
        from .paradox_rules import is_gui_background_container
        
        result_text = base_block.full_text
        
        # Определяем стратегию для родительского блока
        parent_strategy = get_merge_strategy(base_block.name)
        
        # Если весь блок нужно заменять целиком - берём из последнего мода
        if parent_strategy == MergeStrategy.REPLACE_WHOLE:
            if mod_blocks:
                last_mod_name, last_mod_block = mod_blocks[-1]
                self.changes.append(MergeChange(
                    path=base_block.name,
                    change_type='replaced_whole',
                    mod_name=last_mod_name,
                    content=base_block.name
                ))
                return last_mod_block.full_text
            return result_text
        
        # Специальная обработка для GUI контейнеров
        # texture и environment сравниваются по содержимому, не по индексу
        if is_gui_background_container(base_block.name):
            return self._merge_gui_container(base_block, mod_blocks, depth)
        
        # RECURSIVE или ACCUMULATE - обрабатываем children
        # Теперь children это Dict[str, List[ParsedBlock]]
        for child_name, base_children_list in base_block.children.items():
            child_strategy = get_merge_strategy(child_name, base_block.name)
            
            # Обрабатываем КАЖДЫЙ блок с данным именем по индексу
            for idx, base_child in enumerate(base_children_list):
                
                if child_strategy == MergeStrategy.ACCUMULATE_LIST:
                    # === ACCUMULATE: накапливаем элементы списка ===
                    if base_child.list_items:
                        all_items = list(base_child.list_items)
                        
                        for mod_name, mod_block in mod_blocks:
                            mod_children = mod_block.get_all_children(child_name)
                            if idx < len(mod_children):
                                mod_child = mod_children[idx]
                                for item in mod_child.list_items:
                                    if item not in all_items:
                                        all_items.append(item)
                                        self.changes.append(MergeChange(
                                            path=f"{base_block.name}.{child_name}[{idx}]",
                                            change_type='added_list_item',
                                            mod_name=mod_name,
                                            content=item
                                        ))
                        
                        # Если есть новые элементы - обновляем
                        if len(all_items) > len(base_child.list_items):
                            result_text = self._update_list_in_text(
                                result_text, 
                                child_name, 
                                base_child.list_items,
                                all_items,
                                base_child.full_text
                            )
                
                elif child_strategy == MergeStrategy.RECURSIVE:
                    # === RECURSIVE: рекурсивно мержим вложенный контейнер ===
                    # Собираем версии этого child[idx] из всех модов
                    child_mod_blocks = []
                    for mod_name, mod_block in mod_blocks:
                        mod_children = mod_block.get_all_children(child_name)
                        if idx < len(mod_children):
                            child_mod_blocks.append((mod_name, mod_children[idx]))
                    
                    if child_mod_blocks:
                        # Рекурсивный вызов для вложенного блока
                        merged_child_text = self._deep_merge_block(base_child, child_mod_blocks, depth + 1)
                        result_text = result_text.replace(base_child.full_text, merged_child_text, 1)
                
                elif child_strategy == MergeStrategy.REPLACE_WHOLE:
                    # === REPLACE: берём целиком из последнего мода который изменил этот индекс ===
                    for mod_name, mod_block in reversed(mod_blocks):
                        mod_children = mod_block.get_all_children(child_name)
                        if idx < len(mod_children):
                            mod_child = mod_children[idx]
                            # Проверяем что реально изменён
                            if self._blocks_differ(base_child, mod_child):
                                result_text = result_text.replace(
                                    base_child.full_text, 
                                    mod_child.full_text, 
                                    1
                                )
                                self.changes.append(MergeChange(
                                    path=f"{base_block.name}.{child_name}[{idx}]",
                                    change_type='replaced_block',
                                    mod_name=mod_name,
                                    content=child_name
                                ))
                                break  # Берём только из последнего мода
        
        # Добавляем НОВЫЕ блоки из модов
        # 1. Новые блоки с уникальными именами
        # 2. Дополнительные блоки с существующими именами (if[2] когда в базе только if[0], if[1])
        added_blocks = set()  # (child_name, index) - отслеживаем что уже добавили
        
        for mod_name, mod_block in mod_blocks:
            for child_name, mod_children_list in mod_block.children.items():
                base_children = base_block.get_all_children(child_name)
                base_count = len(base_children)
                
                for idx, mod_child in enumerate(mod_children_list):
                    if idx >= base_count:
                        # Это НОВЫЙ блок (индекс за пределами базы)
                        key = (child_name, idx)
                        if key not in added_blocks:
                            if is_safe_to_add_child(child_name, base_block.name):
                                close_brace_pos = result_text.rfind('}')
                                if close_brace_pos > 0:
                                    indent = base_block.indent + '\t'
                                    new_block_text = '\n' + indent + mod_child.full_text.strip()
                                    result_text = result_text[:close_brace_pos] + new_block_text + '\n' + result_text[close_brace_pos:]
                                    added_blocks.add(key)
                                    
                                    self.changes.append(MergeChange(
                                        path=f"{base_block.name}.{child_name}[{idx}]",
                                        change_type='added_child_block',
                                        mod_name=mod_name,
                                        content=child_name
                                    ))
                            else:
                                self.changes.append(MergeChange(
                                    path=f"{base_block.name}.{child_name}[{idx}]",
                                    change_type='skipped_unsafe',
                                    mod_name=mod_name,
                                    content=f"Пропущен небезопасный блок {child_name}"
                                ))
                    
                    elif base_count == 0:
                        # Полностью новый тип блока (не было в базе вообще)
                        key = (child_name, idx)
                        if key not in added_blocks:
                            if is_safe_to_add_child(child_name, base_block.name):
                                close_brace_pos = result_text.rfind('}')
                                if close_brace_pos > 0:
                                    indent = base_block.indent + '\t'
                                    new_block_text = '\n' + indent + mod_child.full_text.strip()
                                    result_text = result_text[:close_brace_pos] + new_block_text + '\n' + result_text[close_brace_pos:]
                                    added_blocks.add(key)
                                    
                                    self.changes.append(MergeChange(
                                        path=f"{base_block.name}.{child_name}[{idx}]",
                                        change_type='added_new_child',
                                        mod_name=mod_name,
                                        content=child_name
                                    ))
        
        return result_text
    
    def _merge_gui_container(self, base_block: ParsedBlock, mod_blocks: List[Tuple[str, ParsedBlock]], depth: int = 0) -> str:
        """
        Специальный мерж для GUI контейнеров (character_view_bg и т.п.).
        
        texture и environment блоки сравниваются по СОДЕРЖИМОМУ (нормализованному),
        а не по индексу. Это позволяет:
        - Накапливать уникальные блоки из разных модов
        - Заменять блоки с одинаковым trigger на версию из последнего мода
        """
        result_text = base_block.full_text
        
        # Собираем все уникальные блоки
        # Ключ = нормализованное содержимое (для сравнения)
        # Значение = (mod_name, full_text)
        
        # Начинаем с базовых блоков
        all_blocks = {}  # normalized_content -> (source, full_text)
        
        for child_name, base_children in base_block.children.items():
            for base_child in base_children:
                normalized = self._normalize_block_content(base_child.inner_text)
                all_blocks[normalized] = ('base', base_child.full_text)
        
        # Добавляем/заменяем из модов
        for mod_name, mod_block in mod_blocks:
            for child_name, mod_children in mod_block.children.items():
                for mod_child in mod_children:
                    normalized = self._normalize_block_content(mod_child.inner_text)
                    
                    if normalized in all_blocks:
                        # Блок уже есть - заменяем если из мода (последний побеждает)
                        old_source, _ = all_blocks[normalized]
                        all_blocks[normalized] = (mod_name, mod_child.full_text)
                    else:
                        # Новый уникальный блок - добавляем
                        all_blocks[normalized] = (mod_name, mod_child.full_text)
                        self.changes.append(MergeChange(
                            path=f"{base_block.name}.{child_name}",
                            change_type='added_gui_block',
                            mod_name=mod_name,
                            content=mod_child.full_text[:50]
                        ))
        
        # Собираем результат
        # Берём header блока и добавляем все уникальные блоки
        
        # Находим начало блока (до первого child)
        block_start = base_block.full_text.find('{') + 1
        
        # Собираем все блоки
        indent = base_block.indent + '\t'
        all_block_texts = []
        for normalized, (source, full_text) in all_blocks.items():
            # Нормализуем отступы
            lines = full_text.strip().split('\n')
            normalized_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped:
                    normalized_lines.append(indent + stripped)
                else:
                    normalized_lines.append('')
            all_block_texts.append('\n'.join(normalized_lines))
        
        # Формируем результат
        header = base_block.full_text[:block_start]
        result = header + '\n' + '\n'.join(all_block_texts) + '\n' + base_block.indent + '}'
        
        return result
    
    def _normalize_block_content(self, content: str) -> str:
        """
        Нормализует содержимое блока для сравнения.
        Убирает пробелы, переносы строк, комментарии.
        """
        # Убираем комментарии
        lines = []
        for line in content.split('\n'):
            if '#' in line:
                line = line[:line.index('#')]
            line = line.strip()
            if line:
                lines.append(line)
        
        # Соединяем и нормализуем пробелы
        normalized = ' '.join(lines)
        # Убираем множественные пробелы
        normalized = ' '.join(normalized.split())
        return normalized
    
    def _update_list_in_text(self, text: str, list_name: str, old_items: List[str], 
                             new_items: List[str], old_block_text: str) -> str:
        """Обновляет список в тексте, добавляя новые элементы"""
        
        # Ищем начало блока
        start_pattern = rf'{re.escape(list_name)}\s*=\s*\{{'
        start_match = re.search(start_pattern, text)
        
        if not start_match:
            return text
        
        start_pos = start_match.start()
        brace_start = start_match.end() - 1  # позиция {
        
        # Находим соответствующую закрывающую скобку
        depth = 0
        end_pos = brace_start
        
        for i in range(brace_start, len(text)):
            char = text[i]
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end_pos = i + 1
                    break
        
        old_block = text[start_pos:end_pos]
        inner = text[brace_start + 1:end_pos - 1]
        
        # Определяем формат
        if '\n' in inner:
            # Многострочный - находим отступ
            indent = '\t\t'
            for line in inner.split('\n'):
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    indent = line[:len(line) - len(line.lstrip())]
                    break
            
            # Формируем новое содержимое
            new_lines = []
            for item in new_items:
                new_lines.append(f'{indent}{item}')
            
            # Сохраняем комментарии
            for line in inner.split('\n'):
                stripped = line.strip()
                if stripped.startswith('#'):
                    new_lines.append(line.rstrip())
            
            # Находим отступ закрывающей скобки
            close_indent = '\t'
            last_lines = inner.split('\n')
            if last_lines:
                last = last_lines[-1]
                if not last.strip():
                    close_indent = last
            
            new_inner = '\n' + '\n'.join(new_lines) + '\n' + close_indent
        else:
            # Однострочный
            new_inner = ' ' + ' '.join(new_items) + ' '
        
        new_block = f'{list_name} = {{{new_inner}}}'
        return text[:start_pos] + new_block + text[end_pos:]
    
    def _find_comment_start(self, line: str) -> int:
        """Находит начало комментария (# вне кавычек)"""
        in_quotes = False
        for i, char in enumerate(line):
            if char == '"' and (i == 0 or line[i-1] != '\\'):
                in_quotes = not in_quotes
            elif char == '#' and not in_quotes:
                return i
        return -1
    
    def _validate_braces(self, content: str) -> bool:
        """Проверяет баланс скобок"""
        open_count, close_count = self._count_braces(content)
        return open_count == close_count
    
    def _count_braces(self, content: str) -> Tuple[int, int]:
        """Считает скобки без комментариев"""
        open_count = 0
        close_count = 0
        
        for line in content.split('\n'):
            hash_pos = self._find_comment_start(line)
            if hash_pos >= 0:
                line = line[:hash_pos]
            open_count += line.count('{')
            close_count += line.count('}')
        
        return open_count, close_count
