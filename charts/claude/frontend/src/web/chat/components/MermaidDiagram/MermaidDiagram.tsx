import React, { useEffect, useState, useCallback, useId, useRef } from "react";
import mermaid from "mermaid";
import { Copy, Check, AlertCircle, Loader2 } from "lucide-react";
import { useTheme } from "../../hooks/useTheme";
import { Button } from "@/web/chat/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/web/chat/components/ui/tooltip";
import { cn } from "@/web/chat/lib/utils";

interface MermaidDiagramProps {
  code: string;
  className?: string;
}

type RenderState =
  | { status: "loading" }
  | { status: "success"; svg: string }
  | { status: "error"; message: string };

export const MermaidDiagram: React.FC<MermaidDiagramProps> = ({
  code,
  className = "",
}) => {
  const theme = useTheme();
  const reactId = useId();
  // Mermaid requires a unique ID for each diagram render
  // The counter ensures uniqueness when re-rendering with different code/theme
  const renderCountRef = useRef(0);
  const diagramIdBase = `mermaid-${reactId.replace(/:/g, "-")}`;
  const [renderState, setRenderState] = useState<RenderState>({
    status: "loading",
  });
  const [copied, setCopied] = useState(false);

  // Initialize mermaid with theme
  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: theme.mode === "dark" ? "dark" : "default",
      securityLevel: "strict",
      fontFamily: "inherit",
    });
  }, [theme.mode]);

  // Render the diagram
  useEffect(() => {
    const renderDiagram = async () => {
      if (!code.trim()) {
        setRenderState({ status: "error", message: "Empty diagram code" });
        return;
      }

      setRenderState({ status: "loading" });

      try {
        // Validate the syntax first
        await mermaid.parse(code);

        // Render the diagram with a unique ID for each render
        renderCountRef.current += 1;
        const diagramId = `${diagramIdBase}-${renderCountRef.current}`;
        const { svg } = await mermaid.render(diagramId, code);
        setRenderState({ status: "success", svg });
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "Failed to render diagram";
        setRenderState({ status: "error", message: errorMessage });
      }
    };

    renderDiagram();
  }, [code, theme.mode, diagramIdBase]);

  const copySvg = useCallback(async () => {
    if (renderState.status !== "success") return;

    try {
      await navigator.clipboard.writeText(renderState.svg);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy SVG:", err);
    }
  }, [renderState]);

  if (renderState.status === "loading") {
    return (
      <div
        className={cn(
          "flex items-center justify-center p-8 bg-card border border-border rounded-md",
          className,
        )}
      >
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">
          Rendering diagram...
        </span>
      </div>
    );
  }

  if (renderState.status === "error") {
    return (
      <div
        className={cn(
          "p-4 bg-card border border-destructive/50 rounded-md",
          className,
        )}
      >
        <div className="flex items-start gap-2 text-destructive mb-2">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <span className="text-sm font-medium">
            Failed to render Mermaid diagram
          </span>
        </div>
        <pre className="text-xs text-muted-foreground bg-muted p-2 rounded overflow-x-auto whitespace-pre-wrap">
          {renderState.message}
        </pre>
        <details className="mt-3">
          <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
            Show diagram code
          </summary>
          <pre className="mt-2 text-xs text-muted-foreground bg-muted p-2 rounded overflow-x-auto whitespace-pre-wrap">
            {code}
          </pre>
        </details>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "relative bg-card border border-border rounded-md overflow-hidden",
        className,
      )}
    >
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={copySvg}
              className="absolute top-2 right-2 h-7 w-7 z-10 bg-background/80 hover:bg-background text-muted-foreground hover:text-foreground"
              aria-label={copied ? "Copied" : "Copy SVG"}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{copied ? "Copied!" : "Copy SVG"}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <div
        className="p-4 flex justify-center items-center overflow-x-auto [&_svg]:max-w-full"
        dangerouslySetInnerHTML={{ __html: renderState.svg }}
      />
    </div>
  );
};
