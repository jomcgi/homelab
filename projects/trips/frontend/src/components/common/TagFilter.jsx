import React, { useState } from "react";
import { Tag, X } from "lucide-react";

export function TagFilter({
  availableTags,
  selectedTags,
  onTagsChange,
  isMobile = false,
}) {
  const [isOpen, setIsOpen] = useState(false);

  if (availableTags.length === 0) return null;

  const toggleTag = (tag) => {
    if (selectedTags.includes(tag)) {
      onTagsChange(selectedTags.filter((t) => t !== tag));
    } else {
      onTagsChange([...selectedTags, tag]);
    }
  };

  const clearTags = () => {
    onTagsChange([]);
    setIsOpen(false);
  };

  if (isMobile) {
    return (
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={`
            flex items-center justify-center w-10 h-10 rounded-full
            transition-all duration-200
            ${
              selectedTags.length > 0
                ? "bg-blue-500/20 border border-blue-500/30 hover:bg-blue-500/30"
                : "bg-gray-200 border border-gray-300 hover:bg-gray-300"
            }
          `}
          title="Filter by tags"
        >
          <Tag
            className={`w-4 h-4 ${selectedTags.length > 0 ? "text-blue-600" : "text-gray-500"}`}
          />
          {selectedTags.length > 0 && (
            <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 text-white text-[10px] rounded-full flex items-center justify-center">
              {selectedTags.length}
            </span>
          )}
        </button>

        {isOpen && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setIsOpen(false)}
            />
            <div className="absolute right-0 top-12 z-50 bg-white border border-gray-200 rounded-lg shadow-lg p-2 min-w-[150px]">
              {selectedTags.length > 0 && (
                <button
                  onClick={clearTags}
                  className="w-full text-left px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 rounded mb-1"
                >
                  Clear all
                </button>
              )}
              {availableTags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => toggleTag(tag)}
                  className={`
                    w-full text-left px-3 py-1.5 text-sm rounded transition-colors
                    ${selectedTags.includes(tag) ? "bg-blue-100 text-blue-700" : "hover:bg-gray-100 text-gray-700"}
                  `}
                >
                  {tag}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Tag className="w-3.5 h-3.5 text-gray-400" />
      <div className="flex items-center gap-1.5 flex-wrap">
        {availableTags.map((tag) => (
          <button
            key={tag}
            onClick={() => toggleTag(tag)}
            className={`
              px-2 py-0.5 rounded-full text-xs font-medium transition-colors
              ${
                selectedTags.includes(tag)
                  ? "bg-blue-500 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }
            `}
          >
            {tag}
          </button>
        ))}
        {selectedTags.length > 0 && (
          <button
            onClick={clearTags}
            className="p-0.5 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-200 transition-colors"
            title="Clear filters"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
