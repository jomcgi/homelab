import { useState, useEffect, useCallback, useRef } from "react";

const JT_GIF_URL = "/jt.gif";
const JT_HEAD_URL = "/justin_head.png";

const MAX_JTS = 10000;

// Faster escalation - gets crunchy quick
const SPAWN_SCHEDULE = [
  { interval: 1500, count: 2, minScale: 0.15, maxScale: 0.4 }, // Phase 1: small Justins
  { interval: 800, count: 3, minScale: 0.2, maxScale: 0.5 }, // Phase 2
  { interval: 400, count: 4, minScale: 0.25, maxScale: 0.6 }, // Phase 3 - KICK button appears
  { interval: 200, count: 5, minScale: 0.3, maxScale: 0.8 }, // Phase 4
  { interval: 100, count: 8, minScale: 0.4, maxScale: 1.0 }, // Phase 5
  { interval: 50, count: 10, minScale: 0.5, maxScale: 1.2 }, // Phase 6
  { interval: 25, count: -1, minScale: 0.6, maxScale: 1.5 }, // Phase 7: BIG JUSTINS FOREVER 🔥
];

// Screen inversion timing per phase (ms)
const INVERSION_SCHEDULE: Record<number, { min: number; max: number } | null> =
  {
    0: null,
    1: null,
    2: null, // Phases 1-3: none
    3: { min: 5000, max: 8000 }, // Phase 4: occasional
    4: { min: 3000, max: 5000 }, // Phase 5: more frequent
    5: { min: 2000, max: 3000 }, // Phase 6: frequent
    6: { min: 500, max: 1000 }, // Phase 7: chaotic
  };

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
  kickVelocityX: number; // 🆕 Horizontal kick velocity for cursor bounce
  cursorBounced: boolean; // 🆕 Was this bounced off cursor? (grows as it flies)
  stalker: boolean; // 🆕 Cursor-stalking Justins
}

export default function SexyBackDemo() {
  const [jts, setJts] = useState<JT[]>([]);
  const [hasEntered, setHasEntered] = useState(false);
  const [isHoveringEnter, setIsHoveringEnter] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [isKicked, setIsKicked] = useState(false);
  const [phase, setPhase] = useState(0);
  const [spawnedInPhase, setSpawnedInPhase] = useState(0);
  const [darkMode, setDarkMode] = useState(false);
  const [isInverted, setIsInverted] = useState(false); // 🆕 Screen flash
  const [cursorPos, setCursorPos] = useState({ x: 50, y: 50 }); // 🆕 Cursor tracking (%)
  const [kickButtonPos, setKickButtonPos] = useState({ x: 24, y: 24 }); // 🆕 Evasive button position (px from bottom-left)
  const animationRef = useRef<number | null>(null);
  const kickTimeRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const kickButtonRef = useRef<HTMLButtonElement | null>(null);

  // Load audio
  useEffect(() => {
    const audio = new Audio("https://cdn.jomcgi.dev/SexyBack.mp3");
    audio.loop = true;
    audioRef.current = audio;

    return () => {
      audio.pause();
      audio.src = "";
    };
  }, []);

  // 🆕 Cursor tracking for stalker Justins and evasive button
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

  // Button behavior: Desktop = runs away from cursor + shrinks, Mobile = bounces around fast
  const kickButtonAnimRef = useRef<number | null>(null);
  const buttonVelocityRef = useRef({ vx: 2, vy: 1.5 });
  const [buttonScale, setButtonScale] = useState(1);
  const isTouchDevice =
    typeof window !== "undefined" &&
    ("ontouchstart" in window || navigator.maxTouchPoints > 0);

  useEffect(() => {
    const shouldShowKickButton = phase >= 5 && !isKicked;
    if (!shouldShowKickButton) {
      if (kickButtonAnimRef.current)
        cancelAnimationFrame(kickButtonAnimRef.current);
      return;
    }

    const updateButtonPosition = () => {
      if (!kickButtonRef.current || !containerRef.current) {
        kickButtonAnimRef.current = requestAnimationFrame(updateButtonPosition);
        return;
      }

      const button = kickButtonRef.current;
      const container = containerRef.current;
      const buttonRect = button.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const margin = 20;
      const maxX = containerRect.width - buttonRect.width - margin;
      const maxY = containerRect.height - buttonRect.height - margin;

      if (isTouchDevice) {
        // MOBILE: Constant bouncing movement
        const baseSpeed = 4 + (phaseRef.current - 5) * 4;

        setKickButtonPos((prev) => {
          let newX = prev.x + buttonVelocityRef.current.vx * baseSpeed;
          let newY = prev.y + buttonVelocityRef.current.vy * baseSpeed;

          if (newX <= margin || newX >= maxX) {
            buttonVelocityRef.current.vx *= -1;
            buttonVelocityRef.current.vy += (Math.random() - 0.5) * 1.5;
            newX = Math.max(margin, Math.min(maxX, newX));
          }
          if (newY <= margin || newY >= maxY) {
            buttonVelocityRef.current.vy *= -1;
            buttonVelocityRef.current.vx += (Math.random() - 0.5) * 1.5;
            newY = Math.max(margin, Math.min(maxY, newY));
          }

          // Clamp velocity
          const maxVel = 5;
          const minVel = 1;
          buttonVelocityRef.current.vx =
            Math.sign(buttonVelocityRef.current.vx) *
            Math.max(
              minVel,
              Math.min(maxVel, Math.abs(buttonVelocityRef.current.vx)),
            );
          buttonVelocityRef.current.vy =
            Math.sign(buttonVelocityRef.current.vy) *
            Math.max(
              minVel,
              Math.min(maxVel, Math.abs(buttonVelocityRef.current.vy)),
            );

          return { x: newX, y: newY };
        });
      } else {
        // DESKTOP: Run away from cursor + shrink when close
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

        // Threshold increases with phase
        const threshold = 300 + (phaseRef.current - 5) * 100;

        // Shrink as cursor gets closer (1.0 at threshold, 0.4 minimum at distance 0)
        const newScale =
          distance < threshold ? 0.4 + 0.6 * (distance / threshold) : 1;
        setButtonScale(newScale);

        if (distance < threshold && distance > 0) {
          const escapeX = -dx / distance;
          const escapeY = -dy / distance;

          const proximity = 1 - distance / threshold;
          const baseSpeed = 30 + (phaseRef.current - 5) * 15;
          const speed = baseSpeed * proximity * proximity;

          setKickButtonPos((prev) => {
            let newX = prev.x + escapeX * speed;
            let newY = prev.y - escapeY * speed;

            newX = Math.max(margin, Math.min(maxX, newX));
            newY = Math.max(margin, Math.min(maxY, newY));

            return { x: newX, y: newY };
          });
        }
      }

      kickButtonAnimRef.current = requestAnimationFrame(updateButtonPosition);
    };

    // Randomize initial direction for mobile
    if (isTouchDevice) {
      buttonVelocityRef.current = {
        vx: (Math.random() > 0.5 ? 1 : -1) * (2 + Math.random() * 2),
        vy: (Math.random() > 0.5 ? 1 : -1) * (2 + Math.random() * 2),
      };
    }

    kickButtonAnimRef.current = requestAnimationFrame(updateButtonPosition);
    return () => {
      if (kickButtonAnimRef.current)
        cancelAnimationFrame(kickButtonAnimRef.current);
    };
  }, [phase, isKicked]);

  // 🆕 Screen inversion flashes
  useEffect(() => {
    if (!isActive || isKicked) {
      setIsInverted(false); // Reset on kick
      return;
    }

    const schedule = INVERSION_SCHEDULE[phase];
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
        // Flash duration: 50-150ms
        flashTimeout = setTimeout(
          () => {
            if (cancelled) return;
            setIsInverted(false);
            scheduleFlash();
          },
          50 + Math.random() * 100,
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
  }, [isActive, isKicked, phase]);

  const spawnJT = useCallback(() => {
    if (isKicked) return;

    setJts((prev) => {
      if (prev.length >= MAX_JTS) return prev;

      let startY;
      if (Math.random() < 0.8) {
        startY = -20 + Math.random() * 15;
      } else {
        startY = Math.random() * 15;
      }

      // Get scale range from current phase, weight towards larger
      const schedule =
        SPAWN_SCHEDULE[phase] || SPAWN_SCHEDULE[SPAWN_SCHEDULE.length - 1];
      const { minScale, maxScale } = schedule;
      // Bias towards larger: use square of random to skew distribution up
      const scaleBias = Math.pow(Math.random(), 0.5); // sqrt makes it favor larger values
      const scale = minScale + scaleBias * (maxScale - minScale);

      // 🆕 ~20% chance of being a stalker, increases with phase
      const stalkerChance = 0.15 + phase * 0.03;
      const isStalker = Math.random() < stalkerChance;

      const newJT: JT = {
        id: Date.now() + Math.random(),
        x: Math.random() * 90 + 3,
        y: startY,
        scale: scale,
        opacity: 0.4 + Math.random() * 0.5,
        rotation: -45 + Math.random() * 90,
        rotationSpeed:
          (0.2 + Math.random() * 1.0) * (Math.random() > 0.5 ? 1 : -1),
        fallSpeed: 0.08 + Math.random() * 0.5,
        landed: false,
        kicked: false,
        kickSpeed: 0,
        kickVelocityX: 0,
        cursorBounced: false,
        stalker: isStalker,
      };

      return [...prev, newJT];
    });
  }, [isKicked, phase]);

  // Store cursor position in a ref for physics loop (avoids re-creating the loop on every mouse move)
  const cursorPosRef = useRef(cursorPos);
  const phaseRef = useRef(phase);
  const kickButtonPosRef = useRef(kickButtonPos);
  useEffect(() => {
    cursorPosRef.current = cursorPos;
  }, [cursorPos]);
  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);
  useEffect(() => {
    kickButtonPosRef.current = kickButtonPos;
  }, [kickButtonPos]);

  // Physics update loop
  useEffect(() => {
    if (!isActive) return;

    const updatePhysics = () => {
      const cursor = cursorPosRef.current;
      const currentPhase = phaseRef.current;

      setJts((prev) => {
        // Remove JTs that have flown off any edge
        const filtered = prev.filter((jt) => {
          if (!jt.kicked) return true;
          return jt.y > -30 && jt.y < 130 && jt.x > -30 && jt.x < 130;
        });

        if (filtered.length === 0 && isKicked) {
          // All JTs gone, could trigger something here
        }

        let changed = filtered.length !== prev.length;
        const updated = filtered.map((jt) => {
          // If kicked, fly off screen (upward + horizontal)
          if (jt.kicked) {
            changed = true;
            // 🆕 Cursor-bounced Justins grow MASSIVE as they fly away
            const newScale = jt.cursorBounced
              ? jt.scale * 1.4 // ~10x size over 6-7 frames
              : jt.scale;
            return {
              ...jt,
              x: jt.x + jt.kickVelocityX,
              y: jt.y - jt.kickSpeed,
              scale: newScale,
              rotation: jt.rotation + jt.rotationSpeed * 3,
            };
          }

          if (jt.landed) {
            // 🆕 Landed stalkers drift towards cursor - faster on desktop, accelerate near kick button
            if (jt.stalker) {
              const dx = cursor.x - jt.x;
              const dy = cursor.y - jt.y;
              const distance = Math.sqrt(dx * dx + dy * dy);

              // Calculate proximity multiplier for EXTREME button acceleration
              let proximityMultiplier = 1;
              const kickBtn = kickButtonPosRef.current;
              const container = containerRef.current;
              if (container && currentPhase >= 5) {
                const containerRect = container.getBoundingClientRect();
                const kickBtnX = (kickBtn.x / containerRect.width) * 100;
                const kickBtnY =
                  ((containerRect.height - kickBtn.y) / containerRect.height) *
                  100;

                const cursorToKickDx = cursor.x - kickBtnX;
                const cursorToKickDy = cursor.y - kickBtnY;
                const cursorToKickDist = Math.sqrt(
                  cursorToKickDx * cursorToKickDx +
                    cursorToKickDy * cursorToKickDy,
                );

                // EXTREME acceleration near button - up to 8x speed!
                const accelThreshold = 35;
                if (cursorToKickDist < accelThreshold) {
                  const proximity = 1 - cursorToKickDist / accelThreshold;
                  proximityMultiplier = 1 + proximity * proximity * 7; // Exponential ramp to 8x
                }
              }

              // 🆕 Cursor collision! Bounce off in random direction - bigger hitbox near button
              const collisionRadius =
                (3 + jt.scale * 2) * Math.min(proximityMultiplier, 2);
              if (distance < collisionRadius) {
                changed = true;
                // Random angle, biased away from cursor
                const awayAngle = Math.atan2(-dy, -dx);
                const randomSpread = (Math.random() - 0.5) * Math.PI; // ±90° spread
                const kickAngle = awayAngle + randomSpread;

                // Kick power scales with proximity - EXPLOSIVE near button!
                const kickPower =
                  (1.5 + Math.random() * 1.5 + currentPhase * 0.3) *
                  Math.min(proximityMultiplier, 3);
                return {
                  ...jt,
                  kicked: true,
                  landed: false,
                  cursorBounced: true, // 🆕 Will grow massive as it flies
                  kickSpeed: Math.abs(Math.sin(kickAngle)) * kickPower + 0.5, // Always some upward
                  kickVelocityX: Math.cos(kickAngle) * kickPower,
                  rotationSpeed:
                    (3 + Math.random() * 5) * (Math.random() > 0.5 ? 1 : -1),
                };
              }

              if (distance > 2) {
                // Only move if not already at cursor
                // Base drift speed with EXTREME multiplier near button
                const baseDriftSpeed =
                  (0.08 + currentPhase * 0.04) * proximityMultiplier;

                const driftX = (dx / distance) * baseDriftSpeed;
                const driftY = (dy / distance) * baseDriftSpeed * 0.4;

                changed = true;
                return {
                  ...jt,
                  x: jt.x + driftX,
                  y: Math.min(jt.y + driftY, 92 - jt.scale * 15), // Don't go below ground
                };
              }
            }
            return jt;
          }

          const groundLevel = 92 - jt.scale * 15;
          let newX = jt.x;
          let newY = jt.y + jt.fallSpeed;
          let newRotation = jt.rotation + jt.rotationSpeed;

          // 🆕 Falling stalkers drift towards cursor horizontally - faster on desktop
          if (jt.stalker) {
            const dx = cursor.x - jt.x;
            const dy = cursor.y - jt.y;
            const distanceToCursor = Math.sqrt(dx * dx + dy * dy);

            // Calculate proximity multiplier for button acceleration
            let proximityMultiplier = 1;
            const kickBtn = kickButtonPosRef.current;
            const container = containerRef.current;
            if (container && currentPhase >= 5) {
              const containerRect = container.getBoundingClientRect();
              const kickBtnX = (kickBtn.x / containerRect.width) * 100;
              const kickBtnY =
                ((containerRect.height - kickBtn.y) / containerRect.height) *
                100;

              const cursorToKickDx = cursor.x - kickBtnX;
              const cursorToKickDy = cursor.y - kickBtnY;
              const cursorToKickDist = Math.sqrt(
                cursorToKickDx * cursorToKickDx +
                  cursorToKickDy * cursorToKickDy,
              );

              // EXTREME acceleration near button - up to 8x speed!
              const accelThreshold = 35;
              if (cursorToKickDist < accelThreshold) {
                const proximity = 1 - cursorToKickDist / accelThreshold;
                proximityMultiplier = 1 + proximity * proximity * 7; // Exponential ramp to 8x
              }
            }

            // 🆕 Cursor collision for falling stalkers too!
            const collisionRadius =
              (4 + jt.scale * 2) * Math.min(proximityMultiplier, 2); // Bigger hitbox near button
            if (distanceToCursor < collisionRadius) {
              const awayAngle = Math.atan2(-dy, -dx);
              const randomSpread = (Math.random() - 0.5) * Math.PI;
              const kickAngle = awayAngle + randomSpread;

              const kickPower =
                (1.5 + Math.random() * 1.5 + currentPhase * 0.3) *
                Math.min(proximityMultiplier, 3);
              changed = true;
              return {
                ...jt,
                kicked: true,
                landed: false,
                cursorBounced: true, // 🆕 Will grow massive as it flies
                kickSpeed: Math.abs(Math.sin(kickAngle)) * kickPower + 0.5,
                kickVelocityX: Math.cos(kickAngle) * kickPower,
                rotationSpeed:
                  (3 + Math.random() * 5) * (Math.random() > 0.5 ? 1 : -1),
              };
            }

            let driftSpeed = (0.15 + currentPhase * 0.06) * proximityMultiplier;
            newX =
              jt.x +
              Math.sign(dx) *
                Math.min(Math.abs(dx) * 0.04 * proximityMultiplier, driftSpeed);
          }

          if (newY >= groundLevel) {
            changed = true;
            return {
              ...jt,
              x: newX,
              y: groundLevel,
              rotation: 0,
              landed: true,
            };
          }

          changed = true;
          return {
            ...jt,
            x: newX,
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

      setSpawnedInPhase((prev) => {
        const newCount = prev + 1;
        if (schedule.count !== -1 && newCount >= schedule.count) {
          setPhase((p) => Math.min(p + 1, SPAWN_SCHEDULE.length - 1));
          return 0;
        }
        return newCount;
      });
    }, schedule.interval);

    return () => clearInterval(interval);
  }, [isActive, isKicked, phase, spawnJT]);

  const kickJustinOut = () => {
    setIsKicked(true);
    kickTimeRef.current = Date.now();
    audioRef.current?.pause();

    // Calculate kick speed so all JTs exit within ~1.5s (~90 frames at 60fps)
    // Each JT needs to travel from current Y to -30 (off screen top)
    // Speed = distance / frames, with some randomness
    const TARGET_FRAMES = 70; // ~1.17s at 60fps, leaves buffer

    setJts((prev) =>
      prev.map((jt) => {
        const distanceToExit = jt.y + 30; // distance to y=-30
        const baseSpeed = distanceToExit / TARGET_FRAMES;
        // Add 20-50% random variation for staggered effect
        const kickSpeed = baseSpeed * (1.2 + Math.random() * 0.5);

        return {
          ...jt,
          kicked: true,
          landed: false,
          cursorBounced: false, // Button kick - don't grow
          kickSpeed: kickSpeed,
          kickVelocityX: (Math.random() - 0.5) * 0.8, // Slight horizontal scatter
          rotationSpeed:
            (2 + Math.random() * 4) * (Math.random() > 0.5 ? 1 : -1),
        };
      }),
    );
  };

  const bgColor = darkMode ? "#000" : "#fff";
  const fgColor = darkMode ? "#fff" : "#000";
  const showKickButton = phase >= 5 && !isKicked; // Appears when chromatic aberration starts

  // 🆕 Chromatic aberration intensity (px) - only in phase 5+
  const chromaticOffset =
    isActive && !isKicked && phase >= 5
      ? 2 + (phase - 5) * 4 // 2px at phase 5, 6px at phase 6, 10px at phase 7
      : 0;

  // 🆕 Scanline opacity - only in phase 4+
  const scanlineOpacity =
    isActive && !isKicked && phase >= 4
      ? Math.min(0.03 + (phase - 4) * 0.04, 0.15)
      : 0;

  // Handle enter - unlock audio immediately for mobile, then delay start
  const handleEnter = () => {
    setHasEntered(true);

    // Unlock audio on mobile by playing then immediately pausing
    const audio = audioRef.current;
    if (audio) {
      audio
        .play()
        .then(() => {
          audio.pause();
          audio.currentTime = 0;

          // Now we can play after delay since audio is "unlocked"
          setTimeout(() => {
            setIsActive(true);
            audio.play();
            spawnJT();
          }, 5000);
        })
        .catch(() => {
          // Fallback if play fails - just start after delay anyway
          setTimeout(() => {
            setIsActive(true);
            audio.play();
            spawnJT();
          }, 5000);
        });
    }
  };

  // Entry screen
  if (!hasEntered) {
    return (
      <div
        className="fixed inset-0 flex items-center justify-center cursor-pointer font-mono"
        style={{
          background: isHoveringEnter ? "#fff" : "#000",
          transition: "background 0.15s ease-out",
        }}
        onClick={handleEnter}
      >
        <span
          className="text-4xl font-bold uppercase tracking-[0.5em] select-none"
          style={{
            color: isHoveringEnter ? "#000" : "#fff",
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
        background: bgColor,
        color: fgColor,
        animation:
          phase >= 4 && !isKicked ? "shake 0.3s ease-in-out infinite" : "none",
        filter: isInverted ? "invert(1)" : "none",
        transition: "filter 0.05s ease-out",
        cursor: isActive && !isKicked && phase >= 3 ? "none" : "auto",
      }}
    >
      {/* Background pulse - delayed to phase 6+ */}
      {isActive && !isKicked && phase >= 5 && (
        <div
          className="fixed inset-0 pointer-events-none"
          style={{
            zIndex: 1,
            background:
              "linear-gradient(45deg, #ff6b6b, #4d96ff, #9b59b6, #ffd93d)",
            backgroundSize: "400% 400%",
            animation:
              "gradient 2s ease infinite, pulse 0.5s ease-in-out infinite",
            opacity: 0.05 + (phase - 5) * 0.05, // Gradually increases
          }}
        />
      )}

      {/* 🆕 VHS Scanlines overlay with tracking glitch */}
      {scanlineOpacity > 0 && (
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
            animation: phase >= 5 ? "vhsTracking 3s steps(1) infinite" : "none",
          }}
        />
      )}

      {/* 🆕 Chromatic aberration layers */}
      {chromaticOffset > 0 && (
        <>
          {/* Red channel - shifted left */}
          <div
            className="fixed inset-0 pointer-events-none"
            style={{
              zIndex: 999,
              background: "inherit",
              transform: `translateX(-${chromaticOffset}px)`,
              opacity: 0.5,
              mixBlendMode: "multiply",
              filter: "url(#redChannel)",
            }}
          />
          {/* Blue channel - shifted right */}
          <div
            className="fixed inset-0 pointer-events-none"
            style={{
              zIndex: 999,
              background: "inherit",
              transform: `translateX(${chromaticOffset}px)`,
              opacity: 0.5,
              mixBlendMode: "multiply",
              filter: "url(#blueChannel)",
            }}
          />
          {/* SVG filters for color channel separation */}
          <svg style={{ position: "absolute", width: 0, height: 0 }}>
            <defs>
              <filter id="redChannel">
                <feColorMatrix
                  type="matrix"
                  values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"
                />
              </filter>
              <filter id="blueChannel">
                <feColorMatrix
                  type="matrix"
                  values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0"
                />
              </filter>
            </defs>
          </svg>
        </>
      )}

      {/* Custom JT head cursor - kicks in at phase 3 */}
      {isActive && !isKicked && phase >= 3 && (
        <div
          className="fixed pointer-events-none"
          style={{
            zIndex: 10000,
            left: `${cursorPos.x}%`,
            top: `${cursorPos.y}%`,
            width: "48px",
            height: "48px",
            backgroundImage: `url(${JT_HEAD_URL})`,
            backgroundSize: "contain",
            backgroundRepeat: "no-repeat",
            backgroundPosition: "center",
            transform: "translate(-50%, -50%)",
            filter: darkMode ? "invert(1)" : "none",
            animation:
              phase >= 5
                ? `cursorSpin ${Math.max(2 - (phase - 5) * 0.5, 0.3)}s linear infinite, cursorPulse ${Math.max(1 - (phase - 5) * 0.2, 0.2)}s ease-in-out infinite`
                : "none",
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
              width: "100px",
              height: "200px",
              backgroundImage: `url(${JT_GIF_URL})`,
              backgroundSize: "contain",
              backgroundRepeat: "no-repeat",
              backgroundPosition: "bottom center",
              transform: `scale(${jt.scale}) rotate(${jt.rotation}deg)`,
              opacity: jt.opacity,
              filter: darkMode ? "invert(1)" : "none",
              transition:
                jt.landed && !jt.kicked ? "transform 0.3s ease-out" : "none",
              willChange: jt.landed && !jt.kicked ? "auto" : "transform",
            }}
          />
        ))}
      </div>

      {/* Content */}
      <div className="relative max-w-3xl mx-auto p-8" style={{ zIndex: 20 }}>
        <div
          className="flex justify-between items-center mb-8 pb-4"
          style={{ borderBottom: `2px solid ${fgColor}` }}
        >
          <span className="text-xs uppercase tracking-widest opacity-70">
            ← jomcgi.dev
          </span>
          <button
            onClick={() => setDarkMode(!darkMode)}
            className="px-3 py-1 text-xs uppercase tracking-wide transition-colors"
            style={{
              border: `2px solid ${fgColor}`,
              background: "transparent",
              color: fgColor,
            }}
          >
            Invert
          </button>
        </div>
        <div>
          <h1
            className="text-2xl font-bold uppercase tracking-widest mb-4"
            style={{
              background: bgColor,
              display: "inline-block",
              padding: "0 4px",
            }}
          >
            The JT Archives
          </h1>
        </div>
        <p
          className="opacity-70 mb-12"
          style={{ background: bgColor, display: "inline", padding: "0 4px" }}
        >
          A comprehensive study of bringing sexy back.
        </p>

        <div className="mb-12 mt-8">
          <div
            className="flex items-baseline gap-4 mb-6 pb-2"
            style={{ borderBottom: `2px solid ${fgColor}` }}
          >
            <span
              className="text-xs opacity-50 uppercase tracking-widest"
              style={{ background: bgColor, padding: "0 4px" }}
            >
              01
            </span>
            <h2
              className="text-lg font-bold uppercase tracking-wide"
              style={{ background: bgColor, padding: "0 4px" }}
            >
              SexyBack (2006)
            </h2>
          </div>

          <div
            className="p-5 mb-6"
            style={{ background: fgColor, color: bgColor }}
          >
            <div className="text-xs uppercase tracking-widest opacity-70 mb-2">
              Cultural Impact
            </div>
            <p>
              The track that redefined pop music. Timbaland's production created
              something the world wasn't ready for.
            </p>
          </div>

          <p
            style={{
              background: bgColor,
              padding: "4px 8px",
              display: "inline-block",
              marginBottom: "8px",
            }}
          >
            "I'm bringing sexy back. Them other boys don't know how to act."
          </p>
          <br />
          <p
            style={{
              background: bgColor,
              padding: "4px 8px",
              display: "inline-block",
              marginBottom: "8px",
            }}
          >
            Peak position: #1 in 11 countries. Grammy Award winner.
          </p>
        </div>

        <div className="mb-12">
          <div
            className="flex items-baseline gap-4 mb-6 pb-2"
            style={{ borderBottom: `2px solid ${fgColor}` }}
          >
            <span
              className="text-xs opacity-50 uppercase tracking-widest"
              style={{ background: bgColor, padding: "0 4px" }}
            >
              02
            </span>
            <h2
              className="text-lg font-bold uppercase tracking-wide"
              style={{ background: bgColor, padding: "0 4px" }}
            >
              The *NSYNC Era
            </h2>
          </div>

          <div
            className="p-5 mb-6"
            style={{ background: fgColor, color: bgColor }}
          >
            <div className="text-xs uppercase tracking-widest opacity-70 mb-2">
              Foundation
            </div>
            <p>
              Before the solo career, there was the boy band that sold 70
              million records worldwide.
            </p>
          </div>

          <p
            style={{
              background: bgColor,
              padding: "4px 8px",
              display: "inline-block",
              marginBottom: "8px",
            }}
          >
            "It's gonna be me." — a prophecy fulfilled.
          </p>
          <br />
          <p
            style={{
              background: bgColor,
              padding: "4px 8px",
              display: "inline-block",
              marginBottom: "8px",
            }}
          >
            Ramen noodle hair. Denim on denim. Icons only.
          </p>
        </div>
      </div>

      {/* KICK JUSTIN OUT button - 🆕 VERY evasive! */}
      {showKickButton && (
        <button
          ref={kickButtonRef}
          onClick={kickJustinOut}
          className="fixed px-5 py-3 text-sm uppercase tracking-wide"
          style={{
            zIndex: 9999, // Highest priority rendering
            left: `${kickButtonPos.x}px`,
            bottom: `${kickButtonPos.y}px`,
            border: "2px solid #ff4444",
            background: "#ff4444",
            color: "#fff",
            cursor: "pointer",
            willChange: "left, bottom, transform",
            transform: `scale(${buttonScale})`,
            transformOrigin: "center",
            transition: "transform 0.1s ease-out",
          }}
        >
          🚫 Kick Justin Out
        </button>
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
        @keyframes vhsTracking {
          0%, 94%, 100% { transform: translateX(0); }
          95% { transform: translateX(-5px); }
          96% { transform: translateX(8px); }
          97% { transform: translateX(-3px); }
          98% { transform: translateX(4px); }
          99% { transform: translateX(-2px); }
        }
        @keyframes noise {
          0%, 100% { background-position: 0 0; }
          10% { background-position: -5% -10%; }
          20% { background-position: -15% 5%; }
          30% { background-position: 7% -25%; }
          40% { background-position: 20% 25%; }
          50% { background-position: -25% 10%; }
          60% { background-position: 15% 5%; }
          70% { background-position: 0% 15%; }
          80% { background-position: 25% 35%; }
          90% { background-position: -10% 10%; }
        }
        @keyframes cursorSpin {
          0% { transform: translate(-50%, -50%) rotate(0deg); }
          100% { transform: translate(-50%, -50%) rotate(360deg); }
        }
        @keyframes cursorPulse {
          0%, 100% { width: 48px; height: 48px; }
          50% { width: 72px; height: 72px; }
        }
      `}</style>
    </div>
  );
}
