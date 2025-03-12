import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState('');
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [useInternet, setUseInternet] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      const res = await fetch('http://localhost:8000/models');
      const data = await res.json();
      setModels(data);
      setSelectedModel(data[0]?.name || '');
    } catch (error) {
      console.error('Error fetching models:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    try {
      const res = await fetch('http://localhost:8000/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: query,
          model: selectedModel,
          use_internet: useInternet
        })
      });

      if (!res.ok) throw new Error(res.statusText);

      const data = await res.json();
      setResponse(data.response);
    } catch (error) {
      console.error('Error:', error);
      setResponse(`Error: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>AI Assistant</h1>
      </header>

      <div className="controls">
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          className="model-selector"
        >
          {models.map(model => (
            <option key={model.name} value={model.name}>
              {model.name}
            </option>
          ))}
        </select>

        <label className="internet-toggle">
          <input
            type="checkbox"
            checked={useInternet}
            onChange={(e) => setUseInternet(e.target.checked)}
          />
          Use Internet
        </label>
      </div>

      <form onSubmit={handleSubmit} className="query-form">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your question..."
          disabled={isLoading}
        />
        <button
          type="submit"
          disabled={isLoading}
          className={isLoading ? 'loading' : ''}
        >
          {isLoading ? 'Processing...' : 'Ask'}
        </button>
      </form>

      <div className="response-container">
        <pre className="response-content">{response}</pre>
      </div>
    </div>
  );
}

export default App;