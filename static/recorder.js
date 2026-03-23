/**
 * AudioRecorder — handles microphone recording with waveform visualization.
 * Uses MediaRecorder API with WebM/Opus or fallback codecs.
 */
class AudioRecorder {
    constructor(options = {}) {
        this.onDataAvailable = options.onDataAvailable || (() => {});
        this.onStateChange = options.onStateChange || (() => {});
        this.onError = options.onError || (() => {});
        
        this.mediaRecorder = null;
        this.stream = null;
        this.chunks = [];
        this.state = 'idle'; // idle | recording | stopped
        this.startTime = 0;
        this.timerInterval = null;
        
        // Waveform visualization
        this.audioContext = null;
        this.analyser = null;
        this.animationFrame = null;
    }

    /**
     * Start recording from the microphone.
     */
    async start() {
        try {
            // Request microphone access
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
            });

            // Determine best available codec
            const mimeType = this._getBestMimeType();
            
            this.mediaRecorder = new MediaRecorder(this.stream, {
                mimeType,
                audioBitsPerSecond: 64000,
            });

            this.chunks = [];

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    this.chunks.push(e.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                const blob = new Blob(this.chunks, { type: mimeType });
                this.chunks = [];
                this._setState('stopped');
                this.onDataAvailable(blob);
            };

            this.mediaRecorder.onerror = (e) => {
                console.error('MediaRecorder error:', e);
                this.onError(e.error?.message || 'Ошибка записи');
            };

            // Start recording with 1-second timeslices
            this.mediaRecorder.start(1000);
            this.startTime = Date.now();
            this._setState('recording');
            
            // Set up waveform visualization
            this._setupVisualizer();
            
            // Start timer
            this._startTimer();
            
        } catch (err) {
            console.error('Microphone access error:', err);
            if (err.name === 'NotAllowedError') {
                this.onError('Доступ к микрофону запрещён. Разрешите доступ в настройках браузера.');
            } else if (err.name === 'NotFoundError') {
                this.onError('Микрофон не найден. Подключите микрофон и попробуйте снова.');
            } else {
                this.onError(`Ошибка доступа к микрофону: ${err.message}`);
            }
        }
    }

    /**
     * Stop recording.
     */
    stop() {
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
        }
        this._stopTimer();
        this._stopVisualizer();
        this._releaseStream();
    }

    /**
     * Get elapsed recording time in seconds.
     */
    getElapsed() {
        if (this.startTime === 0) return 0;
        return Math.floor((Date.now() - this.startTime) / 1000);
    }

    // ── Private methods ──

    _getBestMimeType() {
        const candidates = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
        ];
        for (const mt of candidates) {
            if (MediaRecorder.isTypeSupported(mt)) return mt;
        }
        return ''; // browser default
    }

    _setState(state) {
        this.state = state;
        this.onStateChange(state);
    }

    _startTimer() {
        this._stopTimer();
        this.timerInterval = setInterval(() => {
            const el = document.getElementById('timer');
            if (el) {
                const sec = this.getElapsed();
                const m = String(Math.floor(sec / 60)).padStart(2, '0');
                const s = String(sec % 60).padStart(2, '0');
                el.textContent = `${m}:${s}`;
            }
        }, 500);
    }

    _stopTimer() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }

    _setupVisualizer() {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            
            const source = this.audioContext.createMediaStreamSource(this.stream);
            source.connect(this.analyser);
            
            const canvas = document.getElementById('waveformCanvas');
            const container = document.getElementById('waveformContainer');
            if (canvas && container) {
                container.classList.add('active');
                this._drawWaveform(canvas);
            }
        } catch (e) {
            console.warn('Waveform visualization not available:', e);
        }
    }

    _drawWaveform(canvas) {
        const ctx = canvas.getContext('2d');
        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const draw = () => {
            if (this.state !== 'recording') return;
            this.animationFrame = requestAnimationFrame(draw);

            // Adjust canvas size
            canvas.width = canvas.offsetWidth * (window.devicePixelRatio || 1);
            canvas.height = canvas.offsetHeight * (window.devicePixelRatio || 1);
            const w = canvas.width;
            const h = canvas.height;

            this.analyser.getByteFrequencyData(dataArray);

            ctx.clearRect(0, 0, w, h);
            
            const barWidth = Math.max(2, (w / bufferLength) * 1.5);
            const gap = 1;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                const v = dataArray[i] / 255.0;
                const barHeight = v * h * 0.85;

                // Gradient from blue to red based on intensity
                const r = Math.floor(26 + v * 191);
                const g = Math.floor(115 - v * 70);
                const b = Math.floor(232 - v * 195);
                
                ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.8)`;
                ctx.fillRect(x, (h - barHeight) / 2, barWidth, barHeight);
                
                x += barWidth + gap;
                if (x > w) break;
            }
        };

        draw();
    }

    _stopVisualizer() {
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
            this.animationFrame = null;
        }
        const container = document.getElementById('waveformContainer');
        if (container) container.classList.remove('active');
        
        if (this.audioContext) {
            this.audioContext.close().catch(() => {});
            this.audioContext = null;
        }
    }

    _releaseStream() {
        if (this.stream) {
            this.stream.getTracks().forEach(t => t.stop());
            this.stream = null;
        }
    }
}

// Export globally
window.AudioRecorder = AudioRecorder;
