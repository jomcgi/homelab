import React from "react";
import { Map as MapIcon, Image as ImageIcon } from "lucide-react";

export function ViewToggle({ activeView, onViewChange }) {
  return (
    <div className="flex bg-gray-200 rounded-lg p-1">
      <button
        onClick={() => onViewChange("image")}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-colors text-sm font-medium ${
          activeView === "image"
            ? "bg-blue-500 text-white"
            : "text-gray-600 hover:text-gray-800"
        }`}
      >
        <ImageIcon className="h-4 w-4" />
        Photo
      </button>
      <button
        onClick={() => onViewChange("map")}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-colors text-sm font-medium ${
          activeView === "map"
            ? "bg-blue-500 text-white"
            : "text-gray-600 hover:text-gray-800"
        }`}
      >
        <MapIcon className="h-4 w-4" />
        Map
      </button>
    </div>
  );
}
