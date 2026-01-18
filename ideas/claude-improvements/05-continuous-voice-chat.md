# Continuous Voice Chat Implementation

## Overview
Implement always-on voice interaction with Claude using Whisper for transcription, enabling hands-free coding and natural conversation flow.

## Architecture

### Components
```
┌─────────────────────────────────────────────┐
│                Browser/Client                │
├─────────────────────────────────────────────┤
│  Audio Input  →  VAD  →  WebRTC Streaming   │
│       ↓           ↓            ↓             │
│  Waveform Viz   Detection   Audio Chunks    │
└────────────────┬────────────────────────────┘
                 │ WebSocket
┌────────────────▼────────────────────────────┐
│             Claude Backend                   │
├─────────────────────────────────────────────┤
│  Audio Buffer → Whisper API → Transcription │
│       ↓            ↓              ↓         │
│  Chunking      GPU Inference   Text Output  │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│          Whisper GPU Service                 │
├─────────────────────────────────────────────┤
│  Model: whisper-large-v3                     │
│  Hardware: NVIDIA GPU (via GPU Operator)     │
│  Framework: faster-whisper or whisper.cpp    │
└─────────────────────────────────────────────┘
```

## Whisper Deployment

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: whisper-service
  namespace: claude
spec:
  replicas: 1
  selector:
    matchLabels:
      app: whisper
  template:
    metadata:
      labels:
        app: whisper
    spec:
      nodeSelector:
        nvidia.com/gpu: "true"
      containers:
      - name: whisper
        image: ghcr.io/jomcgi/whisper-gpu:latest
        ports:
        - containerPort: 8000
        env:
        - name: MODEL_SIZE
          value: "large-v3"
        - name: COMPUTE_TYPE
          value: "float16"
        - name: DEVICE
          value: "cuda"
        resources:
          limits:
            nvidia.com/gpu: 1
            memory: "8Gi"
          requests:
            nvidia.com/gpu: 1
            memory: "4Gi"
```

### Whisper Service API
```python
from faster_whisper import WhisperModel
import asyncio
from fastapi import FastAPI, WebSocket

app = FastAPI()
model = WhisperModel("large-v3", device="cuda", compute_type="float16")

@app.websocket("/transcribe")
async def transcribe_stream(websocket: WebSocket):
    await websocket.accept()
    audio_buffer = bytearray()

    while True:
        # Receive audio chunk
        audio_chunk = await websocket.receive_bytes()
        audio_buffer.extend(audio_chunk)

        # Process when buffer is large enough (0.5 seconds)
        if len(audio_buffer) >= 8000:  # 16kHz * 0.5s
            segments, _ = model.transcribe(
                audio_buffer,
                beam_size=5,
                language="en",
                condition_on_previous_text=True
            )

            for segment in segments:
                await websocket.send_json({
                    "text": segment.text,
                    "start": segment.start,
                    "end": segment.end,
                    "confidence": segment.avg_logprob
                })

            audio_buffer.clear()
```

## Client Implementation

### Voice Activity Detection (VAD)
```typescript
class VoiceActivityDetector {
  private audioContext: AudioContext;
  private analyser: AnalyserNode;
  private threshold: number = -50; // dB
  private smoothingFactor: number = 0.8;

  constructor(stream: MediaStream) {
    this.audioContext = new AudioContext();
    const source = this.audioContext.createMediaStreamSource(stream);
    this.analyser = this.audioContext.createAnalyser();
    source.connect(this.analyser);
  }

  detectSpeech(): boolean {
    const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(dataArray);

    // Calculate RMS
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i] * dataArray[i];
    }
    const rms = Math.sqrt(sum / dataArray.length);
    const db = 20 * Math.log10(rms / 255);

    return db > this.threshold;
  }
}
```

### Continuous Recording Manager
```typescript
interface ContinuousRecordingOptions {
  alwaysListening: boolean;
  wakeWord?: string;  // "Hey Claude"
  autoSubmit: boolean;
  silenceTimeout: number;  // ms before considering speech ended
}

class ContinuousRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private vad: VoiceActivityDetector;
  private websocket: WebSocket;
  private silenceTimer: NodeJS.Timeout | null = null;

  async startContinuousListening() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 16000
      }
    });

    this.vad = new VoiceActivityDetector(stream);
    this.mediaRecorder = new MediaRecorder(stream);

    // Connect to Whisper WebSocket
    this.websocket = new WebSocket('wss://claude.jomcgi.dev/whisper');

    // Send audio chunks as they're available
    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0 && this.websocket.readyState === WebSocket.OPEN) {
        this.websocket.send(event.data);
      }
    };

    // Start recording in 100ms chunks
    this.mediaRecorder.start(100);

    // Monitor for speech
    this.monitorSpeech();
  }

  private monitorSpeech() {
    setInterval(() => {
      const isSpeaking = this.vad.detectSpeech();

      if (isSpeaking) {
        // Clear silence timer if speaking
        if (this.silenceTimer) {
          clearTimeout(this.silenceTimer);
          this.silenceTimer = null;
        }

        // Update UI to show speaking
        this.updateUI('speaking');

      } else if (!this.silenceTimer) {
        // Start silence timer
        this.silenceTimer = setTimeout(() => {
          // Consider speech ended
          this.handleSpeechEnd();
        }, this.options.silenceTimeout);
      }
    }, 50); // Check every 50ms
  }
}
```

### Wake Word Detection
```typescript
class WakeWordDetector {
  private buffer: string = '';
  private wakeWords = ['hey claude', 'okay claude', 'claude'];

  processTranscription(text: string): boolean {
    this.buffer = (this.buffer + ' ' + text.toLowerCase()).slice(-100);

    for (const wakeWord of this.wakeWords) {
      if (this.buffer.includes(wakeWord)) {
        this.buffer = ''; // Clear buffer
        return true; // Wake word detected
      }
    }

    return false;
  }
}
```

## UI Components

### Voice Interface
```tsx
interface VoiceInterfaceProps {
  mode: 'always-on' | 'push-to-talk' | 'wake-word';
  visualizer: boolean;
}

const VoiceInterface: React.FC<VoiceInterfaceProps> = ({ mode, visualizer }) => {
  return (
    <div className="voice-interface">
      {/* Mode Toggle */}
      <div className="voice-mode-selector">
        <button className={mode === 'always-on' ? 'active' : ''}>
          Always Listening
        </button>
        <button className={mode === 'wake-word' ? 'active' : ''}>
          Wake Word
        </button>
        <button className={mode === 'push-to-talk' ? 'active' : ''}>
          Push to Talk
        </button>
      </div>

      {/* Status Indicator */}
      <div className="voice-status">
        <span className="status-dot"></span>
        <span className="status-text">Listening...</span>
      </div>

      {/* Waveform Visualizer */}
      {visualizer && <WaveformVisualizer />}

      {/* Real-time Transcription */}
      <div className="transcription-preview">
        <span className="interim-text">What you're saying...</span>
      </div>
    </div>
  );
};
```

### Waveform Visualizer
```typescript
class WaveformVisualizer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private analyser: AnalyserNode;

  draw() {
    const bufferLength = this.analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    this.analyser.getByteTimeDomainData(dataArray);

    this.ctx.fillStyle = 'var(--bg)';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    this.ctx.lineWidth = 2;
    this.ctx.strokeStyle = 'var(--fg)';
    this.ctx.beginPath();

    const sliceWidth = this.canvas.width / bufferLength;
    let x = 0;

    for (let i = 0; i < bufferLength; i++) {
      const v = dataArray[i] / 128.0;
      const y = v * this.canvas.height / 2;

      if (i === 0) {
        this.ctx.moveTo(x, y);
      } else {
        this.ctx.lineTo(x, y);
      }

      x += sliceWidth;
    }

    this.ctx.stroke();
    requestAnimationFrame(() => this.draw());
  }
}
```

## Features

### Modes of Operation
1. **Always Listening**: Continuous transcription with VAD
2. **Wake Word**: Activate with "Hey Claude"
3. **Push to Talk**: Traditional button hold
4. **Auto Mode**: Switch based on context

### Smart Features
- **Context Awareness**: Adjust sensitivity based on conversation
- **Noise Cancellation**: Filter background noise
- **Speaker Diarization**: Identify different speakers
- **Language Detection**: Auto-detect language

### Fallback Options
- **Gemini API**: Backup transcription service
- **Local VAD**: Client-side speech detection
- **Manual Input**: Type if voice fails

## Performance Optimization

### Audio Processing
- **Chunking**: Process in 0.5-second chunks
- **Buffering**: Maintain 2-second buffer
- **Compression**: Opus codec for transmission
- **Sample Rate**: 16kHz for optimal quality/size

### GPU Utilization
- **Batch Processing**: Group requests when possible
- **Model Caching**: Keep model in GPU memory
- **Dynamic Scaling**: Scale replicas based on load

### Network Optimization
- **WebSocket Compression**: permessage-deflate
- **Binary Protocol**: Send audio as binary
- **Reconnection Logic**: Auto-reconnect on failure
- **Local Caching**: Cache common phrases

## Privacy & Security

### Data Handling
- **No Persistent Storage**: Audio deleted after processing
- **Encryption**: TLS for all connections
- **User Consent**: Explicit permission for microphone
- **Opt-out Option**: Disable voice features entirely

### Access Control
- **Session-based**: Voice tied to Claude session
- **Rate Limiting**: Prevent abuse
- **Authentication**: Require valid session token

## Success Metrics
- Transcription accuracy (> 95%)
- Latency (< 500ms for first word)
- User adoption rate
- Session length increase
- Error rate (< 1%)

## Implementation Timeline

### Week 1: Infrastructure
- Deploy Whisper on GPU nodes
- Set up WebSocket server
- Implement basic transcription API

### Week 2: Client Integration
- Add VAD implementation
- Build continuous recording
- Create UI components

### Week 3: Enhanced Features
- Wake word detection
- Waveform visualization
- Real-time feedback

### Week 4: Polish & Optimization
- Performance tuning
- Fallback mechanisms
- Testing & debugging