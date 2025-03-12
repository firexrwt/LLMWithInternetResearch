from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.model_manager import ModelManager
from llama_cpp import Llama
import asyncio
import logging
import os
import shutil
from fastapi.responses import StreamingResponse
from typing import List, Dict

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация роутера
router = APIRouter()

# Глобальные переменные
llm_instance = None
model_cache = {}
model_manager = ModelManager()

# Глобальная переменная для хранения истории диалога
dialog_history = []


class QueryRequest(BaseModel):
    text: str
    model: str = "Mistral-7B-Instruct"
    use_internet: bool = False
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9


class ModelInfo(BaseModel):
    name: str
    status: str
    size: int


def check_disk_space(model_path: str):
    """Проверяет, достаточно ли места для загрузки модели"""
    total, used, free = shutil.disk_usage(os.path.dirname(model_path))
    model_size = os.path.getsize(model_path)
    if free < model_size:
        raise HTTPException(
            status_code=500,
            detail=f"Not enough disk space. Required: {model_size}, Available: {free}"
        )


async def load_model_async(model_name: str):
    """Асинхронная загрузка модели"""
    global llm_instance
    if model_name in model_cache:
        llm_instance = model_cache[model_name]
        return

    try:
        model_path = model_manager.get_model_path(model_name)
        check_disk_space(model_path)
        logger.info(f"Loading model: {model_name}")
        loop = asyncio.get_event_loop()
        llm_instance = await loop.run_in_executor(
            None,
            lambda: Llama(model_path=model_path, n_ctx=2048, n_threads=8)
        )
        model_cache[model_name] = llm_instance
    except Exception as e:
        logger.error(f"Failed to load model: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading model: {str(e)}")


def add_to_history(user_message: str, model_response: str):
    """Добавляет сообщение и ответ в историю"""
    global dialog_history
    dialog_history.append({"role": "user", "content": user_message})
    dialog_history.append({"role": "assistant", "content": model_response})


def format_history(history: List[Dict], max_tokens: int = 512) -> str:
    """Форматирует историю диалога в строку"""
    formatted_history = []
    token_count = 0

    # Идем с конца истории, чтобы сохранить последние сообщения
    for message in reversed(history):
        content = f"{message['role'].capitalize()}: {message['content']}"
        token_count += len(content.split())  # Примерный подсчет токенов

        if token_count > max_tokens:
            break

        formatted_history.append(content)

    # Возвращаем историю в правильном порядке
    return "\n".join(reversed(formatted_history))


@router.get("/models", response_model=list[ModelInfo])
async def list_available_models():
    """Получает список доступных моделей"""
    try:
        models = model_manager.get_available_models()
        return [{"name": m["name"], "status": "Available", "size": 0} for m in models]
    except Exception as e:
        logger.error(f"Error retrieving models: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving models")


@router.post("/load_model")
async def switch_model(model_name: str):
    """Переключает текущую модель"""
    global llm_instance
    try:
        await load_model_async(model_name)
        return {"message": f"Model switched to {model_name}"}
    except HTTPException as e:
        raise e


@router.post("/query")
async def process_query(request: QueryRequest):
    """Обрабатывает пользовательский запрос через LLaMA"""
    global llm_instance, dialog_history

    if not llm_instance:
        raise HTTPException(status_code=500, detail="Model not initialized")

    try:
        # Загружаем модель, если она отличается
        if llm_instance.model_path != model_manager.get_model_path(request.model):
            await load_model_async(request.model)

        # Форматируем историю диалога
        history = format_history(dialog_history, max_tokens=512)

        # Форматируем промпт
        instruction = "Answer the question based on the context and dialog history."
        context = await get_context(request.text) if request.use_internet else ""

        prompt = f"""
        ### System: You are an expert AI assistant.
        ### Instruction: {instruction}
        ### Context: {context}
        ### Dialog History:
        {history}
        ### Question: {request.text}
        ### Response:
        """

        # Генерация ответа
        response = llm_instance(
            prompt.strip(),  # Убираем лишние переносы
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            stop=["###", "<|endoftext|>"],
            repeat_penalty=1.2
        )

        # Извлекаем только ответ
        full_response = response["choices"][0]["text"]
        clean_response = full_response.split("### Response:")[-1].strip()

        # Добавляем запрос и ответ в историю
        add_to_history(request.text, clean_response)

        return {
            "response": clean_response,
            "model": request.model,
            "tokens_used": response["usage"]["total_tokens"]
        }

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream_query")
async def stream_query(request: QueryRequest):
    """Потоковая передача ответа"""
    global llm_instance

    if not llm_instance:
        raise HTTPException(status_code=500, detail="Model not initialized")

    async def generate():
        for chunk in llm_instance(
                request.text,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                stream=True,
        ):
            yield chunk["choices"][0]["text"]

    return StreamingResponse(generate(), media_type="text/plain")


@router.get("/model_status")
async def get_model_status():
    """Возвращает статус текущей модели"""
    global llm_instance
    if not llm_instance:
        return {"status": "No model loaded"}
    return {
        "status": "Model loaded",
        "model_name": os.path.basename(llm_instance.model_path),
        "context_size": llm_instance.n_ctx,
    }


@router.post("/clear_history")
async def clear_history():
    """Очищает историю диалога"""
    global dialog_history
    dialog_history = []
    return {"message": "Dialog history cleared"}


async def get_context(query: str) -> str:
    """Получает контекст из интернета (заглушка)"""
    # Здесь можно добавить логику для поиска в интернете
    return "No additional context available."