import os
import time
from typing import List, Dict
from huggingface_hub import HfApi

MODELS_DIR = "models"
CACHE_TIME = 1800  # 30 минут кеширования
api = HfApi()
cache = {"models": [], "last_update": 0}

class ModelManager:
    def __init__(self):
        self.ensure_models_dir()

    def ensure_models_dir(self):
        global MODELS_DIR  # Явно указываем, что это глобальная переменная
        os.makedirs(MODELS_DIR, exist_ok=True)

    def get_available_models(self) -> List[Dict]:
        current_time = time.time()
        if cache["models"] and (current_time - cache["last_update"] < CACHE_TIME):
            return cache["models"]  # Если кеш свежий, возвращаем его

        try:
            models = api.list_models(filter="gguf", limit=20)  # Запрашиваем ТОЛЬКО GGUF модели
            available_models = [
                {
                    "name": model.id,
                    "repo_id": model.id,
                    "file_name": self.get_gguf_filename(model.id),
                }
                for model in models
            ]

            cache["models"] = available_models
            cache["last_update"] = current_time  # Обновляем кеш
            return available_models
        except Exception as e:
            print(f"Ошибка при получении моделей: {e}")
            return []

    def get_gguf_filename(self, repo_id: str) -> str:
        try:
            files = api.list_repo_files(repo_id)
            for file in files:
                if file.endswith(".gguf"):
                    return file
        except Exception as e:
            print(f"Ошибка при поиске файлов в {repo_id}: {e}")
        return ""

    def get_model_path(self, model_name: str) -> str:
        available_models = self.get_available_models()
        model_info = next((m for m in available_models if m["name"] == model_name), None)

        if not model_info:
            raise ValueError(f"Модель {model_name} не найдена на Hugging Face.")

        local_path = os.path.join(MODELS_DIR, model_info["file_name"])  # Используем глобальную переменную
        return local_path
