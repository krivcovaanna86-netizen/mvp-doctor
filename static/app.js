/**
 * МедЗапись AI — Main Application Logic
 */
(function() {
    'use strict';

    // ── State ──
    let currentRecordId = null;
    let processingTimerInterval = null;
    let processingStartTime = 0;

    // ── DOM elements ──
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const els = {
        recordingPanel: $('#recordingPanel'),
        processingPanel: $('#processingPanel'),
        resultPanel: $('#resultPanel'),
        errorPanel: $('#errorPanel'),
        
        btnRecord: $('#btnRecord'),
        btnStop: $('#btnStop'),
        btnUpload: $('#btnUpload'),
        fileInput: $('#fileInput'),
        btnCopy: $('#btnCopy'),
        btnExportPdf: $('#btnExportPdf'),
        btnExportDocx: $('#btnExportDocx'),
        btnNewRecord: $('#btnNewRecord'),
        btnRetry: $('#btnRetry'),
        btnDemo: $('#btnDemo'),
        
        statusBadge: $('#statusBadge'),
        specialtySelect: $('#specialtySelect'),
        patientInfo: $('#patientInfo'),
        timer: $('#timer'),
        
        processingTimer: $('#processingTimer'),
        stepTranscribe: $('#stepTranscribe'),
        stepStructure: $('#stepStructure'),
        stepDone: $('#stepDone'),
        
        resultEditor: $('#resultEditor'),
        transcriptionText: $('#transcriptionText'),
        processingTime: $('#processingTime'),
        resultSpecialty: $('#resultSpecialty'),
        
        errorMessage: $('#errorMessage'),
        toast: $('#toast'),
    };

    // ── Audio Recorder ──
    const recorder = new AudioRecorder({
        onDataAvailable: (blob) => {
            console.log(`Recording complete: ${(blob.size / 1024).toFixed(1)} KB`);
            processAudioBlob(blob);
        },
        onStateChange: (state) => {
            if (state === 'recording') {
                els.btnRecord.classList.add('hidden');
                els.btnStop.classList.remove('hidden');
                els.statusBadge.textContent = 'Идёт запись';
                els.statusBadge.className = 'badge recording';
            } else {
                els.btnRecord.classList.remove('hidden');
                els.btnStop.classList.add('hidden');
            }
        },
        onError: (msg) => {
            showError(msg);
        },
    });

    // ── Event Listeners ──
    els.btnRecord.addEventListener('click', () => recorder.start());
    els.btnStop.addEventListener('click', () => recorder.stop());
    
    els.btnUpload.addEventListener('click', () => els.fileInput.click());
    els.fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            processAudioBlob(file);
        }
        e.target.value = '';
    });

    els.btnDemo.addEventListener('click', runDemo);
    els.btnCopy.addEventListener('click', copyResult);
    els.btnExportPdf.addEventListener('click', () => exportDocument('pdf'));
    els.btnExportDocx.addEventListener('click', () => exportDocument('docx'));
    els.btnNewRecord.addEventListener('click', resetToRecording);
    els.btnRetry.addEventListener('click', resetToRecording);

    // Tab switching
    $$('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            $$('.tab').forEach(t => t.classList.remove('active'));
            $$('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            const target = tab.dataset.tab;
            $(`#tab${target.charAt(0).toUpperCase() + target.slice(1)}`).classList.add('active');
        });
    });

    // ── Core Processing ──

    /**
     * Run demo with pre-baked example.
     */
    async function runDemo() {
        showPanel('processing');
        startProcessingTimer();
        setStep('transcribe');

        try {
            const response = await fetch('/api/demo', { method: 'POST' });
            if (!response.ok) throw new Error('Demo endpoint error');
            await handleSSEStream(response);
        } catch (err) {
            console.error('Demo error:', err);
            stopProcessingTimer();
            showError(err.message || 'Ошибка демо');
        }
    }

    /**
     * Handle an SSE stream response (shared between processAudioBlob and runDemo).
     */
    async function handleSSEStream(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullStructured = '';
        let transcription = '';
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                
                try {
                    const data = JSON.parse(line.slice(6));
                    
                    switch (data.type) {
                        case 'status':
                            break;
                            
                        case 'transcription':
                            transcription = data.text;
                            els.transcriptionText.textContent = transcription;
                            setStep('structure');
                            break;
                            
                        case 'chunk':
                            fullStructured += data.text;
                            if (els.resultPanel.classList.contains('hidden')) {
                                showPanel('result');
                            }
                            renderMarkdown(fullStructured, true);
                            break;
                            
                        case 'done':
                            currentRecordId = data.id;
                            setStep('done');
                            stopProcessingTimer();
                            
                            showPanel('result');
                            renderMarkdown(fullStructured, false);
                            els.transcriptionText.textContent = transcription;
                            
                            const specialty = els.specialtySelect.options[els.specialtySelect.selectedIndex].text;
                            els.processingTime.textContent = `Обработка: ${data.processing_time_sec} сек`;
                            els.resultSpecialty.textContent = specialty;
                            
                            showToast('Медицинская запись готова');
                            break;
                            
                        case 'error':
                            throw new Error(data.message);
                    }
                } catch (parseErr) {
                    if (parseErr.message && !parseErr.message.includes('JSON')) {
                        throw parseErr;
                    }
                }
            }
        }

        if (fullStructured && !currentRecordId) {
            showPanel('result');
            renderMarkdown(fullStructured, false);
            stopProcessingTimer();
        }
    }

    /**
     * Send audio blob to server for processing (streaming mode).
     */
    async function processAudioBlob(blob) {
        showPanel('processing');
        startProcessingTimer();
        setStep('transcribe');

        const formData = new FormData();
        
        // Determine extension for filename
        let ext = '.webm';
        if (blob.type) {
            if (blob.type.includes('ogg')) ext = '.ogg';
            else if (blob.type.includes('mp3') || blob.type.includes('mpeg')) ext = '.mp3';
            else if (blob.type.includes('wav')) ext = '.wav';
            else if (blob.type.includes('mp4') || blob.type.includes('m4a')) ext = '.m4a';
        }
        if (blob.name) {
            // It's a File object from upload
            formData.append('audio', blob, blob.name);
        } else {
            formData.append('audio', blob, `recording${ext}`);
        }
        
        formData.append('specialty', els.specialtySelect.value);
        formData.append('patient_info', els.patientInfo.value.trim());

        try {
            // Use streaming endpoint
            const response = await fetch('/api/process-stream', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Ошибка сервера' }));
                throw new Error(err.detail || `HTTP ${response.status}`);
            }

            await handleSSEStream(response);

        } catch (err) {
            console.error('Processing error:', err);
            stopProcessingTimer();
            showError(err.message || 'Произошла ошибка при обработке');
        }
    }

    // ── Markdown → HTML rendering ──

    function renderMarkdown(md, streaming) {
        let html = md
            // Headers
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            // Bold
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            // Unordered lists
            .replace(/^[-•] (.+)$/gm, '<li>$1</li>')
            // Ordered lists  
            .replace(/^\d+[\.\)] (.+)$/gm, '<li>$1</li>')
            // Paragraphs (double newline)
            .replace(/\n\n/g, '</p><p>')
            // Single newlines in context
            .replace(/\n/g, '<br>');

        // Wrap consecutive <li> in <ul>
        html = html.replace(/((<li>.*?<\/li>\s*<br>?)+)/g, (match) => {
            const cleaned = match.replace(/<br>/g, '');
            return `<ul>${cleaned}</ul>`;
        });

        // Wrap in paragraph
        html = `<p>${html}</p>`;
        
        // Clean empty paragraphs
        html = html.replace(/<p>\s*<\/p>/g, '');

        if (streaming) {
            html += '<span class="streaming-cursor"></span>';
        }

        // Show result panel during streaming
        if (els.resultPanel.classList.contains('hidden')) {
            showPanel('result');
        }

        els.resultEditor.innerHTML = html;
        
        // Auto-scroll to bottom during streaming
        if (streaming) {
            els.resultEditor.scrollTop = els.resultEditor.scrollHeight;
        }
    }

    // ── Export ──

    async function exportDocument(format) {
        try {
            // Get current (possibly edited) text from editor
            const editorText = getEditorMarkdown();
            
            const response = await fetch(`/api/export-text/${format}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: editorText,
                    patient_info: els.patientInfo.value.trim(),
                }),
            });

            if (!response.ok) {
                throw new Error('Ошибка экспорта');
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `med_record_${Date.now()}.${format}`;
            a.click();
            URL.revokeObjectURL(url);
            
            showToast(`Файл .${format.toUpperCase()} скачан`);
        } catch (err) {
            showToast('Ошибка экспорта: ' + err.message, true);
        }
    }

    /**
     * Extract markdown-like text from the contenteditable editor.
     */
    function getEditorMarkdown() {
        const editor = els.resultEditor;
        let md = '';
        
        function walk(node) {
            if (node.nodeType === Node.TEXT_NODE) {
                md += node.textContent;
                return;
            }
            
            if (node.nodeType !== Node.ELEMENT_NODE) return;
            
            const tag = node.tagName.toLowerCase();
            
            switch (tag) {
                case 'h2':
                    md += '\n## ';
                    for (const child of node.childNodes) walk(child);
                    md += '\n\n';
                    return;
                case 'h3':
                    md += '\n### ';
                    for (const child of node.childNodes) walk(child);
                    md += '\n\n';
                    return;
                case 'li':
                    md += '- ';
                    for (const child of node.childNodes) walk(child);
                    md += '\n';
                    return;
                case 'ul':
                case 'ol':
                    for (const child of node.childNodes) walk(child);
                    md += '\n';
                    return;
                case 'br':
                    md += '\n';
                    return;
                case 'p':
                    for (const child of node.childNodes) walk(child);
                    md += '\n\n';
                    return;
                case 'strong':
                case 'b':
                    md += '**';
                    for (const child of node.childNodes) walk(child);
                    md += '**';
                    return;
                case 'em':
                case 'i':
                    md += '*';
                    for (const child of node.childNodes) walk(child);
                    md += '*';
                    return;
                default:
                    for (const child of node.childNodes) walk(child);
            }
        }
        
        for (const child of editor.childNodes) walk(child);
        return md.trim();
    }

    // ── Copy ──

    async function copyResult() {
        const text = getEditorMarkdown();
        try {
            await navigator.clipboard.writeText(text);
            showToast('Текст скопирован');
        } catch {
            // Fallback
            const textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            showToast('Текст скопирован');
        }
    }

    // ── UI Helpers ──

    function showPanel(name) {
        els.recordingPanel.classList.toggle('hidden', name !== 'recording');
        els.processingPanel.classList.toggle('hidden', name !== 'processing');
        els.resultPanel.classList.toggle('hidden', name !== 'result');
        els.errorPanel.classList.toggle('hidden', name !== 'error');
        
        // During streaming, show both processing and result
        if (name === 'result') {
            els.processingPanel.classList.add('hidden');
        }
    }

    function resetToRecording() {
        currentRecordId = null;
        els.timer.textContent = '00:00';
        els.statusBadge.textContent = 'Готов к записи';
        els.statusBadge.className = 'badge';
        els.resultEditor.innerHTML = '';
        els.transcriptionText.textContent = '';
        
        // Reset steps
        [els.stepTranscribe, els.stepStructure, els.stepDone].forEach(s => {
            s.className = 'step';
        });
        
        showPanel('recording');
    }

    function showError(message) {
        els.errorMessage.textContent = message;
        showPanel('error');
    }

    function setStep(step) {
        const steps = { transcribe: els.stepTranscribe, structure: els.stepStructure, done: els.stepDone };
        
        for (const [key, el] of Object.entries(steps)) {
            if (key === step) {
                el.className = 'step active';
            } else if (
                (step === 'structure' && key === 'transcribe') ||
                (step === 'done' && (key === 'transcribe' || key === 'structure'))
            ) {
                el.className = 'step done';
            } else {
                el.className = 'step';
            }
        }
    }

    function startProcessingTimer() {
        processingStartTime = Date.now();
        stopProcessingTimer();
        processingTimerInterval = setInterval(() => {
            const sec = Math.floor((Date.now() - processingStartTime) / 1000);
            els.processingTimer.textContent = `${sec} сек`;
        }, 500);
    }

    function stopProcessingTimer() {
        if (processingTimerInterval) {
            clearInterval(processingTimerInterval);
            processingTimerInterval = null;
        }
    }

    function showToast(message, isError = false) {
        const toast = els.toast;
        toast.textContent = message;
        toast.style.background = isError ? 'var(--danger)' : 'var(--gray-800)';
        toast.classList.remove('hidden');
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.classList.add('hidden'), 300);
        }, 3000);
    }

    // ── Init ──
    console.log('МедЗапись AI initialized');
    
    // Check microphone support
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        els.btnRecord.disabled = true;
        els.btnRecord.title = 'Запись недоступна в этом браузере';
        console.warn('getUserMedia not supported');
    }

})();
