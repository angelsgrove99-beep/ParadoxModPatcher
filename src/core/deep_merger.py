"""
Deep Structure Merger
Глубокий структурный мерж Paradox файлов

Мержит на уровне:
- Блоков
- Вложенных структур
- Отдельных свойств
- Элементов списков

Логика:
1. Парсим все версии файла в AST
2. Сравниваем с базой - находим ЧТО изменилось
3. Накапливаем уникальные изменения из всех модов
4. При конфликтах - приоритет последнего мода
"""

from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from .pdx_parser import PdxNode, PdxParser, PdxSerializer, NodeType


@dataclass
class ChangeInfo:
    """Информация об изменении"""
    path: str  # Путь к узлу: "on_game_start.on_actions"
    change_type: str  # "added", "modified", "removed", "uncommented", "commented"
    mod_name: str
    node: PdxNode
    priority: int


@dataclass 
class DeepMergeResult:
    """Результат глубокого мержа"""
    success: bool
    content: str = ""
    error: str = ""
    changes: List[ChangeInfo] = field(default_factory=list)


class DeepStructureMerger:
    """Глубокий структурный мержер"""
    
    def __init__(self):
        self.parser = PdxParser()
        self.serializer = PdxSerializer()
        self.changes: List[ChangeInfo] = []
    
    def merge_files(self, base_content: str, mod_contents: List[Tuple[str, str, int]]) -> DeepMergeResult:
        """
        Мержит файлы с глубоким сравнением структуры
        
        Args:
            base_content: Содержимое базового файла
            mod_contents: Список (mod_name, content, priority)
        
        Returns:
            DeepMergeResult
        """
        self.changes = []
        
        try:
            # Парсим базу
            base_ast = self.parser.parse(base_content)
            
            # Собираем изменения из всех модов
            all_changes: Dict[str, List[ChangeInfo]] = {}  # path -> changes
            
            for mod_name, content, priority in mod_contents:
                mod_ast = self.parser.parse(content)
                
                # Находим изменения относительно базы
                changes = self._find_changes(base_ast, mod_ast, mod_name, priority)
                
                for change in changes:
                    if change.path not in all_changes:
                        all_changes[change.path] = []
                    all_changes[change.path].append(change)
            
            # Применяем изменения к базе
            result_ast = base_ast.clone()
            
            for path, changes in all_changes.items():
                # Сортируем по приоритету
                changes.sort(key=lambda c: c.priority)
                
                # Применяем изменения
                for change in changes:
                    self._apply_change(result_ast, change)
                    self.changes.append(change)
            
            # Сериализуем результат
            result_content = self.serializer.serialize(result_ast)
            
            # Валидация
            open_count = 0
            close_count = 0
            for line in result_content.split('\n'):
                if '#' in line:
                    line = line[:line.index('#')]
                open_count += line.count('{')
                close_count += line.count('}')
            
            if open_count != close_count:
                return DeepMergeResult(
                    success=False,
                    error=f"Несбалансированные скобки: {{ = {open_count}, }} = {close_count}"
                )
            
            return DeepMergeResult(
                success=True,
                content=result_content,
                changes=self.changes
            )
            
        except Exception as e:
            return DeepMergeResult(
                success=False,
                error=f"Ошибка парсинга: {str(e)}"
            )
    
    def _find_changes(self, base: PdxNode, mod: PdxNode, mod_name: str, priority: int, 
                      path: str = "") -> List[ChangeInfo]:
        """Рекурсивно находит изменения между базой и модом"""
        changes = []
        
        # Индексируем children базы по имени/значению
        base_index = self._index_children(base)
        mod_index = self._index_children(mod)
        
        # Ищем добавленные и изменённые узлы
        for key, mod_nodes in mod_index.items():
            base_nodes = base_index.get(key, [])
            
            for i, mod_node in enumerate(mod_nodes):
                node_path = f"{path}.{key}" if path else key
                
                if i < len(base_nodes):
                    base_node = base_nodes[i]
                    
                    # Узел существует - проверяем изменения
                    if mod_node.node_type == NodeType.BLOCK and base_node.node_type == NodeType.BLOCK:
                        # Рекурсивно проверяем вложенные изменения
                        nested_changes = self._find_changes(
                            base_node, mod_node, mod_name, priority, node_path
                        )
                        changes.extend(nested_changes)
                        
                        # Проверяем изменение комментирования
                        if base_node.is_commented and not mod_node.is_commented:
                            changes.append(ChangeInfo(
                                path=node_path,
                                change_type="uncommented",
                                mod_name=mod_name,
                                node=mod_node.clone(),
                                priority=priority
                            ))
                        elif not base_node.is_commented and mod_node.is_commented:
                            changes.append(ChangeInfo(
                                path=node_path,
                                change_type="commented",
                                mod_name=mod_name,
                                node=mod_node.clone(),
                                priority=priority
                            ))
                    
                    elif mod_node.node_type == NodeType.PROPERTY:
                        # Свойство - проверяем значение
                        if mod_node.value != base_node.value:
                            changes.append(ChangeInfo(
                                path=node_path,
                                change_type="modified",
                                mod_name=mod_name,
                                node=mod_node.clone(),
                                priority=priority
                            ))
                else:
                    # Новый узел
                    changes.append(ChangeInfo(
                        path=node_path,
                        change_type="added",
                        mod_name=mod_name,
                        node=mod_node.clone(),
                        priority=priority
                    ))
        
        # Ищем удалённые узлы (есть в базе, нет в моде)
        for key, base_nodes in base_index.items():
            if key not in mod_index:
                for base_node in base_nodes:
                    node_path = f"{path}.{key}" if path else key
                    changes.append(ChangeInfo(
                        path=node_path,
                        change_type="removed",
                        mod_name=mod_name,
                        node=base_node.clone(),
                        priority=priority
                    ))
        
        return changes
    
    def _index_children(self, node: PdxNode) -> Dict[str, List[PdxNode]]:
        """Индексирует children по ключу (имя или значение)"""
        index: Dict[str, List[PdxNode]] = {}
        
        for child in node.children:
            # Пропускаем пустые строки и комментарии при индексации
            if child.node_type in (NodeType.EMPTY_LINE, NodeType.COMMENT):
                continue
            
            key = child.name if child.name else child.value
            if key not in index:
                index[key] = []
            index[key].append(child)
        
        return index
    
    def _apply_change(self, ast: PdxNode, change: ChangeInfo):
        """Применяет изменение к AST"""
        path_parts = change.path.split('.') if change.path else []
        
        # Находим родительский узел
        parent = ast
        for i, part in enumerate(path_parts[:-1]):
            found = False
            for child in parent.children:
                if (child.name == part or child.value == part):
                    parent = child
                    found = True
                    break
            
            if not found:
                # Создаём промежуточный узел если нужно
                new_node = PdxNode(
                    node_type=NodeType.BLOCK,
                    name=part
                )
                parent.children.append(new_node)
                parent = new_node
        
        target_key = path_parts[-1] if path_parts else ""
        
        if change.change_type == "added":
            # Добавляем новый узел
            # Проверяем нет ли уже такого
            exists = False
            for child in parent.children:
                if self._nodes_equal(child, change.node):
                    exists = True
                    break
            
            if not exists:
                # Ищем место для вставки (после похожих узлов)
                insert_pos = len(parent.children)
                for i, child in enumerate(parent.children):
                    if child.name == change.node.name or child.value == change.node.value:
                        insert_pos = i + 1
                
                parent.children.insert(insert_pos, change.node.clone())
        
        elif change.change_type == "modified":
            # Модифицируем существующий узел
            for i, child in enumerate(parent.children):
                if child.name == target_key or child.value == target_key:
                    # Обновляем значение
                    if change.node.node_type == NodeType.PROPERTY:
                        child.value = change.node.value
                    elif change.node.node_type == NodeType.BLOCK:
                        parent.children[i] = change.node.clone()
                    break
        
        elif change.change_type == "removed":
            # Удаляем узел (закомментируем вместо удаления для безопасности)
            for child in parent.children:
                if child.name == target_key or child.value == target_key:
                    child.is_commented = True
                    break
        
        elif change.change_type == "uncommented":
            # Раскомментируем узел
            for child in parent.children:
                if child.name == target_key:
                    child.is_commented = False
                    # Обновляем содержимое
                    child.children = change.node.children
                    break
        
        elif change.change_type == "commented":
            # Комментируем узел
            for child in parent.children:
                if child.name == target_key:
                    child.is_commented = True
                    break
    
    def _nodes_equal(self, a: PdxNode, b: PdxNode) -> bool:
        """Проверяет равенство узлов (по структуре)"""
        if a.node_type != b.node_type:
            return False
        if a.name != b.name:
            return False
        if a.value != b.value:
            return False
        if a.is_commented != b.is_commented:
            return False
        
        # Для блоков сравниваем детей
        if a.node_type == NodeType.BLOCK:
            if len(a.children) != len(b.children):
                return False
            for ca, cb in zip(a.children, b.children):
                if not self._nodes_equal(ca, cb):
                    return False
        
        return True
    
    def _normalize_for_comparison(self, node: PdxNode) -> str:
        """Нормализует узел для сравнения"""
        parts = []
        
        if node.name:
            parts.append(node.name)
        if node.value:
            parts.append(node.value)
        
        for child in node.children:
            if child.node_type not in (NodeType.EMPTY_LINE, NodeType.COMMENT):
                parts.append(self._normalize_for_comparison(child))
        
        return '|'.join(parts)
