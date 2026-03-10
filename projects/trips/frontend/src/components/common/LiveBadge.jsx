import React from "react";
import { Eye } from "lucide-react";

export function LiveBadge({
  isLive,
  onToggle,
  viewerCount = null,
  compact = false,
}) {
  if (compact) {
    return (
      <button
        onClick={onToggle}
        className={`
          flex items-center justify-center w-10 h-10 rounded-full
          transition-all duration-200
          ${
            isLive
              ? "bg-red-500/20 border border-red-500/30 hover:bg-red-500/30"
              : "bg-gray-200 border border-gray-300 hover:bg-gray-300"
          }
        `}
        title={isLive ? "LIVE" : "Go Live"}
      >
        <span
          className={`
          w-3 h-3 rounded-full
          ${isLive ? "bg-red-500 animate-pulse" : "bg-gray-400"}
        `}
        />
      </button>
    );
  }

  return (
    <button
      onClick={onToggle}
      className={`
        flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium
        transition-all duration-200
        ${
          isLive
            ? "bg-red-500/20 text-red-600 border border-red-500/30 hover:bg-red-500/30"
            : "bg-gray-200 text-gray-600 border border-gray-300 hover:bg-gray-300 hover:text-gray-800"
        }
      `}
    >
      <span
        className={`
        w-2 h-2 rounded-full
        ${isLive ? "bg-red-500 animate-pulse" : "bg-gray-400"}
      `}
      />
      <span>{isLive ? "LIVE" : "Go Live"}</span>
      {isLive && viewerCount !== null && (
        <span className="flex items-center gap-1 text-xs text-red-500/70 border-l border-red-500/30 pl-2 ml-1">
          <Eye className="w-3 h-3" />
          {viewerCount}
        </span>
      )}
    </button>
  );
}
