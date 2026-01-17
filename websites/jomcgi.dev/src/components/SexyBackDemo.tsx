import { useState, useEffect, useCallback, useRef } from 'react';

const JT_GIF_URL = '/jt.gif';

const MAX_JTS = 10000;

// Faster escalation - gets crunchy quick
const SPAWN_SCHEDULE = [
  { interval: 1500, count: 2, minScale: 0.15, maxScale: 0.4 },   // Phase 1: small Justins
  { interval: 800, count: 3, minScale: 0.2, maxScale: 0.5 },     // Phase 2
  { interval: 400, count: 4, minScale: 0.25, maxScale: 0.6 },    // Phase 3 - KICK button appears
  { interval: 200, count: 5, minScale: 0.3, maxScale: 0.8 },     // Phase 4
  { interval: 100, count: 8, minScale: 0.4, maxScale: 1.0 },     // Phase 5
  { interval: 50, count: 10, minScale: 0.5, maxScale: 1.2 },     // Phase 6
  { interval: 25, count: -1, minScale: 0.6, maxScale: 1.5 },     // Phase 7: BIG JUSTINS FOREVER 🔥
];

interface JT {
  id: number;
  x: number;
  y: number;
  scale: number;
  opacity: number;
  rotation: number;
  rotationSpeed: number;
  fallSpeed: number;
  landed: boolean;
  kicked: boolean;
  kickSpeed: number;
}

export default function SexyBackDemo() {
  const [jts, setJts] = useState<JT[]>([]);
  const [isActive, setIsActive] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isKicked, setIsKicked] = useState(false);
  const [phase, setPhase] = useState(0);
  const [spawnedInPhase, setSpawnedInPhase] = useState(0);
  const [darkMode, setDarkMode] = useState(false);
  const animationRef = useRef<number | null>(null);
  const kickTimeRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Load audio
  useEffect(() => {
    const audio = new Audio('/SexyBack.mp3');
    audio.loop = true;
    audioRef.current = audio;

    audio.addEventListener('canplaythrough', () => setIsLoaded(true));
    audio.addEventListener('error', () => setIsLoaded(true)); // Allow playing without audio on error

    return () => {
      audio.pause();
      audio.src = '';
    };
  }, []);

  const spawnJT = useCallback(() => {
    if (isKicked) return;

    setJts(prev => {
      if (prev.length >= MAX_JTS) return prev;

      let startY;
      if (Math.random() < 0.8) {
        startY = -20 + Math.random() * 15;
      } else {
        startY = Math.random() * 15;
      }

      // Get scale range from current phase, weight towards larger
      const schedule = SPAWN_SCHEDULE[phase] || SPAWN_SCHEDULE[SPAWN_SCHEDULE.length - 1];
      const { minScale, maxScale } = schedule;
      // Bias towards larger: use square of random to skew distribution up
      const scaleBias = Math.pow(Math.random(), 0.5); // sqrt makes it favor larger values
      const scale = minScale + scaleBias * (maxScale - minScale);

      const newJT: JT = {
        id: Date.now() + Math.random(),
        x: Math.random() * 90 + 3,
        y: startY,
        scale: scale,
        opacity: 0.4 + Math.random() * 0.5,
        rotation: -45 + Math.random() * 90,
        rotationSpeed: (0.2 + Math.random() * 1.0) * (Math.random() > 0.5 ? 1 : -1),
        fallSpeed: 0.08 + Math.random() * 0.5,
        landed: false,
        kicked: false,
        kickSpeed: 0,
      };

      return [...prev, newJT];
    });
  }, [isKicked, phase]);

  // Physics update loop
  useEffect(() => {
    if (!isActive) return;

    const updatePhysics = () => {
      setJts(prev => {
        // Remove JTs that have flown off the top
        const filtered = prev.filter(jt => !jt.kicked || jt.y > -30);

        if (filtered.length === 0 && isKicked) {
          // All JTs gone, could trigger something here
        }

        let changed = filtered.length !== prev.length;
        const updated = filtered.map(jt => {
          // If kicked, fly upward fast
          if (jt.kicked) {
            changed = true;
            return {
              ...jt,
              y: jt.y - jt.kickSpeed,
              rotation: jt.rotation + jt.rotationSpeed * 3,
            };
          }

          if (jt.landed) return jt;

          const groundLevel = 92 - (jt.scale * 15);
          const newY = jt.y + jt.fallSpeed;
          let newRotation = jt.rotation + jt.rotationSpeed;

          if (newY >= groundLevel) {
            changed = true;
            return {
              ...jt,
              y: groundLevel,
              rotation: 0,
              landed: true,
            };
          }

          changed = true;
          return {
            ...jt,
            y: newY,
            rotation: newRotation,
          };
        });

        return changed ? updated : prev;
      });

      animationRef.current = requestAnimationFrame(updatePhysics);
    };

    animationRef.current = requestAnimationFrame(updatePhysics);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isActive, isKicked]);

  // Spawn timer
  useEffect(() => {
    if (!isActive || isKicked) return;

    const schedule = SPAWN_SCHEDULE[phase];
    if (!schedule) return;

    const interval = setInterval(() => {
      spawnJT();

      setSpawnedInPhase(prev => {
        const newCount = prev + 1;
        if (schedule.count !== -1 && newCount >= schedule.count) {
          setPhase(p => Math.min(p + 1, SPAWN_SCHEDULE.length - 1));
          return 0;
        }
        return newCount;
      });
    }, schedule.interval);

    return () => clearInterval(interval);
  }, [isActive, isKicked, phase, spawnJT]);

  const bringSexyBack = () => {
    if (isActive) return;
    setIsActive(true);
    audioRef.current?.play();
    spawnJT();
  };

  const kickJustinOut = () => {
    setIsKicked(true);
    kickTimeRef.current = Date.now();
    audioRef.current?.pause();

    // Calculate kick speed so all JTs exit within ~1.5s (~90 frames at 60fps)
    // Each JT needs to travel from current Y to -30 (off screen top)
    // Speed = distance / frames, with some randomness
    const TARGET_FRAMES = 70; // ~1.17s at 60fps, leaves buffer

    setJts(prev => prev.map(jt => {
      const distanceToExit = jt.y + 30; // distance to y=-30
      const baseSpeed = distanceToExit / TARGET_FRAMES;
      // Add 20-50% random variation for staggered effect
      const kickSpeed = baseSpeed * (1.2 + Math.random() * 0.5);

      return {
        ...jt,
        kicked: true,
        landed: false,
        kickSpeed: kickSpeed,
        rotationSpeed: (2 + Math.random() * 4) * (Math.random() > 0.5 ? 1 : -1),
      };
    }));
  };

  const bgColor = darkMode ? '#000' : '#fff';
  const fgColor = darkMode ? '#fff' : '#000';
  const landedCount = jts.filter(jt => jt.landed && !jt.kicked).length;
  const fallingCount = jts.filter(jt => !jt.landed && !jt.kicked).length;
  const showKickButton = phase >= 3 && !isKicked;

  return (
    <div
      className="relative w-full min-h-screen overflow-hidden font-mono"
      style={{
        background: bgColor,
        color: fgColor,
        animation: phase >= 4 && !isKicked ? 'shake 0.3s ease-in-out infinite' : 'none'
      }}
    >

      {/* Background pulse */}
      {isActive && !isKicked && (
        <div
          className="fixed inset-0 pointer-events-none"
          style={{
            zIndex: 1,
            background: 'linear-gradient(45deg, #ff6b6b, #4d96ff, #9b59b6, #ffd93d)',
            backgroundSize: '400% 400%',
            animation: 'gradient 2s ease infinite, pulse 0.5s ease-in-out infinite',
            opacity: 0.1,
          }}
        />
      )}

      {/* Dancing JTs */}
      <div
        className="fixed inset-0 pointer-events-none overflow-hidden"
        style={{ zIndex: 10 }}
      >
        {jts.map((jt) => (
          <div
            key={jt.id}
            className="absolute"
            style={{
              left: `${jt.x}%`,
              top: `${jt.y}%`,
              width: '100px',
              height: '200px',
              backgroundImage: `url(${JT_GIF_URL})`,
              backgroundSize: 'contain',
              backgroundRepeat: 'no-repeat',
              backgroundPosition: 'bottom center',
              transform: `scale(${jt.scale}) rotate(${jt.rotation}deg)`,
              opacity: jt.opacity,
              filter: darkMode ? 'invert(1)' : 'none',
              transition: jt.landed && !jt.kicked ? 'transform 0.3s ease-out' : 'none',
              willChange: jt.landed && !jt.kicked ? 'auto' : 'transform',
            }}
          />
        ))}
      </div>

      {/* Content */}
      <div
        className="relative max-w-3xl mx-auto p-8"
        style={{ zIndex: 20 }}
      >
        <div
          className="flex justify-between items-center mb-8 pb-4"
          style={{ borderBottom: `2px solid ${fgColor}` }}
        >
          <span className="text-xs uppercase tracking-widest opacity-70">← jomcgi.dev</span>
          <button
            onClick={() => setDarkMode(!darkMode)}
            className="px-3 py-1 text-xs uppercase tracking-wide transition-colors"
            style={{
              border: `2px solid ${fgColor}`,
              background: 'transparent',
              color: fgColor,
            }}
          >
            Invert
          </button>
        </div>

        <h1
          className="text-2xl font-bold uppercase tracking-widest mb-4"
          style={{ background: bgColor, display: 'inline-block', padding: '0 4px' }}
        >
          Engineering Notes
        </h1>
        <p className="opacity-70 mb-12" style={{ background: bgColor, display: 'inline', padding: '0 4px' }}>
          Deep dives into interesting problems I've solved.
        </p>

        <div className="mb-12 mt-8">
          <div
            className="flex items-baseline gap-4 mb-6 pb-2"
            style={{ borderBottom: `2px solid ${fgColor}` }}
          >
            <span className="text-xs opacity-50 uppercase tracking-widest" style={{ background: bgColor, padding: '0 4px' }}>01</span>
            <h2 className="text-lg font-bold uppercase tracking-wide" style={{ background: bgColor, padding: '0 4px' }}>Claude Code Web</h2>
          </div>

          <div
            className="p-5 mb-6"
            style={{ background: fgColor, color: bgColor }}
          >
            <div className="text-xs uppercase tracking-widest opacity-70 mb-2">Motivation</div>
            <p>I wanted a coding assistant that could see what's actually happening in my cluster.</p>
          </div>

          <p style={{ background: bgColor, padding: '4px 8px', display: 'inline-block', marginBottom: '8px' }}>
            vLLM runs Qwen3-Coder-30B on a 4090. AWQ 4-bit quantization fits in 24GB VRAM.
          </p>
          <br/>
          <p style={{ background: bgColor, padding: '4px 8px', display: 'inline-block', marginBottom: '8px' }}>
            SigNoz MCP gives direct access to logs, traces, and metrics.
          </p>
        </div>

        <div className="mb-12">
          <div
            className="flex items-baseline gap-4 mb-6 pb-2"
            style={{ borderBottom: `2px solid ${fgColor}` }}
          >
            <span className="text-xs opacity-50 uppercase tracking-widest" style={{ background: bgColor, padding: '0 4px' }}>02</span>
            <h2 className="text-lg font-bold uppercase tracking-wide" style={{ background: bgColor, padding: '0 4px' }}>Trips: Camera to Browser</h2>
          </div>

          <div
            className="p-5 mb-6"
            style={{ background: fgColor, color: bgColor }}
          >
            <div className="text-xs uppercase tracking-widest opacity-70 mb-2">Motivation</div>
            <p>A GoPro on the dash captures photos automatically, and my homelab turns them into a live feed.</p>
          </div>

          <p style={{ background: bgColor, padding: '4px 8px', display: 'inline-block', marginBottom: '8px' }}>
            Python asyncio controller with GPS-triggered capture.
          </p>
          <br/>
          <p style={{ background: bgColor, padding: '4px 8px', display: 'inline-block', marginBottom: '8px' }}>
            NATS JetStream for event sourcing. imgproxy + Cloudflare CDN for delivery.
          </p>
        </div>
      </div>

      {/* BRING SEXY BACK button */}
      {!isActive && (
        <div className="fixed bottom-6 left-6" style={{ zIndex: 100 }}>
          {!isLoaded ? (
            <div
              className="px-5 py-3 text-sm uppercase tracking-wide"
              style={{
                border: `2px solid ${fgColor}`,
                background: bgColor,
                color: fgColor,
                opacity: 0.5,
              }}
            >
              Loading...
            </div>
          ) : (
            <button
              onClick={bringSexyBack}
              className="px-5 py-3 text-sm uppercase tracking-wide transition-all hover:scale-105"
              style={{
                border: `2px solid ${fgColor}`,
                background: bgColor,
                color: fgColor,
                animation: 'buttonPulse 1s ease-in-out infinite',
              }}
            >
              🕺 Bring Sexy Back
            </button>
          )}
        </div>
      )}

      {/* KICK JUSTIN OUT button */}
      {showKickButton && (
        <button
          onClick={kickJustinOut}
          className="fixed bottom-6 left-6 px-5 py-3 text-sm uppercase tracking-wide transition-all hover:scale-105"
          style={{
            zIndex: 100,
            border: '2px solid #ff4444',
            background: '#ff4444',
            color: '#fff',
          }}
        >
          🚫 Kick Justin Out
        </button>
      )}

      {/* Stats counter */}
      {isActive && (
        <div
          className="fixed top-4 right-4 px-4 py-2 text-xs uppercase tracking-wide font-bold"
          style={{
            zIndex: 100,
            background: fgColor,
            color: bgColor,
          }}
        >
          {isKicked ? (
            <div>👋 Bye Justin {jts.length > 0 ? `(${jts.length} yeeting)` : '✓'}</div>
          ) : (
            <>
              <div>🌧️ {fallingCount} | 🕺 {landedCount} | Total: {jts.length.toLocaleString()}</div>
              <div style={{ fontSize: '9px', opacity: 0.7, marginTop: '4px' }}>
                Phase {phase + 1}/{SPAWN_SCHEDULE.length} {phase >= 6 ? '🔥 MAX CHAOS' : ''}
              </div>
            </>
          )}
        </div>
      )}

      <style>{`
        @keyframes shake {
          0%, 100% { transform: translate(0, 0); }
          10% { transform: translate(-2px, -1px); }
          20% { transform: translate(2px, 1px); }
          30% { transform: translate(-1px, 2px); }
          40% { transform: translate(1px, -2px); }
          50% { transform: translate(-2px, 1px); }
        }
        @keyframes gradient {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 0.05; }
          50% { opacity: 0.15; }
        }
        @keyframes buttonPulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.02); }
        }
      `}</style>
    </div>
  );
}
