import { useState, useCallback, useRef } from "react";

export function useResizable({ initialWidth = 420, minWidth = 280, maxWidth = 900 } = {}) {
  const [width, setWidth] = useState(initialWidth);
  const dragging = useRef(false);

  const onMouseDown = useCallback((e) => {
    e.preventDefault();
    dragging.current = true;
    const startX = e.clientX;
    const startWidth = width;

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMouseMove = (ev) => {
      if (!dragging.current) return;
      // Panel is on the right, so dragging left = wider
      const delta = startX - ev.clientX;
      const next = Math.min(maxWidth, Math.max(minWidth, startWidth + delta));
      setWidth(next);
    };

    const onMouseUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, [width, minWidth, maxWidth]);

  return { width, onMouseDown };
}
