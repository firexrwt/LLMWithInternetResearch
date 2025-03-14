import React, { useState, useEffect, useRef } from "react";
import Modal from "react-modal";
import { FiChevronDown } from "react-icons/fi";
import "./App.css";

Modal.setAppElement("#root");

function App() {
  const [query, setQuery] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [useInternet, setUseInternet] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isManageModalOpen, setIsManageModalOpen] = useState(false);
  const chatEndRef = useRef(null);

  // При загрузке получаем список моделей (с сервера, для управления)
  useEffect(() => {
    fetchModels();
  }, []);

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatHistory]);

  const fetchModels = async () => {
    try {
      const res = await fetch("http://127.0.0.1:9015/api/models");
      const data = await res.json();
      // Предполагаем, что сервер возвращает поля: name, file_name, installed, а также, возможно, size и parameters (если доступны)
      setModels(data);
      // Для выпадающего списка выбираем только установленные модели
      const installed = data.filter((m) => m.installed);
      if (installed.length > 0) {
        setSelectedModel(installed[0].name);
      }
    } catch (error) {
      console.error("Ошибка при загрузке моделей:", error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    setChatHistory([...chatHistory, { role: "user", text: query }]);
    setIsLoading(true);
    try {
      const res = await fetch("http://127.0.0.1:9015/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: query,
          model: selectedModel,
          use_internet: useInternet,
        }),
      });
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      setChatHistory((prev) => [...prev, { role: "assistant", text: data.response }]);
    } catch (error) {
      console.error("Ошибка запроса:", error);
      setChatHistory((prev) => [
        ...prev,
        { role: "assistant", text: `Ошибка: ${error.message}` },
      ]);
    } finally {
      setIsLoading(false);
      setQuery("");
    }
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
    // Здесь можно добавить логику удаления модели с локального хранилища,
    // например, вызов API, который удаляет файл.
    // Пока покажем заглушку.
    alert(`Удаление модели ${modelName} пока не реализовано.`);
  };

  return (
    <div className="app-container">
      {/* Заголовок */}
      <header className="header">
        <h1 className="header-title">AI Assistant</h1>
        <button onClick={() => setIsManageModalOpen(true)} className="manage-models-button">
          Управление моделями
        </button>
      </header>

      {/* История чата */}
      <div className="chat-container">
        {chatHistory.length > 0 ? (
          chatHistory.map((msg, index) => (
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

      {/* Поле ввода с выпадающим списком установленных моделей */}
      <div className="input-container">
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          className="model-selector"
        >
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
          disabled={isLoading}
        />
        <button type="submit" onClick={handleSubmit} disabled={isLoading} className="send-button">
          {isLoading ? "..." : "Отправить"}
        </button>
      </div>

      {/* Модальное окно управления моделями */}
      <Modal
        isOpen={isManageModalOpen}
        onRequestClose={() => setIsManageModalOpen(false)}
        className="modal"
        overlayClassName="modal-overlay"
      >
        <h2>Доступные модели</h2>
        <div className="modal-content">
          {models.length > 0 ? (
            <ul className="model-list">
              {models.map((model) => (
                <li key={model.name} className="model-item">
                  <div className="model-info">
                    <strong>{model.name}</strong>
                    <div className="model-details">
                      <span>Размер: {model.size || "Неизвестно"}</span>
                      <span>Параметры: {model.parameters || "Неизвестно"}</span>
                    </div>
                  </div>
                  {model.installed ? (
                    <button onClick={() => handleDeleteModel(model.name)} className="model-action-button delete">
                      Удалить
                    </button>
                  ) : (
                    <button onClick={() => handleInstallModel(model.name)} className="model-action-button install">
                      Установить
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p>Модели загружаются...</p>
          )}
        </div>
        <button onClick={() => setIsManageModalOpen(false)} className="manage-models-button">
          Закрыть
        </button>
      </Modal>
    </div>
  );
}

export default App;
