"""
Paradox Script Rules & Validator
Правила структуры Paradox скриптов и валидация мержа

Определяет:
- Что можно мержить как списки (накапливать элементы)
- Что нужно брать целиком (заменять)
- Структурные правила для валидации
"""

from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class MergeStrategy(Enum):
    """Стратегия мержа для разных типов блоков"""
    
    # Можно накапливать элементы списка
    ACCUMULATE_LIST = "accumulate_list"
    
    # Берём целиком из мода с приоритетом (не мержим внутренности)
    REPLACE_WHOLE = "replace_whole"
    
    # Мержим рекурсивно (для контейнеров)
    RECURSIVE = "recursive"
    
    # Не трогаем - оставляем как в базе
    KEEP_BASE = "keep_base"


class TopLevelStrategy(Enum):
    """
    Стратегия для блоков ВЕРХНЕГО уровня файла.
    
    Определяет как обрабатывать блоки в файле:
    - Уникальные блоки всегда накапливаются
    - Одинаковые блоки - зависит от стратегии
    """
    
    # Блок атомарный, но уникальные накапливаются в файле
    # Пример: события, decisions, traits
    # test.001 из MOD1 + test.002 из MOD2 → оба в результате
    # test.001 из MOD1 + test.001 из MOD2 → берём из MOD2
    ATOMIC_ACCUMULATE = "atomic_accumulate"
    
    # Блок - контейнер, мержим его внутренности
    # Пример: on_actions, scripted_effects
    # on_game_start: on_actions накапливаются, effect заменяется
    MERGEABLE_CONTAINER = "mergeable_container"


@dataclass
class BlockRule:
    """Правило для типа блока"""
    strategy: MergeStrategy
    allowed_children: Optional[Set[str]] = None  # Какие дети допустимы
    max_count: Optional[int] = None  # Макс. количество (для option и т.п.)
    required_children: Optional[Set[str]] = None  # Обязательные дети
    description: str = ""


# Правила для разных типов блоков в Paradox
BLOCK_RULES: Dict[str, BlockRule] = {
    # === ON_ACTIONS ===
    # on_game_start, on_game_start_after_lobby, etc.
    "on_game_start": BlockRule(
        strategy=MergeStrategy.RECURSIVE,
        description="Контейнер on_action - мержим рекурсивно"
    ),
    "on_game_start_after_lobby": BlockRule(
        strategy=MergeStrategy.RECURSIVE,
        description="Контейнер on_action"
    ),
    
    # Внутри on_action - ЭТО можно накапливать
    "on_actions": BlockRule(
        strategy=MergeStrategy.ACCUMULATE_LIST,
        description="Список вызываемых on_actions - можно добавлять"
    ),
    "events": BlockRule(
        strategy=MergeStrategy.ACCUMULATE_LIST,
        description="Список вызываемых событий - можно добавлять"
    ),
    
    # effect внутри on_action - ОСТОРОЖНО
    "effect": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Логический блок эффектов - берём целиком"
    ),
    
    # === EVENTS ===
    # События - ВСЕГДА берём целиком из одного источника
    # Нельзя смешивать option из разных модов!
    "namespace.event": BlockRule(  # Паттерн для событий
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Событие - берём целиком"
    ),
    
    # Внутри события - НЕ мержим
    "option": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Option события - не мержим"
    ),
    "trigger": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Условия - не мержим"
    ),
    "immediate": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Немедленные эффекты - не мержим"
    ),
    "after": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Эффекты после - не мержим"
    ),
    "desc": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Описание - не мержим"
    ),
    
    # === COMMON BLOCKS ===
    "limit": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Ограничения - логический блок"
    ),
    "modifier": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Модификатор - не мержим"
    ),
    "ai_will_do": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="AI веса - не мержим"
    ),
    
    # === DECISIONS ===
    # Решения - берём целиком
    "decision": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Решение - берём целиком"
    ),
    
    # === SCRIPTED TRIGGERS/EFFECTS ===
    "scripted_trigger": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Скриптовый триггер - берём целиком"
    ),
    "scripted_effect": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Скриптовый эффект - берём целиком"
    ),
    
    # === CHARACTER INTERACTIONS ===
    "interaction": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Взаимодействие - берём целиком"
    ),
    
    # === GUI ===
    "window": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="GUI окно - берём целиком"
    ),
    "widget": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="GUI виджет - берём целиком"
    ),
    
    # === TRAITS ===
    "trait": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Черта - берём целиком"
    ),
    
    # === CULTURES/RELIGIONS ===
    "culture": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Культура - берём целиком"
    ),
    "religion": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Религия - берём целиком"
    ),
    "faith": BlockRule(
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Вера - берём целиком"
    ),
    
    # === HISTORY ===
    # Даты в history - можно накапливать (разные даты - разные записи)
    # Но одна дата - берём целиком
    "date_block": BlockRule(  # 1066.1.1 = { }
        strategy=MergeStrategy.REPLACE_WHOLE,
        description="Блок даты - берём целиком"
    ),
}

# Паттерны для определения типа блока
BLOCK_PATTERNS = {
    # События: namespace.number или просто number
    r'^[a-z_]+\.\d+$': 'event',
    r'^\d+$': 'province_id',
    
    # Даты: year.month.day
    r'^\d+\.\d+\.\d+$': 'date_block',
    
    # Титулы: x_something
    r'^[ekdcb]_[a-z_]+$': 'title',
}

# Блоки которые БЕЗОПАСНО мержить как списки
# ВАЖНО: on_actions позволяют ДОБАВЛЯТЬ events и on_actions, но НЕ effects и triggers!
# Источник: https://ck3.paradoxwikis.com/Event_modding
SAFE_LIST_BLOCKS = {
    'on_actions',       # Вызовы других on_actions - МОЖНО добавлять
    'events',           # Списки событий для вызова - МОЖНО добавлять
    'random_events',    # Случайные события - МОЖНО добавлять
    'random_on_actions',# Случайные on_actions
    'first_valid',      # Первый валидный из списка
}

# Блоки которые НЕЛЬЗЯ мержить - только заменять целиком
# Источник: CK3 Wiki Scripting, Event modding
NO_MERGE_BLOCKS = {
    # === ЛОГИЧЕСКИЕ БЛОКИ (trigger/effect контексты) ===
    'trigger',          # Проверка условий - атомарный
    'limit',            # Ограничение в скоупе - атомарный  
    'effect',           # Блок эффектов - атомарный (в on_action НЕ добавляется!)
    'immediate',        # Немедленные эффекты события - атомарный
    'after',            # Эффекты после события - атомарный
    'on_trigger_fail',  # При провале триггера
    
    # === МОДИФИКАТОРЫ И ВЕСА ===
    'modifier',         # Модификатор значения
    'ai_will_do',       # AI веса для решений
    'ai_check_interval',# Интервал проверки AI
    'ai_chance',        # Шанс AI выбрать опцию
    'weight',           # Вес
    'weight_multiplier',# Множитель веса
    'compare_modifier', # Сравнительный модификатор
    'opinion_modifier', # Модификатор мнения
    'mult',             # Множитель
    'add',              # Добавление к значению
    'factor',           # Фактор
    
    # === СОБЫТИЯ - внутренние блоки ===
    'option',           # Опция события - АТОМАРНАЯ (нельзя смешивать из разных модов!)
    'desc',             # Описание события
    'title',            # Заголовок
    'theme',            # Тема события
    'override_background',  # Фон
    'left_portrait',    # Портреты
    'right_portrait',
    'lower_left_portrait',
    'lower_center_portrait',
    'lower_right_portrait',
    'artifact',         # Артефакт в событии
    'override_icon',    # Иконка
    'cooldown',         # Кулдаун
    
    # === РЕШЕНИЯ (Decisions) ===
    'is_shown',         # Условие видимости решения
    'is_valid',         # Условие доступности
    'is_valid_showing_failures_only',
    'cost',             # Стоимость
    'minimum_cost',     # Минимальная стоимость
    'confirm_text',     # Текст подтверждения
    'selection_tooltip',# Тултип выбора
    
    # === ВЗАИМОДЕЙСТВИЯ (Interactions) ===
    'can_send',         # Можно ли отправить
    'can_be_picked',    # Можно ли выбрать
    'is_highlighted',   # Подсветка
    'on_accept',        # При принятии
    'on_decline',       # При отказе
    'on_send',          # При отправке
    'on_auto_accept',   # При автопринятии
    'reply_item',       # Элемент ответа
    'send_option',      # Опция отправки
    'greeting',         # Приветствие
    'notification_text',# Текст уведомления
    
    # === СХЕМЫ (Schemes) ===
    'on_ready',         # При готовности
    'on_monthly',       # Ежемесячно
    'on_invalidated',   # При инвалидации
    
    # === АКТИВНОСТИ (Activities) ===
    'on_start',         # При старте
    'on_complete',      # При завершении
    'on_enter_location',# При входе в локацию
    'on_leave_location',# При выходе
    'phases',           # Фазы активности
    
    # === ИТЕРАТОРЫ - всегда атомарные ===
    # every_*, random_*, ordered_*, any_* - определяются паттернами
    
    # === GUI ===
    'window',
    'widget',
    'container',
    'vbox',
    'hbox',
    'button',
    'text',
    'icon',
    'portrait',
    'scrollarea',
    'flowcontainer',
    
    # === СКРИПТЫ ===
    'scripted_trigger', # Скриптовый триггер - атомарный
    'scripted_effect',  # Скриптовый эффект (но может содержать character: блоки)
    
    # === ДАННЫЕ - определения сущностей ===
    'trait',            # Черта персонажа
    'culture',          # Культура
    'culture_group',    # Группа культур
    'heritage',         # Наследие
    'tradition',        # Традиция
    'religion',         # Религия
    'faith',            # Вера
    'doctrine',         # Доктрина
    'dynasty',          # Династия
    'house',            # Дом
    'character',        # Определение персонажа (в history)
    'province',         # Провинция
    'holding',          # Владение
    'building',         # Здание
    'men_at_arms',      # Тип войск
    'innovation',       # Инновация
    'law',              # Закон
    'lifestyle',        # Образ жизни
    'perk',             # Перк
    'focus',            # Фокус
    
    # === ИСТОРИИ (History) - определяются паттернами дат ===
    # 1066.1.1 = { } - атомарные блоки дат
}

# Контейнеры которые мержим рекурсивно
# Все on_* блоки - это on_action контейнеры
# Внутри них on_actions и events ДОБАВЛЯЮТСЯ, а effect/trigger ЗАМЕНЯЮТСЯ
CONTAINER_BLOCKS = {
    # === ON_ACTIONS (код вызывает эти точки) ===
    'on_game_start', 'on_game_start_after_lobby',
    'on_birth', 'on_birth_child', 'on_birth_mother', 'on_birth_father', 'on_birth_real_father',
    'on_death', 'on_natural_death_second_chance',
    'on_join_court', 'on_leave_court',
    'on_imprison', 'on_release_from_prison',
    'on_marriage', 'on_divorce', 'on_concubinage',
    'on_character_faith_change', 'on_faith_created', 'on_faith_conversion',
    'on_character_culture_change',
    'on_war_started', 'on_war_ended', 'on_war_won', 'on_war_lost', 'on_war_white_peace',
    'on_title_gain', 'on_title_lost', 'on_title_destroyed',
    'on_realm_capital_change',
    'on_county_faith_change', 'on_county_culture_change',
    'on_yearly_pulse', 'on_monthly_pulse', 'on_weekly_pulse', 'on_quarterly_pulse',
    'five_year_playable_pulse', 'three_year_playable_pulse', 'yearly_playable_pulse',
    'random_yearly_playable_pulse', 'random_yearly_everyone_pulse',
    'on_prestige_gained', 'on_piety_gained', 'on_gold_gained',
    'on_army_enter_province',
    'on_siege_completion', 'on_siege_great_success', 'on_siege_looting',
    'on_artifact_created', 'on_artifact_destroyed', 'on_artifact_changed_owner',
    'on_holy_order_founded', 'on_holy_order_destroyed',
    'on_dynasty_created', 'on_house_created',
    # ... и все остальные on_* блоки определяются динамически
    
    # === SCRIPTED EFFECTS контейнеры ===
    # Определяются функцией is_scripted_effect_container()
}

# Паттерны для определения типа блока
BLOCK_PATTERNS = {
    # События: namespace.number - ВСЕГДА атомарные
    r'^[a-z_]+\.\d+$': 'event',
    
    # Числовые ID (провинции, персонажи в history)
    r'^\d+$': 'province_id',
    
    # Даты в history: year.month.day - ВСЕГДА атомарные
    r'^\d+\.\d+\.\d+$': 'date_block',
    
    # Титулы: x_something
    r'^[ekdcb]_[a-z_]+$': 'title',
}

# Паттерны для scope targets - можно добавлять в scripted_effects
SCOPE_TARGET_PATTERNS = [
    r'^character:[a-zA-Z0-9_]+$',   # character:xxx
    r'^title:[a-zA-Z0-9_:]+$',      # title:xxx или title:k_france
    r'^culture:[a-zA-Z0-9_]+$',     # culture:xxx
    r'^faith:[a-zA-Z0-9_]+$',       # faith:xxx
    r'^religion:[a-zA-Z0-9_]+$',    # religion:xxx
    r'^dynasty:[a-zA-Z0-9_]+$',     # dynasty:xxx
    r'^house:[a-zA-Z0-9_]+$',       # house:xxx
    r'^province:\d+$',               # province:123
    r'^scope:[a-zA-Z0-9_]+$',       # scope:xxx (saved scope)
]

# Паттерны для итераторов - ВСЕГДА атомарные
ITERATOR_PATTERNS = [
    r'^every_[a-z_]+$',     # every_character, every_realm, etc.
    r'^random_[a-z_]+$',    # random_character (но НЕ random_events!)
    r'^ordered_[a-z_]+$',   # ordered_character
    r'^any_[a-z_]+$',       # any_character (триггер-итератор)
]

# === ФАЙЛОВЫЙ КОНТЕКСТ ===
# Некоторые типы файлов содержат ТОЛЬКО атомарные блоки верхнего уровня
# В них НЕЛЬЗЯ мержить внутренности - берём блок целиком

# ЧИСТО атомарные файлы - блоки полностью заменяются
ATOMIC_FILE_CONTEXTS = {
    # Путь содержит -> все блоки верхнего уровня атомарные
    'decisions',            # common/decisions/ - каждое решение атомарно
    'events',               # events/ - каждое событие атомарно
    'character_interactions',  # common/character_interactions/
    'schemes',              # common/schemes/
    'activities',           # common/activities/
}

# Файлы где можно мержить рекурсивно
RECURSIVE_FILE_CONTEXTS = {
    'on_action',            # common/on_action/ - контейнеры
    'scripted_effects',     # common/scripted_effects/ - могут содержать character: блоки
}

# GUI файлы - texture/environment накапливаются по содержимому
GUI_FILE_CONTEXTS = {
    'character_backgrounds',# gfx/portraits/character_backgrounds/
    'shared',               # gui/shared/
}

# === ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА ИЗ ДОКУМЕНТАЦИИ ===

# Файлы где блоки идентифицируются по КЛЮЧУ (имени)
# Одинаковые ключи из разных модов -> последний мод побеждает
# Разные ключи -> накапливаются
KEY_BASED_FILES = {
    'traits',               # trait_name = { } - уникальный trait_name
    'dynasties',            # dynasty_id = { } - уникальный ID
    'dynasty_houses',       # house_id = { }
    'cultures',             # culture_name = { }
    'religions',            # religion_name = { }
    'governments',          # government_name = { }
    'laws',                 # law_name = { }
    'buildings',            # building_name = { }
    'holdings',             # holding_name = { }
    'men_at_arms_types',    # maa_name = { }
    'casus_belli_types',    # cb_name = { }
    'modifiers',            # modifier_name = { }
    'scripted_triggers',    # trigger_name = { }
    'game_rules',           # rule_name = { }
    'nicknames',            # nickname_name = { }
    'lifestyle_perks',      # perk_name = { }
    'focuses',              # focus_name = { }
}

# Файлы с ПРИОРИТЕТОМ (flavorization)
# Блоки с higher priority перезаписывают lower priority
PRIORITY_BASED_FILES = {
    'flavorization',        # priority = N определяет порядок
}

# Файлы где порядок ВАЖЕН (списки имён)
# Элементы накапливаются, порядок сохраняется
LIST_ACCUMULATE_FILES = {
    'coat_of_arms',         # Гербы - по имени title
    'name_lists',           # Списки имён - накапливаются
    'customizable_localization', # Локализация
}

# Файлы с ЧИСЛОВЫМИ ID (history)
# character_id = { } - уникальный ID
NUMERIC_ID_FILES = {
    'characters',           # history/characters/
    'provinces',            # history/provinces/
    'titles',               # history/titles/
}


def get_file_context(file_path: str) -> str:
    """
    Определяет контекст файла по пути.
    
    Returns:
        'atomic' - все блоки верхнего уровня атомарные
        'recursive' - можно мержить рекурсивно
        'unknown' - неизвестный контекст
    """
    if not file_path:
        return 'unknown'
    
    path_lower = file_path.lower().replace('\\', '/')
    
    # Сначала проверяем рекурсивные контексты (приоритет выше)
    for context in RECURSIVE_FILE_CONTEXTS:
        if f'/{context}/' in path_lower or path_lower.startswith(context + '/') or f'/{context}' in path_lower:
            return 'recursive'
    
    # Затем проверяем атомарные контексты
    for context in ATOMIC_FILE_CONTEXTS:
        if f'/{context}/' in path_lower or path_lower.startswith(context + '/') or f'/{context}' in path_lower:
            return 'atomic'
    
    return 'unknown'


def is_top_level_atomic(block_name: str, file_path: str) -> bool:
    """
    Проверяет должен ли блок верхнего уровня быть атомарным
    на основе контекста файла.
    
    Например:
    - decisions/xxx.txt -> все блоки атомарные
    - events/xxx.txt -> все блоки атомарные (события)
    """
    context = get_file_context(file_path)
    
    if context == 'atomic':
        return True
    
    # События всегда атомарные
    if is_event_block(block_name):
        return True
    
    return False


def get_top_level_strategy(block_name: str, file_path: str = "") -> TopLevelStrategy:
    """
    Определяет стратегию для блока ВЕРХНЕГО уровня.
    
    Это главная функция для определения как обрабатывать блок в файле.
    
    Args:
        block_name: Имя блока верхнего уровня
        file_path: Путь к файлу (для контекста)
    
    Returns:
        TopLevelStrategy
    """
    # 1. События - атомарные (но уникальные накапливаются)
    if is_event_block(block_name):
        return TopLevelStrategy.ATOMIC_ACCUMULATE
    
    # 2. Даты в history - атомарные
    if is_date_block(block_name):
        return TopLevelStrategy.ATOMIC_ACCUMULATE
    
    # 3. Проверяем файловый контекст
    file_context = get_file_context(file_path)
    
    if file_context == 'atomic':
        # decisions/, traits/, cultures/, etc.
        return TopLevelStrategy.ATOMIC_ACCUMULATE
    
    if file_context == 'recursive':
        # on_action/, scripted_effects/
        return TopLevelStrategy.MERGEABLE_CONTAINER
    
    # 4. Проверяем по имени блока
    if is_on_action_container(block_name):
        return TopLevelStrategy.MERGEABLE_CONTAINER
    
    if is_scripted_effect_container(block_name):
        return TopLevelStrategy.MERGEABLE_CONTAINER
    
    # 5. GUI контейнеры (texture, environment накапливаются)
    if is_gui_background_container(block_name):
        return TopLevelStrategy.MERGEABLE_CONTAINER
    
    # 6. По умолчанию - атомарный (безопаснее)
    return TopLevelStrategy.ATOMIC_ACCUMULATE


def is_on_action_container(block_name: str) -> bool:
    """
    Проверяет является ли блок on_action контейнером.
    
    on_action блоки - это контейнеры где:
    - on_actions и events ДОБАВЛЯЮТСЯ (можно мержить)
    - effect и trigger ЗАМЕНЯЮТСЯ (берём из последнего мода)
    """
    # Все блоки начинающиеся с on_ - это on_action контейнеры
    # КРОМЕ on_actions (это список внутри on_action)
    if block_name.startswith('on_') and block_name != 'on_actions':
        return True
    # Пульсы
    if '_pulse' in block_name or '_playable_pulse' in block_name:
        return True
    return False


def is_scripted_effect_container(block_name: str) -> bool:
    """
    Проверяет является ли блок scripted_effect контейнером.
    
    Scripted effects часто содержат блоки character:xxx = { } которые
    нужно накапливать из разных модов.
    """
    # Паттерны scripted_effects
    if block_name.endswith('_effect') or block_name.endswith('_effects'):
        return True
    if block_name.startswith('fire_') or block_name.startswith('setup_'):
        return True
    if block_name.startswith('initialize_') or block_name.startswith('init_'):
        return True
    if '_intro_' in block_name or '_gamestart_' in block_name:
        return True
    if '_setup_' in block_name or '_spawn_' in block_name:
        return True
    return False


def is_scope_target_block(block_name: str) -> bool:
    """
    Проверяет является ли блок scope target.
    
    Scope targets (character:xxx, title:xxx, etc.) внутри scripted_effects
    можно безопасно накапливать из разных модов.
    """
    import re
    for pattern in SCOPE_TARGET_PATTERNS:
        if re.match(pattern, block_name):
            return True
    return False


def is_iterator_block(block_name: str) -> bool:
    """
    Проверяет является ли блок итератором.
    
    Итераторы (every_*, random_*, ordered_*, any_*) - ВСЕГДА атомарные.
    Исключение: random_events - это список, не итератор.
    """
    import re
    # Исключения - это списки, не итераторы
    if block_name in SAFE_LIST_BLOCKS:
        return False
    
    for pattern in ITERATOR_PATTERNS:
        if re.match(pattern, block_name):
            return True
    return False


def is_character_effect_block(block_name: str) -> bool:
    """
    Проверяет является ли блок эффектом для scope target.
    
    character:xxx = { }, title:xxx = { } блоки внутри scripted_effects - 
    это эффекты для конкретных сущностей, их можно безопасно накапливать.
    """
    return is_scope_target_block(block_name)


def is_gui_background_container(block_name: str) -> bool:
    """
    Проверяет является ли блок GUI контейнером для backgrounds.
    
    Эти блоки содержат множественные texture = {} и environment = {}
    которые должны накапливаться из разных модов.
    """
    gui_containers = {
        'character_view_bg',
        'character_location_exterior',
        'character_religion_interior',
        'religion_interior',
        'religion_holding',
        'title_holding',
        'artifact_regional_pattern',
        'character_private',
        'culture_levy_big_illustration',
        'culture_knight_big_illustration',
        'culture_levy_small_illustration',
        'culture_knight_small_illustration',
    }
    
    # Точное совпадение
    if block_name in gui_containers:
        return True
    
    # Паттерны
    if block_name.endswith('_bg') or block_name.endswith('_illustration'):
        return True
    if block_name.endswith('_interior') or block_name.endswith('_exterior'):
        return True
    # _pattern для GUI, но НЕ _holding (holdings это атомарные блоки, не GUI)
    if block_name.endswith('_pattern'):
        return True
    
    return False


def is_safe_to_add_child(child_name: str, parent_name: str) -> bool:
    """
    Проверяет безопасно ли добавить дочерний блок.
    
    Логика:
    1. Если родитель - MERGEABLE контейнер (on_action, scripted_effect, GUI),
       то ЛЮБЫЕ новые блоки из модов добавляются (мод явно их добавил)
    2. Иначе - только ACCUMULATE или RECURSIVE стратегии
    """
    # Если родитель - контейнер для мержа, добавляем любые блоки
    # Мод явно добавил этот блок - значит он нужен
    if is_scripted_effect_container(parent_name):
        return True
    
    if is_on_action_container(parent_name):
        return True
    
    # GUI контейнеры - texture и environment накапливаются
    if is_gui_background_container(parent_name):
        return True
    
    # Для остальных родителей - стандартная проверка
    strategy = get_merge_strategy(child_name, parent_name)
    return strategy in (MergeStrategy.ACCUMULATE_LIST, MergeStrategy.RECURSIVE)


def get_merge_strategy(block_name: str, parent_name: str = "") -> MergeStrategy:
    """
    Определяет стратегию мержа для блока.
    
    Правила основаны на документации CK3 Wiki:
    - on_actions позволяют ДОБАВЛЯТЬ events и on_actions, но НЕ effects и triggers
    - События (namespace.0001) - атомарные единицы
    - Итераторы (every_*, random_*, etc.) - атомарные
    - Scope targets (character:xxx) в scripted_effects - можно добавлять
    
    Args:
        block_name: Имя блока
        parent_name: Имя родительского блока (для контекста)
    
    Returns:
        MergeStrategy
    """
    import re
    
    # 1. Проверяем паттерны (события, даты, провинции)
    for pattern, block_type in BLOCK_PATTERNS.items():
        if re.match(pattern, block_name):
            if block_type == 'event':
                return MergeStrategy.REPLACE_WHOLE
            elif block_type == 'date_block':
                return MergeStrategy.REPLACE_WHOLE
            elif block_type == 'province_id':
                return MergeStrategy.REPLACE_WHOLE
    
    # 2. Итераторы - ВСЕГДА атомарные (кроме списков)
    if is_iterator_block(block_name):
        return MergeStrategy.REPLACE_WHOLE
    
    # 3. Проверяем явно разрешённые списки
    if block_name in SAFE_LIST_BLOCKS:
        return MergeStrategy.ACCUMULATE_LIST
    
    # 4. Проверяем явно запрещённые блоки
    if block_name in NO_MERGE_BLOCKS:
        return MergeStrategy.REPLACE_WHOLE
    
    # 5. Проверяем контейнеры (on_actions, scripted_effects)
    if block_name in CONTAINER_BLOCKS:
        return MergeStrategy.RECURSIVE
    if is_on_action_container(block_name):
        return MergeStrategy.RECURSIVE
    if is_scripted_effect_container(block_name):
        return MergeStrategy.RECURSIVE
    
    # 6. GUI контейнеры - texture/environment накапливаются
    if is_gui_background_container(block_name):
        return MergeStrategy.RECURSIVE
    
    # 7. По умолчанию - заменяем целиком (безопаснее)
    return MergeStrategy.REPLACE_WHOLE


def is_safe_to_accumulate(block_name: str, parent_name: str = "") -> bool:
    """Можно ли безопасно накапливать элементы в этом блоке"""
    return get_merge_strategy(block_name, parent_name) == MergeStrategy.ACCUMULATE_LIST


def is_event_block(block_name: str) -> bool:
    """Проверяет является ли блок событием"""
    import re
    return bool(re.match(r'^[a-z_]+\.\d+$', block_name))


def is_date_block(block_name: str) -> bool:
    """Проверяет является ли блок датой (для history)"""
    import re
    return bool(re.match(r'^\d+\.\d+\.\d+$', block_name))


@dataclass
class ValidationError:
    """Ошибка валидации"""
    path: str
    message: str
    severity: str  # 'error', 'warning'


class StructureValidator:
    """Валидатор структуры после мержа"""
    
    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
    
    def validate(self, content: str, filename: str = "") -> Tuple[bool, List[ValidationError]]:
        """
        Валидирует структуру файла после мержа.
        
        Returns:
            (is_valid, list_of_issues)
        """
        self.errors = []
        self.warnings = []
        
        # 1. Проверка баланса скобок
        if not self._validate_braces(content):
            self.errors.append(ValidationError(
                path=filename,
                message="Несбалансированные скобки",
                severity="error"
            ))
        
        # 2. Проверка дублирования блоков
        self._check_duplicate_blocks(content, filename)
        
        # 3. Проверка структуры событий
        if 'events' in filename or filename.endswith('_events.txt'):
            self._validate_events(content, filename)
        
        is_valid = len(self.errors) == 0
        return is_valid, self.errors + self.warnings
    
    def _validate_braces(self, content: str) -> bool:
        """Проверяет баланс скобок"""
        open_count = 0
        close_count = 0
        
        for line in content.split('\n'):
            # Убираем комментарии
            if '#' in line:
                hash_pos = self._find_comment(line)
                if hash_pos >= 0:
                    line = line[:hash_pos]
            
            open_count += line.count('{')
            close_count += line.count('}')
        
        return open_count == close_count
    
    def _find_comment(self, line: str) -> int:
        """Находит # вне кавычек"""
        in_quotes = False
        for i, c in enumerate(line):
            if c == '"' and (i == 0 or line[i-1] != '\\'):
                in_quotes = not in_quotes
            elif c == '#' and not in_quotes:
                return i
        return -1
    
    def _check_duplicate_blocks(self, content: str, filename: str):
        """Проверяет дублирование блоков верхнего уровня"""
        import re
        
        # Ищем блоки верхнего уровня
        blocks = re.findall(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.]*)\s*=\s*\{', content, re.MULTILINE)
        
        seen = {}
        for block in blocks:
            if block in seen:
                seen[block] += 1
            else:
                seen[block] = 1
        
        for block, count in seen.items():
            if count > 1 and is_event_block(block):
                self.errors.append(ValidationError(
                    path=f"{filename}.{block}",
                    message=f"Дублирование события '{block}' ({count} раз)",
                    severity="error"
                ))
    
    def _validate_events(self, content: str, filename: str):
        """Валидирует структуру событий"""
        import re
        
        # Ищем события
        event_pattern = r'([a-z_]+\.\d+)\s*=\s*\{'
        
        for match in re.finditer(event_pattern, content):
            event_name = match.group(1)
            start = match.end()
            
            # Находим конец события
            depth = 1
            end = start
            for i in range(start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            
            event_content = content[start:end]
            
            # Проверяем количество option
            options = re.findall(r'\boption\s*=\s*\{', event_content)
            if len(options) > 20:  # Подозрительно много
                self.warnings.append(ValidationError(
                    path=f"{filename}.{event_name}",
                    message=f"Подозрительно много option ({len(options)}) - возможно ошибка мержа",
                    severity="warning"
                ))


# ============================================
# ОПРЕДЕЛЕНИЕ ТИПА ФАЙЛА ДЛЯ МЕРЖА
# ============================================

class FileMergeType(Enum):
    """Типы файлов по стратегии мержа"""
    KEY_BASED = "key_based"           # Блоки по уникальному ключу (traits, buildings)
    RECURSIVE = "recursive"            # Рекурсивный мерж (on_action, scripted_effects)
    ATOMIC = "atomic"                  # Атомарные блоки (events, decisions)
    ACCUMULATE = "accumulate"          # Накопление элементов (name_lists)
    PRIORITY = "priority"              # По приоритету (flavorization)
    NUMERIC_ID = "numeric_id"          # Числовые ID (history/characters)
    GUI = "gui"                        # GUI файлы (texture накапливаются)


def get_file_merge_type(file_path: str) -> FileMergeType:
    """
    Определяет тип мержа для файла по его пути.
    
    Это КРИТИЧЕСКИ важная функция для корректного мержа!
    
    Args:
        file_path: Путь к файлу (относительный)
    
    Returns:
        FileMergeType
    """
    if not file_path:
        return FileMergeType.KEY_BASED
    
    path_lower = file_path.lower().replace('\\', '/')
    
    # History с числовыми ID
    if 'history/characters/' in path_lower:
        return FileMergeType.NUMERIC_ID
    if 'history/provinces/' in path_lower:
        return FileMergeType.NUMERIC_ID
    if 'history/titles/' in path_lower:
        return FileMergeType.NUMERIC_ID
    
    # События (events/ folder) - всегда атомарные
    if 'events/' in path_lower:
        return FileMergeType.ATOMIC
    
    # GUI файлы (texture/environment накапливаются)
    for context in GUI_FILE_CONTEXTS:
        if f'{context}/' in path_lower or path_lower.endswith(f'/{context}'):
            return FileMergeType.GUI
    
    # Общие GUI/GFX файлы
    if 'gfx/' in path_lower or 'gui/' in path_lower:
        return FileMergeType.GUI
    
    # Атомарные файлы (decisions)
    for context in ATOMIC_FILE_CONTEXTS:
        if f'{context}/' in path_lower or path_lower.endswith(f'/{context}'):
            return FileMergeType.ATOMIC
    
    # Рекурсивные файлы
    for context in RECURSIVE_FILE_CONTEXTS:
        if f'{context}/' in path_lower or path_lower.endswith(f'/{context}'):
            return FileMergeType.RECURSIVE
    
    # Key-based файлы
    for context in KEY_BASED_FILES:
        if f'{context}/' in path_lower or path_lower.endswith(f'/{context}'):
            return FileMergeType.KEY_BASED
    
    # Priority-based
    for context in PRIORITY_BASED_FILES:
        if f'{context}/' in path_lower:
            return FileMergeType.PRIORITY
    
    # По умолчанию - key_based (большинство common/ файлов)
    return FileMergeType.KEY_BASED


def should_skip_file(file_path: str) -> bool:
    """
    Проверяет нужно ли пропустить файл при мерже.
    
    Пропускаем:
    - Локализацию (.yml) - не мержим
    - Бинарные файлы
    """
    if not file_path:
        return False
    
    path_lower = file_path.lower()
    
    # Локализация - НЕ мержим
    if 'localization/' in path_lower or path_lower.endswith('.yml'):
        return True
    
    # Бинарные файлы
    binary_extensions = {'.dds', '.png', '.jpg', '.wav', '.ogg', '.mesh', '.anim'}
    for ext in binary_extensions:
        if path_lower.endswith(ext):
            return True
    
    return False


def get_block_identity_type(block_name: str, file_path: str = "") -> str:
    """
    Определяет как идентифицировать блок для сопоставления.
    
    Returns:
        'name' - по имени блока (большинство случаев)
        'content' - по содержимому (texture в GUI)
        'index' - по позиции/индексу (if блоки)
        'id' - по числовому ID (characters)
    """
    file_type = get_file_merge_type(file_path)
    
    # GUI файлы - texture и environment по содержимому
    if file_type == FileMergeType.GUI:
        if block_name in ('texture', 'environment'):
            return 'content'
    
    # History с числовыми ID
    if file_type == FileMergeType.NUMERIC_ID:
        # Если имя блока - число, то по ID
        if block_name.isdigit():
            return 'id'
    
    # События идентифицируются по имени
    if is_event_block(block_name):
        return 'name'
    
    # Блоки типа if - по индексу
    if block_name in ('if', 'else', 'else_if', 'trigger_if', 'trigger_else'):
        return 'index'
    
    # По умолчанию - по имени
    return 'name'
