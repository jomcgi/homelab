import { useState, useRef, useCallback } from "react";

// ── Web Speech API hook (with adaptive debounce) ──────────────────────────
// Accumulates speech fragments and only fires onResult after a silence window.
// Default 800ms debounce — messages queue when the agent is busy, so short
// silence windows are fine. Drops to 400ms during approval state for snappy
// "yes"/"go ahead" responses.
const DEBOUNCE_DEFAULT = 800;
const DEBOUNCE_FAST = 400;

export function useVoiceInput() {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [pending, setPending] = useState(""); // accumulated final text not yet sent
  const [wakeWordFlash, setWakeWordFlash] = useState(false); // visual indicator
  const recognitionRef = useRef(null);
  const debounceRef = useRef(null);
  const debounceMsRef = useRef(DEBOUNCE_DEFAULT); // current debounce duration
  const bufRef = useRef("");
  const onResultRef = useRef(null);
  const onWakeWordRef = useRef(null);  // callback for wake word bypass
  const onCompactRef = useRef(null);   // callback for "hey claude compact"
  const suppressedRef = useRef(false); // true while TTS is playing (prevents feedback loop)

  const supported = typeof window !== "undefined" && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);

  const flush = useCallback(() => {
    const text = bufRef.current.trim();
    if (text && onResultRef.current) {
      onResultRef.current(text);
    }
    bufRef.current = "";
    // Keep pending text visible during async classification — consumer calls clearPending()
    // Reset to default debounce after each send
    debounceMsRef.current = DEBOUNCE_DEFAULT;
  }, []);

  const clearPending = useCallback(() => {
    setPending("");
  }, []);

  const micStreamRef = useRef(null);

  const start = useCallback(async (onResult, { onWakeWord, onCompact } = {}) => {
    if (!supported) { console.warn("Voice: Speech API not supported in this browser"); return; }

    // Stop any existing recognition first
    if (recognitionRef.current) {
      const old = recognitionRef.current;
      recognitionRef.current = null;
      old.onend = null;
      old.abort();
    }

    // Acquire mic via getUserMedia first — this gives a clear error if blocked
    // and warms up the audio pipeline so SpeechRecognition doesn't silently fail
    try {
      if (micStreamRef.current) {
        micStreamRef.current.getTracks().forEach((t) => t.stop());
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;
      console.log("Voice: mic acquired via getUserMedia");
    } catch (err) {
      console.warn("Voice: mic access denied:", err.message);
      setListening(false);
      return;
    }

    onResultRef.current = onResult;
    onWakeWordRef.current = onWakeWord || null;
    onCompactRef.current = onCompact || null;
    bufRef.current = "";

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onaudiostart = () => console.log("Voice: recognition audio active");
    recognition.onspeechstart = () => console.log("Voice: speech detected");

    // Track whether wake word already handled for the current utterance
    let wakeHandled = false;

    recognition.onresult = (e) => {
      let finalText = "";
      let interimText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const transcript = e.results[i][0].transcript;
        if (e.results[i].isFinal) {
          finalText += transcript;
        } else {
          interimText += transcript;
        }
      }

      // Wake word detection ALWAYS works, even when suppressed.
      // This lets "hey claude, also do X" punch through during streaming/TTS.
      if (interimText && !wakeHandled) {
        const lower = interimText.toLowerCase().trim();
        if (lower.startsWith("hey claude")) {
          const remainder = interimText.slice("hey claude".length).trim();

          // Check for "hey claude compact [directive]" subcommand
          const compactMatch = remainder.match(/^compact\s*(.*)/i);
          if (compactMatch) {
            wakeHandled = true;
            suppressedRef.current = false; // Wake word overrides suppression
            const directive = compactMatch[1].trim();
            if (onCompactRef.current) onCompactRef.current(directive);
            // Flash indicator
            setWakeWordFlash(true);
            setTimeout(() => setWakeWordFlash(false), 600);
            // Clear buffer so final result doesn't also send
            bufRef.current = "";
            setPending("");
            setInterim("");
            if (debounceRef.current) clearTimeout(debounceRef.current);
            return;
          }

          // Strip wake word and flush immediately (skip debounce)
          if (remainder.length > 3) {
            wakeHandled = true;
            suppressedRef.current = false; // Wake word overrides suppression
            // Flash indicator
            setWakeWordFlash(true);
            setTimeout(() => setWakeWordFlash(false), 600);
            bufRef.current = remainder;
            setPending("");
            setInterim("");
            if (debounceRef.current) clearTimeout(debounceRef.current);
            flush(); // Immediate send, no 2s wait
            return;
          }
        }
      }

      // Normal speech is suppressed during streaming/TTS to prevent feedback
      if (suppressedRef.current) return;

      if (finalText) {
        // If wake word was already handled for this utterance, skip
        if (wakeHandled) {
          wakeHandled = false;
          return;
        }
        bufRef.current += (bufRef.current ? " " : "") + finalText.trim();
        setPending(bufRef.current);
        setInterim("");

        // Reset debounce timer — wait for more speech or flush after silence
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(flush, debounceMsRef.current);
      } else if (!wakeHandled) {
        setInterim(interimText);
      }
    };

    recognition.onerror = (e) => {
      console.warn("Voice: recognition error:", e.error);
    };

    recognition.onend = () => {
      // Restart if still supposed to be listening
      if (recognitionRef.current === recognition) {
        try { recognition.start(); } catch { /* ignore */ }
      }
    };

    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
    console.log("Voice: recognition started");
  }, [supported, flush]);

  const stop = useCallback(() => {
    // Flush any pending text immediately on stop
    if (debounceRef.current) clearTimeout(debounceRef.current);
    flush();

    if (recognitionRef.current) {
      const r = recognitionRef.current;
      recognitionRef.current = null;
      r.onend = null;
      r.abort();
    }
    // Release the mic stream
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    setListening(false);
    setInterim("");
    onResultRef.current = null;
  }, [flush]);

  // Suppress/unsuppress — used to mute recognition during TTS playback
  const suppress = useCallback(() => {
    suppressedRef.current = true;
    // Clear any in-flight buffer so stale audio doesn't fire after unsuppress
    if (debounceRef.current) clearTimeout(debounceRef.current);
    bufRef.current = "";
    setPending("");
    setInterim("");
  }, []);

  const unsuppress = useCallback(() => {
    // Small delay to let trailing TTS audio dissipate from the mic
    setTimeout(() => { suppressedRef.current = false; }, 500);
  }, []);

  // Let parent signal fast debounce mode (e.g., pending approval → "yes"/"go ahead" faster)
  const setFastDebounce = useCallback((fast) => {
    debounceMsRef.current = fast ? DEBOUNCE_FAST : DEBOUNCE_DEFAULT;
  }, []);

  return { listening, interim, pending, supported, start, stop, wakeWordFlash, suppress, unsuppress, setFastDebounce, clearPending };
}
