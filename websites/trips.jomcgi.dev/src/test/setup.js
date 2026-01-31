import "@testing-library/jest-dom";
import { vi } from "vitest";

// Mock maplibre-gl with proper class constructors
class MockMap {
  constructor() {
    this.on = vi.fn((event, layerOrCallback, callback) => {
      if (event === "load") {
        const cb = callback || layerOrCallback;
        setTimeout(() => cb(), 0);
      }
    });
    this.remove = vi.fn();
    this.addControl = vi.fn();
    this.addSource = vi.fn();
    this.addLayer = vi.fn();
    this.getSource = vi.fn(() => ({
      setData: vi.fn(),
    }));
    this.getCanvas = vi.fn(() => ({
      style: {},
    }));
    this.addImage = vi.fn();
    this.fitBounds = vi.fn();
    this.setCenter = vi.fn();
    this.setZoom = vi.fn();
  }
}

class MockNavigationControl {}

class MockMarker {
  setLngLat() {
    return this;
  }
  addTo() {
    return this;
  }
  remove() {}
  getElement() {
    return document.createElement("div");
  }
}

class MockPopup {
  setLngLat() {
    return this;
  }
  setHTML() {
    return this;
  }
  addTo() {
    return this;
  }
  remove() {}
}

class MockLngLatBounds {
  extend() {
    return this;
  }
}

vi.mock("maplibre-gl", () => ({
  default: {
    Map: MockMap,
    NavigationControl: MockNavigationControl,
    Marker: MockMarker,
    Popup: MockPopup,
    LngLatBounds: MockLngLatBounds,
  },
  Map: MockMap,
  NavigationControl: MockNavigationControl,
  Marker: MockMarker,
  Popup: MockPopup,
  LngLatBounds: MockLngLatBounds,
}));

// Mock window.matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));
