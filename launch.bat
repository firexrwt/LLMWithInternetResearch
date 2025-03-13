@echo off
cd /d "%~dp0"

:: Запускаем Uvicorn в фоне
start /B uvicorn backend.main:app --host 127.0.0.1 --port 9015

:: Переходим в папку фронтенда и запускаем его
cd frontend
npm start