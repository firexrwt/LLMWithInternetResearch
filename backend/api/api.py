import os
import logging
import torch
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from backend.model_manager import ModelManager  # Убедись, что путь импорта верный
from llama_cpp import Llama
# deque больше не нужен
from typing import Dict, Optional, List
import uuid
from dotenv import load_dotenv
import sqlite3  # <--- Добавили SQLite
import datetime  # <--- Добавили datetime

# --- Настройка Базы Данных ---
# Путь к .env и базе данных относительно текущего файла api.py
# Предполагаем, что api.py находится в backend/api/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../.."))  # Корень проекта
ENV_PATH = os.path.join(BASE_DIR, ".env")
DATABASE_PATH = os.path.join(BASE_DIR, "neurabox_chats.db")  # БД в корне проекта

load_dotenv(dotenv_path=ENV_PATH)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def init_db():
    """Инициализирует БД и создает таблицы, если их нет."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                sender TEXT NOT NULL CHECK(sender IN ('user', 'ai')), -- 'user' or 'ai'
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (chat_id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_chat_modtime
            AFTER INSERT ON messages
            FOR EACH ROW
            BEGIN
                UPDATE chats SET last_modified_at = CURRENT_TIMESTAMP WHERE chat_id = NEW.chat_id;
            END;
        """)
        conn.commit()
        logger.info(f"База данных инициализирована: {DATABASE_PATH}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        raise
    finally:
        if conn:
            conn.close()


# Инициализация БД при запуске
init_db()


def get_db_connection():
    """Устанавливает соединение с БД."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row  # Возвращать строки как словари
        return conn
    except sqlite3.Error as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        raise HTTPException(status_code=500, detail="Ошибка подключения к базе данных.")


# --- Хелперы для работы с БД ---

def db_add_chat(chat_id: str, title: str, model_used: Optional[str] = None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chats (chat_id, title, model_used, created_at, last_modified_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, title, model_used, datetime.datetime.now(), datetime.datetime.now())
        )
        conn.commit()
        logger.info(f"Чат '{title}' (ID: {chat_id}) добавлен в БД.")
    except sqlite3.IntegrityError:
        logger.warning(f"Чат с ID {chat_id} уже существует.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления чата {chat_id} в БД: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Ошибка сохранения чата в БД.")
    finally:
        if conn:
            conn.close()


def db_add_message(chat_id: str, sender: str, content: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (chat_id, sender, content) VALUES (?, ?, ?)",
            (chat_id, sender, content)
        )
        # Обновляем название чата первым сообщением пользователя, если оно стандартное
        # Проверяем, есть ли уже сообщения от пользователя в этом чате
        cursor.execute("SELECT COUNT(*) FROM messages WHERE chat_id = ? AND sender = 'user'", (chat_id,))
        user_message_count = cursor.fetchone()[0]

        if user_message_count == 1 and sender == 'user':  # Если это первое сообщение пользователя
            cursor.execute("UPDATE chats SET title = ? WHERE chat_id = ? AND title LIKE 'New Chat %'",
                           (content[:50], chat_id))
            logger.info(f"Название чата {chat_id} обновлено на: {content[:50]}")

        conn.commit()
        logger.info(f"Сообщение от '{sender}' добавлено в чат {chat_id}.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления сообщения в чат {chat_id}: {e}")
        conn.rollback()
        # Важно решить, должен ли запрос /query завершиться ошибкой, если сообщение не сохранилось
        raise HTTPException(status_code=500, detail="Ошибка сохранения сообщения в БД.")
    finally:
        if conn:
            conn.close()


def db_get_chats() -> List[Dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, title, model_used, last_modified_at FROM chats ORDER BY last_modified_at DESC")
        chats = [dict(row) for row in cursor.fetchall()]
        return chats
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения чатов из БД: {e}")
        raise HTTPException(status_code=500, detail="Ошибка чтения списка чатов.")
    finally:
        if conn:
            conn.close()


def db_get_messages(chat_id: str) -> List[Dict]:
    conn = get_db_connection()
    # Сначала проверим, существует ли чат
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM chats WHERE chat_id = ?", (chat_id,))
    chat_exists = cursor.fetchone()

    if not chat_exists:
        conn.close()
        logger.warning(f"Попытка получить сообщения для несуществующего чата: {chat_id}")
        # Возвращаем None или пустой список, чтобы вызывающий код мог обработать 404
        return None

    try:
        cursor.execute(
            "SELECT message_id, sender, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp ASC",
            (chat_id,)
        )
        messages = [dict(row) for row in cursor.fetchall()]
        return messages
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения сообщений для чата {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка чтения сообщений чата.")
    finally:
        if conn:
            conn.close()


def db_delete_chat(chat_id: str) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        deleted_rows = cursor.rowcount
        conn.commit()
        if deleted_rows > 0:
            logger.info(f"Чат {chat_id} и его сообщения удалены из БД.")
            return True
        else:
            logger.warning(f"Попытка удаления несуществующего чата {chat_id}.")
            return False
    except sqlite3.Error as e:
        logger.error(f"Ошибка удаления чата {chat_id} из БД: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Ошибка удаления чата.")
    finally:
        if conn:
            conn.close()


# --- Существующий код API (с изменениями) ---

router = APIRouter()

HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    logger.warning("HF_TOKEN не задан в .env или окружении.")

model_manager = None  # Инициализируем при первом запросе, требующем токен
llm_instance = None
# Убрали: conversation_histories: Dict[str, deque] = {}

global_model_settings = {
    "max_tokens": 1024,  # Увеличим по умолчанию
    "temperature": 0.7,
    "top_p": 0.95  # Немного увеличим
}


# Pydantic модели
class TokenRequestBody(BaseModel):
    token: str


def get_gpu_layers():
    if torch.cuda.is_available():
        try:
            device_name = torch.cuda.get_device_name(0)
            logger.info(f"CUDA доступна. Используем устройство: {device_name}")
            gpu_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            logger.info(f"Доступно видеопамяти: {gpu_memory_gb:.2f} GB")
            # Примерная логика слоев (можно настроить)
            if gpu_memory_gb >= 22:
                return -1  # -1 = все слои на GPU
            elif gpu_memory_gb >= 15:
                return 40
            elif gpu_memory_gb >= 10:
                return 30
            elif gpu_memory_gb >= 7:
                return 20
            elif gpu_memory_gb >= 5:
                return 15
            else:
                return 10
        except Exception as e:
            logger.error(f"Ошибка при получении информации о CUDA: {e}")
            return 0  # Возвращаемся к CPU в случае ошибки
    logger.info("CUDA недоступна или не найдена. Будет использован CPU.")
    return 0


class ModelRequestBody(BaseModel):
    model: str


class ModelSettingsRequestBody(BaseModel):
    max_tokens: int = Field(default=global_model_settings["max_tokens"], ge=1, le=8192)
    temperature: float = Field(default=global_model_settings["temperature"], ge=0.0, le=2.0)
    top_p: float = Field(default=global_model_settings["top_p"], ge=0.0, le=1.0)


class QueryRequestBody(ModelSettingsRequestBody):  # Настройки можно переопределять в запросе
    text: str
    model: str
    chat_id: str  # ID чата теперь обязателен от фронтенда
    use_internet: bool = False  # Оставляем, если используется


def load_model(model_name: str):
    global llm_instance, model_manager
    if model_manager is None:
        # Этого не должно происходить, т.к. manager инициализируется в /models
        logger.error("ModelManager не инициализирован перед загрузкой модели!")
        raise HTTPException(status_code=500, detail="Менеджер моделей не готов.")
    try:
        model_path = model_manager.get_model_path(model_name)
        if not model_path or not os.path.exists(model_path):
            logger.error(f"Путь к модели не найден или не существует: {model_path} для {model_name}")
            raise HTTPException(status_code=404, detail=f"Файл модели {model_name} не найден. Установите ее.")

        gpu_layers = get_gpu_layers()
        # Увеличиваем контекст и отключаем лишний вывод llama-cpp
        n_ctx = 4096  # Важно: должно соответствовать возможностям модели
        logger.info(f"Загрузка модели: {model_name} (Путь: {model_path})")
        logger.info(f"Параметры Llama: n_ctx={n_ctx}, n_gpu_layers={gpu_layers}")

        # Освобождаем память от предыдущей модели, если она есть
        if llm_instance:
            logger.info("Освобождаем ресурсы предыдущей модели...")
            del llm_instance
            llm_instance = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Ресурсы освобождены.")

        llm_instance = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=os.cpu_count() // 2,  # Используем половину доступных потоков CPU
            n_gpu_layers=gpu_layers,
            use_mmap=True,  # Ускоряет загрузку
            use_mlock=False,  # Может вызвать проблемы с памятью, отключаем
            verbose=False  # Отключаем стандартный вывод llama.cpp
        )
        logger.info(f"Модель {model_name} успешно загружена.")
    except Exception as e:
        logger.exception(f"Критическая ошибка загрузки модели {model_name}: {e}")  # Логируем traceback
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки модели: {str(e)}")


# --- Существующие эндпоинты (некоторые с изменениями) ---

@router.get("/models")
async def list_available_models(request: Request):
    global model_manager
    hf_token = request.headers.get("X-HF-Token", HF_TOKEN)
    # Инициализируем или обновляем менеджер, если токен изменился
    if model_manager is None or model_manager.hf_token != hf_token:
        logger.info(f"Инициализация ModelManager с токеном {'(есть)' if hf_token else '(нет)'}")
        try:
            model_manager = ModelManager(hf_token=hf_token)
        except Exception as e:
            logger.error(f"Ошибка инициализации ModelManager: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка инициализации менеджера моделей: {e}")
    try:
        return model_manager.get_available_models()
    except Exception as e:
        logger.error(f"Ошибка при получении списка моделей: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении списка моделей.")


@router.post("/install_model")
async def install_model(request: ModelRequestBody):
    if model_manager is None:
        raise HTTPException(status_code=400,
                            detail="Менеджер моделей не инициализирован. Сначала выполните GET /models.")
    try:
        logger.info(f"Начало установки модели: {request.model}")
        local_path = model_manager.download_model(request.model)
        logger.info(f"Модель {request.model} успешно установлена в: {local_path}")
        return {"message": f"Модель {request.model} установлена", "local_path": local_path}
    except Exception as e:
        logger.error(f"Ошибка установки модели {request.model}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка установки модели: {str(e)}")


@router.post("/update_model_settings")
async def update_model_settings(request: ModelSettingsRequestBody):
    global global_model_settings
    try:
        settings_changed = False
        for key, value in request.dict().items():
            if global_model_settings.get(key) != value:
                global_model_settings[key] = value
                settings_changed = True
        if settings_changed:
            logger.info(f"Глобальные настройки генерации обновлены: {global_model_settings}")
            return {"message": "Настройки модели обновлены", "settings": global_model_settings}
        else:
            logger.info("Настройки генерации не изменились.")
            return {"message": "Настройки модели не изменились", "settings": global_model_settings}
    except Exception as e:
        logger.error(f"Ошибка обновления настроек: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обновления настроек.")


@router.post("/query")
async def process_query(request: QueryRequestBody):
    global llm_instance, global_model_settings, model_manager

    logger.info(f"Запрос к /query для chat_id: {request.chat_id}, модель: {request.model}")

    if model_manager is None:
        logger.error("Попытка выполнить /query до инициализации ModelManager.")
        raise HTTPException(status_code=500, detail="Сервер не готов, менеджер моделей не инициализирован.")

    # --- Проверка и загрузка модели ---
    try:
        model_path = model_manager.get_model_path(request.model)
        if not model_path or not os.path.exists(model_path):
            logger.warning(f"Модель {request.model} не найдена локально.")
            raise HTTPException(status_code=404, detail=f"Модель {request.model} не установлена.")

        # Проверяем, загружена ли нужная модель
        if not llm_instance or llm_instance.model_path != model_path:
            logger.info(f"Требуется загрузка/перезагрузка модели {request.model}...")
            load_model(request.model)
        else:
            logger.info(f"Модель {request.model} уже загружена.")

    except HTTPException as http_exc:
        raise http_exc  # Передаем ошибки 404 и 500 от load_model/get_model_path
    except Exception as e:
        logger.exception(f"Неожиданная ошибка при проверке/загрузке модели: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера при подготовке модели.")

    # --- Сохранение сообщения пользователя ---
    user_text = request.text.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Текст запроса не может быть пустым.")

    try:
        db_add_message(request.chat_id, 'user', user_text)
    except HTTPException as db_exc:
        # Если сохранение в БД не удалось, прерываем запрос
        logger.error(f"Не удалось сохранить сообщение пользователя для чата {request.chat_id}. Запрос прерван.")
        raise db_exc
    except Exception as e:
        logger.exception(f"Неожиданная ошибка сохранения сообщения пользователя: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при сохранении запроса.")

    # --- Формирование промпта с историей из БД ---
    try:
        messages_from_db = db_get_messages(request.chat_id)
        if messages_from_db is None:  # Проверка, что чат существует (db_get_messages вернет None)
            logger.error(f"Чат {request.chat_id} не найден при попытке сформировать историю.")
            raise HTTPException(status_code=404, detail=f"Чат с ID {request.chat_id} не найден.")

        # Ограничиваем историю для контекста (например, последние 15 пар сообщений)
        history_limit_pairs = 15
        relevant_history = messages_from_db[-(history_limit_pairs * 2):]

        history_text_parts = []
        for msg in relevant_history:
            # Используем 'User' и 'Assistant' как стандартные роли для промпта
            sender_prefix = "User" if msg['sender'] == 'user' else "Assistant"
            history_text_parts.append(f"{sender_prefix}: {msg['content']}")

        # Собираем историю. Последнее сообщение пользователя уже включено.
        history_text = "\n".join(history_text_parts)

        # Системный промпт можно вынести в настройки или константы
        system_prompt = """You are NeuraBox, a helpful AI assistant running locally.
        Answer concisely and factually in the same language as the user's last message.
        **Format your response using GitHub Flavored Markdown (GFM).**
        - Use ```python ... ``` for code blocks (replace 'python' with the correct language).
        - Use `inline_code` for inline code.
        - Use **bold** and *italic* text for emphasis.
        - Use lists (`- item` or `1. item`) where appropriate."""
        prompt = f"{system_prompt}\n\nConversation history:\n{history_text}\n\nAssistant:"

        logger.info(f"Промпт для модели (Chat ID: {request.chat_id}, длина: {len(prompt)}):\n{prompt[:300]}...")

        # Используем настройки из запроса или глобальные
        max_tokens = request.max_tokens if request.max_tokens is not None else global_model_settings["max_tokens"]
        temperature = request.temperature if request.temperature is not None else global_model_settings["temperature"]
        top_p = request.top_p if request.top_p is not None else global_model_settings["top_p"]

        # --- Генерация ответа ---
        logger.info(f"Параметры генерации: max_tokens={max_tokens}, temp={temperature}, top_p={top_p}")
        response = llm_instance(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            echo=False,
            stop=["\nUser:", "\nAssistant:", "<|endoftext|>"]  # Добавим стандартные стоп-токены
        )

        model_response = response["choices"][0]["text"].strip()
        usage = response.get("usage", {})  # usage может отсутствовать
        tokens_used = usage.get("total_tokens", 0)

        logger.info(
            f"Ответ модели получен (Chat ID: {request.chat_id}, токены: {tokens_used}):\n{model_response[:300]}...")

        if not model_response:
            logger.warning(f"Модель вернула пустой ответ для чата {request.chat_id}.")
            model_response = "(Модель не смогла сгенерировать ответ)"  # Сообщение об ошибке

        # --- Сохранение ответа ИИ ---
        try:
            db_add_message(request.chat_id, 'ai', model_response)
        except HTTPException as db_exc:
            # Если не удалось сохранить ответ ИИ, логируем, но все равно возвращаем ответ пользователю
            logger.error(f"Не удалось сохранить ответ ИИ для чата {request.chat_id}: {db_exc.detail}")
            # Не прерываем запрос, но можно добавить флаг в ответ, что сохранение не удалось
        except Exception as e:
            logger.exception(f"Неожиданная ошибка сохранения ответа ИИ: {e}")

        return {
            "response": model_response,
            "chat_id": request.chat_id,
            "model": request.model,
            "tokens_used": tokens_used,
            "settings_used": {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p
            }
        }

    except HTTPException as http_exc:
        raise http_exc  # Передаем 404, 500 и другие ошибки дальше
    except Exception as e:
        logger.exception(f"Критическая ошибка обработки /query для чата {request.chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при обработке запроса.")


@router.post("/save_token")
async def save_token(request: TokenRequestBody):
    # Логика сохранения токена остается прежней, но убедимся, что ENV_PATH верный
    try:
        current_token = os.getenv("HF_TOKEN")
        new_token = request.token.strip()

        if current_token == new_token:
            logger.info("Предоставленный токен совпадает с текущим, обновление не требуется.")
            return {"message": "Токен совпадает с текущим"}

        env_file_path = ENV_PATH  # Используем определенный ранее путь
        lines = []
        token_found = False

        # Читаем существующий .env, если он есть
        if os.path.exists(env_file_path):
            try:
                with open(env_file_path, "r", encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception as e:
                logger.error(f"Не удалось прочитать .env файл {env_file_path}: {e}")
                # Продолжаем, попытаемся перезаписать

        # Записываем обновленный .env
        try:
            with open(env_file_path, "w", encoding='utf-8') as f:
                for line in lines:
                    stripped_line = line.strip()
                    if stripped_line and not stripped_line.startswith('#') and stripped_line.startswith("HF_TOKEN="):
                        f.write(f"HF_TOKEN={new_token}\n")
                        token_found = True
                    else:
                        f.write(line)  # Сохраняем остальные строки
                if not token_found:
                    f.write(f"\nHF_TOKEN={new_token}\n")  # Добавляем, если не было

            # Перезагружаем переменные окружения
            load_dotenv(dotenv_path=env_file_path, override=True)
            global HF_TOKEN
            HF_TOKEN = os.getenv("HF_TOKEN")
            # Обновляем токен и в model_manager, если он уже создан
            if model_manager:
                model_manager.hf_token = HF_TOKEN

            logger.info("Токен HF_TOKEN успешно сохранен/обновлен в .env")
            return {"message": "Токен успешно сохранен"}

        except Exception as e:
            logger.error(f"Ошибка записи в .env файл {env_file_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка записи токена в файл конфигурации.")

    except Exception as e:
        logger.error(f"Общая ошибка при сохранении токена: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при сохранении токена.")


# --- Новые эндпоинты для управления чатами ---

# Используем Pydantic модели для валидации данных API
class ChatInfo(BaseModel):
    chat_id: str
    title: str
    model_used: Optional[str] = None
    last_modified_at: datetime.datetime


class MessageInfo(BaseModel):
    message_id: int  # ID из БД
    sender: str
    content: str
    timestamp: datetime.datetime


class ChatCreateResponse(ChatInfo):  # Ответ при создании содержит ту же информацию
    pass


@router.get("/chats", response_model=List[ChatInfo])
async def get_all_chats():
    """Получает метаданные всех чатов, отсортированные по последнему изменению."""
    try:
        chats_data = db_get_chats()
        return chats_data  # FastAPI автоматически обработает список словарей в List[ChatInfo]
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception("Неожиданная ошибка в эндпоинте /chats (GET): {e}")
        raise HTTPException(status_code=500, detail="Не удалось получить список чатов.")


@router.post("/chats", response_model=ChatCreateResponse, status_code=201)
async def create_new_chat():
    """Создает новую сессию чата."""
    try:
        new_chat_id = str(uuid.uuid4())
        # Название по умолчанию с временной меткой
        initial_title = f"New Chat {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        db_add_chat(chat_id=new_chat_id, title=initial_title)

        # Получаем только что созданный чат, чтобы вернуть актуальные данные (включая время)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, title, model_used, last_modified_at FROM chats WHERE chat_id = ?",
                       (new_chat_id,))
        new_chat_data = cursor.fetchone()
        conn.close()

        if new_chat_data:
            # Преобразуем last_modified_at в datetime для Pydantic
            chat_dict = dict(new_chat_data)
            chat_dict['last_modified_at'] = datetime.datetime.fromisoformat(chat_dict['last_modified_at'])
            return chat_dict
        else:
            # Этого не должно произойти, если db_add_chat отработал без ошибок
            logger.error(f"Не удалось найти только что созданный чат {new_chat_id} в БД.")
            raise HTTPException(status_code=500, detail="Ошибка получения данных нового чата.")

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Неожиданная ошибка при создании нового чата: {e}")
        raise HTTPException(status_code=500, detail="Не удалось создать новый чат.")


@router.get("/chats/{chat_id}/messages", response_model=List[MessageInfo])
async def get_chat_messages(chat_id: str):
    """Получает все сообщения для указанного чата."""
    try:
        messages_data = db_get_messages(chat_id)
        if messages_data is None:  # Если db_get_messages вернул None, чат не найден
            raise HTTPException(status_code=404, detail=f"Чат с ID {chat_id} не найден.")
        # Преобразуем строки времени в datetime объекты для Pydantic
        for msg in messages_data:
            msg['timestamp'] = datetime.datetime.fromisoformat(msg['timestamp'])
        return messages_data
    except HTTPException as http_exc:
        raise http_exc  # Передаем 404 дальше
    except Exception as e:
        logger.exception(f"Неожиданная ошибка получения сообщений для чата {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Не удалось получить сообщения чата.")


@router.delete("/chats/{chat_id}", status_code=204)  # 204 No Content - стандартный ответ для успешного DELETE
async def delete_chat(chat_id: str):
    """Удаляет чат и все связанные с ним сообщения."""
    try:
        success = db_delete_chat(chat_id)
        if not success:
            # Если db_delete_chat вернул False, значит чат не был найден
            raise HTTPException(status_code=404, detail=f"Чат с ID {chat_id} не найден.")
        # При успехе (status_code=204) тело ответа должно быть пустым
        return None
    except HTTPException as http_exc:
        raise http_exc  # Передаем 404 и 500 от db_delete_chat дальше
    except Exception as e:
        logger.exception(f"Неожиданная ошибка при удалении чата {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Не удалось удалить чат.")