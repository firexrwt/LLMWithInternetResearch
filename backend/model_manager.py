import os
from huggingface_hub import hf_hub_download
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

MODELS_DIR = "models"


class ModelManager:
    def __init__(self):
        self.ensure_models_dir()

    def ensure_models_dir(self):
        os.makedirs(MODELS_DIR, exist_ok=True)

    def get_available_models(self) -> List[Dict]:
        return [
            {
                "name": "Mistral-7B-Instruct",
                "repo_id": "TheBloke/Mistral-7B-Instruct-v0.1-GGUF",
                "file_name": "mistral-7b-instruct-v0.1.Q4_K_M.gguf",
                "required_space": 4700000000  # ~4.7GB
            },
            {
                "name": "Llama-2-7B-Chat",
                "repo_id": "TheBloke/Llama-2-7B-Chat-GGUF",
                "file_name": "llama-2-7b-chat.Q4_K_M.gguf",
                "required_space": 3800000000  # ~3.8GB
            }
        ]

    def get_model_path(self, model_name: str) -> str:
        model_info = next((m for m in self.get_available_models() if m["name"] == model_name), None)
        if not model_info:
            raise ValueError(f"Модель {model_name} не найдена")

        local_path = os.path.join(MODELS_DIR, model_info["file_name"])
        if not os.path.exists(local_path):
            self.download_model(model_info)

        return local_path

    def download_model(self, model_info: Dict):
        logger.info(f"Начата загрузка модели {model_info['name']}...")
        try:
            hf_hub_download(
                repo_id=model_info["repo_id"],
                filename=model_info["file_name"],
                local_dir=MODELS_DIR,
                local_dir_use_symlinks=False,
                resume_download=True,
                token=os.getenv("HF_TOKEN"),
                cache_dir=MODELS_DIR
            )
            logger.info(f"Модель {model_info['name']} успешно загружена")
        except Exception as e:
            logger.error(f"Ошибка загрузки: {str(e)}")
            raise RuntimeError(f"Не удалось загрузить модель: {str(e)}")

    def check_model_installed(self, model_name: str) -> bool:
        try:
            path = self.get_model_path(model_name)
            return os.path.exists(path)
        except:
            return False