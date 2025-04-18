const {app, BrowserWindow} = require("electron");
const path = require("path");
// --- Добавляем нужные модули ---
const {spawn} = require("child_process"); // Для запуска внешнего процесса
const fs = require("fs"); // Для проверки существования файла
// --- Конец добавления ---

let backendProcess = null; // Переменная для хранения процесса бэкенда
let mainWindow = null; // Переменная для главного окна

function createWindow() {
  mainWindow = new BrowserWindow({ // Используем mainWindow вместо win
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: true, // Оставляем пока для простоты
      contextIsolation: false,
      // preload: path.join(__dirname, 'preload.js') // Пример для contextIsolation: true
    }
  });

  // --- Логика запуска бэкенда ---
  if (app.isPackaged) {
    // В упакованном приложении
    // Путь к backend.exe внутри extraResources
    const backendPath = path.join(process.resourcesPath, "app", "backend", "backend.exe");
    console.log(`Trying to start backend from: ${backendPath}`);

    if (fs.existsSync(backendPath)) {
      backendProcess = spawn(backendPath, [], {
        // Опции для spawn, если нужны (например, cwd)
        // detached: true, // Можно попробовать, если есть проблемы с закрытием
        // stdio: 'ignore' // Можно игнорировать вывод бэкенда, если не нужен в консоли Electron
      });

      backendProcess.stdout.on("data", (data) => {
        console.log(`Backend stdout: ${data}`); // Логируем вывод бэкенда
      });

      backendProcess.stderr.on("data", (data) => {
        console.error(`Backend stderr: ${data}`); // Логируем ошибки бэкенда
      });

      backendProcess.on("close", (code) => {
        console.log(`Backend process exited with code ${code}`);
        backendProcess = null;
        // Можно добавить логику перезапуска или уведомления пользователя
      });

      backendProcess.on("error", (err) => {
        console.error("Failed to start backend process:", err);
        // Уведомить пользователя об ошибке
      });

      console.log("Backend process started.");
    } else {
      console.error(`Backend executable not found at ${backendPath}`);
      // Уведомить пользователя об ошибке
    }
  } else {
    // В режиме разработки бэкенд нужно запускать отдельно (например, в другом терминале)
    console.log("Running in development mode. Start backend manually.");
  }
  // --- Конец логики запуска бэкенда ---


  // Загрузка фронтенда
  if (process.env.NODE_ENV === "development") {
    // Режим разработки: загружаем с сервера React
    mainWindow.loadURL("http://localhost:3000");
    mainWindow.webContents.openDevTools(); // Открываем инструменты разработчика
  } else {
    // Режим продакшена: загружаем собранный index.html
    // Путь может отличаться в зависимости от структуры сборки
    const indexPath = path.join(__dirname, "..", "build", "index.html"); // Путь относительно electron.js
    console.log(`Loading production index from: ${indexPath}`);
    mainWindow.loadFile(indexPath);
    // mainWindow.webContents.openDevTools(); // Раскомментировать для отладки в продакшене
  }


  mainWindow.on("closed", () => {
    mainWindow = null;
    // Бэкенд будет остановлен через app.on('quit')
  });

} // Конец функции createWindow

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// --- Логика остановки бэкенда при выходе ---
app.on("quit", () => {
  console.log("Application quitting...");
  if (backendProcess) {
    console.log("Killing backend process...");
    // Используем kill() для завершения процесса бэкенда
    const killed = backendProcess.kill();
    if (killed) {
      console.log("Backend process killed successfully.");
    } else {
      console.log("Failed to kill backend process (it might have already exited).");
    }
  }
});
// --- Конец логики остановки ---


app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});