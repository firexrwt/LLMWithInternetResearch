import React, { useState, useEffect, useRef } from "react";
import Modal from "react-modal";
import "./App.css";

Modal.setAppElement("#root");

function App() {
  const [query, setQuery] = useState("");
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [useInternet, setUseInternet] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isManageModalOpen, setIsManageModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const chatEndRef = useRef(null);
  const [chats, setChats] = useState([{ id: 1, name: "Новый чат", messages: [] }]);
  const [activeChatId, setActiveChatId] = useState(1);
  const [sendButton, setSendButton] = useState("⌯⌲")
  const [activeTab, setActiveTab] = useState("installed_models");

  // Model settings state
  const [modelSettings, setModelSettings] = useState({
    max_tokens: 512,
    temperature: 0.7,
    top_p: 0.9
  });

  useEffect(() => {
    fetchModels();
  }, []);

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chats.find(chat => chat.id === activeChatId)?.messages]);

  const fetchModels = async () => {
    try {
      const res = await fetch("http://127.0.0.1:9015/api/models");
      const data = await res.json();
      setModels(data);
      const installed = data.filter((m) => m.installed);

      if (installed.length > 0) {
        setSelectedModel(installed[0].name);
      } else {
        setSelectedModel("");
      }
    } catch (error) {
      console.error("Ошибка при загрузке моделей:", error);
    }
  };

  const updateModelSettings = async (settings) => {
    try {
      const res = await fetch("http://127.0.0.1:9015/api/update_model_settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });

      if (!res.ok) throw new Error("Ошибка обновления настроек");

      setModelSettings(settings);
      setIsSettingsModalOpen(false);
    } catch (error) {
      console.error("Ошибка обновления настроек:", error);
      alert(`Не удалось обновить настройки: ${error.message}`);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    if (!selectedModel) {
      alert("Выберите модель!");
      return;
    }

    setChats((prevChats) => {
      const updatedChats = prevChats.map((chat) =>
        chat.id === activeChatId
          ? { ...chat, messages: [...chat.messages, { role: "user", text: query }] }
          : chat
      );
      return [
        ...updatedChats.filter(chat => chat.id !== activeChatId),
        updatedChats.find(chat => chat.id === activeChatId)
      ];
    });

    setIsLoading(true);

    try {
      const res = await fetch("http://127.0.0.1:9015/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: query,
          model: selectedModel,
          use_internet: useInternet,
          chat_id: activeChatId.toString(), // Передаем идентификатор чата
          ...modelSettings
        }),
      });

      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();

      setChats((prevChats) => {
        const updatedChats = prevChats.map(chat =>
          chat.id === activeChatId
            ? { ...chat, messages: [...chat.messages, { role: "assistant", text: data.response }] }
            : chat
        );
        return [
          ...updatedChats.filter(chat => chat.id !== activeChatId),
          updatedChats.find(chat => chat.id === activeChatId)
        ];
      });

    } catch (error) {
      console.error("Ошибка запроса:", error);
      setChats((prevChats) => {
        const updatedChats = prevChats.map(chat =>
          chat.id === activeChatId
            ? { ...chat, messages: [...chat.messages, { role: "assistant", text: `Ошибка: ${error.message}` }] }
            : chat
        );
        return [
          ...updatedChats.filter(chat => chat.id !== activeChatId),
          updatedChats.find(chat => chat.id === activeChatId)
        ];
      });
    } finally {
      setIsLoading(false);
      setQuery("");
    }
  };

  const handleSubmitOnKey = async (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleEasterEgg = async (e) => {
    setSendButton("⌯⌲ ▐▐")
  }

  const createNewChat = () => {
    const newChatId = Date.now();
    const newChat = { id: newChatId, name: `Новый чат`, messages: [] };
    setChats([newChat, ...chats]);
    setActiveChatId(newChatId);
  };

  const deleteChat = (id) => {
    if (chats.length === 1) return;
    const updatedChats = chats.filter(chat => chat.id !== id);
    setChats(updatedChats);
    setActiveChatId(updatedChats[0]?.id || 1);
  };

  const setActiveChat = (id) => {
    setActiveChatId(id);
  };

  const handleInstallModel = async (modelName) => {
    try {
      const res = await fetch("http://127.0.0.1:9015/api/install_model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelName }),
      });
      if (!res.ok) throw new Error("Ошибка установки модели");
      fetchModels();
    } catch (error) {
      console.error("Ошибка установки модели:", error);
    }
  };

  const handleDeleteModel = async (modelName) => {
    alert(`Удаление модели ${modelName} пока не реализовано.`);
  };

  return (
    <div className="app-container">
      <div className="sidebar">
        <div className="sidebar-header">
          <button className="new-chat-button" onClick={createNewChat}>
            + Новый чат
          </button>
        </div>
        <div className="chat-list">
          {chats.map((chat) => (
            <div
              key={chat.id}
              className={`chat-tab ${chat.id === activeChatId ? "active" : ""}`}
              onClick={() => setActiveChat(chat.id)}
            >
              <span>{chat.name}</span>
              {chats.length > 1 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteChat(chat.id);
                  }}
                >
                  ✖
                </button>
              )}
            </div>
          ))}
        </div>
        <div className="sidebar-footer">
          <button
            onClick={() => setIsManageModalOpen(true)}
            className="manage-models-button"
          >
            Управление моделями
          </button>
          <button
            onClick={() => setIsSettingsModalOpen(true)}
            className="manage-models-button"
            style={{ marginTop: '10px' }}
          >
            Настройки генерации
          </button>
        </div>
      </div>

      <div className="main-content">
        <header className="header">
          <h1 className="header-title">NeuraBox</h1>
        </header>

        <div className="chat-container">
          {chats.find(chat => chat.id === activeChatId)?.messages.length > 0 ? (
            chats.find(chat => chat.id === activeChatId)?.messages.map((msg, index) => (
              <div
                key={index}
                className={`message ${msg.role === "user" ? "message-user" : "message-assistant"}`}
              >
                {msg.text}
              </div>
            ))
          ) : (
            <p style={{ textAlign: "center", color: "#777" }}>Нет сообщений</p>
          )}

          <div ref={chatEndRef} />
        </div>

        <div className="input-container">
          <div className="input-field-wrapper">
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="model-selector"
            >
              <option value="">Выберите модель</option>
              {models.filter((m) => m.installed).map((model) => (
                <option key={model.name} value={model.name}>
                  {model.name}
                </option>
              ))}
            </select>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Введите запрос..."
              className="input-field"
              rows="2"
              onKeyDown={handleSubmitOnKey}
              disabled={isLoading}
            />
            <button
              type="submit"
              onClick={handleSubmit}
              onDoubleClick={handleEasterEgg}
              disabled={isLoading}
              className="send-button"
            >
              {isLoading ? "..." : sendButton}
            </button>
          </div>
        </div>
      </div>

      <Modal
        isOpen={isManageModalOpen}
        onRequestClose={() => setIsManageModalOpen(false)}
        className="modal"
        overlayClassName="modal-overlay"
      >
        <div className="tab-container">
          <button
            className={`tab-button ${activeTab === "available_models" ? "active" : ""}`}
            onClick={() => setActiveTab("available_models")}
          >
            Доступные модели
          </button>
          <button
            className={`tab-button ${activeTab === "installed_models" ? "active" : ""}`}
            onClick={() => setActiveTab("installed_models")}
          >
            Установленные модели
          </button>
        </div>
        {activeTab === "available_models" && (
          <ul className="model-list">
            {models.map((model) => (
              <li key={model.name} className="model-item">
                <div>
                  <strong>{model.name}</strong>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                    Размер: {model.size || "Неизвестно"} |
                    Параметры: {model.parameters || "Неизвестно"}
                  </div>
                </div>
                {model.installed ? (
                  <button
                    onClick={() => handleDeleteModel(model.name)}
                    className="model-action-button delete"
                  >
                    Удалить
                  </button>
                ) : (
                  <button
                    onClick={() => handleInstallModel(model.name)}
                    className="model-action-button install"
                  >
                    Установить
                  </button>
                )}
              </li>
            ))}
          </ul>)}

        {activeTab === "installed_models" && (
          <ul className="model-list">
            {models.filter((m) => m.installed).map((model) => (
              <li key={model.name} className="model-item">
                <div>
                  <strong>{model.name}</strong>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                    Размер: {model.size || "Неизвестно"} |
                    Параметры: {model.parameters || "Неизвестно"}
                  </div>
                </div>
                {model.installed ? (
                  <button
                    onClick={() => handleDeleteModel(model.name)}
                    className="model-action-button delete"
                  >
                    Удалить
                  </button>
                ) : (
                  <button
                    onClick={() => handleInstallModel(model.name)}
                    className="model-action-button install"
                  >
                    Установить
                  </button>
                )}
              </li>
            ))}
          </ul>)}
      </Modal>

      <Modal
        isOpen={isSettingsModalOpen}
        onRequestClose={() => setIsSettingsModalOpen(false)}
        className="modal"
        overlayClassName="modal-overlay"
      >
        <div className="modal-header">
          <h2>Настройки генерации</h2>
        </div>
        <div className="model-settings">
          <div className="model-settings-input">
            <label>Максимальное количество токенов</label>
            <input
              type="number"
              value={modelSettings.max_tokens}
              onChange={(e) => setModelSettings({
                ...modelSettings,
                max_tokens: parseInt(e.target.value)
              })}
              min="1"
              max="4096"
            />
          </div>
          <div className="model-settings-input">
            <label>Температура</label>
            <input
              type="number"
              step="0.1"
              value={modelSettings.temperature}
              onChange={(e) => setModelSettings({
                ...modelSettings,
                temperature: parseFloat(e.target.value)
              })}
              min="0"
              max="2"
            />
          </div>
          <div className="model-settings-input">
            <label>Top P</label>
            <input
              type="number"
              step="0.1"
              value={modelSettings.top_p}
              onChange={(e) => setModelSettings({
                ...modelSettings,
                top_p: parseFloat(e.target.value)
              })}
              min="0"
              max="1"
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '20px' }}>
            <button
              onClick={() => setIsSettingsModalOpen(false)}
              className="model-action-button delete"
            >
              Отмена
            </button>
            <button
              onClick={() => updateModelSettings(modelSettings)}
              className="model-action-button install"
            >
              Сохранить
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default App;