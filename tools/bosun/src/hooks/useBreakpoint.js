import { useState, useEffect } from "react";

export function useBreakpoint() {
  const [bp, setBp] = useState(() =>
    typeof window === "undefined" ? "desktop" : window.innerWidth < 768 ? "mobile" : "desktop",
  );
  useEffect(() => {
    const check = () => setBp(window.innerWidth < 768 ? "mobile" : "desktop");
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  return bp;
}
