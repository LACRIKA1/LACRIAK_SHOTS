# ShareX Analog

Локальный аналог ShareX для дипломного проекта. Приложение написано на Python и PySide6, работает без облачных сервисов и сохраняет данные только на компьютере пользователя.

## Что реализовано

- захват всего экрана, выбранного монитора, активного окна и окна из списка;
- интерактивный оверлей для выделения произвольной области;
- захват объекта под курсором после короткой задержки;
- автоматическое именование файлов по шаблону с датой, временем и названием окна;
- локальная история созданных файлов;
- копирование изображения в системный буфер обмена после захвата;
- запись экрана в MP4 и GIF в отдельном потоке;
- автозахват по таймеру;
- глобальные горячие клавиши через низкоуровневые Windows hooks, включая `Page Up`, `C+V`, `Ctrl+Page Up`, кнопки мыши и колесо;
- встроенный редактор аннотаций: карандаш, линия, стрелка, прямоугольник, эллипс, текст, масштабирование, автосохранение в буфер при закрытии;
- настройки папки, формата, шаблона имени, задержки, FPS и горячих клавиш.

## Запуск

1. Создайте виртуальное окружение:

```powershell
python -m venv venv
```

2. Установите зависимости:

```powershell
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

3. Запустите приложение:

```powershell
.\venv\Scripts\python.exe .\main.py
```

## Автономная Windows-сборка

Для подготовки `ShareXAnalog.exe` установите PyInstaller и выполните:

```powershell
.\venv\Scripts\python.exe -m pip install pyinstaller
.\venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed --icon .\assets\sharex_analog_icon.ico --name ShareXAnalog .\main.py
```

Готовый файл появится в `dist/ShareXAnalog.exe`. Конечному пользователю не требуется устанавливать Python.

## Проверка

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe .\scripts\smoke_check.py
.\venv\Scripts\python.exe -m compileall -q .\main.py .\core .\scripts
```

## Горячие клавиши по умолчанию

- `Print Screen` - захват всего экрана;
- `Ctrl + Print Screen` - захват области;
- `Alt + Print Screen` - захват активного окна;
- `Shift + Print Screen` - старт/стоп записи MP4;
- `Ctrl + Shift + Print Screen` - старт/стоп записи GIF.

## Локальные данные

- `captures/` - сохраненные скриншоты, GIF и MP4;
- `data/settings.json` - настройки приложения;
- `data/history.json` - история захватов.

Локальные данные, снимки и автономные сборки не добавляются в Git-репозиторий.

## Структура проекта

- `main.py` - точка входа и главное окно;
- `core/capture.py` - захват экрана и буфер обмена;
- `core/hotkeys.py` - глобальные сочетания клавиатуры и мыши;
- `core/editor.py` - редактор аннотаций;
- `core/recorder.py` - запись MP4 и GIF;
- `core/storage.py` - локальная история;
- `assets/` - логотип и значок приложения;
- `scripts/smoke_check.py` - воспроизводимая smoke-проверка.
