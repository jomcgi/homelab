// esbuild entry point - CSS loaded via HTML link tag instead of import
// This avoids Tailwind v4's @import "tailwindcss" which esbuild can't process
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Router } from "wouter";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Router>
      <App />
    </Router>
  </StrictMode>,
);
