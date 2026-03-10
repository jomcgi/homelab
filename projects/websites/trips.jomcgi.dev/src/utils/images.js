import { IMAGE_BASE_URL } from "../constants/api";

// Construct image URLs from filename
export const getThumbUrl = (image) => `${IMAGE_BASE_URL}/trips/thumb/${image}`;
export const getDisplayUrl = (image) =>
  `${IMAGE_BASE_URL}/trips/display/${image}`;
