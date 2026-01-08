/**
 * Calculate perpendicular offsets for overlapping route days
 * Prevents days traveling the same road from obscuring each other
 */
export function calculateDayOffsets(pointsByDay, options = {}) {
  const {
    overlapThreshold = 0.01, // ~1km in lat/lng units
    minOverlapPoints = 10,
    sampleRate = 5,
    offsetAmount = 4,
  } = options;

  const offsets = new Map();
  const dayNumbers = Array.from(pointsByDay.keys()).sort((a, b) => a - b);

  // Find overlapping day pairs
  const overlaps = [];
  for (let i = 0; i < dayNumbers.length; i++) {
    for (let j = i + 1; j < dayNumbers.length; j++) {
      const day1 = dayNumbers[i];
      const day2 = dayNumbers[j];
      const points1 = pointsByDay.get(day1);
      const points2 = pointsByDay.get(day2);

      let overlapCount = 0;

      for (let pi = 0; pi < points2.length; pi += sampleRate) {
        const p2 = points2[pi];
        for (let pj = 0; pj < points1.length; pj += sampleRate) {
          const p1 = points1[pj];
          const dist = Math.abs(p1.lat - p2.lat) + Math.abs(p1.lng - p2.lng);
          if (dist < overlapThreshold) {
            overlapCount++;
            break;
          }
        }
      }

      if (overlapCount >= minOverlapPoints) {
        overlaps.push({ day1, day2, points1, points2, overlapCount });
      }
    }
  }

  // Sort by most overlap first
  overlaps.sort((a, b) => b.overlapCount - a.overlapCount);

  // Assign offsets based on travel direction
  for (const { day1, day2, points1, points2 } of overlaps) {
    if (offsets.has(day1) && offsets.has(day2)) {
      continue;
    }

    // Determine travel direction (north vs south)
    const dir1 =
      points1.length > 1
        ? Math.sign(points1[points1.length - 1].lat - points1[0].lat)
        : 0;
    const dir2 =
      points2.length > 1
        ? Math.sign(points2[points2.length - 1].lat - points2[0].lat)
        : 0;
    const sameDirection = dir1 === dir2 || dir1 === 0 || dir2 === 0;

    let offset1, offset2;
    if (sameDirection) {
      // Same direction: offset to opposite sides
      offset1 = -offsetAmount;
      offset2 = offsetAmount;
    } else {
      // Opposite directions: offset to same side (visually separates outbound/return)
      offset1 = -offsetAmount;
      offset2 = -offsetAmount;
    }

    if (!offsets.has(day1)) {
      offsets.set(day1, offset1);
    }
    if (!offsets.has(day2)) {
      offsets.set(day2, offset2);
    }
  }

  return offsets;
}

/**
 * Group points by day number from day segments
 * @param {Array} segments - Array of segment objects with { dayNumber, points }
 * @returns {Map} Map of dayNumber -> points array
 */
export function groupPointsByDayNumber(segments) {
  const pointsByDay = new Map();
  for (const segment of segments) {
    const existing = pointsByDay.get(segment.dayNumber) || [];
    pointsByDay.set(segment.dayNumber, [...existing, ...segment.points]);
  }
  return pointsByDay;
}

/**
 * Calculate marker offset based on line direction and day offset
 * @param {Object} point - Current point
 * @param {number} pointIndex - Index in points array
 * @param {Array} points - All points
 * @param {number} lineOffset - The line offset for this day
 * @returns {Array} [x, y] offset for marker
 */
export function calculateMarkerOffset(point, pointIndex, points, lineOffset) {
  if (lineOffset === 0) return [0, 0];

  const prevPoint = pointIndex > 0 ? points[pointIndex - 1] : null;
  const nextPoint =
    pointIndex < points.length - 1 ? points[pointIndex + 1] : null;

  let dx = 0,
    dy = 0;
  if (prevPoint && nextPoint) {
    dx = nextPoint.lng - prevPoint.lng;
    dy = -(nextPoint.lat - prevPoint.lat);
  } else if (nextPoint) {
    dx = nextPoint.lng - point.lng;
    dy = -(nextPoint.lat - point.lat);
  } else if (prevPoint) {
    dx = point.lng - prevPoint.lng;
    dy = -(point.lat - prevPoint.lat);
  }

  const len = Math.sqrt(dx * dx + dy * dy);
  if (len > 0) {
    dx /= len;
    dy /= len;
    const perpX = -dy;
    const perpY = dx;
    return [perpX * lineOffset, perpY * lineOffset];
  }

  return [0, 0];
}
