# МедЗапись — AI-ассистент врача

Веб-приложение для автоматического формирования структурированных медицинских записей из голосовых записей приёма пациента.

## Возможности

- **Запись голоса** прямо во время приёма (через браузер)
- **Загрузка аудиофайлов** (MP3, WAV, OGG, WebM)
- **Распознавание речи** (OpenAI Whisper API)
- **Структурирование** в формат медицинской карты с помощью LLM
- **Редактирование** результата прямо в браузере
- **Экспорт** в PDF и DOCX
- **Шаблоны** для разных специализаций (терапевт, педиатрия, хирургия)

## Структура медицинской записи

- Жалобы
- Анамнез заболевания
- Анамнез жизни
- Объективный осмотр
- Предварительный диагноз
- План обследования
- Лечение и рекомендации

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn
- **STT**: OpenAI Whisper API
- **LLM**: GPT-5 (через OpenAI-совместимый API)
- **Export**: python-docx (DOCX), ReportLab (PDF)
- **Database**: SQLite (MVP)
- **Frontend**: Vanilla JS, CSS (без фреймворков — минимальный размер)

## Запуск

```bash
pip install -r requirements.txt
python run.py
```

Приложение будет доступно по адресу http://localhost:8000

## Переменные окружения

```
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
```

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/health` | Health check |
| GET | `/api/specialties` | Список специализаций |
| POST | `/api/process` | Обработка аудио (синхронно) |
| POST | `/api/process-stream` | Обработка аудио (стриминг SSE) |
| POST | `/api/demo` | Демо с примером приёма |
| GET | `/api/export/{id}/{fmt}` | Экспорт записи (pdf/docx) |
| POST | `/api/export-text/{fmt}` | Экспорт произвольного текста |
| GET | `/api/records` | Список записей |
| GET | `/api/records/{id}` | Детали записи |

## Архитектура

```
webapp/
├── run.py                 # Entry point
├── backend/
│   └── app/
│       ├── main.py        # FastAPI app + endpoints
│       ├── config.py      # Configuration
│       ├── database.py    # SQLite storage
│       ├── transcribe.py  # Whisper STT service
│       ├── llm.py         # LLM structuring service
│       ├── prompts.py     # Medical prompts & templates
│       └── export.py      # PDF/DOCX export
├── static/
│   ├── index.html         # SPA frontend
│   ├── style.css          # UI styles
│   ├── recorder.js        # Audio recording module
│   └── app.js             # Main app logic
├── uploads/               # Uploaded audio files
└── exports/               # Generated documents
```
