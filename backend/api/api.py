import os
import logging
import torch
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.model_manager import ModelManager
from llama_cpp import Llama

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаём API-роутер
router = APIRouter()

# Менеджер моделей и глобальная переменная для текущей модели
model_manager = ModelManager()
llm_instance = None


# Определяем параметры GPU
def get_gpu_layers():
    if torch.cuda.is_available():
        gpu_memory = torch.cuda.get_device_properties(0).total_memory // (1024 ** 2)  # Видеопамять в MB
        if gpu_memory >= 24576:  # Если 24ГБ и больше (например, RTX 3090, 4090)
            return 60
        elif gpu_memory >= 12288:  # Если 12ГБ (например, RTX 3060, 4070)
            return 35
        elif gpu_memory >= 8192:  # Если 8ГБ (например, RTX 2060, 3070, 4060)
            return 20
        else:
            return 10  # Если видеопамяти мало, используем меньше слоев на GPU
    return 0  # Если GPU нет, работаем только на CPU


# Классы для валидации запросов
class ModelRequestBody(BaseModel):
    model: str  # Название модели для загрузки


class QueryRequestBody(BaseModel):
    text: str  # Текст запроса
    model: str  # Выбранная модель
    use_internet: bool = False  # Использовать ли веб-поиск (пока заглушка)
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9


# Получение списка доступных моделей
@router.get("/models")
async def list_available_models():
    try:
        models = model_manager.get_available_models()
        for model in models:
            local_path = os.path.join(model_manager.MODELS_DIR, model["file_name"])
            model["installed"] = os.path.exists(local_path)
        return models
    except Exception as e:
        logger.error(f"Ошибка при получении списка моделей: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при получении моделей.")


# Установка модели (скачивание)
@router.post("/install_model")
async def install_model(request: ModelRequestBody):
    try:
        local_path = model_manager.download_model(request.model)
        return {"message": f"Модель {request.model} установлена", "local_path": local_path}
    except Exception as e:
        logger.error(f"Ошибка установки модели: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка установки модели: {str(e)}")


# Переключение на другую модель
def load_model(model_name: str):
    global llm_instance
    try:
        model_path = model_manager.get_model_path(model_name)
        gpu_layers = get_gpu_layers()
        logger.info(f"Загружаем модель: {model_name} с {gpu_layers} слоями на GPU")
        llm_instance = Llama(model_path=model_path, n_ctx=2048, n_threads=8, n_gpu_layers=gpu_layers)
    except Exception as e:
        logger.error(f"Ошибка загрузки модели: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки модели: {str(e)}")


# Запрос в модель
@router.post("/query")
async def process_query(request: QueryRequestBody):
    global llm_instance

    logger.info(f"Получен запрос: {request}")
    logger.info(f"Выбранная модель: {request.model}")

    try:
        if not llm_instance or llm_instance.model_path != model_manager.get_model_path(request.model):
            logger.info(f"Модель {request.model} не загружена. Загружаем...")
            load_model(request.model)
            logger.info(f"Модель {request.model} загружена!")

        user_text = request.text.strip()
        lang_instruction = """You must answer in the same language as the user's question.
        Do not repeat the question. Answer in a complete sentence with useful information."""
        prompt = f"""You are a helpful AI assistant.
        {lang_instruction}

        User: {user_text}
        Assistant:"""

        logger.info(f"Отправляем промпт в модель:\n{prompt}")

        response = llm_instance(
            prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            echo=False,
            stop=["\n\n", "User:", "Assistant:"]
        )

        model_response = response["choices"][0]["text"].strip()
        logger.info(f"Ответ модели: {model_response}")

        if not model_response:
            model_response = "I couldn't generate a response."

        return {
            "response": model_response,
            "model": request.model,
            "tokens_used": response["usage"]["total_tokens"]
        }

    except Exception as e:
        logger.error(f"Ошибка обработки запроса: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
