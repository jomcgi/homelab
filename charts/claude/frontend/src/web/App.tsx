import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import InspectorApp from "./inspector/InspectorApp";
import ChatApp from "./chat/ChatApp";
import { useAuth } from "./hooks/useAuth";
import { useRegisterSW } from "virtual:pwa-register/react";

function App() {
  // Handle auth token extraction from URL fragment (for backward compatibility)
  useAuth();

  // Service worker update detection
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegistered(r) {
      console.log("SW Registered:", r);
    },
    onRegisterError(error) {
      console.log("SW registration error", error);
    },
  });

  // No auth check - Cloudflare handles SSO
  return (
    <>
      {needRefresh && (
        <div className="fixed top-0 left-0 right-0 bg-blue-600 text-white p-3 text-center z-[9999] shadow-lg">
          <span className="font-medium">New version available!</span>
          <button
            onClick={() => updateServiceWorker(true)}
            className="ml-4 bg-white text-blue-600 px-4 py-1 rounded hover:bg-gray-100 transition-colors font-medium"
          >
            Refresh Now
          </button>
          <button
            onClick={() => setNeedRefresh(false)}
            className="ml-2 text-white hover:text-gray-200 px-2"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}
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
    </>
  );
}

export default App;
