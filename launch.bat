@echo off
pushd %~dp0
echo Запуск виртуального окружения...
call .venv\Scripts\activate

echo Запуск бэкенда...
start cmd /k "uvicorn backend.main:app --host 127.0.0.1 --port 19015"

echo Запуск фронтенда...
cd frontend
start cmd /k "npm start"

popd
exit
