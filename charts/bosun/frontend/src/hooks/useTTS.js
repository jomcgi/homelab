import { useState, useRef, useCallback, useEffect } from "react";

// ── Pre-cached TTS audio (loaded once from server at startup) ─────────────
const _ttsCache = new Map();  // phrase -> { audio: base64, mime_type }
let _cacheLoaded = false;

async function _loadTtsCache() {
  if (_cacheLoaded) return;
  _cacheLoaded = true;
  try {
    const res = await fetch("/api/tts/cache");
    const data = await res.json();
    if (data.cache) {
      for (const [phrase, audio] of Object.entries(data.cache)) {
        _ttsCache.set(phrase, { audio, mime_type: data.mime_type || "audio/wav" });
      }
    }
  } catch {
    // Server may not have cache ready yet — browser TTS fallback will work
  }
}

// ── TTS hook (Gemini-powered with browser fallback) ────────────────────────
export function useTTS() {
  const [enabled, setEnabled] = useState(() => localStorage.getItem("bosun-tts") !== "off");

  // Load pre-cached TTS audio on first mount
  useEffect(() => { _loadTtsCache(); }, []);
  const [speaking, setSpeaking] = useState(false);
  const audioRef = useRef(null);
  const abortRef = useRef(null);

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("bosun-tts", next ? "on" : "off");
      if (!next) {
        if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
        if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
        setSpeaking(false);
      }
      return next;
    });
  }, []);

  const speak = useCallback(async (text) => {
    if (!enabled || !text) return;

    // Abort any in-flight request
    if (abortRef.current) abortRef.current.abort();
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }

    const controller = new AbortController();
    abortRef.current = controller;
    setSpeaking(true);

    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, summarize: true }),
        signal: controller.signal,
      });
      const data = await res.json();

      if (data.audio) {
        // Gemini returned audio — play it
        const audioData = atob(data.audio);
        const bytes = new Uint8Array(audioData.length);
        for (let i = 0; i < audioData.length; i++) bytes[i] = audioData.charCodeAt(i);
        const blob = new Blob([bytes], { type: data.mime_type || "audio/wav" });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => { setSpeaking(false); URL.revokeObjectURL(url); };
        audio.onerror = (err) => { console.warn("TTS audio error:", err); setSpeaking(false); URL.revokeObjectURL(url); };
        try {
          await audio.play();
        } catch (playErr) {
          // Browser autoplay policy may block first play without user gesture
          console.warn("TTS autoplay blocked:", playErr.message);
          setSpeaking(false);
          URL.revokeObjectURL(url);
        }
      } else if (data.error) {
        console.warn("TTS server error:", data.error);
        setSpeaking(false);
      } else {
        // Fallback to browser TTS if Gemini unavailable
        if (window.speechSynthesis) {
          let toSpeak = text;
          if (text.length > 300) {
            const cut = text.slice(0, 300);
            const lp = cut.lastIndexOf(".");
            toSpeak = lp > 100 ? cut.slice(0, lp + 1) : cut + "...";
          }
          const utterance = new SpeechSynthesisUtterance(toSpeak);
          utterance.rate = 1.1;
          utterance.onend = () => setSpeaking(false);
          utterance.onerror = () => setSpeaking(false);
          window.speechSynthesis.speak(utterance);
        } else {
          setSpeaking(false);
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") console.warn("TTS error:", e);
      setSpeaking(false);
    }
  }, [enabled]);

  const stop = useCallback(() => {
    if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  }, []);

  return { enabled, toggle, speak, stop, speaking };
}

// ── Instant confirmations: pre-cached Gemini voice, browser TTS fallback ──
export function confirmTTS(text) {
  const cached = _ttsCache.get(text);
  if (cached) {
    const audioData = atob(cached.audio);
    const bytes = new Uint8Array(audioData.length);
    for (let i = 0; i < audioData.length; i++) bytes[i] = audioData.charCodeAt(i);
    const blob = new Blob([bytes], { type: cached.mime_type });
    const audio = new Audio(URL.createObjectURL(blob));
    audio.onended = () => URL.revokeObjectURL(audio.src);
    audio.play().catch(() => URL.revokeObjectURL(audio.src));
    return;
  }
  // Fallback to browser SpeechSynthesis if cache miss
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.2;
  window.speechSynthesis.speak(u);
}
