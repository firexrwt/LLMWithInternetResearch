# backend.spec

# -*- mode: python ; coding: utf-8 -*-

import sys
# Добавим импорт для поиска пакетов
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

# Определяем базовую папку проекта (где лежит этот spec-файл)
# Это поможет PyInstaller найти скрипты и модули
a = Analysis(
    ['backend/main.py'], # Главный скрипт вашего FastAPI приложения
    pathex=['.'],        # Указываем PyInstaller искать модули в корневой папке проекта
    binaries=[
        # Пытаемся автоматически собрать динамические библиотеки (.dll) для llama_cpp
        *collect_dynamic_libs('llama_cpp'),
    ],
    datas=[
        # Сюда можно добавлять не-Python файлы, если они нужны вашему коду
        # или зависимостям во время выполнения. Например:
        # ('путь/к/данным/в/проекте', 'путь/внутри/пакета')
        # Пока оставляем пустым. НЕ добавляйте сюда .env, .db или папку models!
    ],
    hiddenimports=[
        # PyInstaller не всегда находит все импорты автоматически,
        # особенно для uvicorn/fastapi и библиотек типа llama_cpp_python.
        # Добавим стандартные для uvicorn и fastapi:
        'uvicorn.lifespan.on',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        # Если при запуске backend.exe будут ошибки 'ModuleNotFound',
        # нужно будет добавить сюда недостающие модули.
        # Например, могут понадобиться модули из 'llama_cpp', 'huggingface_hub',
        # 'fastapi.encoders', 'pydantic.v1', etc.
        # Попробуйте добавить явно модули вашего API:
        'backend.api.api',
        'backend.model_manager',
        # Если llama_cpp использует какие-то специфичные бэкенды, их тоже может понадобиться добавить.
        # Также соберем данные для некоторых часто проблемных пакетов:
        *collect_submodules('fastapi'),
        *collect_submodules('starlette'),
        *collect_submodules('pydantic'),
        *collect_submodules('huggingface_hub'),
        *collect_submodules('llama_cpp'),
    ],
    hookspath=[],        # Пути к дополнительным хукам PyInstaller (обычно не нужны)
    hooksconfig={},
    runtime_hooks=[],    # Скрипты, выполняемые перед запуском вашего кода
    excludes=[
        # Модули, которые точно не нужны (экономит место)
        'tkinter',
        'pytest',
        'unittest',
        # Добавьте другие ненужные модули, если знаете о них
    ],
    noarchive=False,     # Оставить как False
    optimize=0           # Оптимизация байт-кода (0=нет, 1, 2)
)

# Сбор данных (например, для FastAPI/Starlette могут понадобиться шаблоны, если вы их используете)
# datas += collect_data_files('fastapi') # Раскомментируйте, если используете стандартные шаблоны FastAPI/Starlette
# datas += collect_data_files('llama_cpp') # Возможно, llama_cpp нужны какие-то файлы данных

# Передаем обновленные datas в Analysis
# a.datas += datas # Если добавляли datas выше

pyz = PYZ(a.pure) # Создание архива с Python-модулями

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='backend',        # Имя выходного .exe файла (backend.exe)
    debug=False,           # Отладка (False для релиза)
    bootloader_ignore_signals=False,
    strip=False,           # Удалять ли символы из бинарных файлов (False лучше для совместимости)
    upx=False,             # Использовать ли UPX для сжатия (False надежнее)
    upx_exclude=[],
    runtime_tmpdir=None,   # Временная папка для onefile-сборок (пока не используем onefile)
    console=True,          # Показывать ли консольное окно (True для сервера полезно для логов)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,      # Архитектура (None = текущая)
    codesign_identity=None,# Подпись кода (для macOS/Windows)
    entitlements_file=None # Права (для macOS)
)

# Собираем все в одну папку (режим --onedir по умолчанию для spec)
# coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='backend') # Это для --onedir