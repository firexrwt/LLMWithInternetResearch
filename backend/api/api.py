import os
from fastapi import APIRouter, HTTPException
from backend.model_manager import ModelManager
from llama_cpp import Llama
import logging
from pydantic import BaseModel

#Тела запросов
class ModelRequestBody(BaseModel):
    model: str

class MessageRequestBody(BaseModel):
    message: str

class QueryRequestBody(BaseModel):
    text: str
    model: str = "Mistral-7B-Instruct"
    use_internet: bool = False

logger = logging.getLogger(__name__)
router = APIRouter()
model_manager = ModelManager()
llm_instance = None  # Глобальная переменная для текущей модели

@router.get("/models")
async def list_available_models():          # Получает список доступных моделей с Hugging Face. Для каждой модели добавляем флаг installed: True, если локальный файл существует.
    
    try:
        models = model_manager.get_available_models()
        for model in models:
            local_path = os.path.join(model_manager.MODELS_DIR, model["file_name"])
            model["installed"] = os.path.exists(local_path)
        return models
    except Exception as e:
        logger.error(f"Ошибка при получении моделей: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при получении списка моделей.")

@router.post("/install_model")
async def install_model(request: ModelRequestBody):         # Загружает модель, если она ещё не установлена.
    try:
        local_path = model_manager.download_model(request.model)
        return {"message": f"Модель {request.model} установлена", "local_path": local_path}
    except Exception as e:
        logger.error(f"Ошибка установки модели: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка установки модели: {str(e)}")

@router.post("/load_model")
async def switch_model(request: ModelRequestBody):          # Переключает текущую модель.
    global llm_instance
    try:
        model_path = model_manager.get_model_path(request.model)
        logger.info(f"Загружаем модель: {request.model}")
        llm_instance = Llama(model_path=model_path, n_ctx=2048, n_threads=8)
        return {"message": f"Модель {request.model} загружена"}
    except Exception as e:
        logger.error(f"Ошибка загрузки модели: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки модели: {str(e)}")

@router.post("/summarize_chat_title")
async def summarize_chat_title(request: MessageRequestBody):        # Генерирует краткое название чата (3-4 слова) на основе первого сообщения.
    global llm_instance
    if not llm_instance:
        raise HTTPException(status_code=500, detail="Модель не загружена")

    try:
        prompt = f"Summarize the following message in 3-4 words:\n\n{request.message}\n\nSummary:"
        response = llm_instance(prompt, max_tokens=10, temperature=0.5, echo=False)

        summary = response["choices"][0]["text"].strip()
        if not summary:
            summary = "Untitled Chat"

        return {"title": summary}
    except Exception as e:
        logger.error(f"Ошибка генерации заголовка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

#TODO: Сделать учет выбранной модели.
#FIXME: Избавится от ошибки при отправки сообщения (думаю это решится, как сделаем TODO)
@router.post("/query")
async def process_query(request: ModelRequestBody):         # Обрабатывает запрос пользователя через LLaMA. Если текущая модель не совпадает с выбранной, происходит переключение.
    global llm_instance
    if not llm_instance:
        raise HTTPException(status_code=500, detail="Модель не загружена")

    try:
        response = llm_instance(
            request.text,
            max_tokens=512,
            temperature=0.7,
            top_p=0.9,
            echo=False,
            stop=["\n", "###"]
        )

        return {
            "response": response["choices"][0]["text"].strip(),
            "model": request.model,
            "tokens_used": response["usage"]["total_tokens"]
        }

    except Exception as e:
        logger.error(f"Ошибка обработки запроса: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
