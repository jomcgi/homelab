import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import InspectorApp from "./inspector/InspectorApp";
import ChatApp from "./chat/ChatApp";
import { useAuth } from "./hooks/useAuth";

function App() {
  // Handle auth token extraction from URL fragment (for backward compatibility)
  useAuth();

  // No auth check - Cloudflare handles SSO
  return (
    <Router
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Routes>
        <Route path="/*" element={<ChatApp />} />
        <Route path="/inspector" element={<InspectorApp />} />
      </Routes>
    </Router>
  );
}

export default App;
