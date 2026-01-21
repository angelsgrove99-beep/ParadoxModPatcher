#!/usr/bin/env python3
"""
Paradox Mod Patcher - Command Line Interface
Командная строка для автопатчера

Использование:
    python -m src.cli --mods "./mod" --output "./patch"
    python -m src.cli --mods "./mod" --output "./patch" --name "My Patch"
    python -m src.cli --mods "./mod" --list-conflicts
"""

import argparse
import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent))

from core import (
    ModScanner, PatchGenerator, MergeStrategy,
    get_paradox_mods_path
)


def main():
    parser = argparse.ArgumentParser(
        description="Paradox Mod Patcher - автоматический генератор патчей совместимости",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s --mods "./mod" --output "./MyPatch"
  %(prog)s --mods "./mod" --output "./MyPatch" --name "Compatibility Patch"
  %(prog)s --auto-detect --list-conflicts
  %(prog)s --mods "./mod" --list-mods
        """
    )
    
    # Аргументы
    parser.add_argument(
        '-m', '--mods',
        help='Путь к папке модов'
    )
    parser.add_argument(
        '-o', '--output',
        help='Путь для сохранения патча'
    )
    parser.add_argument(
        '-n', '--name',
        default='AutoPatch',
        help='Имя патча (по умолчанию: AutoPatch)'
    )
    parser.add_argument(
        '--auto-detect',
        action='store_true',
        help='Автоопределение папки модов CK3'
    )
    parser.add_argument(
        '--game',
        choices=['ck3', 'eu4', 'hoi4', 'stellaris', 'vic3'],
        default='ck3',
        help='Игра для автоопределения (по умолчанию: ck3)'
    )
    parser.add_argument(
        '--strategy',
        choices=['smart', 'priority', 'base'],
        default='smart',
        help='Стратегия мержа (по умолчанию: smart)'
    )
    parser.add_argument(
        '--list-mods',
        action='store_true',
        help='Показать список найденных модов'
    )
    parser.add_argument(
        '--list-conflicts',
        action='store_true',
        help='Показать список конфликтов'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Подробный вывод'
    )
    
    args = parser.parse_args()
    
    # Определяем путь к модам
    mods_path = None
    if args.auto_detect:
        mods_path = get_paradox_mods_path(args.game)
        if mods_path:
            print(f"Автоопределён путь: {mods_path}")
        else:
            print("Ошибка: не удалось автоматически найти папку модов")
            return 1
    elif args.mods:
        mods_path = Path(args.mods)
        if not mods_path.exists():
            print(f"Ошибка: папка не существует: {mods_path}")
            return 1
    else:
        print("Ошибка: укажите --mods или --auto-detect")
        parser.print_help()
        return 1
        
    # Сканируем моды
    print(f"\nСканирование: {mods_path}")
    print("-" * 50)
    
    scanner = ModScanner(mods_path)
    result = scanner.scan_all()
    
    print(f"Найдено модов: {len(result.mods)}")
    print(f"Всего файлов: {result.total_files}")
    print(f"Конфликтов: {len(result.conflicts)}")
    
    # Список модов
    if args.list_mods:
        print("\n📦 Моды:")
        print("-" * 50)
        for mod in sorted(result.mods, key=lambda m: m.name.lower()):
            print(f"  • {mod.name}")
            if args.verbose:
                print(f"      Путь: {mod.path}")
                print(f"      Файлов: {len(mod.files)}")
                if mod.version:
                    print(f"      Версия: {mod.version}")
                    
    # Список конфликтов
    if args.list_conflicts:
        print("\n⚠️ Конфликты:")
        print("-" * 50)
        for conflict in result.conflicts:
            mod_names = ", ".join(m.name for m in conflict.mods[:3])
            if len(conflict.mods) > 3:
                mod_names += f" (+{len(conflict.mods) - 3})"
            print(f"  • {conflict.relative_path}")
            print(f"      Тип: {conflict.conflict_type}")
            print(f"      Моды: {mod_names}")
            
    # Генерация патча
    if args.output:
        if not result.conflicts:
            print("\nНет конфликтов - патч не нужен")
            return 0
            
        output_path = Path(args.output)
        
        # Стратегия мержа
        strategy_map = {
            'smart': MergeStrategy.SMART_MERGE,
            'priority': MergeStrategy.PRIORITY_WINS,
            'base': MergeStrategy.BASE_WINS
        }
        strategy = strategy_map.get(args.strategy, MergeStrategy.SMART_MERGE)
        
        print(f"\n🔧 Генерация патча...")
        print(f"   Имя: {args.name}")
        print(f"   Путь: {output_path}")
        print(f"   Стратегия: {args.strategy}")
        print("-" * 50)
        
        generator = PatchGenerator(output_path, args.name)
        patch_result = generator.generate_from_conflicts(result.conflicts, strategy)
        
        if patch_result.success:
            print(f"\n✅ Патч успешно создан!")
            print(f"   Смержено файлов: {patch_result.merged_count}")
            print(f"   Скопировано: {patch_result.copied_count}")
            print(f"   Путь: {patch_result.output_path}")
        else:
            print(f"\n❌ Ошибки при создании патча:")
            for error in patch_result.errors:
                print(f"   • {error}")
            return 1
            
    return 0


if __name__ == "__main__":
    sys.exit(main())
