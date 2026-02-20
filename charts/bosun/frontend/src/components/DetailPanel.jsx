import { useState, useEffect, useCallback, useRef } from "react";
import { X, ClipboardCopy, Download, Code, ZoomIn, ZoomOut, Grid, Maximize, Expand, FileCode, Terminal, GitBranch, Image } from "lucide-react";
import { C, sans, mono } from "../tokens.js";
import { MarkdownContent } from "./MarkdownContent.jsx";
import { MermaidDiagram } from "./MermaidDiagram.jsx";
import { ArtifactGalleryItem } from "./ArtifactGalleryItem.jsx";
import { artifactIcon } from "../artifactIcons.js";

export function DetailPanel({ artifact, onClose, allArtifacts, onSelectArtifact }) {
  const [showSource, setShowSource] = useState(false);
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [tab, setTab] = useState(artifact ? "detail" : "gallery");
  const [fullscreen, setFullscreen] = useState(false);

  const dragRef = useRef({ active: false, startX: 0, startY: 0, panX: 0, panY: 0 });
  const contentRef = useRef(null);
  const fullscreenRef = useRef(null);

  // Auto-switch tabs based on artifact presence
  useEffect(() => {
    setTab(artifact ? "detail" : "gallery");
  }, [artifact]);

  // Reset zoom + pan when artifact changes
  useEffect(() => { setZoom(1.0); setPan({ x: 0, y: 0 }); }, [artifact]);

  // Proportional step: 25% of current zoom (min 0.1), so buttons stay useful at any level
  const zoomIn = useCallback(() => setZoom((z) => Math.min(20.0, z + Math.max(0.1, z * 0.25))), []);
  const zoomOut = useCallback(() => setZoom((z) => Math.max(0.25, z - Math.max(0.1, z * 0.2))), []);
  const zoomFit = useCallback(() => { setZoom(1.0); setPan({ x: 0, y: 0 }); }, []);

  // ── Drag-to-pan ──────────────────────────────────────────────────────────
  const handlePointerDown = useCallback((e) => {
    if (e.button !== 0) return; // left click only
    dragRef.current = { active: true, startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [pan]);

  const handlePointerMove = useCallback((e) => {
    if (!dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setPan({ x: dragRef.current.panX + dx, y: dragRef.current.panY + dy });
  }, []);

  const handlePointerUp = useCallback(() => {
    dragRef.current.active = false;
    setDragging(false);
  }, []);

  // ── Scroll-wheel zoom ────────────────────────────────────────────────────
  const handleWheel = useCallback((e) => {
    e.preventDefault();
    setZoom((z) => {
      const step = z * 0.1; // 10% of current zoom per scroll tick
      const next = e.deltaY < 0 ? z + step : z - step;
      return Math.min(20.0, Math.max(0.25, next));
    });
  }, []);

  // Attach wheel handler (needs {passive: false} to preventDefault)
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [handleWheel, tab, artifact]);

  // Attach wheel handler to fullscreen canvas too
  useEffect(() => {
    const el = fullscreenRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [handleWheel, fullscreen]);

  // Escape key exits fullscreen
  useEffect(() => {
    if (!fullscreen) return;
    const handler = (e) => { if (e.key === "Escape") setFullscreen(false); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [fullscreen]);

  // Reset fullscreen when artifact changes
  useEffect(() => { setFullscreen(false); }, [artifact]);

  const copyToClipboard = useCallback(() => {
    if (!artifact) return;
    let content = "";
    if (artifact.type === "diff") {
      content = artifact.data.map((l) => l.x).join("\n");
    } else if (artifact.type === "mermaid") {
      content = artifact.data;
    } else if (artifact.type === "output") {
      content = artifact.data;
    }
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [artifact]);

  const downloadSvg = useCallback(() => {
    const svgEl = document.querySelector(`[data-detail-mermaid] svg`);
    if (!svgEl) return;
    const svgData = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([svgData], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const ts = new Date().toISOString().slice(0, 16).replace(/[T:]/g, "-");
    a.download = `${sanitizeFilename(artifact?.label || "diagram")}-${ts}.svg`;
    a.click();
    URL.revokeObjectURL(url);
  }, [artifact]);

  const downloadImage = useCallback(() => {
    if (!artifact?.data) return;
    const binary = atob(artifact.data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: artifact.mimeType || "image/png" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const ext = (artifact.mimeType || "image/png").split("/")[1] || "png";
    const ts = new Date().toISOString().slice(0, 16).replace(/[T:]/g, "-");
    a.download = `${sanitizeFilename(artifact.label || "image")}-${ts}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  }, [artifact]);

  const toolbarBtnStyle = {
    background: "none", border: `1px solid ${C.border}`, borderRadius: 6, cursor: "pointer",
    padding: "4px 8px", display: "flex", alignItems: "center", gap: 4,
    fontSize: 11, color: C.textSec, fontFamily: sans,
  };

  const tabStyle = (active) => ({
    background: "none", border: "none", cursor: "pointer",
    padding: "6px 12px", fontSize: 12, fontWeight: 500, fontFamily: sans,
    color: active ? C.accentBlue : C.textTer,
    borderBottom: active ? `2px solid ${C.accentBlue}` : "2px solid transparent",
  });

  const galleryCount = allArtifacts?.length || 0;
  const showZoom = artifact && (artifact.type === "image" || artifact.type === "mermaid");

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Tab bar */}
      <div style={{
        display: "flex", alignItems: "center", padding: "0 16px",
        borderBottom: `1px solid ${C.border}`, flexShrink: 0,
        justifyContent: "space-between",
      }}>
        <div style={{ display: "flex" }}>
          <button onClick={() => setTab("detail")} style={tabStyle(tab === "detail")}>
            Detail
          </button>
          <button onClick={() => setTab("gallery")} style={tabStyle(tab === "gallery")}>
            Gallery{galleryCount > 0 ? ` (${galleryCount})` : ""}
          </button>
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: C.textTer, padding: 4, display: "flex" }}>
          <X size={16} />
        </button>
      </div>

      {/* Gallery tab */}
      {tab === "gallery" && (
        <div style={{ flex: 1, overflow: "auto", padding: 12 }}>
          {galleryCount === 0 ? (
            <div style={{
              height: "100%", display: "flex", alignItems: "center", justifyContent: "center",
              color: C.textFaint, fontFamily: sans, fontSize: 13,
              flexDirection: "column", gap: 8, textAlign: "center",
            }}>
              <Grid size={32} color={C.textFaint} strokeWidth={1.2} />
              <span>No artifacts yet</span>
            </div>
          ) : (
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8,
            }}>
              {allArtifacts.map((item) => (
                <ArtifactGalleryItem
                  key={item.id}
                  artifact={item.artifact}
                  time={item.msgTime}
                  onClick={() => {
                    if (onSelectArtifact) onSelectArtifact(item.artifact, item.id);
                    setTab("detail");
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Detail tab */}
      {tab === "detail" && (
        <>
          {!artifact ? (
            <div style={{
              flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
              color: C.textFaint, fontFamily: sans, fontSize: 13,
              flexDirection: "column", gap: 8, padding: 32, textAlign: "center",
            }}>
              <FileCode size={32} color={C.textFaint} strokeWidth={1.2} />
              <span>Select a diff, output, or diagram to inspect it here</span>
            </div>
          ) : (
            <>
              {/* Artifact header toolbar */}
              <div style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "8px 16px", borderBottom: `1px solid ${C.borderLight}`, flexShrink: 0,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {(() => { const I = artifactIcon(artifact); return <I size={14} color={C.textSec} />; })()}
                  <span style={{ fontSize: 13, fontWeight: 600, color: C.text, fontFamily: sans }}>{artifact.label}</span>
                  {artifact.additions > 0 && <span style={{ fontSize: 12, color: C.addGreen, fontFamily: mono }}>+{artifact.additions}</span>}
                  {artifact.deletions > 0 && <span style={{ fontSize: 12, color: C.delRed, fontFamily: mono }}>{"-"}{artifact.deletions}</span>}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <button onClick={copyToClipboard} style={toolbarBtnStyle} title="Copy to clipboard">
                    <ClipboardCopy size={12} /> {copied ? "Copied" : "Copy"}
                  </button>
                  {artifact.type === "mermaid" && (
                    <>
                      <button onClick={downloadSvg} style={toolbarBtnStyle} title="Download SVG">
                        <Download size={12} /> SVG
                      </button>
                      <button onClick={() => setShowSource(!showSource)} style={toolbarBtnStyle} title="View source">
                        <Code size={12} /> {showSource ? "Diagram" : "Source"}
                      </button>
                    </>
                  )}
                  {artifact.type === "image" && (
                    <button onClick={downloadImage} style={toolbarBtnStyle} title="Download image">
                      <Download size={12} /> Save
                    </button>
                  )}
                  <button onClick={() => setFullscreen(true)} style={toolbarBtnStyle} title="Fullscreen (Esc to exit)">
                    <Expand size={12} />
                  </button>
                </div>
              </div>
              {/* Zoom + pan toolbar for image/mermaid */}
              {showZoom && (
                <div style={{
                  display: "flex", alignItems: "center", gap: 6, padding: "6px 16px",
                  borderBottom: `1px solid ${C.borderLight}`, flexShrink: 0,
                }}>
                  <button onClick={zoomOut} style={toolbarBtnStyle} title="Zoom out">
                    <ZoomOut size={12} />
                  </button>
                  <span style={{ fontSize: 11, color: C.textSec, fontFamily: mono, minWidth: 36, textAlign: "center" }}>
                    {Math.round(zoom * 100)}%
                  </span>
                  <button onClick={zoomIn} style={toolbarBtnStyle} title="Zoom in">
                    <ZoomIn size={12} />
                  </button>
                  <button onClick={zoomFit} style={toolbarBtnStyle} title="Reset zoom and pan">
                    <Maximize size={12} /> Fit
                  </button>
                  {zoom !== 1.0 && (
                    <span style={{ fontSize: 10, color: C.textTer, fontFamily: sans, marginLeft: 4 }}>
                      Drag to pan / scroll to zoom
                    </span>
                  )}
                </div>
              )}
              {/* Content area — scrollable for text types, pan canvas for visual types */}
              {(artifact.type === "diff" || artifact.type === "output" || (artifact.type === "mermaid" && showSource)) ? (
                <div style={{ flex: 1, overflow: "auto" }}>
                  {artifact.type === "diff" && (
                    <div style={{ fontFamily: mono, fontSize: 13, lineHeight: 1.8, minWidth: "fit-content" }}>
                      {artifact.data.map((l, i) => (
                        <div key={i} style={{
                          padding: "0 16px", whiteSpace: "pre",
                          color: l.t === "+" ? C.addGreen : l.t === "-" ? C.delRed : l.t === "h" ? C.textTer : C.textSec,
                          backgroundColor: l.t === "+" ? C.addBg : l.t === "-" ? C.delBg : "transparent",
                        }}>{l.x}</div>
                      ))}
                    </div>
                  )}
                  {artifact.type === "output" && (
                    <div style={{ padding: "12px 16px" }}>
                      <MarkdownContent text={artifact.data} />
                    </div>
                  )}
                  {artifact.type === "mermaid" && showSource && (
                    <pre style={{ padding: "12px 16px", margin: 0, fontFamily: mono, fontSize: 12, lineHeight: 1.6, color: C.you }}>{artifact.data}</pre>
                  )}
                </div>
              ) : (
                <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
                  <div
                    ref={contentRef}
                    data-detail-mermaid={artifact.type === "mermaid" ? "" : undefined}
                    onPointerDown={handlePointerDown}
                    onPointerMove={handlePointerMove}
                    onPointerUp={handlePointerUp}
                    style={{
                      position: "absolute", inset: 0,
                      cursor: dragging ? "grabbing" : "grab",
                      overflow: "hidden",
                      userSelect: "none",
                      touchAction: "none",
                    }}
                  >
                    <div style={{
                      transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                      transformOrigin: "top center",
                      display: "flex", justifyContent: "center",
                    }}>
                      {artifact.type === "mermaid" && (
                        <MermaidDiagram code={artifact.data} id={`detail-${artifact.label}`} />
                      )}
                      {artifact.type === "image" && (
                        <img
                          src={`data:${artifact.mimeType || "image/png"};base64,${artifact.data}`}
                          alt={artifact.label}
                          draggable={false}
                          style={{
                            maxWidth: zoom === 1.0 && pan.x === 0 && pan.y === 0 ? "100%" : "none",
                            objectFit: "contain", borderRadius: 6,
                            pointerEvents: "none",
                          }}
                        />
                      )}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
      {/* ── Fullscreen overlay ──────────────────────────────────────────── */}
      {fullscreen && artifact && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 9999,
          backgroundColor: C.bg, display: "flex", flexDirection: "column",
        }}>
          {/* Fullscreen header */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "8px 20px", borderBottom: `1px solid ${C.border}`, flexShrink: 0,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {artifact.type === "diff" && <FileCode size={14} color={C.textSec} />}
              {artifact.type === "output" && <Terminal size={14} color={C.textSec} />}
              {artifact.type === "mermaid" && <GitBranch size={14} color={C.textSec} />}
              {artifact.type === "image" && <Image size={14} color={C.textSec} />}
              <span style={{ fontSize: 14, fontWeight: 600, color: C.text, fontFamily: sans }}>{artifact.label}</span>
              {artifact.additions > 0 && <span style={{ fontSize: 12, color: C.addGreen, fontFamily: mono }}>+{artifact.additions}</span>}
              {artifact.deletions > 0 && <span style={{ fontSize: 12, color: C.delRed, fontFamily: mono }}>{"-"}{artifact.deletions}</span>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {showZoom && (
                <>
                  <button onClick={zoomOut} style={toolbarBtnStyle} title="Zoom out"><ZoomOut size={12} /></button>
                  <span style={{ fontSize: 11, color: C.textSec, fontFamily: mono, minWidth: 36, textAlign: "center" }}>
                    {Math.round(zoom * 100)}%
                  </span>
                  <button onClick={zoomIn} style={toolbarBtnStyle} title="Zoom in"><ZoomIn size={12} /></button>
                  <button onClick={zoomFit} style={toolbarBtnStyle} title="Reset zoom and pan"><Maximize size={12} /> Fit</button>
                  <div style={{ width: 1, height: 20, backgroundColor: C.border, margin: "0 4px" }} />
                </>
              )}
              <button onClick={copyToClipboard} style={toolbarBtnStyle} title="Copy to clipboard">
                <ClipboardCopy size={12} /> {copied ? "Copied" : "Copy"}
              </button>
              <button onClick={() => setFullscreen(false)} style={{
                background: "none", border: `1px solid ${C.border}`, borderRadius: 6, cursor: "pointer",
                padding: "4px 8px", display: "flex", alignItems: "center", gap: 4,
                fontSize: 11, color: C.textSec, fontFamily: sans,
              }} title="Exit fullscreen (Esc)">
                <X size={12} /> Close
              </button>
            </div>
          </div>
          {/* Fullscreen content */}
          {(artifact.type === "diff" || artifact.type === "output" || (artifact.type === "mermaid" && showSource)) ? (
            <div style={{ flex: 1, overflow: "auto", padding: "0 20px" }}>
              {artifact.type === "diff" && (
                <div style={{ fontFamily: mono, fontSize: 14, lineHeight: 1.8, minWidth: "fit-content" }}>
                  {artifact.data.map((l, i) => (
                    <div key={i} style={{
                      padding: "0 16px", whiteSpace: "pre",
                      color: l.t === "+" ? C.addGreen : l.t === "-" ? C.delRed : l.t === "h" ? C.textTer : C.textSec,
                      backgroundColor: l.t === "+" ? C.addBg : l.t === "-" ? C.delBg : "transparent",
                    }}>{l.x}</div>
                  ))}
                </div>
              )}
              {artifact.type === "output" && (
                <div style={{ padding: "16px 0" }}>
                  <MarkdownContent text={artifact.data} />
                </div>
              )}
              {artifact.type === "mermaid" && showSource && (
                <pre style={{ padding: "16px 0", margin: 0, fontFamily: mono, fontSize: 13, lineHeight: 1.6, color: C.you }}>{artifact.data}</pre>
              )}
            </div>
          ) : (
            <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
              <div
                ref={fullscreenRef}
                data-detail-mermaid={artifact.type === "mermaid" ? "" : undefined}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                style={{
                  position: "absolute", inset: 0,
                  cursor: dragging ? "grabbing" : "grab",
                  overflow: "hidden",
                  userSelect: "none",
                  touchAction: "none",
                }}
              >
                <div style={{
                  transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                  transformOrigin: "top center",
                  display: "flex", justifyContent: "center",
                }}>
                  {artifact.type === "mermaid" && (
                    <MermaidDiagram code={artifact.data} id={`fs-${artifact.label}`} />
                  )}
                  {artifact.type === "image" && (
                    <img
                      src={`data:${artifact.mimeType || "image/png"};base64,${artifact.data}`}
                      alt={artifact.label}
                      draggable={false}
                      style={{
                        maxWidth: zoom === 1.0 && pan.x === 0 && pan.y === 0 ? "100%" : "none",
                        objectFit: "contain", borderRadius: 6,
                        pointerEvents: "none",
                      }}
                    />
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function sanitizeFilename(name) {
  return name.replace(/[^a-zA-Z0-9._-]/g, "_").replace(/_+/g, "_").slice(0, 60);
}
