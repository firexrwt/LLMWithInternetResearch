import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Создаём роутер для управления чатами
router = APIRouter()

# Временное хранилище для чатов (in-memory). В продакшене рекомендуется использовать базу данных.
chat_sessions = {}

# Модель сообщения в чате
class ChatMessage(BaseModel):
    role: str  # "user" или "assistant"
    text: str  # Текст сообщения

# Модель чата
class ChatSession(BaseModel):
    chat_id: str  # Уникальный идентификатор чата
    title: str    # Заголовок чата
    messages: list[ChatMessage] = Field(default_factory=list)  # Список сообщений чата
    # В будущем можно добавить поле pinned для закреплённых сообщений

# Модель запроса на создание нового чата
class NewChatRequest(BaseModel):
    title: str | None = None  # Заголовок чата (если не указан, генерируется автоматически)

# API для получения списка всех чатов
@router.get("/chats")
async def get_chats():
    # Возвращаем список чатов
    return list(chat_sessions.values())

# API для создания нового чата
@router.post("/chats")
async def create_chat(request: NewChatRequest | None = None):
    # Генерируем уникальный идентификатор для нового чата
    chat_id = str(uuid.uuid4())
    # Если заголовок указан, используем его, иначе генерируем "new_chat <номер>"
    if request and request.title:
        title = request.title
    else:
        title = f"new_chat {len(chat_sessions) + 1}"
    # Создаём новый чат с пустой историей сообщений
    new_chat = ChatSession(chat_id=chat_id, title=title, messages=[])
    chat_sessions[chat_id] = new_chat.dict()
    return new_chat

# API для удаления чата по его chat_id
@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]
        return {"message": f"Chat {chat_id} deleted"}
    raise HTTPException(status_code=404, detail="Chat not found")
