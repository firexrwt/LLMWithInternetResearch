import os
import logging
import torch
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.model_manager import ModelManager
from llama_cpp import Llama
from collections import deque
from typing import Dict, Optional
import uuid

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаём API-роутер
router = APIRouter()

# Менеджер моделей и глобальная переменная для текущей модели
model_manager = ModelManager()
llm_instance = None
conversation_histories: Dict[str, deque] = {}  # Словарь для хранения истории каждого чата

# Глобальные настройки модели по умолчанию
global_model_settings = {
    "max_tokens": 512,
    "temperature": 0.7,
    "top_p": 0.9
}


# Определяем параметры GPU
def get_gpu_layers():
    if torch.cuda.is_available():
        logger.info(f"CUDA доступна. Используем устройство: {torch.cuda.get_device_name(0)}")
        gpu_memory = torch.cuda.get_device_properties(0).total_memory // (1024 ** 2)  # Видеопамять в MB
        if gpu_memory >= 24000:  # Если 24ГБ и больше (например, RTX 3090, 4090)
            return 60
        elif gpu_memory >= 12000:  # Если 12ГБ (например, RTX 3060, 4070)
            return 35
        elif gpu_memory >= 8000:  # Если 8ГБ (например, RTX 2060, 3070, 4060)
            return 20
        else:
            return 10  # Если видеопамяти мало, используем меньше слоев на GPU
    logger.error("CUDA не доступна. Будет использован процессор.")
    return 0  # Если GPU нет, работаем только на CPU


# Классы для валидации запросов
class ModelRequestBody(BaseModel):
    model: str  # Название модели для загрузки


class ModelSettingsRequestBody(BaseModel):
    max_tokens: int = Field(default=512, ge=1, le=4096, description="Максимальное количество токенов для генерации")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Температура сэмплирования")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="Порог вероятности для nucleus сэмплинга")


class QueryRequestBody(ModelSettingsRequestBody):
    text: str  # Текст запроса
    model: str  # Выбранная модель
    chat_id: Optional[str] = Field(default=None, description="Уникальный идентификатор чата")
    use_internet: bool = False  # Использовать ли веб-поиск (пока заглушка)


# Переключение на другую модель
def load_model(model_name: str):
    global llm_instance
    try:
        model_path = model_manager.get_model_path(model_name)
        gpu_layers = get_gpu_layers()
        logger.info(f"Загружаем модель: {model_name} с {gpu_layers} слоями на GPU")
        llm_instance = Llama(model_path=model_path, n_ctx=2048, n_threads=8, n_gpu_layers=gpu_layers, use_mmap=True,
                             use_mlock=True)
    except Exception as e:
        logger.error(f"Ошибка загрузки модели: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки модели: {str(e)}")


@router.get("/models")
async def list_available_models():
    try:
        # Получаем список локально установленных моделей
        local_models = {}
        if os.path.exists(model_manager.MODELS_DIR):
            for file_name in os.listdir(model_manager.MODELS_DIR):
                if file_name.endswith(".gguf") or file_name.endswith(".bin"):
                    local_models[file_name] = {"name": file_name, "installed": True}

        # Получаем список доступных моделей с Hugging Face
        models_from_hf = model_manager.get_available_models()

        # Проверяем, какие модели из HF уже установлены
        for model in models_from_hf:
            file_name = model["file_name"]
            if file_name in local_models:
                model["installed"] = True
                del local_models[file_name]  # Удаляем из локального списка, чтобы не дублировать

        # Объединяем оба списка
        all_models = models_from_hf + list(local_models.values())

        return all_models

    except Exception as e:
        logger.error(f"Ошибка при получении списка моделей: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при получении моделей.")


@router.post("/install_model")
async def install_model(request: ModelRequestBody):
    try:
        local_path = model_manager.download_model(request.model)
        return {"message": f"Модель {request.model} установлена", "local_path": local_path}
    except Exception as e:
        logger.error(f"Ошибка установки модели: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка установки модели: {str(e)}")


@router.post("/update_model_settings")
async def update_model_settings(request: ModelSettingsRequestBody):
    """
    Обновление глобальных настроек модели

    :param request: ModelSettingsRequestBody с настраиваемыми параметрами
    :return: Подтверждение обновления настроек
    """
    global global_model_settings
    try:
        global_model_settings.update({
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p
        })
        logger.info(f"Обновлены настройки модели: {global_model_settings}")
        return {
            "message": "Настройки модели обновлены",
            "settings": global_model_settings
        }
    except Exception as e:
        logger.error(f"Ошибка обновления настроек: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка обновления настроек.")


@router.post("/query")
async def process_query(request: QueryRequestBody):
    global llm_instance, global_model_settings, conversation_histories

    logger.info(f"Получен запрос: {request}")
    logger.info(f"Данные запроса: {request.dict()}")
    logger.info(f"Выбранная модель: {request.model}")

    chat_id = request.chat_id  # Получаем ID чата из запроса

    try:
        if not llm_instance or llm_instance.model_path != model_manager.get_model_path(request.model):
            logger.info(f"Модель {request.model} не загружена. Загружаем...")
            load_model(request.model)
            logger.info(f"Модель {request.model} загружена!")

        max_tokens = request.max_tokens or global_model_settings["max_tokens"]
        temperature = request.temperature or global_model_settings["temperature"]
        top_p = request.top_p or global_model_settings["top_p"]

        user_text = request.text.strip()

        # Получаем историю для конкретного чата или создаем новую, если ее нет
        if chat_id is None:
            logger.info("chat_id не предоставлен клиентом, генерируем новый")
            chat_id = str(uuid.uuid4())  # Генерируем новый chat_id, если он не предоставлен

        if chat_id not in conversation_histories:
            logger.info(f"История для chat_id: {chat_id} не найдена, создаем новую")
            conversation_history = deque(maxlen=20)  # Создаем новую историю
            conversation_histories[chat_id] = conversation_history  # Сохраняем новую историю
        else:
            logger.info(f"История для chat_id: {chat_id} найдена")
            conversation_history = conversation_histories[chat_id]  # Получаем существующую историю

        # Добавляем текущее сообщение в историю
        conversation_history.append(f"User: {user_text}")
        conversation_histories[chat_id] = conversation_history  # Обновляем историю в словаре

        # Формируем полный контекст для модели
        history_text = "\n".join(conversation_history)
        prompt = f"""
                You are a helpful AI assistant.
                Keep the conversation context.
                You must answer in the same language as the user's question.
                Do not repeat the question. Answer in a complete sentence with useful information.
                
                Conversation context:
                {history_text}

                Assistant:"""

        logger.info(f"Отправляем промпт в модель:\n{prompt}")

        response = llm_instance(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            echo=False,
            stop=["\n\n", "User:", "Assistant:"]
        )

        model_response = response["choices"][0]["text"].strip()
        logger.info(f"Ответ модели: {model_response}")

        # Добавляем ответ модели в историю
        conversation_history.append(f"Assistant: {model_response}")
        conversation_histories[chat_id] = conversation_history  # Обновляем историю в словаре

        if not model_response:
            model_response = "I couldn't generate a response."

        return {
            "response": model_response,
            "model": request.model,
            "tokens_used": response["usage"]["total_tokens"],
            "settings_used": {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p
            }
        }

    except Exception as e:
        logger.error(f"Ошибка обработки запроса: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))