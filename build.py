#!/usr/bin/env python3
"""
Build script for Paradox Mod Patcher
Скрипт сборки exe файла

Использование:
    python build.py           - обычная сборка
    python build.py --onefile - сборка в один файл
    python build.py --clean   - очистка перед сборкой
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def clean():
    """Очистка директорий сборки"""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    
    for d in dirs_to_clean:
        if Path(d).exists():
            print(f"Удаление {d}...")
            shutil.rmtree(d)
            
    # Очистка __pycache__ в src
    for pycache in Path('src').rglob('__pycache__'):
        shutil.rmtree(pycache)
        
    print("Очистка завершена")


def build(onefile=False):
    """Сборка приложения"""
    print("=" * 50)
    print("Paradox Mod Patcher - Build")
    print("=" * 50)
    
    # Проверяем PyInstaller
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("PyInstaller не установлен!")
        print("Установите: pip install pyinstaller")
        return False
        
    # Команда сборки
    cmd = ['pyinstaller']
    
    if onefile:
        cmd.extend([
            '--onefile',
            '--windowed',
            '--name', 'ParadoxModPatcher',
            '--add-data', 'src/core;core',
            '--add-data', 'src/gui;gui',
            '--add-data', 'src/utils;utils',
            'src/main.py'
        ])
    else:
        cmd.append('build.spec')
        
    print(f"Команда: {' '.join(cmd)}")
    print()
    
    # Запускаем сборку
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print()
        print("=" * 50)
        print("Сборка успешна!")
        print(f"Результат: dist/ParadoxModPatcher/")
        print("=" * 50)
        return True
    else:
        print()
        print("Ошибка сборки!")
        return False


def main():
    os.chdir(Path(__file__).parent)
    
    if '--clean' in sys.argv:
        clean()
        if len(sys.argv) == 2:
            return
            
    onefile = '--onefile' in sys.argv
    build(onefile)


if __name__ == "__main__":
    main()
