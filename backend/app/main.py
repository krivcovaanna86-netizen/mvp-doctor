"""Main FastAPI application — МедЗапись AI."""

import time
import uuid
import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import (
    HTMLResponse, JSONResponse, StreamingResponse, FileResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config import (
    APP_TITLE, APP_VERSION, UPLOADS_DIR, EXPORTS_DIR,
    STATIC_DIR, MAX_AUDIO_SIZE_MB, ALLOWED_AUDIO_TYPES,
)
from .database import init_db, create_record, update_record, get_record, get_recent_records
from .transcribe import transcribe_audio
from .llm import structure_medical_text, structure_medical_text_stream
from .export import export_to_docx, export_to_pdf
from .prompts import SPECIALTY_TEMPLATES

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# --- App init ---
app = FastAPI(title=APP_TITLE, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup():
    init_db()
    logger.info(f"🏥 {APP_TITLE} v{APP_VERSION} started")


# ─────────────────────────────────────────────
# API endpoints
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main SPA page."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(500, "Frontend not built")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/specialties")
async def list_specialties():
    """List available specialty templates."""
    return {
        key: {"name": val["name"], "sections": val["sections"]}
        for key, val in SPECIALTY_TEMPLATES.items()
    }


@app.post("/api/process")
async def process_audio(
    audio: UploadFile = File(...),
    specialty: str = Form("general"),
    patient_info: str = Form(""),
):
    """
    Main endpoint: upload audio → transcribe → structure → return result.
    """
    start_time = time.time()
    
    # --- Validate ---
    content_type = audio.content_type or ""
    if content_type not in ALLOWED_AUDIO_TYPES and not content_type.startswith("audio/"):
        raise HTTPException(400, f"Неподдерживаемый формат аудио: {content_type}")
    
    contents = await audio.read()
    size_mb = len(contents) / (1024 * 1024)
    
    if size_mb > MAX_AUDIO_SIZE_MB:
        raise HTTPException(400, f"Файл слишком большой: {size_mb:.1f}MB (макс. {MAX_AUDIO_SIZE_MB}MB)")
    
    # --- Save audio file ---
    ext = _get_extension(audio.filename or "audio.webm", content_type)
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    file_path = UPLOADS_DIR / filename
    file_path.write_bytes(contents)
    
    logger.info(f"Audio saved: {filename} ({size_mb:.2f}MB, {content_type})")
    
    # --- Create DB record ---
    record_id = create_record(filename, len(contents), specialty, patient_info)
    
    try:
        # --- Step 1: Transcribe ---
        transcription = await transcribe_audio(file_path, language="ru")
        
        if not transcription or len(transcription.strip()) < 10:
            update_record(record_id, status="error", transcription="[Пустая транскрипция]")
            raise HTTPException(422, "Не удалось распознать речь в аудиозаписи. Попробуйте записать заново.")
        
        update_record(record_id, transcription=transcription, status="structuring")
        
        # --- Step 2: Structure with LLM ---
        structured = await structure_medical_text(transcription, specialty)
        
        elapsed = time.time() - start_time
        update_record(
            record_id,
            structured_text=structured,
            status="done",
            processing_time_sec=round(elapsed, 2),
        )
        
        logger.info(f"Record #{record_id} processed in {elapsed:.1f}s")
        
        return {
            "id": record_id,
            "transcription": transcription,
            "structured_text": structured,
            "specialty": specialty,
            "processing_time_sec": round(elapsed, 2),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        update_record(record_id, status="error", processing_time_sec=round(elapsed, 2))
        logger.exception(f"Processing error for record #{record_id}")
        raise HTTPException(500, f"Ошибка обработки: {str(e)}")


@app.post("/api/process-stream")
async def process_audio_stream(
    audio: UploadFile = File(...),
    specialty: str = Form("general"),
    patient_info: str = Form(""),
):
    """
    Streaming version: transcribes then streams LLM output via SSE.
    """
    content_type = audio.content_type or ""
    contents = await audio.read()
    size_mb = len(contents) / (1024 * 1024)
    
    if size_mb > MAX_AUDIO_SIZE_MB:
        raise HTTPException(400, f"Файл слишком большой")
    
    ext = _get_extension(audio.filename or "audio.webm", content_type)
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    file_path = UPLOADS_DIR / filename
    file_path.write_bytes(contents)
    
    record_id = create_record(filename, len(contents), specialty, patient_info)
    
    async def generate():
        import json
        start = time.time()
        
        try:
            # Transcription phase
            yield f"data: {json.dumps({'type': 'status', 'message': 'Распознавание речи...'})}\n\n"
            
            transcription = await transcribe_audio(file_path, language="ru")
            
            if not transcription or len(transcription.strip()) < 10:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Не удалось распознать речь'})}\n\n"
                return
            
            yield f"data: {json.dumps({'type': 'transcription', 'text': transcription})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'message': 'Формирование медицинской записи...'})}\n\n"
            
            update_record(record_id, transcription=transcription, status="structuring")
            
            # LLM streaming phase
            full_text = ""
            async for chunk in structure_medical_text_stream(transcription, specialty):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
            
            elapsed = time.time() - start
            update_record(
                record_id,
                structured_text=full_text,
                status="done",
                processing_time_sec=round(elapsed, 2),
            )
            
            yield f"data: {json.dumps({'type': 'done', 'id': record_id, 'processing_time_sec': round(elapsed, 2)})}\n\n"
        
        except Exception as e:
            logger.exception("Stream processing error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/export/{record_id}/{fmt}")
async def export_record(record_id: int, fmt: str):
    """Export a record to PDF or DOCX."""
    if fmt not in ("pdf", "docx"):
        raise HTTPException(400, "Формат должен быть 'pdf' или 'docx'")
    
    record = get_record(record_id)
    if not record:
        raise HTTPException(404, "Запись не найдена")
    
    if not record["structured_text"]:
        raise HTTPException(422, "Запись ещё не обработана")
    
    patient = record.get("patient_info", "")
    
    if fmt == "docx":
        content = export_to_docx(record["structured_text"], patient)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"med_record_{record_id}.docx"
    else:
        content = export_to_pdf(record["structured_text"], patient)
        media_type = "application/pdf"
        filename = f"med_record_{record_id}.pdf"
    
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/export-text/{fmt}")
async def export_text(fmt: str, request: Request):
    """Export arbitrary text (e.g. edited text) to PDF or DOCX."""
    if fmt not in ("pdf", "docx"):
        raise HTTPException(400, "Формат должен быть 'pdf' или 'docx'")
    
    body = await request.json()
    text = body.get("text", "")
    patient_info = body.get("patient_info", "")
    
    if not text:
        raise HTTPException(400, "Текст не может быть пустым")
    
    if fmt == "docx":
        content = export_to_docx(text, patient_info)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"med_record_{int(time.time())}.docx"
    else:
        content = export_to_pdf(text, patient_info)
        media_type = "application/pdf"
        filename = f"med_record_{int(time.time())}.pdf"
    
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/records")
async def list_records():
    """List recent records."""
    return get_recent_records(20)


@app.get("/api/records/{record_id}")
async def get_record_detail(record_id: int):
    """Get full record details."""
    record = get_record(record_id)
    if not record:
        raise HTTPException(404, "Запись не найдена")
    return record


@app.post("/api/demo")
async def demo_process():
    """
    Demo endpoint: returns a pre-baked example showing the full pipeline result.
    Useful for testing the UI without a working API key.
    """
    import json
    import asyncio

    demo_transcription = (
        "Ну здравствуйте, проходите, садитесь. На что жалуетесь? "
        "Доктор, у меня уже неделю болит голова, вот тут вот, в висках. И давление стало подниматься. "
        "А какие цифры давления? Ну я мерила, было 160 на 100, а вчера вообще 170 на 105. "
        "А раньше такое было? Давление повышалось? Ну так, иногда, но не так сильно. "
        "Таблетки какие-нибудь принимаете? Нет, я ничего не пила. "
        "Мама моя тоже гипертоник была, умерла от инсульта. "
        "Аллергии на лекарства есть? Нет, вроде нет. "
        "Давайте я вас посмотрю. Давление сейчас 158 на 96. Пульс 78. "
        "Сердце — тоны ритмичные, шумов нет. Лёгкие чистые. Живот мягкий. "
        "У вас артериальная гипертензия второй степени. Нужно обследоваться. "
        "Назначу общий анализ крови, биохимию, ЭКГ и УЗИ почек. "
        "Из лечения — лизиноприл, 10 миллиграмм, один раз в день утром. "
        "Ведите дневник давления. Соль ограничьте. Придёте через две недели."
    )

    demo_structured = """## ЖАЛОБЫ

- Головная боль в височной области, беспокоит в течение 1 недели
- Повышение артериального давления до 170/105 мм рт. ст.

## АНАМНЕЗ ЗАБОЛЕВАНИЯ

Головные боли в височной области беспокоят в течение последней недели. Отмечает ежедневное повышение артериального давления, максимальные зафиксированные цифры — 170/105 мм рт. ст. Ранее эпизодически отмечала повышение АД, но менее выраженное. Антигипертензивную терапию ранее не получала. Самостоятельно лекарственных препаратов не принимала.

## АНАМНЕЗ ЖИЗНИ

- Наследственность: мать страдала артериальной гипертензией, умерла от острого нарушения мозгового кровообращения (ОНМК)
- Аллергологический анамнез: не отягощён
- Хронические заболевания: данные не предоставлены
- Перенесённые операции: данные не предоставлены

## ОБЪЕКТИВНЫЙ ОСМОТР

- АД: 158/96 мм рт. ст.
- ЧСС: 78 уд/мин
- Аускультация сердца: тоны ритмичные, ясные, патологические шумы не выслушиваются
- Аускультация лёгких: дыхание везикулярное, хрипов нет
- Пальпация живота: живот мягкий, безболезненный

## ПРЕДВАРИТЕЛЬНЫЙ ДИАГНОЗ

Артериальная гипертензия II степени. Отягощённый наследственный анамнез по сердечно-сосудистым заболеваниям.

## ПЛАН ОБСЛЕДОВАНИЯ

1. Общий анализ крови (ОАК)
2. Биохимический анализ крови (липидный спектр, глюкоза, креатинин, мочевина, калий, натрий)
3. Электрокардиография (ЭКГ)
4. Ультразвуковое исследование (УЗИ) почек

## ЛЕЧЕНИЕ И РЕКОМЕНДАЦИИ

1. Лизиноприл 10 мг — 1 раз в сутки, утром, внутрь
2. Ведение дневника самоконтроля артериального давления (измерение утром и вечером)
3. Ограничение потребления поваренной соли до 5 г/сутки
4. Явка на повторный приём через 2 недели с результатами обследований и дневником АД"""

    async def generate():
        yield f"data: {json.dumps({'type': 'status', 'message': 'Распознавание речи...'})}\n\n"
        await asyncio.sleep(1.0)

        yield f"data: {json.dumps({'type': 'transcription', 'text': demo_transcription})}\n\n"
        yield f"data: {json.dumps({'type': 'status', 'message': 'Формирование медицинской записи...'})}\n\n"
        await asyncio.sleep(0.5)

        # Simulate streaming output
        words = demo_structured.split(' ')
        chunk = ''
        for i, word in enumerate(words):
            chunk = word + ' '
            if word.endswith('\n'):
                chunk = word
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
            if i % 5 == 0:
                await asyncio.sleep(0.05)

        record_id = create_record("demo.webm", 0, "general", "Демонстрация")
        update_record(
            record_id,
            transcription=demo_transcription,
            structured_text=demo_structured,
            status="done",
            processing_time_sec=4.2,
        )

        yield f"data: {json.dumps({'type': 'done', 'id': record_id, 'processing_time_sec': 4.2})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _get_extension(filename: str, content_type: str) -> str:
    """Determine file extension."""
    ext_map = {
        "audio/webm": ".webm",
        "video/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/mp3": ".mp3",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/flac": ".flac",
    }
    
    if content_type in ext_map:
        return ext_map[content_type]
    
    suffix = Path(filename).suffix
    return suffix if suffix else ".webm"
