import os
import time
from typing import List, Dict
from huggingface_hub import HfApi, hf_hub_download
import re


class ModelManager:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    MODELS_DIR = os.path.join(BASE_DIR, "models")
    CACHE_TIME = 1800  # 30 минут кеширования

    def __init__(self, hf_token=None):
        self.api = HfApi(token=hf_token) if hf_token else HfApi()
        self.cache = {"models": [], "last_update": 0}
        self.ensure_models_dir()

    def ensure_models_dir(self):
        os.makedirs(self.MODELS_DIR, exist_ok=True)

    def get_available_models(self) -> List[Dict]:
        current_time = time.time()

        if self.cache["models"] and (current_time - self.cache["last_update"] < self.CACHE_TIME):
            return self.cache["models"]

        # Локальные модели
        local_models = []
        for file in os.listdir(self.MODELS_DIR):
            if file.endswith(".gguf"):
                metadata = self.get_model_metadata(file)
                local_models.append({
                    "name": file,
                    "repo_id": None,
                    "file_name": file,
                    "installed": True,
                    **metadata
                })

        # Модели с Hugging Face
        hf_models_list = []
        try:
            hf_models = list(self.api.list_models(filter="gguf", sort="downloads", direction=-1, limit=20))
            print(f"HF Models fetched: {len(hf_models)} models")
            if not hf_models:
                print("Список моделей с Hugging Face пуст. Проверьте фильтр или токен.")
            for model in hf_models:
                try:
                    print(f"Processing model: {model.id}")
                    model_info = self.api.model_info(model.id)
                    file_name = self.get_gguf_filename(model.id)
                    if file_name:
                        metadata = self.get_hf_model_metadata(model_info, file_name)
                        hf_models_list.append({
                            "name": model.id,
                            "repo_id": model.id,
                            "file_name": file_name,
                            "installed": os.path.exists(os.path.join(self.MODELS_DIR, file_name)),
                            **metadata
                        })
                    else:
                        print(f"No GGUF file found for {model.id}")
                except Exception as e:
                    print(f"Ошибка обработки {model.id}: {e}")
                    continue
        except Exception as e:
            print(f"Ошибка при получении моделей из Hugging Face: {e}")

        all_models = local_models + hf_models_list
        self.cache["models"] = all_models
        self.cache["last_update"] = current_time
        print(f"Returning {len(all_models)} models: {all_models}")
        return all_models

    def get_gguf_filename(self, repo_id: str) -> str:
        try:
            files = self.api.list_repo_files(repo_id)
            if files is None:
                print(f"list_repo_files returned None for {repo_id}")
                return ""
            for file in files:
                if file.endswith(".gguf"):
                    return file
            print(f"No GGUF files in {repo_id}")
            return ""
        except Exception as e:
            print(f"Ошибка при поиске файлов в {repo_id}: {e}")
            return ""

    def get_file_size(self, repo_id: str, file_name: str) -> str:
        local_path = os.path.join(self.MODELS_DIR, file_name)
        if os.path.exists(local_path):
            size_mb = os.path.getsize(local_path) / (1024 ** 2)
            return f"{size_mb:.1f}MB"
        try:
            # Получаем размер файла с Hugging Face
            file_info = self.api.hf_hub_download(repo_id=repo_id, filename=file_name, dry_run=True)
            size_mb = file_info.size / (1024 ** 2) if file_info.size else 0
            return f"{size_mb:.1f}MB"
        except Exception as e:
            print(f"Ошибка получения размера файла {file_name} для {repo_id}: {e}")
            return "Unknown"

    def get_model_metadata(self, file_name: str) -> Dict:
        param_match = re.search(r"(\d+[bB])", file_name)
        parameters = param_match.group(0).upper() if param_match else "Unknown"
        type_guess = "Text"
        if "image" in file_name.lower() or "vision" in file_name.lower():
            type_guess = "Image"
        elif "multi" in file_name.lower():
            type_guess = "Multimodal"
        elif "video" in file_name.lower():
            type_guess = "Video"
        return {"parameters": parameters, "type": type_guess, "size": self.get_file_size("", file_name)}

    def get_hf_model_metadata(self, model_info, file_name: str) -> Dict:
        # Параметры
        parameters = "Unknown"
        if model_info.config and "num_parameters" in model_info.config:
            parameters = model_info.config["num_parameters"]
        elif model_info.card_data and "parameters" in model_info.card_data:
            parameters = model_info.card_data["parameters"]
        else:
            param_match = re.search(r"(\d+[bB])", model_info.id)
            parameters = param_match.group(0).upper() if param_match else "Unknown"

        # Тип по pipeline_tag
        model_type = "Text"  # По умолчанию
        if model_info.card_data and "pipeline_tag" in model_info.card_data:
            pipeline = model_info.card_data["pipeline_tag"].lower()
            if "text-generation" in pipeline or "text-classification" in pipeline:
                model_type = "Text"
            elif "image" in pipeline or "vision" in pipeline:
                model_type = "Image"
            elif "multimodal" in pipeline:
                model_type = "Multimodal"
            elif "video" in pipeline:
                model_type = "Video"
        elif model_info.card_data and "tags" in model_info.card_data:
            tags = [tag.lower() for tag in model_info.card_data["tags"]]
            if any(t in tags for t in ["image", "vision", "generative-image"]):
                model_type = "Image"
            elif "multimodal" in tags:
                model_type = "Multimodal"
            elif "video" in tags:
                model_type = "Video"
        elif "image" in model_info.id.lower() or "vision" in model_info.id.lower():
            model_type = "Image"
        elif "multi" in model_info.id.lower():
            model_type = "Multimodal"
        elif "video" in model_info.id.lower():
            model_type = "Video"

        return {
            "parameters": parameters,
            "type": model_type,
            "size": self.get_file_size(model_info.id, file_name)
        }