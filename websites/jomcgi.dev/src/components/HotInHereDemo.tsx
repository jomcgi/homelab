import { useState, useEffect, useCallback, useRef } from "react";

// Phase thresholds - each unlocks new chaos
const PHASE_THRESHOLDS = [0, 20, 40, 60, 80, 95];
// Phase 0: 0-19%   - Calm brutalism, slight warmth
// Phase 1: 20-39%  - Sweat drops start, slight color shift
// Phase 2: 40-59%  - Fire particles spawn, text starts sagging
// Phase 3: 60-79%  - Cursor becomes flame, leaves trails, screen shake
// Phase 4: 80-94%  - VHS corruption, stalker fires, COOL DOWN button appears
// Phase 5: 95-100% - MAXIMUM CHAOS - everything melts, screen inverts

interface SweatDrop {
  id: number;
  x: number;
  y: number;
  speed: number;
  size: number;
  opacity: number;
}

interface FireParticle {
  id: number;
  x: number;
  y: number;
  scale: number;
  opacity: number;
  rotation: number;
  rotationSpeed: number;
  riseSpeed: number;
  stalker: boolean;
  driftX: number;
}

interface HeatTrail {
  id: number;
  x: number;
  y: number;
  opacity: number;
  scale: number;
}

const MAX_SWEAT = 50;
const MAX_FIRE = 100;
const MAX_TRAILS = 30;

export default function HotInHereDemo() {
  const [hasEntered, setHasEntered] = useState(false);
  const [isHoveringEnter, setIsHoveringEnter] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [temperature, setTemperature] = useState(0);
  const [isCooledDown, setIsCooledDown] = useState(false);
  const [isInverted, setIsInverted] = useState(false);

  const [sweatDrops, setSweatDrops] = useState<SweatDrop[]>([]);
  const [fireParticles, setFireParticles] = useState<FireParticle[]>([]);
  const [heatTrails, setHeatTrails] = useState<HeatTrail[]>([]);

  const [cursorPos, setCursorPos] = useState({ x: 50, y: 50 });
  const [coolButtonPos, setCoolButtonPos] = useState({ x: 24, y: 24 });
  const [buttonScale, setButtonScale] = useState(1);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const coolButtonRef = useRef<HTMLButtonElement | null>(null);
  const animationRef = useRef<number | null>(null);
  const cursorPosRef = useRef(cursorPos);
  const temperatureRef = useRef(temperature);
  const lastTrailTime = useRef(0);

  // Calculate current phase
  const phase = PHASE_THRESHOLDS.reduce(
    (acc, threshold, idx) => (temperature >= threshold ? idx : acc),
    0,
  );

  // Load audio
  useEffect(() => {
    const audio = new Audio("https://cdn.jomcgi.dev/HotInHere.mp3");
    audio.loop = true;
    audioRef.current = audio;

    return () => {
      audio.pause();
      audio.src = "";
    };
  }, []);

  // Keep refs updated
  useEffect(() => {
    cursorPosRef.current = cursorPos;
  }, [cursorPos]);
  useEffect(() => {
    temperatureRef.current = temperature;
  }, [temperature]);

  // Cursor tracking
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      setCursorPos({ x, y });
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  // Temperature rises over time
  useEffect(() => {
    if (!isActive || isCooledDown) return;

    const interval = setInterval(() => {
      setTemperature((prev) => Math.min(prev + 0.5, 100));
    }, 200);

    return () => clearInterval(interval);
  }, [isActive, isCooledDown]);

  // Screen inversion flashes (phase 4+)
  useEffect(() => {
    if (!isActive || isCooledDown || phase < 4) {
      setIsInverted(false);
      return;
    }

    const schedules: Record<number, { min: number; max: number }> = {
      4: { min: 3000, max: 5000 },
      5: { min: 500, max: 1500 },
    };
    const schedule = schedules[phase];
    if (!schedule) return;

    let mainTimeout: ReturnType<typeof setTimeout>;
    let flashTimeout: ReturnType<typeof setTimeout>;
    let cancelled = false;

    const scheduleFlash = () => {
      if (cancelled) return;
      const delay =
        schedule.min + Math.random() * (schedule.max - schedule.min);
      mainTimeout = setTimeout(() => {
        if (cancelled) return;
        setIsInverted(true);
        flashTimeout = setTimeout(
          () => {
            if (cancelled) return;
            setIsInverted(false);
            scheduleFlash();
          },
          50 + Math.random() * 150,
        );
      }, delay);
    };

    scheduleFlash();
    return () => {
      cancelled = true;
      clearTimeout(mainTimeout);
      clearTimeout(flashTimeout);
      setIsInverted(false);
    };
  }, [isActive, isCooledDown, phase]);

  // Spawn sweat drops (phase 1+)
  const spawnSweat = useCallback(() => {
    if (isCooledDown || phase < 1) return;

    setSweatDrops((prev) => {
      if (prev.length >= MAX_SWEAT) return prev;

      // Spawn from header area
      const newDrop: SweatDrop = {
        id: Date.now() + Math.random(),
        x: 5 + Math.random() * 60, // Header region
        y: 8 + Math.random() * 5,
        speed: 0.3 + Math.random() * 0.5 + phase * 0.1,
        size: 3 + Math.random() * 4,
        opacity: 0.6 + Math.random() * 0.4,
      };

      return [...prev, newDrop];
    });
  }, [isCooledDown, phase]);

  // Spawn fire particles (phase 2+)
  const spawnFire = useCallback(() => {
    if (isCooledDown || phase < 2) return;

    setFireParticles((prev) => {
      if (prev.length >= MAX_FIRE) return prev;

      const isStalker = phase >= 4 && Math.random() < 0.3 + (phase - 4) * 0.15;

      const newFire: FireParticle = {
        id: Date.now() + Math.random(),
        x: Math.random() * 100,
        y: 100 + Math.random() * 10,
        scale: 0.3 + Math.random() * 0.5 + phase * 0.1,
        opacity: 0.5 + Math.random() * 0.5,
        rotation: Math.random() * 360,
        rotationSpeed: (Math.random() - 0.5) * 4,
        riseSpeed: 0.5 + Math.random() * 1 + phase * 0.2,
        stalker: isStalker,
        driftX: (Math.random() - 0.5) * 0.5,
      };

      return [...prev, newFire];
    });
  }, [isCooledDown, phase]);

  // Physics update loop
  useEffect(() => {
    if (!isActive) return;

    const updatePhysics = (timestamp: number) => {
      const cursor = cursorPosRef.current;
      const temp = temperatureRef.current;
      const currentPhase = PHASE_THRESHOLDS.reduce(
        (acc, threshold, idx) => (temp >= threshold ? idx : acc),
        0,
      );

      // Add heat trails (phase 3+)
      if (currentPhase >= 3 && !isCooledDown) {
        if (timestamp - lastTrailTime.current > 50) {
          lastTrailTime.current = timestamp;
          setHeatTrails((prev) => {
            const filtered = prev.filter((t) => t.opacity > 0.05);
            if (filtered.length >= MAX_TRAILS) {
              return [
                ...filtered.slice(1),
                {
                  id: timestamp,
                  x: cursor.x,
                  y: cursor.y,
                  opacity: 0.8,
                  scale: 1,
                },
              ];
            }
            return [
              ...filtered,
              {
                id: timestamp,
                x: cursor.x,
                y: cursor.y,
                opacity: 0.8,
                scale: 1,
              },
            ];
          });
        }
      }

      // Update heat trails - fade out
      setHeatTrails((prev) =>
        prev
          .map((trail) => ({
            ...trail,
            opacity: trail.opacity * 0.92,
            scale: trail.scale * 1.02,
          }))
          .filter((t) => t.opacity > 0.05),
      );

      // Update sweat drops
      setSweatDrops((prev) =>
        prev
          .map((drop) => ({
            ...drop,
            y: drop.y + drop.speed,
            opacity: drop.y > 80 ? drop.opacity * 0.9 : drop.opacity,
          }))
          .filter((d) => d.y < 110 && d.opacity > 0.1),
      );

      // Update fire particles
      setFireParticles((prev) =>
        prev
          .map((fire) => {
            let newX = fire.x + fire.driftX;
            let newY = fire.y - fire.riseSpeed;

            // Stalker fires drift toward cursor
            if (fire.stalker && !isCooledDown) {
              const dx = cursor.x - fire.x;
              const dy = cursor.y - fire.y;
              const dist = Math.sqrt(dx * dx + dy * dy);
              if (dist > 5) {
                const stalkSpeed = 0.3 + currentPhase * 0.15;
                newX += (dx / dist) * stalkSpeed;
                newY += (dy / dist) * stalkSpeed * 0.5;
              }
            }

            return {
              ...fire,
              x: newX,
              y: newY,
              rotation: fire.rotation + fire.rotationSpeed,
              opacity: fire.y < 20 ? fire.opacity * 0.95 : fire.opacity,
            };
          })
          .filter((f) => f.y > -20 && f.opacity > 0.1),
      );

      animationRef.current = requestAnimationFrame(updatePhysics);
    };

    animationRef.current = requestAnimationFrame(updatePhysics);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [isActive, isCooledDown]);

  // Spawn timers
  useEffect(() => {
    if (!isActive || isCooledDown) return;

    // Sweat spawner (phase 1+)
    const sweatInterval = setInterval(
      () => {
        if (phase >= 1) spawnSweat();
      },
      Math.max(800 - phase * 100, 200),
    );

    // Fire spawner (phase 2+)
    const fireInterval = setInterval(
      () => {
        if (phase >= 2) {
          const count = 1 + Math.floor(phase / 2);
          for (let i = 0; i < count; i++) {
            setTimeout(() => spawnFire(), i * 50);
          }
        }
      },
      Math.max(600 - phase * 80, 100),
    );

    return () => {
      clearInterval(sweatInterval);
      clearInterval(fireInterval);
    };
  }, [isActive, isCooledDown, phase, spawnSweat, spawnFire]);

  // Evasive COOL DOWN button behavior (phase 4+)
  const coolButtonAnimRef = useRef<number | null>(null);
  const buttonVelocityRef = useRef({ vx: 2, vy: 1.5 });
  const isTouchDevice =
    typeof window !== "undefined" &&
    ("ontouchstart" in window || navigator.maxTouchPoints > 0);

  useEffect(() => {
    const shouldShow = phase >= 4 && !isCooledDown;
    if (!shouldShow) {
      if (coolButtonAnimRef.current)
        cancelAnimationFrame(coolButtonAnimRef.current);
      return;
    }

    const updateButtonPosition = () => {
      if (!coolButtonRef.current || !containerRef.current) {
        coolButtonAnimRef.current = requestAnimationFrame(updateButtonPosition);
        return;
      }

      const button = coolButtonRef.current;
      const container = containerRef.current;
      const buttonRect = button.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const margin = 20;
      const maxX = containerRect.width - buttonRect.width - margin;
      const maxY = containerRect.height - buttonRect.height - margin;

      if (isTouchDevice) {
        // Mobile: bounce around
        const baseSpeed = 3 + (phase - 4) * 3;

        setCoolButtonPos((prev) => {
          let newX = prev.x + buttonVelocityRef.current.vx * baseSpeed;
          let newY = prev.y + buttonVelocityRef.current.vy * baseSpeed;

          if (newX <= margin || newX >= maxX) {
            buttonVelocityRef.current.vx *= -1;
            newX = Math.max(margin, Math.min(maxX, newX));
          }
          if (newY <= margin || newY >= maxY) {
            buttonVelocityRef.current.vy *= -1;
            newY = Math.max(margin, Math.min(maxY, newY));
          }

          return { x: newX, y: newY };
        });
      } else {
        // Desktop: flee from cursor (heat source)
        const cursor = cursorPosRef.current;
        const cursorX = (cursor.x / 100) * containerRect.width;
        const cursorY = (cursor.y / 100) * containerRect.height;

        const buttonCenterX =
          buttonRect.left - containerRect.left + buttonRect.width / 2;
        const buttonCenterY =
          buttonRect.top - containerRect.top + buttonRect.height / 2;

        const dx = cursorX - buttonCenterX;
        const dy = cursorY - buttonCenterY;
        const distance = Math.sqrt(dx * dx + dy * dy);

        const threshold = 250 + (phase - 4) * 100;

        // Shrink when cursor (heat) gets close - it's scared of the heat!
        const newScale =
          distance < threshold ? 0.5 + 0.5 * (distance / threshold) : 1;
        setButtonScale(newScale);

        if (distance < threshold && distance > 0) {
          const escapeX = -dx / distance;
          const escapeY = -dy / distance;

          const proximity = 1 - distance / threshold;
          const baseSpeed = 25 + (phase - 4) * 20;
          const speed = baseSpeed * proximity * proximity;

          setCoolButtonPos((prev) => {
            let newX = prev.x + escapeX * speed;
            let newY = prev.y - escapeY * speed;

            newX = Math.max(margin, Math.min(maxX, newX));
            newY = Math.max(margin, Math.min(maxY, newY));

            return { x: newX, y: newY };
          });
        }
      }

      coolButtonAnimRef.current = requestAnimationFrame(updateButtonPosition);
    };

    if (isTouchDevice) {
      buttonVelocityRef.current = {
        vx: (Math.random() > 0.5 ? 1 : -1) * (2 + Math.random() * 2),
        vy: (Math.random() > 0.5 ? 1 : -1) * (2 + Math.random() * 2),
      };
    }

    coolButtonAnimRef.current = requestAnimationFrame(updateButtonPosition);
    return () => {
      if (coolButtonAnimRef.current)
        cancelAnimationFrame(coolButtonAnimRef.current);
    };
  }, [phase, isCooledDown, isTouchDevice]);

  const handleCoolDown = () => {
    setIsCooledDown(true);
    audioRef.current?.pause();

    // Rapidly cool down
    const coolInterval = setInterval(() => {
      setTemperature((prev) => {
        if (prev <= 0) {
          clearInterval(coolInterval);
          return 0;
        }
        return prev - 2;
      });
    }, 30);

    // Clear particles
    setFireParticles([]);
    setSweatDrops([]);
    setHeatTrails([]);
  };

  const handleEnter = () => {
    setHasEntered(true);

    const audio = audioRef.current;
    if (audio) {
      audio
        .play()
        .then(() => {
          audio.pause();
          audio.currentTime = 0;
          setTimeout(() => {
            setIsActive(true);
            audio.play();
          }, 2000);
        })
        .catch(() => {
          setTimeout(() => {
            setIsActive(true);
            audio.play();
          }, 2000);
        });
    }
  };

  // Visual calculations
  const heatIntensity = temperature / 100;

  // Background: white -> yellow -> orange -> red -> dark red
  const bgHue = 60 - temperature * 0.6;
  const bgSaturation = Math.min(50 + temperature * 0.8, 100);
  const bgLightness = isCooledDown ? 95 : Math.max(95 - temperature * 0.5, 45);

  // Text color shifts
  const textColor =
    temperature > 60 ? "#fff" : temperature > 30 ? "#1a0000" : "#000";

  // Melt amount for text/borders (phase 2+)
  const meltAmount = phase >= 2 ? (temperature - 40) * 0.15 : 0;

  // Chromatic aberration (phase 4+)
  const chromaticOffset = phase >= 4 ? 2 + (phase - 4) * 3 : 0;

  // Scanline opacity (phase 3+)
  const scanlineOpacity = phase >= 3 ? 0.02 + (phase - 3) * 0.03 : 0;

  // Screen shake intensity
  const shakeIntensity = phase >= 3 ? 1 + (phase - 3) * 2 : 0;

  const showCoolButton = phase >= 4 && !isCooledDown;

  // Entry screen
  if (!hasEntered) {
    return (
      <div
        className="fixed inset-0 flex items-center justify-center cursor-pointer font-mono"
        style={{
          background: isHoveringEnter ? "#ff4400" : "#000",
          transition: "background 0.15s ease-out",
        }}
        onClick={handleEnter}
      >
        <span
          className="text-4xl font-bold uppercase tracking-[0.5em] select-none"
          style={{
            color: isHoveringEnter ? "#000" : "#ff4400",
            transition: "color 0.15s ease-out",
          }}
          onMouseEnter={() => setIsHoveringEnter(true)}
          onMouseLeave={() => setIsHoveringEnter(false)}
        >
          Enter
        </span>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative w-full min-h-screen overflow-hidden font-mono"
      style={{
        background: isCooledDown
          ? "#f5f5f5"
          : `hsl(${bgHue}, ${bgSaturation}%, ${bgLightness}%)`,
        color: isCooledDown ? "#000" : textColor,
        transition: isCooledDown
          ? "background 1s ease-out, color 1s ease-out"
          : "background 0.5s ease-out",
        filter: isInverted ? "invert(1)" : "none",
        cursor: phase >= 3 && !isCooledDown ? "none" : "auto",
        animation:
          shakeIntensity > 0 && !isCooledDown
            ? `shake ${0.3 - phase * 0.03}s ease-in-out infinite`
            : "none",
      }}
    >
      {/* Heat gradient overlay */}
      {!isCooledDown && temperature > 10 && (
        <div
          className="fixed inset-0 pointer-events-none"
          style={{
            zIndex: 1,
            background: `radial-gradient(ellipse at ${cursorPos.x}% ${cursorPos.y}%, 
              rgba(255, ${Math.max(150 - temperature, 0)}, 0, ${heatIntensity * 0.4}) 0%, 
              transparent 50%)`,
            transition: "background 0.1s ease-out",
          }}
        />
      )}

      {/* Heat shimmer effect */}
      {!isCooledDown && temperature > 20 && (
        <div
          className="fixed inset-0 pointer-events-none"
          style={{
            zIndex: 2,
            background: `repeating-linear-gradient(
              0deg,
              transparent,
              transparent 2px,
              rgba(255, ${100 - temperature}, 0, ${heatIntensity * 0.1}) 2px,
              rgba(255, ${100 - temperature}, 0, ${heatIntensity * 0.1}) 4px
            )`,
            animation: `heatShimmer ${Math.max(2 - heatIntensity, 0.5)}s ease-in-out infinite`,
          }}
        />
      )}

      {/* VHS Scanlines (phase 3+) */}
      {scanlineOpacity > 0 && !isCooledDown && (
        <div
          className="fixed inset-0 pointer-events-none"
          style={{
            zIndex: 1000,
            background: `repeating-linear-gradient(
              0deg,
              transparent,
              transparent 2px,
              rgba(0, 0, 0, ${scanlineOpacity}) 2px,
              rgba(0, 0, 0, ${scanlineOpacity}) 4px
            )`,
            mixBlendMode: "multiply",
            animation: phase >= 4 ? "vhsTracking 2s steps(1) infinite" : "none",
          }}
        />
      )}

      {/* Chromatic aberration layers (phase 4+) */}
      {chromaticOffset > 0 && !isCooledDown && (
        <>
          <div
            className="fixed inset-0 pointer-events-none"
            style={{
              zIndex: 999,
              background: `linear-gradient(90deg, rgba(255,0,0,0.1) 0%, transparent 50%)`,
              transform: `translateX(-${chromaticOffset}px)`,
              mixBlendMode: "screen",
            }}
          />
          <div
            className="fixed inset-0 pointer-events-none"
            style={{
              zIndex: 999,
              background: `linear-gradient(90deg, transparent 50%, rgba(0,0,255,0.1) 100%)`,
              transform: `translateX(${chromaticOffset}px)`,
              mixBlendMode: "screen",
            }}
          />
        </>
      )}

      {/* Custom flame cursor (phase 3+) */}
      {phase >= 3 && !isCooledDown && (
        <div
          className="fixed pointer-events-none select-none"
          style={{
            zIndex: 10001,
            left: `${cursorPos.x}%`,
            top: `${cursorPos.y}%`,
            transform: "translate(-50%, -50%)",
            fontSize: `${32 + phase * 8}px`,
            filter: "drop-shadow(0 0 10px #ff4400)",
            animation: `flamePulse ${Math.max(0.5 - phase * 0.1, 0.15)}s ease-in-out infinite`,
          }}
        >
          🔥
        </div>
      )}

      {/* Heat trails from cursor (phase 3+) */}
      {heatTrails.map((trail) => (
        <div
          key={trail.id}
          className="fixed pointer-events-none"
          style={{
            zIndex: 9999,
            left: `${trail.x}%`,
            top: `${trail.y}%`,
            width: `${20 * trail.scale}px`,
            height: `${20 * trail.scale}px`,
            background: `radial-gradient(circle, rgba(255, 100, 0, ${trail.opacity}) 0%, transparent 70%)`,
            transform: "translate(-50%, -50%)",
            borderRadius: "50%",
          }}
        />
      ))}

      {/* Sweat drops */}
      {sweatDrops.map((drop) => (
        <div
          key={drop.id}
          className="fixed pointer-events-none"
          style={{
            zIndex: 100,
            left: `${drop.x}%`,
            top: `${drop.y}%`,
            width: `${drop.size}px`,
            height: `${drop.size * 1.5}px`,
            background: `radial-gradient(ellipse at 30% 30%, rgba(150, 200, 255, ${drop.opacity}), rgba(100, 150, 200, ${drop.opacity * 0.8}))`,
            borderRadius: "50% 50% 50% 50% / 60% 60% 40% 40%",
            boxShadow: `0 0 ${drop.size / 2}px rgba(100, 150, 200, 0.3)`,
          }}
        />
      ))}

      {/* Fire particles */}
      {fireParticles.map((fire) => (
        <div
          key={fire.id}
          className="fixed pointer-events-none select-none"
          style={{
            zIndex: fire.stalker ? 150 : 50,
            left: `${fire.x}%`,
            top: `${fire.y}%`,
            fontSize: `${24 * fire.scale}px`,
            transform: `rotate(${fire.rotation}deg)`,
            opacity: fire.opacity,
            filter: fire.stalker
              ? "drop-shadow(0 0 8px #ff0000) hue-rotate(-20deg)"
              : "drop-shadow(0 0 5px #ff4400)",
            transition: "filter 0.3s",
          }}
        >
          {fire.stalker ? "🔥" : Math.random() > 0.5 ? "🔥" : "✨"}
        </div>
      ))}

      {/* Content */}
      <div className="relative max-w-3xl mx-auto p-8" style={{ zIndex: 20 }}>
        {/* Header */}
        <div
          className="flex justify-between items-center mb-8 pb-4"
          style={{
            borderBottom: `3px solid ${isCooledDown ? "#000" : textColor}`,
            transform:
              meltAmount > 0 ? `skewY(${meltAmount * 0.5}deg)` : "none",
            transition: "transform 0.3s ease-out",
          }}
        >
          <span
            className="text-xs uppercase tracking-widest"
            style={{
              opacity: 0.7,
              transform:
                meltAmount > 0 ? `translateY(${meltAmount * 2}px)` : "none",
            }}
          >
            &larr; jomcgi.dev
          </span>
          <span
            className="text-xs uppercase tracking-widest font-bold"
            style={{
              background:
                temperature > 50 ? "rgba(255,255,255,0.2)" : "rgba(0,0,0,0.1)",
              padding: "4px 12px",
            }}
          >
            {isCooledDown ? "COOLED" : `${Math.round(temperature)}°`}
          </span>
        </div>

        {/* Title - melts and drips */}
        <div
          style={{
            transform:
              meltAmount > 0
                ? `skewX(${meltAmount * 0.3}deg) translateY(${meltAmount}px)`
                : "none",
            transition: "transform 0.5s ease-out",
          }}
        >
          <h1
            className="text-3xl font-black uppercase tracking-widest mb-4"
            style={{
              textShadow:
                temperature > 70 && !isCooledDown
                  ? `0 0 ${temperature / 5}px #ff4400, 0 ${meltAmount}px ${meltAmount * 2}px rgba(255,68,0,0.5)`
                  : "none",
              letterSpacing: `${0.3 + meltAmount * 0.02}em`,
            }}
          >
            It's Getting Hot In Here
          </h1>
        </div>

        {/* Subtitle */}
        <p
          className="text-lg mb-12"
          style={{
            opacity: 0.8,
            transform:
              meltAmount > 0 ? `translateY(${meltAmount * 1.5}px)` : "none",
          }}
        >
          {isCooledDown
            ? "Ah... much better."
            : temperature > 80
              ? "🥵 MAXIMUM HEAT 🥵"
              : temperature > 60
                ? "So take off all your clothes..."
                : temperature > 40
                  ? "I am getting so hot..."
                  : "So hot."}
        </p>

        {/* Brutalist content blocks */}
        <div className="space-y-8">
          <div
            className="p-6"
            style={{
              background: isCooledDown
                ? "#000"
                : temperature > 50
                  ? "rgba(0,0,0,0.8)"
                  : "#000",
              color: isCooledDown ? "#fff" : temperature > 50 ? "#fff" : "#fff",
              transform:
                meltAmount > 0
                  ? `skewY(${-meltAmount * 0.3}deg) translateY(${meltAmount * 0.5}px)`
                  : "none",
              boxShadow:
                temperature > 60 && !isCooledDown
                  ? `0 ${meltAmount}px ${meltAmount * 3}px rgba(255, 68, 0, 0.4)`
                  : "none",
            }}
          >
            <div className="text-xs uppercase tracking-widest opacity-50 mb-3">
              Status Report
            </div>
            <p className="text-sm leading-relaxed">
              {isCooledDown
                ? "Systems nominal. Temperature stabilized. Crisis averted."
                : temperature > 80
                  ? "CRITICAL: Heat levels exceeding safe parameters. Immediate action required."
                  : temperature > 60
                    ? "WARNING: Temperature rising rapidly. Consider activating cooling systems."
                    : temperature > 40
                      ? "ADVISORY: Elevated heat detected. Monitoring situation."
                      : "All systems operating within normal parameters."}
            </p>
          </div>

          {/* Dripping border block */}
          <div
            className="p-6"
            style={{
              border: `3px solid ${isCooledDown ? "#000" : textColor}`,
              position: "relative",
              transform:
                meltAmount > 0
                  ? `perspective(500px) rotateX(${meltAmount * 0.2}deg)`
                  : "none",
            }}
          >
            {/* Drip effects on border */}
            {meltAmount > 5 && !isCooledDown && (
              <>
                <div
                  className="absolute"
                  style={{
                    bottom: "-20px",
                    left: "20%",
                    width: "8px",
                    height: `${meltAmount * 2}px`,
                    background: textColor,
                    borderRadius: "0 0 50% 50%",
                  }}
                />
                <div
                  className="absolute"
                  style={{
                    bottom: "-15px",
                    left: "60%",
                    width: "6px",
                    height: `${meltAmount * 1.5}px`,
                    background: textColor,
                    borderRadius: "0 0 50% 50%",
                  }}
                />
                <div
                  className="absolute"
                  style={{
                    bottom: "-25px",
                    left: "80%",
                    width: "10px",
                    height: `${meltAmount * 2.5}px`,
                    background: textColor,
                    borderRadius: "0 0 50% 50%",
                  }}
                />
              </>
            )}
            <div className="text-xs uppercase tracking-widest opacity-50 mb-3">
              Heat Index
            </div>
            <div className="flex items-center gap-4">
              <div
                className="flex-1 h-4 bg-gray-200"
                style={{ overflow: "hidden" }}
              >
                <div
                  className="h-full transition-all duration-300"
                  style={{
                    width: `${temperature}%`,
                    background: isCooledDown
                      ? "#4ade80"
                      : temperature > 80
                        ? "#ff0000"
                        : temperature > 60
                          ? "#ff4400"
                          : temperature > 40
                            ? "#ff8800"
                            : "#ffcc00",
                    boxShadow:
                      temperature > 60 && !isCooledDown
                        ? "0 0 20px currentColor"
                        : "none",
                  }}
                />
              </div>
              <span className="text-sm font-bold uppercase">
                {isCooledDown ? "SAFE" : `${Math.round(temperature)}%`}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* COOL DOWN button - runs from cursor */}
      {showCoolButton && (
        <button
          ref={coolButtonRef}
          onClick={handleCoolDown}
          className="fixed px-6 py-4 text-sm font-bold uppercase tracking-wide"
          style={{
            zIndex: 10000,
            left: `${coolButtonPos.x}px`,
            bottom: `${coolButtonPos.y}px`,
            border: "3px solid #00aaff",
            background: "#00aaff",
            color: "#000",
            cursor: "pointer",
            transform: `scale(${buttonScale})`,
            transformOrigin: "center",
            transition: "transform 0.1s ease-out",
            boxShadow: "0 0 20px rgba(0, 170, 255, 0.5)",
            animation: "coolPulse 0.5s ease-in-out infinite",
          }}
        >
          ❄️ COOL DOWN ❄️
        </button>
      )}

      {/* Cooled down message */}
      {isCooledDown && temperature === 0 && (
        <div
          className="fixed bottom-8 left-1/2 transform -translate-x-1/2 px-8 py-4 text-center"
          style={{
            zIndex: 10000,
            background: "#000",
            color: "#fff",
            animation: "fadeIn 1s ease-out",
          }}
        >
          <div className="text-xs uppercase tracking-widest opacity-50 mb-2">
            System Restored
          </div>
          <div className="text-lg font-bold uppercase tracking-wide">
            Crisis Averted
          </div>
        </div>
      )}

      <style>{`
        @keyframes shake {
          0%, 100% { transform: translate(0, 0); }
          10% { transform: translate(-${shakeIntensity}px, -${shakeIntensity * 0.5}px); }
          20% { transform: translate(${shakeIntensity}px, ${shakeIntensity * 0.5}px); }
          30% { transform: translate(-${shakeIntensity * 0.5}px, ${shakeIntensity}px); }
          40% { transform: translate(${shakeIntensity * 0.5}px, -${shakeIntensity}px); }
          50% { transform: translate(-${shakeIntensity}px, ${shakeIntensity * 0.5}px); }
          60% { transform: translate(${shakeIntensity}px, -${shakeIntensity * 0.5}px); }
          70% { transform: translate(-${shakeIntensity * 0.5}px, -${shakeIntensity}px); }
          80% { transform: translate(${shakeIntensity * 0.5}px, ${shakeIntensity}px); }
          90% { transform: translate(-${shakeIntensity}px, -${shakeIntensity * 0.5}px); }
        }
        @keyframes heatShimmer {
          0%, 100% { 
            transform: translateY(0) scaleY(1); 
            opacity: 0.5; 
          }
          50% { 
            transform: translateY(-3px) scaleY(1.01); 
            opacity: 0.8; 
          }
        }
        @keyframes vhsTracking {
          0%, 94%, 100% { transform: translateX(0); }
          95% { transform: translateX(-4px); }
          96% { transform: translateX(6px); }
          97% { transform: translateX(-2px); }
          98% { transform: translateX(3px); }
          99% { transform: translateX(-1px); }
        }
        @keyframes flamePulse {
          0%, 100% { 
            transform: translate(-50%, -50%) scale(1) rotate(-5deg); 
          }
          50% { 
            transform: translate(-50%, -50%) scale(1.2) rotate(5deg); 
          }
        }
        @keyframes coolPulse {
          0%, 100% { 
            box-shadow: 0 0 20px rgba(0, 170, 255, 0.5); 
          }
          50% { 
            box-shadow: 0 0 40px rgba(0, 170, 255, 0.8), 0 0 60px rgba(0, 170, 255, 0.4); 
          }
        }
        @keyframes fadeIn {
          0% { opacity: 0; transform: translate(-50%, 20px); }
          100% { opacity: 1; transform: translate(-50%, 0); }
        }
      `}</style>
    </div>
  );
}
