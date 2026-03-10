import { describe, it, expect, beforeEach, vi } from "vitest";
import { getThumbUrl, getDisplayUrl } from "../utils/images";

// IMAGE_BASE_URL is resolved from import.meta.env at module load time.
// In the test environment, VITE_IMAGE_URL is not set, so the module falls back to
// the default "https://img.jomcgi.dev".
const DEFAULT_BASE = "https://img.jomcgi.dev";

describe("getThumbUrl", () => {
  it("builds a thumb URL from a filename", () => {
    const url = getThumbUrl("IMG_0001.jpg");
    expect(url).toBe(`${DEFAULT_BASE}/trips/thumb/IMG_0001.jpg`);
  });

  it("includes the /trips/thumb/ path segment", () => {
    const url = getThumbUrl("photo.jpg");
    expect(url).toContain("/trips/thumb/");
  });

  it("preserves the exact filename", () => {
    const filename = "2024-01-15_vacation_001.jpg";
    const url = getThumbUrl(filename);
    expect(url).toContain(filename);
  });

  it("works with filenames that have no extension", () => {
    const url = getThumbUrl("myimage");
    expect(url).toBe(`${DEFAULT_BASE}/trips/thumb/myimage`);
  });

  it("works with filenames containing spaces", () => {
    const url = getThumbUrl("my image.jpg");
    expect(url).toBe(`${DEFAULT_BASE}/trips/thumb/my image.jpg`);
  });

  it("works with empty string filename", () => {
    const url = getThumbUrl("");
    expect(url).toBe(`${DEFAULT_BASE}/trips/thumb/`);
  });

  it("returns a string", () => {
    expect(typeof getThumbUrl("test.jpg")).toBe("string");
  });
});

describe("getDisplayUrl", () => {
  it("builds a display URL from a filename", () => {
    const url = getDisplayUrl("IMG_0001.jpg");
    expect(url).toBe(`${DEFAULT_BASE}/trips/display/IMG_0001.jpg`);
  });

  it("includes the /trips/display/ path segment", () => {
    const url = getDisplayUrl("photo.jpg");
    expect(url).toContain("/trips/display/");
  });

  it("preserves the exact filename", () => {
    const filename = "landscape_wide.jpg";
    const url = getDisplayUrl(filename);
    expect(url).toContain(filename);
  });

  it("works with filenames that have no extension", () => {
    const url = getDisplayUrl("rawimage");
    expect(url).toBe(`${DEFAULT_BASE}/trips/display/rawimage`);
  });

  it("returns a string", () => {
    expect(typeof getDisplayUrl("test.jpg")).toBe("string");
  });
});

describe("getThumbUrl vs getDisplayUrl", () => {
  it("thumb and display URLs differ for the same filename", () => {
    const filename = "IMG_0042.jpg";
    expect(getThumbUrl(filename)).not.toBe(getDisplayUrl(filename));
  });

  it("thumb URL contains 'thumb' and display URL contains 'display'", () => {
    const filename = "photo.jpg";
    expect(getThumbUrl(filename)).toContain("thumb");
    expect(getDisplayUrl(filename)).toContain("display");
  });

  it("both URLs share the same base", () => {
    const filename = "shared.jpg";
    const thumbUrl = getThumbUrl(filename);
    const displayUrl = getDisplayUrl(filename);

    // Both should start with the same base URL
    expect(thumbUrl.startsWith(DEFAULT_BASE)).toBe(true);
    expect(displayUrl.startsWith(DEFAULT_BASE)).toBe(true);
  });

  it("both URLs end with the provided filename", () => {
    const filename = "ending.jpg";
    expect(getThumbUrl(filename).endsWith(filename)).toBe(true);
    expect(getDisplayUrl(filename).endsWith(filename)).toBe(true);
  });
});
