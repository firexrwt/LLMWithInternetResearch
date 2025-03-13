import React, { useState, useEffect, useRef } from "react";
import Modal from "react-modal";
import { FiChevronDown } from "react-icons/fi";

Modal.setAppElement("#root");

function App() {
  const [query, setQuery] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [useInternet, setUseInternet] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isModelModalOpen, setIsModelModalOpen] = useState(false);
  const [isFullModelsModalOpen, setIsFullModelsModalOpen] = useState(false);
  const [loadingModels, setLoadingModels] = useState(true);

  const chatEndRef = useRef(null);

  useEffect(() => {
    fetchModels();
  }, []);

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatHistory]);

  const fetchModels = async () => {
    setLoadingModels(true);
    try {
      const res = await fetch("http://127.0.0.1:9015/api/models");
      const data = await res.json();
      setModels(data);
      // Если есть хоть одна установленная модель, выбираем её
      const installed = data.filter((m) => m.installed);
      if (installed.length > 0) {
        setSelectedModel(installed[0].name);
      }
    } catch (error) {
      console.error("Ошибка при загрузке моделей:", error);
    } finally {
      setLoadingModels(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    const userMessage = { role: "user", text: query };
    setChatHistory([...chatHistory, userMessage]);
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
      const assistantMessage = { role: "assistant", text: data.response };
      setChatHistory((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Ошибка запроса:", error);
      const errorMessage = { role: "assistant", text: `Ошибка: ${error.message}` };
      setChatHistory((prev) => [...prev, errorMessage]);
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
      const data = await res.json();
      // После успешной установки обновляем список моделей
      fetchModels();
    } catch (error) {
      console.error("Ошибка установки модели:", error);
    }
  };

  return (
    /*FIXME: ЭТО ЧЕ НАХУЙ ТАКОЕ БЛЯТЬ?!?!?!? ДЛЯ КОГО CSS ПРИДУМАЛИ, ДИБИЛЫЧ СУКА?!?!? ЧТОБ РАЗОБРАЛСЯ И ПОФИКСИЛ НАХУЙ*/ 
    <div className="flex flex-col h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="p-4 border-b border-gray-700 flex justify-between items-center rounded-[25px] m-4">
        <h1 className="text-2xl font-bold">AI Assistant</h1>
        <button
          onClick={() => setIsFullModelsModalOpen(true)}
          className="bg-gray-700 hover:bg-gray-600 text-white py-2 px-4 rounded-[25px]"
        >
          Управление моделями
        </button>
      </header>

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatHistory.map((msg, index) => (
          <div
            key={index}
            className={`max-w-xs p-3 rounded-[25px] ${
              msg.role === "user"
                ? "bg-blue-500 self-end"
                : "bg-gray-700 self-start"
            }`}
          >
            {msg.text}
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Input Section */}
      <div className="p-4 border-t border-gray-700 rounded-[25px] m-4">
        <div className="flex items-center mb-2">
          {/* Кнопка выбора модели (встроенная в область ввода) */}
          <button
            onClick={() => setIsModelModalOpen(true)}
            className="flex items-center bg-gray-800 hover:bg-gray-700 text-white py-1 px-2 rounded-[25px] mr-2"
          >
            {selectedModel ? selectedModel : "Выбрать модель"}
            <FiChevronDown className="ml-1" />
          </button>
          {/* Чекбокс "Использовать интернет" */}
          <label className="flex items-center space-x-1">
            <input
              type="checkbox"
              checked={useInternet}
              onChange={(e) => setUseInternet(e.target.checked)}
              className="form-checkbox"
            />
            <span className="text-sm">Интернет</span>
          </label>
        </div>
        <form onSubmit={handleSubmit} className="flex">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Введите запрос..."
            className="flex-1 bg-gray-800 text-white p-2 rounded-l-[25px] resize-none"
            rows="2"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading}
            className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-r-[25px]"
          >
            {isLoading ? "..." : "Отправить"}
          </button>
        </form>
      </div>

      {/* Модальное окно для выбора установленных моделей */}
      <Modal
        isOpen={isModelModalOpen}
        onRequestClose={() => setIsModelModalOpen(false)}
        className="bg-gray-900 text-white p-6 rounded-[25px] shadow-lg max-w-md mx-auto mt-20 outline-none"
        overlayClassName="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-start"
      >
        <h2 className="text-xl font-bold mb-4">Выберите установленную модель</h2>
        {models.filter(m => m.installed).length > 0 ? (
          <ul>
            {models
              .filter((model) => model.installed)
              .map((model) => (
                <li key={model.name}>
                  <button
                    onClick={() => {
                      setSelectedModel(model.name);
                      setIsModelModalOpen(false);
                    }}
                    className="w-full text-left py-2 px-4 hover:bg-gray-800 rounded-[25px]"
                  >
                    {model.name}
                  </button>
                </li>
              ))}
          </ul>
        ) : (
          <p>Нет установленных моделей.</p>
        )}
        <button
          onClick={() => setIsModelModalOpen(false)}
          className="mt-4 bg-red-500 hover:bg-red-700 text-white py-2 px-4 rounded-[25px]"
        >
          Закрыть
        </button>
      </Modal>

      {/* Модальное окно для полного списка моделей с кнопками установки */}
      <Modal
        isOpen={isFullModelsModalOpen}
        onRequestClose={() => setIsFullModelsModalOpen(false)}
        className="bg-gray-900 text-white p-6 rounded-[25px] shadow-lg max-w-lg mx-auto mt-20 outline-none"
        overlayClassName="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-start"
      >
        <h2 className="text-xl font-bold mb-4">Доступные модели на Hugging Face</h2>
        {models.length > 0 ? (
          <ul className="space-y-2 max-h-80 overflow-y-auto">
            {models.map((model) => (
              <li key={model.name} className="flex justify-between items-center">
                <span>{model.name}</span>
                {model.installed ? (
                  /* FIXME: Кста, тут отступа не хватает от правого края */
                  <span className="text-sm text-green-400">Установлена</span>
                ) : (
                  <button
                    onClick={() => handleInstallModel(model.name)}
                    className="bg-blue-500 hover:bg-blue-700 text-white py-1 px-3 rounded-[25px] text-sm"
                  >
                    Установить
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p>Модели загружаются...</p>
        )}
        <button
          onClick={() => setIsFullModelsModalOpen(false)}
          className="mt-4 bg-red-500 hover:bg-red-700 text-white py-2 px-4 rounded-[25px]"
        >
          Закрыть
        </button>
      </Modal>
    </div>
  );
}

export default App;
