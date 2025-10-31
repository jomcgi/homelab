import React, { useState, useEffect } from "react";
import {
  Terminal,
  Search,
  X,
  Maximize2,
  Minimize2,
  Image,
  FileCode,
  Globe,
  File,
  ChevronRight,
} from "lucide-react";

// Mock data
const mockSessions = [
  {
    id: "a1b2c3d4",
    name: "Main Development",
    created_at: "2025-10-20T10:30:00Z",
    last_active: "2025-10-25T09:15:00Z",
    state: "active",
    branch: "feature/api-refactor",
    age_days: 5,
    memory_usage: "45%",
    cpu_usage: "12%",
    claude_context: "Working on API refactor, 15 messages",
    artifacts: [
      {
        id: "art1",
        type: "react",
        title: "Dashboard Component",
        timestamp: "2025-10-25T09:10:00Z",
        content: "<div>React component would render here</div>",
      },
      {
        id: "art2",
        type: "image",
        title: "Architecture Diagram",
        timestamp: "2025-10-25T08:30:00Z",
        url: "https://via.placeholder.com/800x600/1a1a1a/10b981?text=Architecture+Diagram",
      },
    ],
  },
  {
    id: "e5f6g7h8",
    name: "Database Migration",
    created_at: "2025-10-23T14:20:00Z",
    last_active: "2025-10-24T16:45:00Z",
    state: "suspended",
    branch: "fix/db-migration",
    age_days: 2,
    memory_usage: "0%",
    cpu_usage: "0%",
    claude_context: "Migration scripts ready, 8 messages",
    artifacts: [],
  },
  {
    id: "i9j0k1l2",
    name: "Quick Debug",
    created_at: "2025-10-25T08:00:00Z",
    last_active: "2025-10-25T10:22:00Z",
    state: "active",
    branch: "main",
    age_days: 0,
    memory_usage: "23%",
    cpu_usage: "8%",
    claude_context: "Debugging webhook handler, 3 messages",
    artifacts: [
      {
        id: "art3",
        type: "html",
        title: "Test Page",
        timestamp: "2025-10-25T10:15:00Z",
        content:
          '<html><body style="background: #0a0a0a; color: #10b981; padding: 40px; font-family: monospace;"><h1>Webhook Test Page</h1><p>Status: OK</p></body></html>',
      },
    ],
  },
];

const SessionManagerUI = () => {
  const [sessions, setSessions] = useState(mockSessions);
  const [activeSessionId, setActiveSessionId] = useState("a1b2c3d4");
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [hoveredSessionId, setHoveredSessionId] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const [showPreview, setShowPreview] = useState(true);
  const [selectedArtifact, setSelectedArtifact] = useState(null);
  const [previewMaximized, setPreviewMaximized] = useState(false);

  // Resize states
  const [sidebarWidth, setSidebarWidth] = useState(288); // 72 * 4 = 288px (w-72)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [previewWidth, setPreviewWidth] = useState(50); // percentage
  const [isDraggingSidebar, setIsDraggingSidebar] = useState(false);
  const [isDraggingPreview, setIsDraggingPreview] = useState(false);

  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const hasArtifacts = activeSession?.artifacts?.length > 0;

  // Auto-select first artifact when session changes
  useEffect(() => {
    if (activeSession?.artifacts?.length > 0) {
      setSelectedArtifact(activeSession.artifacts[0]);
      setShowPreview(true);
    } else {
      setSelectedArtifact(null);
    }
  }, [activeSessionId]);

  // Keyboard Shortcuts:
  // ⌘K - Open command palette
  // ⌘N - Create new session
  // ⌘S - Toggle sidebar
  // ⌘1-9 - Switch to session 1-9
  // ⌘P - Toggle preview panel
  // ⌘⇧P - Maximize/minimize preview
  // ↑↓ - Navigate command palette (when open)
  // Enter - Execute selected command (when command palette open)
  // ESC - Close modals

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Cmd/Ctrl + K for command palette
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowCommandPalette(true);
        setSelectedCommandIndex(0);
        setSearchQuery("");
      }
      // Cmd/Ctrl + N for new session
      if ((e.metaKey || e.ctrlKey) && e.key === "n") {
        e.preventDefault();
        setShowCreateModal(true);
      }
      // Cmd/Ctrl + S for sidebar toggle
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (sidebarCollapsed) {
          setSidebarCollapsed(false);
          if (sidebarWidth < 220) {
            setSidebarWidth(288); // Reset to default
          }
        } else {
          setSidebarCollapsed(true);
        }
      }
      // Cmd/Ctrl + P for preview toggle
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key === "p") {
        e.preventDefault();
        if (hasArtifacts) {
          setShowPreview(!showPreview);
        }
      }
      // Cmd/Ctrl + Shift + P for maximize preview
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "P") {
        e.preventDefault();
        if (hasArtifacts && showPreview) {
          setPreviewMaximized(!previewMaximized);
        }
      }
      // Cmd/Ctrl + Numbers 1-9 for quick session switch
      if ((e.metaKey || e.ctrlKey) && /^[1-9]$/.test(e.key)) {
        e.preventDefault();
        const index = parseInt(e.key) - 1;
        if (sessions[index]) {
          setActiveSessionId(sessions[index].id);
        }
      }
      // Escape to close modals
      if (e.key === "Escape") {
        if (previewMaximized) {
          setPreviewMaximized(false);
        } else {
          setShowCommandPalette(false);
          setShowCreateModal(false);
          setSearchQuery("");
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [sessions, showPreview, hasArtifacts, previewMaximized, sidebarCollapsed]);

  // Command palette keyboard navigation
  useEffect(() => {
    if (!showCommandPalette) return;

    const handleCommandPaletteKeys = (e) => {
      const quickActions = 2;
      const totalItems = quickActions + sessions.length;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedCommandIndex((prev) => (prev + 1) % totalItems);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedCommandIndex((prev) => (prev - 1 + totalItems) % totalItems);
      } else if (e.key === "Enter") {
        e.preventDefault();

        if (selectedCommandIndex === 0) {
          setShowCreateModal(true);
          setShowCommandPalette(false);
        } else if (selectedCommandIndex === 1) {
          console.log("Suspend all sessions");
          setShowCommandPalette(false);
        } else {
          const sessionIndex = selectedCommandIndex - quickActions;
          if (sessions[sessionIndex]) {
            setActiveSessionId(sessions[sessionIndex].id);
            setShowCommandPalette(false);
          }
        }
      }
    };

    window.addEventListener("keydown", handleCommandPaletteKeys);
    return () =>
      window.removeEventListener("keydown", handleCommandPaletteKeys);
  }, [showCommandPalette, selectedCommandIndex, sessions]);

  // Sidebar resize handler with RAF for smooth performance
  useEffect(() => {
    if (!isDraggingSidebar) return;

    let rafId;
    const handleMouseMove = (e) => {
      if (rafId) cancelAnimationFrame(rafId);

      rafId = requestAnimationFrame(() => {
        const newWidth = Math.max(200, Math.min(500, e.clientX));
        setSidebarWidth(newWidth);

        // Collapse if dragged too far left
        if (newWidth < 220) {
          setSidebarCollapsed(true);
        } else {
          setSidebarCollapsed(false);
        }
      });
    };

    const handleMouseUp = () => {
      setIsDraggingSidebar(false);
      if (rafId) cancelAnimationFrame(rafId);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [isDraggingSidebar]);

  // Preview resize handler with RAF for smooth performance
  useEffect(() => {
    if (!isDraggingPreview) return;

    let rafId;
    const handleMouseMove = (e) => {
      if (rafId) cancelAnimationFrame(rafId);

      rafId = requestAnimationFrame(() => {
        const container = document.getElementById("main-content-area");
        if (!container) return;

        const containerRect = container.getBoundingClientRect();
        const relativeX = e.clientX - containerRect.left;
        const newPercentage = (relativeX / containerRect.width) * 100;

        // Clamp between 20% and 80%
        const clampedPercentage = Math.max(20, Math.min(80, newPercentage));
        setPreviewWidth(100 - clampedPercentage);
      });
    };

    const handleMouseUp = () => {
      setIsDraggingPreview(false);
      if (rafId) cancelAnimationFrame(rafId);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [isDraggingPreview]);

  const getAgeDisplay = (days) => {
    if (days === 0) return "today";
    if (days === 1) return "1d";
    return `${days}d`;
  };

  const isOldSession = (days) => days >= 4;

  const getArtifactIcon = (type) => {
    switch (type) {
      case "image":
        return <Image className="w-3.5 h-3.5" />;
      case "react":
      case "html":
        return <FileCode className="w-3.5 h-3.5" />;
      case "webpage":
        return <Globe className="w-3.5 h-3.5" />;
      default:
        return <File className="w-3.5 h-3.5" />;
    }
  };

  const getArtifactTypeLabel = (type) => {
    switch (type) {
      case "image":
        return "Image";
      case "react":
        return "React";
      case "html":
        return "HTML";
      case "webpage":
        return "Web";
      default:
        return "File";
    }
  };

  return (
    <div
      className={`flex h-screen bg-zinc-950 text-zinc-100 ${isDraggingSidebar || isDraggingPreview ? "cursor-col-resize select-none" : ""}`}
    >
      {/* Sidebar */}
      <div
        className={`bg-zinc-900/50 border-r border-zinc-800/50 flex flex-col flex-shrink-0 overflow-hidden ${
          isDraggingSidebar ? "" : "transition-all duration-200"
        }`}
        style={{ width: sidebarCollapsed ? "0px" : `${sidebarWidth}px` }}
      >
        <div
          className={`${sidebarCollapsed ? "opacity-0" : "opacity-100"} transition-opacity duration-200`}
        >
          {/* Header */}
          <div className="p-6 border-b border-zinc-800/50">
            <div className="flex items-center justify-between mb-6">
              <h1 className="text-sm font-medium text-zinc-400">Sessions</h1>
              <div className="text-xs text-zinc-600">
                {sessions.filter((s) => s.state === "active").length} active
              </div>
            </div>

            {/* Search */}
            <button
              onClick={() => setShowCommandPalette(true)}
              className="w-full bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-lg px-3 py-2 flex items-center gap-3 text-sm text-zinc-500 transition-colors group"
            >
              <Search className="w-4 h-4" />
              <span className="flex-1 text-left">Quick actions...</span>
              <kbd className="px-2 py-0.5 bg-zinc-800 rounded text-xs font-mono border border-zinc-700 group-hover:border-zinc-600">
                ⌘K
              </kbd>
            </button>
          </div>

          {/* Sessions List */}
          <div className="flex-1 overflow-y-auto p-3">
            <div className="space-y-1">
              {sessions.map((session, index) => (
                <div
                  key={session.id}
                  onClick={() => setActiveSessionId(session.id)}
                  onMouseEnter={() => setHoveredSessionId(session.id)}
                  onMouseLeave={() => setHoveredSessionId(null)}
                  className={`group relative px-3 py-3 rounded-lg cursor-pointer transition-all ${
                    activeSessionId === session.id
                      ? "bg-zinc-800 text-zinc-100"
                      : "text-zinc-400 hover:bg-zinc-900/50 hover:text-zinc-300"
                  }`}
                >
                  {/* Session Header */}
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <div
                        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                          session.state === "active"
                            ? "bg-emerald-500"
                            : "bg-zinc-700"
                        }`}
                      />
                      <span className="text-sm font-medium truncate">
                        {session.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      {session.artifacts?.length > 0 && (
                        <div
                          className="w-1 h-1 rounded-full bg-blue-500"
                          title={`${session.artifacts.length} artifacts`}
                        />
                      )}
                      <kbd className="px-1.5 py-0.5 bg-zinc-800/50 rounded text-xs font-mono border border-zinc-700/50 text-zinc-600 ml-1">
                        ⌘{index + 1}
                      </kbd>
                    </div>
                  </div>

                  {/* Session Meta */}
                  <div className="ml-3.5 text-xs text-zinc-600 flex items-center gap-3">
                    <span className="font-mono">{session.branch}</span>
                    <span
                      className={
                        isOldSession(session.age_days) ? "text-amber-600" : ""
                      }
                    >
                      {getAgeDisplay(session.age_days)}
                    </span>
                  </div>

                  {/* Hover Details */}
                  {hoveredSessionId === session.id &&
                    session.state === "active" && (
                      <div className="ml-3.5 mt-2 pt-2 border-t border-zinc-800 flex gap-4 text-xs text-zinc-600">
                        <span>cpu {session.cpu_usage}</span>
                        <span>mem {session.memory_usage}</span>
                      </div>
                    )}
                </div>
              ))}
            </div>
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-zinc-800/50">
            <button
              onClick={() => setShowCreateModal(true)}
              className="w-full bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-sm px-4 py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              New Session
              <kbd className="px-1.5 py-0.5 bg-zinc-900 rounded text-xs font-mono border border-zinc-700">
                ⌘N
              </kbd>
            </button>
          </div>
        </div>
      </div>

      {/* Sidebar Resize Handle */}
      <div
        onMouseDown={() => setIsDraggingSidebar(true)}
        className={`w-1 hover:w-1.5 bg-zinc-800/50 hover:bg-blue-500/50 cursor-col-resize transition-all flex-shrink-0 group ${
          isDraggingSidebar ? "bg-blue-500" : ""
        }`}
        title="Drag to resize sidebar (⌘S to toggle)"
      >
        <div className="h-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="w-0.5 h-8 bg-zinc-600 rounded-full" />
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Terminal Header */}
        {activeSession && (
          <div className="bg-zinc-900/30 border-b border-zinc-800/50 px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              {sidebarCollapsed && (
                <button
                  onClick={() => {
                    setSidebarCollapsed(false);
                    if (sidebarWidth < 220) {
                      setSidebarWidth(288);
                    }
                  }}
                  className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 rounded transition-all"
                  title="Show sidebar (⌘S)"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              )}
              <div>
                <h2 className="text-sm font-medium mb-0.5">
                  {activeSession.name}
                </h2>
                <p className="text-xs text-zinc-600">
                  {activeSession.branch} •{" "}
                  {new Date(activeSession.last_active).toLocaleString()}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1">
              {hasArtifacts && (
                <>
                  <button
                    onClick={() => setShowPreview(!showPreview)}
                    className={`px-3 py-1.5 text-xs rounded transition-all flex items-center gap-1.5 ${
                      showPreview
                        ? "text-blue-400 bg-blue-950/30"
                        : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50"
                    }`}
                    title="Toggle preview (⌘P)"
                  >
                    <FileCode className="w-3.5 h-3.5" />
                    Preview
                  </button>
                  <div className="w-px h-4 bg-zinc-800 mx-1" />
                </>
              )}
              <button
                className="px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 rounded transition-all"
                title="Suspend"
              >
                Suspend
              </button>
              <button
                className="px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 rounded transition-all"
                title="Clone"
              >
                Clone
              </button>
              <button
                className="px-3 py-1.5 text-xs text-red-500/70 hover:text-red-400 hover:bg-red-950/30 rounded transition-all"
                title="Delete"
              >
                Delete
              </button>
            </div>
          </div>
        )}

        {/* Main Content - Terminal and Preview */}
        <div id="main-content-area" className="flex-1 flex overflow-hidden">
          {/* Terminal Display */}
          <div
            className={`flex flex-col border-r border-zinc-800/50 ${
              isDraggingPreview ? "" : "transition-all"
            }`}
            style={{
              width:
                showPreview && hasArtifacts && !previewMaximized
                  ? `${100 - previewWidth}%`
                  : "100%",
            }}
          >
            <div className="flex-1 bg-black p-6 font-mono text-sm overflow-auto">
              {activeSession ? (
                <div className="h-full">
                  <div className="text-emerald-400 mb-3">
                    <span className="text-zinc-600">
                      ~/{activeSession.branch}
                    </span>
                    <span className="text-zinc-500 mx-2">❯</span>
                    <span className="animate-pulse">█</span>
                  </div>

                  <div className="space-y-1 text-zinc-500 text-xs">
                    <div>claude session resume</div>
                    <div className="text-emerald-400/70 pl-6">
                      ✓ session restored from persistent storage
                    </div>
                    <div className="text-emerald-400/70 pl-6">
                      ✓ {activeSession.claude_context.toLowerCase()}
                    </div>
                    {hasArtifacts && (
                      <div className="text-blue-400/70 pl-6">
                        ✓ {activeSession.artifacts.length} artifact
                        {activeSession.artifacts.length > 1 ? "s" : ""}{" "}
                        available
                      </div>
                    )}
                    <div className="text-zinc-700 mt-3">
                      [xterm.js terminal instance would be mounted here]
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-full flex items-center justify-center text-zinc-700">
                  <div className="text-center">
                    <Terminal className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p className="text-sm">No session selected</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Preview Resize Handle */}
          {showPreview && hasArtifacts && !previewMaximized && (
            <div
              onMouseDown={() => setIsDraggingPreview(true)}
              className={`w-1 hover:w-1.5 bg-zinc-800/50 hover:bg-blue-500/50 cursor-col-resize transition-all flex-shrink-0 group ${
                isDraggingPreview ? "bg-blue-500" : ""
              }`}
              title="Drag to resize preview"
            >
              <div className="h-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="w-0.5 h-8 bg-zinc-600 rounded-full" />
              </div>
            </div>
          )}

          {/* Preview Panel */}
          {showPreview && hasArtifacts && (
            <div
              className={`flex flex-col bg-zinc-950 ${
                isDraggingPreview ? "" : "transition-all"
              }`}
              style={{
                width: previewMaximized ? "100%" : `${previewWidth}%`,
                position: previewMaximized ? "absolute" : "relative",
                inset: previewMaximized ? 0 : "auto",
                zIndex: previewMaximized ? 40 : "auto",
              }}
            >
              {/* Preview Header */}
              <div className="bg-zinc-900/50 border-b border-zinc-800/50 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <span className="text-xs font-medium text-zinc-400">
                    Preview
                  </span>
                  {activeSession.artifacts.length > 1 && (
                    <>
                      <div className="w-px h-3 bg-zinc-700" />
                      <div className="flex items-center gap-1 overflow-x-auto">
                        {activeSession.artifacts.map((artifact, idx) => (
                          <button
                            key={artifact.id}
                            onClick={() => setSelectedArtifact(artifact)}
                            className={`px-2 py-1 text-xs rounded transition-all flex items-center gap-1.5 whitespace-nowrap ${
                              selectedArtifact?.id === artifact.id
                                ? "bg-zinc-800 text-zinc-200"
                                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50"
                            }`}
                          >
                            {getArtifactIcon(artifact.type)}
                            <span className="truncate max-w-[120px]">
                              {artifact.title}
                            </span>
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setPreviewMaximized(!previewMaximized)}
                    className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 rounded transition-all"
                    title={
                      previewMaximized ? "Restore (⌘⇧P)" : "Maximize (⌘⇧P)"
                    }
                  >
                    {previewMaximized ? (
                      <Minimize2 className="w-4 h-4" />
                    ) : (
                      <Maximize2 className="w-4 h-4" />
                    )}
                  </button>
                  <button
                    onClick={() => setShowPreview(false)}
                    className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 rounded transition-all"
                    title="Close preview (⌘P)"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Preview Content */}
              <div className="flex-1 overflow-auto bg-zinc-900/20">
                {selectedArtifact ? (
                  <div className="h-full">
                    {/* Artifact Meta */}
                    <div className="border-b border-zinc-800/50 px-4 py-2 flex items-center justify-between bg-zinc-900/30">
                      <div className="flex items-center gap-2">
                        {getArtifactIcon(selectedArtifact.type)}
                        <div>
                          <div className="text-sm font-medium text-zinc-300">
                            {selectedArtifact.title}
                          </div>
                          <div className="text-xs text-zinc-600">
                            {getArtifactTypeLabel(selectedArtifact.type)} •{" "}
                            {new Date(
                              selectedArtifact.timestamp,
                            ).toLocaleTimeString()}
                          </div>
                        </div>
                      </div>
                      <button className="px-2 py-1 text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 rounded transition-all">
                        Export
                      </button>
                    </div>

                    {/* Artifact Render */}
                    <div className="h-[calc(100%-60px)]">
                      {selectedArtifact.type === "image" ? (
                        <div className="flex items-center justify-center h-full p-8 bg-zinc-950">
                          <img
                            src={selectedArtifact.url}
                            alt={selectedArtifact.title}
                            className="max-w-full max-h-full object-contain rounded-lg border border-zinc-800"
                          />
                        </div>
                      ) : selectedArtifact.type === "html" ||
                        selectedArtifact.type === "react" ? (
                        <iframe
                          srcDoc={selectedArtifact.content}
                          className="w-full h-full border-0"
                          sandbox="allow-scripts"
                          title={selectedArtifact.title}
                        />
                      ) : (
                        <div className="h-full flex items-center justify-center text-zinc-600">
                          <div className="text-center">
                            <File className="w-12 h-12 mx-auto mb-3 opacity-30" />
                            <p className="text-sm">Unsupported artifact type</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="h-full flex items-center justify-center text-zinc-600">
                    <div className="text-center">
                      <FileCode className="w-12 h-12 mx-auto mb-3 opacity-30" />
                      <p className="text-sm">No artifact selected</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Command Palette */}
      {showCommandPalette && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-start justify-center pt-32 p-4 z-50">
          <div className="bg-zinc-900 rounded-xl border border-zinc-800 w-full max-w-xl shadow-2xl">
            {/* Search Input */}
            <div className="flex items-center gap-3 p-4 border-b border-zinc-800">
              <Search className="w-4 h-4 text-zinc-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setSelectedCommandIndex(0);
                }}
                placeholder="Search sessions or run command..."
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-zinc-600"
                autoFocus
              />
              <div className="flex items-center gap-1">
                <kbd className="px-1.5 py-1 bg-zinc-800 rounded text-xs font-mono border border-zinc-700 text-zinc-500">
                  ↑↓
                </kbd>
                <kbd className="px-2 py-1 bg-zinc-800 rounded text-xs font-mono border border-zinc-700 text-zinc-500">
                  ESC
                </kbd>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="p-2">
              <div className="text-xs text-zinc-600 px-3 py-2 font-medium">
                Quick Actions
              </div>
              <button
                onClick={() => {
                  setShowCreateModal(true);
                  setShowCommandPalette(false);
                }}
                onMouseEnter={() => setSelectedCommandIndex(0)}
                className={`w-full text-left px-3 py-2.5 rounded-lg flex items-center justify-between group transition-colors ${
                  selectedCommandIndex === 0
                    ? "bg-zinc-800"
                    : "hover:bg-zinc-800"
                }`}
              >
                <span className="text-sm text-zinc-300">
                  Create new session
                </span>
                <kbd className="px-2 py-1 bg-zinc-800 rounded text-xs font-mono border border-zinc-700 text-zinc-600 group-hover:border-zinc-600">
                  ⌘N
                </kbd>
              </button>
              <button
                onMouseEnter={() => setSelectedCommandIndex(1)}
                className={`w-full text-left px-3 py-2.5 rounded-lg flex items-center justify-between group transition-colors ${
                  selectedCommandIndex === 1
                    ? "bg-zinc-800"
                    : "hover:bg-zinc-800"
                }`}
              >
                <span className="text-sm text-zinc-300">
                  Suspend all sessions
                </span>
                <kbd className="px-2 py-1 bg-zinc-800 rounded text-xs font-mono border border-zinc-700 text-zinc-600 group-hover:border-zinc-600">
                  ⌘⇧P
                </kbd>
              </button>
            </div>

            {/* Recent Sessions */}
            {searchQuery === "" && (
              <div className="p-2 border-t border-zinc-800">
                <div className="text-xs text-zinc-600 px-3 py-2 font-medium">
                  Recent Sessions
                </div>
                {sessions.slice(0, 5).map((session, index) => {
                  const commandIndex = 2 + index;
                  return (
                    <button
                      key={session.id}
                      onClick={() => {
                        setActiveSessionId(session.id);
                        setShowCommandPalette(false);
                      }}
                      onMouseEnter={() => setSelectedCommandIndex(commandIndex)}
                      className={`w-full text-left px-3 py-2.5 rounded-lg flex items-center justify-between group transition-colors ${
                        selectedCommandIndex === commandIndex
                          ? "bg-zinc-800"
                          : "hover:bg-zinc-800"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-1.5 h-1.5 rounded-full ${
                            session.state === "active"
                              ? "bg-emerald-500"
                              : "bg-zinc-700"
                          }`}
                        />
                        <div>
                          <div className="text-sm text-zinc-300">
                            {session.name}
                          </div>
                          <div className="text-xs text-zinc-600 font-mono">
                            {session.branch}
                          </div>
                        </div>
                      </div>
                      <kbd className="px-2 py-1 bg-zinc-800 rounded text-xs font-mono border border-zinc-700 text-zinc-600 group-hover:border-zinc-600">
                        ⌘{index + 1}
                      </kbd>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create Session Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-6 max-w-md w-full shadow-2xl">
            <h3 className="text-base font-medium mb-6">Create New Session</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-zinc-400 mb-2">
                  Session name
                </label>
                <input
                  type="text"
                  className="w-full bg-zinc-950 border border-zinc-800 focus:border-zinc-700 rounded-lg px-3 py-2 text-sm outline-none transition-colors"
                  placeholder="My development session"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm text-zinc-400 mb-2">
                  Branch (optional)
                </label>
                <input
                  type="text"
                  className="w-full bg-zinc-950 border border-zinc-800 focus:border-zinc-700 rounded-lg px-3 py-2 text-sm outline-none transition-colors font-mono"
                  placeholder="main"
                />
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-sm px-4 py-2.5 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setShowCreateModal(false);
                  }}
                  className="flex-1 bg-zinc-100 hover:bg-white text-zinc-900 text-sm px-4 py-2.5 rounded-lg transition-colors font-medium"
                >
                  Create Session
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SessionManagerUI;
