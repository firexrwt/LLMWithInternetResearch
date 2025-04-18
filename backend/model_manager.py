import os
import time
import platformdirs
from typing import List, Dict
from huggingface_hub import HfApi, hf_hub_download, ModelInfo  # Добавил ModelInfo для аннотации
import re

APP_NAME = "NeuraBox"
APP_AUTHOR = "NeuraBoxTeam"


USER_DATA_DIR = platformdirs.user_data_dir(APP_NAME, APP_AUTHOR)


class ModelManager:
    MODELS_DIR = os.path.join(USER_DATA_DIR, "models")
    CACHE_TIME = 1800  # 30 минут кеширования

    def __init__(self, hf_token: str | None = None):  # Добавил аннотацию типа
        self.hf_token = hf_token  # <--- ДОБАВЛЕНА ЭТА СТРОКА
        self.api = HfApi(token=self.hf_token) if self.hf_token else HfApi()  # Можно использовать self.hf_token
        self.cache: Dict = {"models": [], "last_update": 0}  # Добавил аннотацию типа
        self.ensure_models_dir()

    def ensure_models_dir(self):
        # Создаем папку MODELS_DIR (e.g., %APPDATA%\NeuraBox\models), если ее нет
        try:
            os.makedirs(self.MODELS_DIR, exist_ok=True)
        except OSError as e:
            print(f"Ошибка создания папки моделей {self.MODELS_DIR}: {e}")
            raise  # Передаем ошибку дальше

    def get_model_path(self, model_name: str) -> str | None:  # Может вернуть None, если файла нет
        available_models = self.get_available_models()
        model_info = next((m for m in available_models if m["name"] == model_name), None)

        # Важно: get_available_models может вернуть модели без repo_id (локальные)
        # И file_name может быть разным для локальных и HF моделей
        # Надо искать по имени и брать file_name из найденного объекта

        if not model_info:
            # Если не нашли в кеше/HF, проверим еще раз локально на всякий случай
            local_path_direct = os.path.join(self.MODELS_DIR, model_name)  # Если имя == имя файла
            if os.path.exists(local_path_direct) and model_name.endswith(".gguf"):
                return local_path_direct
            # Попробуем найти по имени репозитория, если передали его
            parts = model_name.split('/')
            if len(parts) == 2:  # Похоже на repo_id
                guessed_filename = self.get_gguf_filename(model_name)
                if guessed_filename:
                    local_path_repo = os.path.join(self.MODELS_DIR, guessed_filename)
                    if os.path.exists(local_path_repo):
                        return local_path_repo

            # Если ничего не найдено
            print(f"Модель {model_name} не найдена в {self.MODELS_DIR} или в кеше Hugging Face.")
            return None  # Возвращаем None, если путь не найден

        # Используем file_name из найденного model_info
        local_path = os.path.join(self.MODELS_DIR, model_info["file_name"])
        # Проверяем существование файла перед возвратом пути
        if os.path.exists(local_path):
            return local_path
        else:
            # Если в кеше модель есть, но файла нет (например, удалили вручную)
            print(f"Файл {model_info['file_name']} для модели {model_name} не найден в {self.MODELS_DIR}.")
            return None  # Возвращаем None

    def get_available_models(self) -> List[Dict]:
        current_time = time.time()
        models_output: List[Dict] = []  # Используем новый список для вывода

        # Проверяем кеш
        if self.cache["models"] and (current_time - self.cache["last_update"] < self.CACHE_TIME):
            print(f"Возвращаем кешированные модели ({len(self.cache['models'])} шт.)")
            # Перед возвратом кеша проверим актуальность поля 'installed'
            for model in self.cache["models"]:
                if model.get("file_name"):  # Проверяем только если есть имя файла
                    local_path = os.path.join(self.MODELS_DIR, model["file_name"])
                    model["installed"] = os.path.exists(local_path)
            return self.cache["models"]

        print("Обновление списка моделей...")
        # Используем set для отслеживания добавленных репозиториев/файлов, чтобы избежать дубликатов
        added_identifiers = set()

        # 1. Локальные модели
        try:
            for file in os.listdir(self.MODELS_DIR):
                if file.endswith(".gguf"):
                    # Проверяем, не добавляли ли уже модель с таким именем файла
                    if file not in added_identifiers:
                        metadata = self.get_model_metadata(file)
                        models_output.append({
                            "name": file,  # Имя = имя файла для локальных
                            "repo_id": None,  # Нет repo_id для чисто локальных
                            "file_name": file,
                            "installed": True,
                            **metadata
                        })
                        added_identifiers.add(file)
        except Exception as e:
            print(f"Ошибка чтения локальных моделей: {e}")

        # 2. Модели с Hugging Face
        try:
            # Ищем модели с тегом 'gguf'
            hf_models_iterator = self.api.list_models(
                filter="gguf",
                sort="downloads",
                direction=-1,
                limit=50  # Увеличим лимит для большего выбора
            )
            print("Запрос моделей с Hugging Face...")
            count = 0
            for model in hf_models_iterator:
                count += 1
                # Проверяем, не обрабатывали ли уже этот repo_id
                if model.id in added_identifiers:
                    continue

                try:
                    print(f"Обработка HF модели: {model.id}")
                    # Получаем информацию о модели (может быть медленно для многих моделей)
                    model_info: ModelInfo = self.api.model_info(model.id)
                    # Ищем GGUF файл в репозитории
                    file_name = self.get_gguf_filename(model.id)

                    if file_name:
                        # Проверяем, не добавляли ли модель с таким же именем файла (из локальных)
                        if file_name not in added_identifiers:
                            metadata = self.get_hf_model_metadata(model_info, file_name)
                            local_path = os.path.join(self.MODELS_DIR, file_name)
                            models_output.append({
                                "name": model.id,  # Имя = repo_id для HF моделей
                                "repo_id": model.id,
                                "file_name": file_name,
                                "installed": os.path.exists(local_path),
                                **metadata
                            })
                            added_identifiers.add(model.id)  # Добавляем repo_id
                            added_identifiers.add(file_name)  # Добавляем и имя файла
                        else:
                            print(f"Модель с файлом {file_name} ({model.id}) уже добавлена из локальных.")
                    else:
                        print(f"Не найден GGUF файл для {model.id}")

                except Exception as e:
                    # Логируем ошибку, но продолжаем обработку других моделей
                    print(f"Ошибка обработки репозитория {model.id}: {e}")
                    continue  # Переходим к следующей модели
            print(f"Обработано {count} моделей с Hugging Face.")
        except Exception as e:
            print(f"Критическая ошибка при получении списка моделей из Hugging Face: {e}")
            # В случае ошибки HF, вернем хотя бы локальные модели
            if not models_output:  # Если и локальных нет, возвращаем пустой список
                print("Не удалось получить модели ни локально, ни с HF.")
                return []

        # Обновляем кеш
        self.cache["models"] = models_output
        self.cache["last_update"] = current_time
        print(f"Список моделей обновлен. Всего: {len(models_output)} моделей.")
        return models_output

    def get_gguf_filename(self, repo_id: str) -> str | None:  # Может вернуть None
        try:
            files = self.api.list_repo_files(repo_id, repo_type="model")  # Уточняем тип репозитория
            # Ищем файлы .gguf, отдаем предпочтение большим файлам или файлам с квантованием Q4_K_M/Q5_K_M
            gguf_files = [f for f in files if f.endswith(".gguf")]
            if not gguf_files:
                return None

            # Приоритеты квантования (можно настроить)
            preferred_quants = ["Q5_K_M", "Q4_K_M", "Q8_0"]
            for quant in preferred_quants:
                for f in gguf_files:
                    if quant in f.upper():
                        return f

            # Если не нашли предпочтительные, возвращаем первый попавшийся
            return gguf_files[0]

        except Exception as e:
            print(f"Ошибка при поиске файлов в {repo_id}: {e}")
            return None

    def get_file_size(self, repo_id: str | None, file_name: str) -> str:
        local_path = os.path.join(self.MODELS_DIR, file_name)
        if os.path.exists(local_path):
            try:
                size_bytes = os.path.getsize(local_path)
                if size_bytes > 1024 * 1024 * 1024:  # GB
                    return f"{size_bytes / (1024 ** 3):.2f} GB"
                else:  # MB
                    return f"{size_bytes / (1024 ** 2):.1f} MB"
            except Exception as e:
                print(f"Ошибка получения размера локального файла {local_path}: {e}")
                return "Error"

        # Если файла нет локально и есть repo_id, пытаемся получить размер с HF
        if repo_id:
            try:
                # Получаем информацию о файле без скачивания
                file_url = self.api.hf_hub_url(repo_id=repo_id, filename=file_name)
                response = self.api.session.head(file_url, timeout=10)  # HEAD запрос для заголовков
                response.raise_for_status()
                size_bytes = int(response.headers.get("Content-Length", 0))
                if size_bytes > 1024 * 1024 * 1024:  # GB
                    return f"{size_bytes / (1024 ** 3):.2f} GB"
                elif size_bytes > 0:  # MB
                    return f"{size_bytes / (1024 ** 2):.1f} MB"
                else:
                    return "Unknown Size"
            except Exception as e:
                print(f"Ошибка получения размера файла {file_name} с HF для {repo_id}: {e}")
                return "N/A"  # Not Available
        else:
            # Если файла нет локально и нет repo_id (чисто локальная модель была удалена?)
            return "Not Found"

    def get_model_metadata(self, file_name: str) -> Dict:
        # Пытаемся извлечь параметры из имени файла
        param_match = re.search(r"(\d+(\.\d+)?[Bb])", file_name)  # Ищем числа типа 7b, 13b, 8.5b
        parameters = param_match.group(1).upper() if param_match else "?"

        # Определяем тип по ключевым словам
        type_guess = "Text"
        lower_name = file_name.lower()
        if "vision" in lower_name or "image" in lower_name:
            type_guess = "Vision"
        elif "instruct" in lower_name or "chat" in lower_name:
            type_guess = "Instruct"  # Добавим тип Instruct/Chat
        elif "video" in lower_name:
            type_guess = "Video"
        elif "multimodal" in lower_name:
            type_guess = "Multimodal"

        # Размер файла (только локальный путь, т.к. нет repo_id)
        size = self.get_file_size(None, file_name)

        return {"parameters": parameters, "type": type_guess, "size": size}

    def get_hf_model_metadata(self, model_info: ModelInfo, file_name: str) -> Dict:
        # Параметры
        parameters = "?"
        try:  # Обернем в try-except на случай отсутствия полей
            # Сначала из cardData (часто более точные)
            if model_info.cardData and isinstance(model_info.cardData, dict):
                if model_info.cardData.get('model_metadata', {}).get('inference', {}).get('parameters', {}).get(
                        'count'):
                    count = model_info.cardData['model_metadata']['inference']['parameters']['count']
                    if count > 1_000_000_000:
                        parameters = f"{count / 1_000_000_000:.1f}B"
                    elif count > 1_000_000:
                        parameters = f"{count / 1_000_000:.0f}M"
                elif model_info.cardData.get('model-index', [{}])[0].get('results', [{}])[0].get('model_details',
                                                                                                 {}).get('Parameters'):
                    params_str = model_info.cardData['model-index'][0]['results'][0]['model_details']['Parameters']
                    param_match = re.search(r"(\d+(\.\d+)?)\s*(B|M)", str(params_str), re.IGNORECASE)
                    if param_match: parameters = param_match.group(1) + param_match.group(3).upper()

            # Потом из config.json
            if parameters == "?" and model_info.config:
                if model_info.config.get("num_parameters"):  # Иногда есть прямо числом
                    count = model_info.config["num_parameters"]
                    if count > 1_000_000_000:
                        parameters = f"{count / 1_000_000_000:.1f}B"
                    elif count > 1_000_000:
                        parameters = f"{count / 1_000_000:.0f}M"
                elif model_info.config.get("hidden_size") and model_info.config.get("num_hidden_layers"):
                    # Очень грубая оценка для трансформеров, если нет явного числа
                    # Не стоит на нее сильно полагаться
                    pass  # Пока уберем оценку, т.к. она неточная

            # Если все еще неизвестно, пробуем из имени репозитория
            if parameters == "?":
                param_match = re.search(r"(\d+(\.\d+)?[Bb])", model_info.id)  # Ищем в repo_id
                if param_match: parameters = param_match.group(1).upper()

        except Exception as e:
            print(f"Ошибка извлечения параметров для {model_info.id}: {e}")
            parameters = "?"

        # Тип модели
        model_type = "Text"  # По умолчанию
        try:
            if model_info.pipeline_tag:
                pipeline = model_info.pipeline_tag.lower()
                if "text-generation" in pipeline or "conversational" in pipeline:
                    model_type = "Instruct" if "instruct" in model_info.id.lower() or "chat" in model_info.id.lower() else "Text"
                elif "text-classification" in pipeline or "fill-mask" in pipeline or "summarization" in pipeline:
                    model_type = "Text"
                elif "image" in pipeline or "vision" in pipeline or "depth-estimation" in pipeline:
                    model_type = "Vision"
                elif "audio" in pipeline:
                    model_type = "Audio"
                elif "video" in pipeline:
                    model_type = "Video"
                elif "multimodal" in pipeline:
                    model_type = "Multimodal"
            elif "vision" in model_info.id.lower() or "image" in model_info.id.lower():
                model_type = "Vision"
            elif "instruct" in model_info.id.lower() or "chat" in model_info.id.lower():
                model_type = "Instruct"
            elif "video" in model_info.id.lower():
                model_type = "Video"
            elif "multimodal" in model_info.id.lower():
                model_type = "Multimodal"
        except Exception as e:
            print(f"Ошибка определения типа для {model_info.id}: {e}")
            model_type = "?"

        # Размер файла
        size = self.get_file_size(model_info.id, file_name)

        return {
            "parameters": parameters,
            "type": model_type,
            "size": size
        }

    def download_model(self, model_repo_id: str) -> str:  # Принимаем repo_id
        # Получаем актуальную информацию о модели с HF
        try:
            model_info: ModelInfo = self.api.model_info(model_repo_id)
            file_name = self.get_gguf_filename(model_repo_id)

            if not file_name:
                raise ValueError(f"Не найден GGUF файл в репозитории {model_repo_id}.")

            local_path = os.path.join(self.MODELS_DIR, file_name)

            if os.path.exists(local_path):
                print(f"Модель {model_repo_id} (файл {file_name}) уже загружена в {self.MODELS_DIR}.")
                # Обновим статус в кеше, если модель есть в кеше
                for model in self.cache["models"]:
                    if model.get("repo_id") == model_repo_id or model.get("file_name") == file_name:
                        model["installed"] = True
                return local_path

            print(f"Скачивание файла {file_name} из репозитория {model_repo_id} в {self.MODELS_DIR}...")
            # Убедимся, что директория существует
            self.ensure_models_dir()

            # Скачиваем файл напрямую в нужную директорию
            downloaded_path = hf_hub_download(
                repo_id=model_repo_id,
                filename=file_name,
                local_dir=self.MODELS_DIR,
                local_dir_use_symlinks=False  # Важно: скачивать напрямую, а не симлинки
            )

            # Проверяем, совпадает ли скачанный путь с ожидаемым
            if downloaded_path != local_path:
                print(f"Предупреждение: Файл скачан в {downloaded_path}, ожидался {local_path}")
                # Попытка переименовать/переместить, если возможно
                # Но hf_hub_download с local_dir должен скачивать правильно
                # Возможно, стоит проверить права доступа?

            print(f"Модель {model_repo_id} (файл {file_name}) успешно загружена в {downloaded_path}.")

            # Обновим статус в кеше
            self.cache["last_update"] = 0  # Сбросим кеш при следующем запросе списка

            return downloaded_path  # Возвращаем фактический путь

        except Exception as e:
            print(f"Ошибка при загрузке модели {model_repo_id}: {e}")
            # Попробуем удалить частично скачанный файл, если он есть
            try:
                potential_incomplete_path = os.path.join(self.MODELS_DIR, file_name + ".incomplete")  # Или .download
                if file_name and os.path.exists(potential_incomplete_path):
                    os.remove(potential_incomplete_path)
                    print(f"Удален частично скачанный файл: {potential_incomplete_path}")
                elif file_name and os.path.exists(local_path):  # Если скачался, но была другая ошибка
                    # Не удаляем, если файл целый, но была ошибка API например
                    pass
            except OSError as remove_err:
                print(f"Ошибка при удалении неполного файла: {remove_err}")
            raise  # Передаем исходную ошибку дальше


# --- Можно добавить метод для удаления ---
def delete_model(self, file_name_to_delete: str) -> bool:
    """Удаляет локальный файл модели и обновляет кеш."""
    local_path = os.path.join(self.MODELS_DIR, file_name_to_delete)
    if os.path.exists(local_path):
        try:
            os.remove(local_path)
            print(f"Файл модели {file_name_to_delete} удален.")
            # Обновляем статус 'installed' в кеше
            for model in self.cache["models"]:
                if model.get("file_name") == file_name_to_delete:
                    model["installed"] = False
                    break  # Нашли и обновили, выходим
            return True
        except OSError as e:
            print(f"Ошибка при удалении файла {local_path}: {e}")
            return False
    else:
        print(f"Файл {file_name_to_delete} не найден для удаления.")
        # На всякий случай обновим кеш, если там статус был неверный
        for model in self.cache["models"]:
            if model.get("file_name") == file_name_to_delete:
                model["installed"] = False
                break
        return False