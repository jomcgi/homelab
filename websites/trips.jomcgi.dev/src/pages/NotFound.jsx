import React from "react";
import { Link } from "wouter";
import { MapPin } from "lucide-react";

export function NotFound() {
  return (
    <div className="h-dvh w-full bg-gray-50 flex flex-col items-center justify-center gap-6 px-4">
      <MapPin className="h-16 w-16 text-gray-300" />
      <div className="text-center">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">404</h1>
        <p className="text-gray-600 text-lg mb-1">Trip not found</p>
        <p className="text-gray-500 text-sm">
          The trip you're looking for doesn't exist or has been moved.
        </p>
      </div>
      <Link href="/2025-liard-hot-springs">
        <button className="px-6 py-3 bg-gray-900 text-white rounded-lg font-medium hover:bg-gray-800 transition-colors">
          View Latest Trip →
        </button>
      </Link>
    </div>
  );
}
