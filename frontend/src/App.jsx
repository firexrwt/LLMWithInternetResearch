import React, {useState, useEffect, useRef, useCallback} from "react";
import Modal from "react-modal";
import {format, parseISO} from 'date-fns'; // Для форматирования дат
import {ru} from 'date-fns/locale/ru'; // Правильный импорт локали ru
import ReactMarkdown from 'react-markdown'; // Для отображения Markdown
import remarkGfm from 'remark-gfm'; // Плагин для Markdown (таблицы, ссылки и т.д.)
import "./App.css";

Modal.setAppElement("#root");

// Определяем базовый URL API
const API_BASE_URL = "http://127.0.0.1:9015/api";

function App() {
  // --- Состояния ---
  const [query, setQuery] = useState(""); // Текст в поле ввода
  const [models, setModels] = useState([]); // Список всех моделей (из /models)
  const [selectedModel, setSelectedModel] = useState(""); // Выбранная модель для чата
  const [isSendingQuery, setIsSendingQuery] = useState(false); // Флаг отправки запроса к модели
  const [useInternet] = useState(false); // Состояние флага интернета (если нужно)

  // Состояния для чатов
  const [chats, setChats] = useState([]); // Список метаданных чатов { id, name, model_used, last_modified_at }
  const [activeChatId, setActiveChatId] = useState(null); // ID активного чата
  const [currentChatMessages, setCurrentChatMessages] = useState([]); // Сообщения текущего активного чата { id, role, text, timestamp }
  const [isLoadingChats, setIsLoadingChats] = useState(true); // Загрузка списка чатов
  const [isLoadingMessages, setIsLoadingMessages] = useState(false); // Загрузка сообщений активного чата

  // Состояния для модальных окон
  const [isManageModalOpen, setIsManageModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [hfToken, setHfToken] = useState(""); // Токен HF для управления моделями
  const [activeManageTab, setActiveManageTab] = useState("installed_models"); // Вкладка в модалке управления
  const [sortBy, setSortBy] = useState("parameters"); // Сортировка в модалке
  const [modelInstallStatus, setModelInstallStatus] = useState({}); // Статус установки моделей { modelName: 'installing' | 'error' | 'success' }
  const [offset, setOffset] = useState(0); // Смещение для загрузки моделей
  const [isLoadingMoreModels, setIsLoadingMoreModels] = useState(false); // Загрузка доп. моделей
  const LIMIT = 30; // Увеличим лимит загрузки моделей

  // Настройки генерации
  const [modelSettings, setModelSettings] = useState({
    max_tokens: 1024,
    temperature: 0.7,
    top_p: 0.95
  });
  // Состояние для хранения изначальных настроек при открытии модалки
  const [initialModalSettings, setInitialModalSettings] = useState({});

  // Ref для скролла
  const chatEndRef = useRef(null);
  const modelListRef = useRef(null);


  // --- Функции для работы с API ---

  // Получение списка чатов с бэкенда
  const fetchChatList = useCallback(async (selectChatId = null) => {
    setIsLoadingChats(true);
    console.log("Запрос списка чатов...");
    try {
      const res = await fetch(`${API_BASE_URL}/chats`);
      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${res.statusText}`);
      const data = await res.json();
      const formattedChats = data.map(chat => ({
        id: chat.chat_id,
        name: chat.title,
        model_used: chat.model_used,
        last_modified_at: chat.last_modified_at
      }));
      setChats(formattedChats);
      console.log("Список чатов загружен:", formattedChats.length);

      // Логика выбора активного чата после загрузки
      if (selectChatId && formattedChats.some(c => c.id === selectChatId)) {
        setActiveChatId(selectChatId); // Активируем запрошенный ID, если он есть
        console.log(`Активирован запрошенный чат: ${selectChatId}`);
      } else if (formattedChats.length > 0) {
        // Если нет запрошенного или он не найден, активируем самый последний
        const currentActiveExists = formattedChats.some(c => c.id === activeChatId);
        if (!activeChatId || !currentActiveExists) {
          setActiveChatId(formattedChats[0].id);
          console.log(`Активирован последний чат: ${formattedChats[0].id}`);
        } else {
          // Оставляем текущий активный чат, если он все еще существует
          console.log(`Активный чат ${activeChatId} остался прежним.`);
        }
      } else {
        setActiveChatId(null); // Если чатов нет
        setCurrentChatMessages([]);
        console.log("Чаты отсутствуют.");
      }

    } catch (error) {
      console.error("Ошибка при загрузке списка чатов:", error);
      setChats([]);
      setActiveChatId(null);
      setCurrentChatMessages([]);
      // Можно показать уведомление пользователю
    } finally {
      setIsLoadingChats(false);
    }
  }, [activeChatId]); // Зависимость от activeChatId нужна для логики "оставить текущий активный"

  // Первичная загрузка списка чатов
  useEffect(() => {
    fetchChatList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Пустой массив зависимостей - выполнить один раз при монтировании

  // Загрузка сообщений при смене активного чата
  useEffect(() => {
    const fetchMessages = async () => {
      if (!activeChatId) {
        setCurrentChatMessages([]);
        return;
      }
      setIsLoadingMessages(true);
      setCurrentChatMessages([]); // Очищаем перед загрузкой
      console.log(`Запрос сообщений для чата: ${activeChatId}`);
      try {
        const res = await fetch(`${API_BASE_URL}/chats/${activeChatId}/messages`);
        if (!res.ok) {
          if (res.status === 404) {
            console.warn(`Чат ${activeChatId} не найден на сервере.`);
            // Обновляем список, убирая несуществующий чат
            setChats(prev => prev.filter(c => c.id !== activeChatId));
            // Не вызываем fetchChatList здесь напрямую, чтобы избежать потенциального зацикливания.
            // Логика в fetchChatList сама выберет новый активный чат при следующем рендере,
            // если activeChatId окажется невалидным. Просто сбрасываем ID.
            setActiveChatId(null);
          } else {
            throw new Error(`Ошибка ${res.status}: ${res.statusText}`);
          }
          return; // Выход, если чат не найден или другая ошибка сети
        }
        const data = await res.json();
        const formattedMessages = data.map(msg => ({
          id: msg.message_id, // Используем ID из БД
          role: msg.sender === 'user' ? 'user' : 'assistant',
          text: msg.content,
          timestamp: msg.timestamp // Сохраняем ISO строку времени
        }));
        setCurrentChatMessages(formattedMessages);
        console.log("Сообщения загружены:", formattedMessages.length);
      } catch (error) {
        console.error(`Ошибка загрузки сообщений для чата ${activeChatId}:`, error);
        setCurrentChatMessages([]); // Очищаем в случае ошибки
        // Можно показать уведомление
      } finally {
        setIsLoadingMessages(false);
      }
    };

    fetchMessages();
    // Зависимость fetchChatList удалена, чтобы избежать лишних вызовов при 404
  }, [activeChatId]);

  // Автоскролл вниз при обновлении сообщений
  useEffect(() => {
    // Небольшая задержка, чтобы дать DOM обновиться перед скроллом
    const timer = setTimeout(() => {
      if (chatEndRef.current) {
        chatEndRef.current.scrollIntoView({behavior: "smooth", block: "end"});
      }
    }, 100); // Задержка в 100мс
    return () => clearTimeout(timer); // Очистка таймера
  }, [currentChatMessages]);

  // Загрузка списка моделей (доступных и установленных)
  const fetchModels = useCallback(async (newOffset = 0, append = false) => {
    if (isLoadingMoreModels && append) return; // Предотвращаем двойной запуск только для дозагрузки
    setIsLoadingMoreModels(true);
    console.log(`Запрос моделей: offset=${newOffset}, append=${append}`);
    try {
      const headers = hfToken ? {"X-HF-Token": hfToken} : {};
      const res = await fetch(`${API_BASE_URL}/models?offset=${newOffset}&limit=${LIMIT}`, {headers});
      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${res.statusText}`);
      const data = await res.json(); // Ожидаем [{ name, installed, size, parameters, type }]

      const uniqueData = data.filter(newItem =>
        append ? !models.some(existingItem => existingItem.name === newItem.name) : true
      ); // Фильтруем дубликаты при дозагрузке

      const newModels = append ? [...models, ...uniqueData] : uniqueData;
      setModels(newModels);
      setOffset(newModels.length); // Обновляем offset на основе общего кол-ва

      // Автовыбор первой установленной модели, если модель не выбрана ИЛИ текущая выбранная не установлена
      const currentSelectedModelData = newModels.find(m => m.name === selectedModel);
      if (!selectedModel || !currentSelectedModelData || !currentSelectedModelData.installed) {
        const firstInstalled = newModels.find(m => m.installed);
        if (firstInstalled) {
          setSelectedModel(firstInstalled.name);
          console.log(`Автоматически выбрана установленная модель: ${firstInstalled.name}`);
        } else if (!selectedModel && newModels.length > 0) {
          // Если нет установленных и модель вообще не была выбрана, возможно, стоит очистить selectedModel?
          // Пока оставляем как есть, пользователь выберет сам или установит новую.
        }
      }

      console.log(`Загружено ${uniqueData.length} моделей. Всего: ${newModels.length}`);
    } catch (error) {
      console.error("Ошибка при загрузке списка моделей:", error);
      // Можно показать уведомление
    } finally {
      setIsLoadingMoreModels(false);
    }
  }, [hfToken, selectedModel, isLoadingMoreModels, offset, models]); // Добавили models в зависимости для фильтрации дубликатов


  // Первичная загрузка моделей и при смене токена
  useEffect(() => {
    setModels([]); // Очищаем список перед загрузкой
    setOffset(0); // Сбрасываем смещение
    fetchModels(0, false); // Загружаем с начала
    // fetchModels вызывается внутри этого useEffect, поэтому нет нужды добавлять его в зависимости
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hfToken]); // Только при смене токена

  // Обработчик скролла для дозагрузки моделей
  const handleModelScroll = useCallback(() => {
    const element = modelListRef.current;
    if (!element || isLoadingMoreModels) return;
    // Загружаем немного раньше, чем достигнут самый низ
    const isNearBottom = element.scrollTop + element.clientHeight >= element.scrollHeight - 150; // Увеличим порог
    if (isNearBottom) {
      console.log("Достигнут низ списка моделей, загружаем еще...");
      fetchModels(offset, true); // Используем текущий offset для дозагрузки
    }
  }, [fetchModels, isLoadingMoreModels, offset]); // Зависимости включают offset

  // Обновление глобальных настроек генерации
  const updateGlobalModelSettings = async (settingsToUpdate) => {
    try {
      const res = await fetch(`${API_BASE_URL}/update_model_settings`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(settingsToUpdate),
      });
      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${res.statusText}`);
      const data = await res.json();
      setModelSettings(data.settings); // Обновляем состояние актуальными настройками с бэка
      setIsSettingsModalOpen(false);
      console.log("Глобальные настройки генерации обновлены:", data.settings);
    } catch (error) {
      console.error("Ошибка обновления настроек:", error);
      alert(`Не удалось обновить настройки: ${error.message}`);
    }
  };

  // Отправка запроса к модели
  const handleSubmit = async (e) => {
    if (e) e.preventDefault(); // Если вызвано из формы/кнопки
    if (!query.trim() || !activeChatId || !selectedModel || isSendingQuery) return;

    const userMessageText = query.trim();
    const tempUserMessageId = `user-${Date.now()}`; // Уникальный временный ID

    // Оптимистичное обновление UI
    const optimisticUserMessage = {
      id: tempUserMessageId,
      role: "user",
      text: userMessageText,
      timestamp: new Date().toISOString()
    };
    // Добавляем сообщение пользователя и СРАЗУ ЖЕ пустое сообщение для ответа ИИ
    const optimisticAiPlaceholder = {
      id: `assistant-placeholder-${Date.now()}`,
      role: "assistant",
      text: "...", // Плейсхолдер загрузки
      timestamp: new Date().toISOString() // Примерное время начала генерации
    };
    setCurrentChatMessages(prev => [...prev, optimisticUserMessage, optimisticAiPlaceholder]);
    setQuery(""); // Очищаем поле ввода
    setIsSendingQuery(true);
    console.log(`Отправка запроса для чата ${activeChatId}, модель: ${selectedModel}`);

    let responseData = null;
    let fetchError = null;

    try {
      const res = await fetch(`${API_BASE_URL}/query`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          chat_id: activeChatId,
          model: selectedModel,
          text: userMessageText,
          use_internet: useInternet, // Передаем флаг интернета
          // Передаем текущие настройки генерации
          max_tokens: modelSettings.max_tokens,
          temperature: modelSettings.temperature,
          top_p: modelSettings.top_p
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({detail: `Ошибка ${res.status}: ${res.statusText}`}));
        throw new Error(errorData.detail || `Ошибка ${res.status}`);
      }

      responseData = await res.json(); // { response, chat_id, model, tokens_used, settings_used }

    } catch (error) {
      console.error("Ошибка при выполнении запроса к модели:", error);
      fetchError = error;
    } finally {
      setIsSendingQuery(false);

      // Обновляем UI: заменяем плейсхолдер на реальный ответ или сообщение об ошибке
      setCurrentChatMessages(prevMessages => {
        const newMessages = [...prevMessages];
        // Находим индекс плейсхолдера (последнее сообщение ассистента)
        const placeholderIndex = newMessages.findLastIndex(msg => msg.id.startsWith('assistant-placeholder-'));

        if (placeholderIndex !== -1) {
          if (responseData) {
            // Успешный ответ
            newMessages[placeholderIndex] = {
              ...newMessages[placeholderIndex], // Сохраняем ID и роль
              id: `assistant-${Date.now()}`, // Можно сгенерировать новый реальный ID, если нужно
              text: responseData.response,
              timestamp: new Date().toISOString() // Точное время получения
            };
            console.log("Ответ ИИ получен и отображен.");
          } else if (fetchError) {
            // Ошибка сети или ответа
            newMessages[placeholderIndex] = {
              ...newMessages[placeholderIndex],
              id: `error-${Date.now()}`,
              text: `**Ошибка:** ${fetchError.message}`, // Используем Markdown для выделения
              timestamp: new Date().toISOString()
            };
          } else {
            // Случай, когда не было ни ответа, ни ошибки (маловероятно, но для полноты)
            newMessages.splice(placeholderIndex, 1); // Просто удаляем плейсхолдер
          }
        } else {
          // Если плейсхолдер не найден (странно, но возможно), просто добавляем ошибку в конец
          if (fetchError) {
            newMessages.push({
              id: `error-${Date.now()}`,
              role: "assistant",
              text: `**Ошибка:** ${fetchError.message}`,
              timestamp: new Date().toISOString()
            });
          }
        }
        return newMessages;
      });

      // Обновляем список чатов, чтобы переместить текущий наверх (только если ответ был успешным)
      if (responseData) {
        fetchChatList(activeChatId); // Перезагружаем список, оставаясь на активном чате
      }
    }
  };

  // Отправка по Enter
  const handleSubmitOnKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Создание нового чата
  const createNewChat = async () => {
    console.log("Запрос на создание нового чата...");
    setIsLoadingChats(true); // Показываем индикатор на время создания
    try {
      const res = await fetch(`${API_BASE_URL}/chats`, {method: "POST"});
      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${res.statusText}`);
      const newChatData = await res.json(); // { chat_id, title, ... }

      const formattedNewChat = {
        id: newChatData.chat_id,
        name: newChatData.title,
        model_used: newChatData.model_used,
        last_modified_at: newChatData.last_modified_at // Используем время с бэка
      };

      // Добавляем новый чат в начало списка и делаем активным
      setChats(prevChats => [formattedNewChat, ...prevChats]);
      setActiveChatId(formattedNewChat.id);
      // setCurrentChatMessages([]); // Не нужно, т.к. useEffect [activeChatId] сделает это
      console.log("Новый чат создан и активирован:", formattedNewChat.id);
    } catch (error) {
      console.error("Ошибка при создании нового чата:", error);
      alert(`Не удалось создать чат: ${error.message}`);
    } finally {
      setIsLoadingChats(false);
    }
  };

  // Удаление чата
  const deleteChat = async (idToDelete) => {
    // Найдем чат для подтверждения
    const chatToDelete = chats.find(c => c.id === idToDelete);
    if (!chatToDelete) return; // Чата нет в списке

    // Нельзя удалить последний чат (убрано, т.к. теперь можно остаться без чатов)
    // if (chats.length <= 1) {
    //     alert("Нельзя удалить последний чат.");
    //     return;
    // }

    // Запрашиваем подтверждение
    if (!window.confirm(`Вы уверены, что хотите удалить чат "${chatToDelete.name || idToDelete}"? Это действие необратимо.`)) {
      return;
    }

    console.log(`Запрос на удаление чата: ${idToDelete}`);
    const originalChats = [...chats]; // Сохраняем текущее состояние для отката
    const originalActiveId = activeChatId;

    // Оптимистичное удаление из UI
    const updatedChats = originalChats.filter(chat => chat.id !== idToDelete);
    setChats(updatedChats);
    let nextActiveId = activeChatId;
    if (activeChatId === idToDelete) {
      // Активируем первый из оставшихся или null
      nextActiveId = updatedChats[0]?.id || null;
      setActiveChatId(nextActiveId);
      console.log(`Оптимистично активирован другой чат: ${nextActiveId || 'null'}`);
    }


    try {
      const res = await fetch(`${API_BASE_URL}/chats/${idToDelete}`, {method: "DELETE"});
      // Успешное удаление возвращает 204 No Content
      if (res.status === 204) {
        console.log(`Чат ${idToDelete} успешно удален с сервера.`);
        // UI уже обновлен оптимистично
      } else if (res.status === 404) {
        console.warn(`Чат ${idToDelete} не найден на сервере при попытке удаления.`);
        // UI уже обновлен оптимистично
      } else {
        // Если сервер вернул другую ошибку
        throw new Error(`Ошибка сервера ${res.status}: ${res.statusText}`);
      }
    } catch (error) {
      console.error("Ошибка при удалении чата на сервере:", error);
      alert(`Не удалось удалить чат: ${error.message}`);
      // Откат UI в случае ошибки
      setChats(originalChats);
      setActiveChatId(originalActiveId);
      console.log("Откат UI после ошибки удаления.");
    }
  };

  // Установка модели
  const handleInstallModel = async (modelName) => {
    setModelInstallStatus(prev => ({...prev, [modelName]: 'installing'}));
    console.log(`Запрос на установку модели: ${modelName}`);
    try {
      const res = await fetch(`${API_BASE_URL}/install_model`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({model: modelName}),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({detail: `Ошибка ${res.status}: ${res.statusText}`}));
        throw new Error(errorData.detail || `Ошибка ${res.status}`);
      }
      setModelInstallStatus(prev => ({...prev, [modelName]: 'success'}));
      console.log(`Модель ${modelName} успешно установлена.`);

      // Обновляем только информацию об этой модели в списке, не перезагружая все
      setModels(prevModels => prevModels.map(m =>
        m.name === modelName ? {...m, installed: true} : m
      ));
      // Автоматически выбираем установленную модель, если никакая не выбрана
      if (!selectedModel) {
        setSelectedModel(modelName);
      }

      // Можно показать уведомление об успехе
      setTimeout(() => setModelInstallStatus(prev => ({...prev, [modelName]: undefined})), 3000); // Убираем статус через 3 сек
    } catch (error) {
      console.error("Ошибка установки модели:", error);
      setModelInstallStatus(prev => ({...prev, [modelName]: 'error'}));
      alert(`Не удалось установить модель ${modelName}: ${error.message}`);
      // Можно оставить статус 'error' до следующего обновления списка или убирать через время
      // setTimeout(() => setModelInstallStatus(prev => ({ ...prev, [modelName]: undefined })), 5000);
    }
  };

  // Удаление модели (Заглушка)
  const handleDeleteModel = async (modelName) => {
    alert(`Удаление модели ${modelName} пока не реализовано на бэкенде.`);
    // TODO: Реализовать эндпоинт на бэкенде и вызывать его здесь
    // const res = await fetch(`${API_BASE_URL}/delete_model`, { method: "POST", ... body: { model: modelName } });
    // if (res.ok) {
    //      setModels(prevModels => prevModels.map(m =>
    //          m.name === modelName ? { ...m, installed: false } : m
    //      ));
    //      if (selectedModel === modelName) {
    //          const nextInstalled = models.find(m => m.installed && m.name !== modelName);
    //          setSelectedModel(nextInstalled?.name || "");
    //      }
    // }
  };

  // Сохранение токена HF
  const handleTokenSave = async () => {
    console.log("Сохранение токена HF...");
    try {
      const res = await fetch(`${API_BASE_URL}/save_token`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({token: hfToken}),
      });
      if (!res.ok) throw new Error(`Ошибка ${res.status}: ${res.statusText}`);
      alert("Токен сохранен. Список моделей будет обновлен.");
      // Не нужно вызывать fetchModels здесь, т.к. useEffect [hfToken] сработает сам
    } catch (error) {
      console.error("Ошибка сохранения токена:", error);
      alert(`Не удалось сохранить токен: ${error.message}`);
    }
  };

  // Открытие модалки настроек - сохраняем текущие настройки
  const openSettingsModal = () => {
    setInitialModalSettings({...modelSettings}); // Копируем текущие настройки
    setIsSettingsModalOpen(true);
  };

  // Закрытие модалки настроек - восстанавливаем, если не сохранили
  const closeSettingsModal = (saved = false) => {
    if (!saved) {
      setModelSettings(initialModalSettings); // Восстанавливаем исходные
    }
    setIsSettingsModalOpen(false);
  };

  // Утилита сортировки моделей
  const sortModels = (modelsToSort, criteria) => {
    return [...modelsToSort].sort((a, b) => {
      try {
        if (criteria === "parameters") {
          const paramA = parseFloat(a.parameters?.replace(/[^\d.]/g, '')) || 0;
          const paramB = parseFloat(b.parameters?.replace(/[^\d.]/g, '')) || 0;
          return paramB - paramA; // Descending
        } else if (criteria === "size") {
          const parseSize = (sizeStr) => {
            if (!sizeStr) return 0;
            const value = parseFloat(sizeStr.replace(/[^\d.]/g, '')) || 0;
            if (sizeStr.toUpperCase().includes('G')) return value * 1024; // Convert GB to MB
            if (sizeStr.toUpperCase().includes('K')) return value / 1024; // Convert KB to MB
            return value; // Assume MB if no unit
          };
          return parseSize(b.size) - parseSize(a.size); // Descending
        } else if (criteria === "type") {
          // Сортировка по типу, пустые в конце
          const typeA = a.type || 'zzz'; // Put empty types last
          const typeB = b.type || 'zzz';
          return typeA.localeCompare(typeB); // Ascending
        }
      } catch (e) {
        console.error("Ошибка сортировки моделей:", e);
      }
      return 0;
    });
  };


  // --- Рендеринг Компонента ---
  return (
    <div className="app-container">
      {/* --- Сайдбар --- */}
      <div className="sidebar">
        <div className="sidebar-header">
          <button className="new-chat-button" onClick={createNewChat} disabled={isLoadingChats}>
            {isLoadingChats ? <span className="spinner small white"></span> : "+ Новый чат"}
          </button>
        </div>
        <div className="chat-list">
          {isLoadingChats && chats.length === 0 ? ( // Показываем только при самой первой загрузке
            <div className="loading-placeholder">Загрузка чатов...</div>
          ) : chats.length > 0 ? (
            chats.map((chat) => (
              <div
                key={chat.id}
                className={`chat-tab ${chat.id === activeChatId ? "active" : ""}`}
                onClick={() => !isLoadingMessages && setActiveChatId(chat.id)} // Блокируем клик во время загрузки сообщений
                title={`Чат: ${chat.name}\nПоследнее изменение: ${format(parseISO(chat.last_modified_at), 'Pp', {locale: ru})}`}
              >
                <span className="chat-tab-name">{chat.name}</span>
                {/* Убираем условие chats.length > 1, чтобы всегда можно было удалить */}
                <button
                  className="delete-chat-button"
                  onClick={(e) => {
                    e.stopPropagation(); // Остановить всплытие, чтобы не выбрать чат
                    deleteChat(chat.id);
                  }}
                  title="Удалить чат"
                >
                  ✖
                </button>
              </div>
            ))
          ) : (
            !isLoadingChats && <div className="loading-placeholder">Нет доступных чатов.</div>
          )}
        </div>
        <div className="sidebar-footer">
          <button onClick={() => setIsManageModalOpen(true)} className="manage-models-button">
            Управление моделями
          </button>
          <button
            onClick={openSettingsModal} // Используем новую функцию
            className="manage-models-button"
          >
            Настройки генерации
          </button>
        </div>
      </div>

      {/* --- Основной контент --- */}
      <div className="main-content">
        <header className="header">
          <h1 className="header-title">NeuraBox</h1>
          {selectedModel && (
            <span className="header-model-info" title={selectedModel}>
                            Модель: {selectedModel.split('/').pop()} {/* Показываем только имя модели */}
                        </span>
          )}
        </header>

        {/* Контейнер чата */}
        <div className="chat-container">
          {!activeChatId && !isLoadingChats && (
            <div className="placeholder-message">Выберите чат или создайте новый.</div>
          )}
          {isLoadingMessages && activeChatId && (
            <div className="placeholder-message">Загрузка сообщений...</div>
          )}
          {!isLoadingMessages && activeChatId && currentChatMessages.length === 0 && (
            <div className="placeholder-message">Нет сообщений в этом чате. Начните диалог!</div>
          )}
          {!isLoadingMessages && currentChatMessages.map((msg, index) => ( // Добавил index для ключа плейсхолдера
            <div
              // Используем message_id из БД или временный ID для ключа
              key={msg.id || `msg-${index}`}
              className={`message ${msg.role === "user" ? "message-user" : "message-assistant"} ${msg.text === "..." ? "message-loading" : ""}`}
              title={msg.timestamp ? `Отправлено: ${format(parseISO(msg.timestamp), 'Pp', {locale: ru})}` : ''}
            >
              {/* Используем ReactMarkdown для рендеринга */}
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text || ""}</ReactMarkdown>
            </div>
          ))}
          <div ref={chatEndRef}/>
          {/* Элемент для скролла */}
        </div>

        {/* Поле ввода */}
        <div className="input-container">
          <div className="input-field-wrapper">
            {/* Селектор модели */}
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="model-selector"
              disabled={isSendingQuery || models.filter(m => m.installed).length === 0}
              title={selectedModel || "Выберите установленную модель"}
            >
              <option value="" disabled>
                {models.filter(m => m.installed).length === 0 ? "Нет моделей" : "Выберите модель"}
              </option>
              {/* Показываем сначала выбранную (если она установлена), потом остальные */}
              {selectedModel && models.find(m => m.name === selectedModel && m.installed) && (
                <option key={selectedModel} value={selectedModel}>
                  {selectedModel.split('/').pop()}
                </option>
              )}
              {models.filter(m => m.installed && m.name !== selectedModel).map((model) => (
                <option key={model.name} value={model.name}>
                  {model.name.split('/').pop()} {/* Показываем только имя */}
                </option>
              ))}
            </select>
            {/* Поле ввода текста */}
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={!activeChatId ? "Выберите или создайте чат" : !selectedModel ? "Выберите модель" : "Введите ваш запрос..."}
              className="input-field"
              rows="1" // Начнем с одной строки, CSS сделает остальное
              onKeyDown={handleSubmitOnKey}
              disabled={isSendingQuery || !activeChatId || !selectedModel}
            />
            {/* Кнопка отправки */}
            <button
              type="button" // Изменим на type="button", т.к. нет <form>
              onClick={handleSubmit}
              disabled={isSendingQuery || !query.trim() || !activeChatId || !selectedModel}
              className="send-button"
              title="Отправить (Enter)"
            >
              {isSendingQuery ?
                <span className="spinner"></span> : "➤"} {/* Заменим иконку и добавим спиннер */}
            </button>
          </div>
        </div>
      </div>

      {/* --- Модальные окна --- */}

      {/* Модалка Управления Моделями */}
      <Modal
        isOpen={isManageModalOpen}
        onRequestClose={() => setIsManageModalOpen(false)}
        className="modal manage-models-modal" // Добавим класс для специфичных стилей
        overlayClassName="modal-overlay"
      >
        {/* --- НАЧАЛО НЕ СКРОЛЛЯЩЕГОСЯ ЗАГОЛОВКА --- */}
        <div className="modal-header">
          <h2>Управление моделями</h2>
          {/* Поле ввода токена HF */}
          <div className="token-container">
            <input
              type="password"
              value={hfToken}
              onChange={(e) => setHfToken(e.target.value)}
              placeholder="Токен Hugging Face (Read)"
              className="token-input"
              title="Введите ваш Read-токен Hugging Face для доступа к моделям"
            />
            <button onClick={handleTokenSave} className="token-save-button"
                    title="Сохранить токен в .env файл">
              Сохранить
            </button>
            <button
              onClick={() => window.open("https://huggingface.co/settings/tokens", "_blank")}
              className="token-create-button"
              title="Перейти на Hugging Face для создания токена"
            >
              Создать
            </button>
          </div>
        </div>
        {/* --- КОНЕЦ НЕ СКРОЛЛЯЩЕГОСЯ ЗАГОЛОВКА --- */}

        {/* --- НАЧАЛО СКРОЛЛЯЩЕГОСЯ КОНТЕНТА --- */}
        <div className="modal-content-scrollable">
          {/* Вкладки */}
          <div className="tab-container">
            <button
              className={`tab-button ${activeManageTab === "available_models" ? "active" : ""}`}
              onClick={() => {
                setActiveManageTab("available_models");
                // Не сбрасываем offset здесь, т.к. он может быть нужен для дозагрузки
                // fetchModels(0, false); // Не перезагружаем сразу, только при необходимости
              }}
            >
              Доступные модели ({models.length})
            </button>
            <button
              className={`tab-button ${activeManageTab === "installed_models" ? "active" : ""}`}
              onClick={() => setActiveManageTab("installed_models")}
            >
              Установленные ({models.filter(m => m.installed).length})
            </button>
          </div>
          {/* Сортировка */}
          <div className="sort-container">
            <label htmlFor="sort-select">Сортировать по: </label>
            <select id="sort-select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="parameters">Параметры (убыв.)</option>
              <option value="size">Размер (убыв.)</option>
              <option value="type">Тип (А-Я)</option>
            </select>
          </div>
          {/* Списки моделей */}
          <div className="model-list-container">
            {activeManageTab === "available_models" && (
              <ul className="model-list" ref={modelListRef} onScroll={handleModelScroll}>
                {sortModels(models, sortBy).map((model) => (
                  <li key={model.name} className="model-item">
                    <div className="model-info">
                      <strong>{model.name}</strong>
                      <span>({model.type || '?'}, {model.parameters || '?'} params, {model.size || '?'})</span>
                    </div>
                    <button
                      onClick={() => model.installed ? handleDeleteModel(model.name) : handleInstallModel(model.name)}
                      className={`model-action-button ${model.installed ? 'delete' : 'install'}`}
                      disabled={modelInstallStatus[model.name] === 'installing'}
                    >
                      {modelInstallStatus[model.name] === 'installing' ? <span
                        className="spinner small"></span> : model.installed ? 'Удалить' : 'Установить'}
                      {modelInstallStatus[model.name] === 'error' && ' Ошибка!'}
                      {modelInstallStatus[model.name] === 'success' && ' ✓'}
                    </button>
                  </li>
                ))}
                {isLoadingMoreModels && <li className="loading-placeholder">Загрузка моделей...</li>}
                {!isLoadingMoreModels && models.length === 0 &&
                  <li className="loading-placeholder">Модели не найдены. Проверьте токен HF или соединение.</li>}
              </ul>
            )}
            {activeManageTab === "installed_models" && (
              <ul className="model-list">
                {sortModels(models.filter(m => m.installed), sortBy).length > 0 ? (
                  sortModels(models.filter(m => m.installed), sortBy).map((model) => (
                    <li key={model.name} className="model-item">
                      <div className="model-info">
                        <strong>{model.name}</strong>
                        <span>({model.type || '?'}, {model.parameters || '?'} params, {model.size || '?'})</span>
                      </div>
                      <button onClick={() => handleDeleteModel(model.name)}
                              className="model-action-button delete">
                        Удалить
                      </button>
                    </li>
                  ))
                ) : (
                  <li className="loading-placeholder">Установленные модели отсутствуют.</li>
                )}
              </ul>
            )}
          </div>
        </div>
        {/* --- КОНЕЦ СКРОЛЛЯЩЕГОСЯ КОНТЕНТА --- */}

        {/* Опциональный футер модалки */}
        <div className="modal-actions">
          <button onClick={() => setIsManageModalOpen(false)} className="modal-button secondary">Закрыть</button>
        </div>
      </Modal>

      {/* Модалка Настроек Генерации */}
      <Modal
        isOpen={isSettingsModalOpen}
        onRequestClose={() => closeSettingsModal(false)} // Восстанавливаем настройки при закрытии без сохранения
        className="modal settings-modal" // Отдельный класс
        overlayClassName="modal-overlay"
      >
        {/* --- НАЧАЛО НЕ СКРОЛЛЯЩЕГОСЯ ЗАГОЛОВКА --- */}
        <div className="modal-header">
          <h2>Настройки генерации (Глобальные)</h2>
          <p className="modal-subtitle">Эти настройки применяются ко всем чатам по умолчанию.</p>
        </div>
        {/* --- КОНЕЦ НЕ СКРОЛЛЯЩЕГОСЯ ЗАГОЛОВКА --- */}

        {/* --- НАЧАЛО СКРОЛЛЯЩЕГОСЯ КОНТЕНТА (на всякий случай) --- */}
        <div className="modal-content-scrollable">
          <div className="model-settings">
            <div className="model-settings-input">
              <label htmlFor="max_tokens_input">Max Tokens (Макс. токенов ответа)</label>
              <input
                id="max_tokens_input" type="number"
                value={modelSettings.max_tokens}
                onChange={(e) => setModelSettings(prev => ({
                  ...prev,
                  max_tokens: Math.max(1, parseInt(e.target.value) || 1)
                }))}
                min="1" max="8192" step="64"
              />
            </div>
            <div className="model-settings-input">
              <label htmlFor="temp_input">Temperature (Случайность: 0.1-1.9)</label>
              <input
                id="temp_input" type="number" step="0.05"
                value={modelSettings.temperature}
                onChange={(e) => setModelSettings(prev => ({
                  ...prev,
                  temperature: Math.max(0.01, Math.min(1.99, parseFloat(e.target.value) || 0.1))
                }))}
                min="0.01" max="1.99"
              />
            </div>
            <div className="model-settings-input">
              <label htmlFor="topp_input">Top P (Отсечение: 0.1-0.99)</label>
              <input
                id="topp_input" type="number" step="0.05"
                value={modelSettings.top_p}
                onChange={(e) => setModelSettings(prev => ({
                  ...prev,
                  top_p: Math.max(0.01, Math.min(0.99, parseFloat(e.target.value) || 0.1))
                }))}
                min="0.01" max="0.99"
              />
            </div>
          </div>
        </div>
        {/* --- КОНЕЦ СКРОЛЛЯЩЕГОСЯ КОНТЕНТА --- */}

        {/* --- НАЧАЛО НЕ СКРОЛЛЯЩЕГОСЯ ФУТЕРА --- */}
        <div className="modal-actions">
          <button onClick={() => closeSettingsModal(false)} className="modal-button secondary">
            Отмена
          </button>
          <button onClick={() => {
            updateGlobalModelSettings(modelSettings);
            closeSettingsModal(true); // Закрываем без восстановления
          }} className="modal-button primary">
            Сохранить
          </button>
        </div>
        {/* --- КОНЕЦ НЕ СКРОЛЛЯЩЕГОСЯ ФУТЕРА --- */}
      </Modal>
    </div>
  );
}

export default App;