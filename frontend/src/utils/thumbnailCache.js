/**
 * Simple in-memory cache to track which thumbnails have been loaded.
 * This helps avoid showing the loading skeleton for images that are already in the browser cache.
 */

const loadedThumbnails = new Set();

export const isThumbnailLoaded = (fileId) => {
    return loadedThumbnails.has(fileId);
};

export const markThumbnailLoaded = (fileId) => {
    loadedThumbnails.add(fileId);
};

export const clearThumbnailCache = () => {
    loadedThumbnails.clear();
};
