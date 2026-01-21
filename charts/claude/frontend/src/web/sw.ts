/// <reference lib="webworker" />
// Basic service worker to handle push notifications and precache

/* eslint-env serviceworker */
/* global ServiceWorkerGlobalScope, ExtendableEvent, PushEvent, NotificationEvent, WindowClient */

import { precacheAndRoute } from "workbox-precaching";

interface ManifestEntry {
  url: string;
  revision?: string;
}

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: ManifestEntry[];
};

// Removed forced skipWaiting on install - let vite-plugin-pwa control update strategy
// with registerType: "prompt" to avoid mid-session cache issues

self.addEventListener("activate", (event: ExtendableEvent) => {
  event.waitUntil(self.clients.claim());
});

// Injected by vite-plugin-pwa (injectManifest)
precacheAndRoute(self.__WB_MANIFEST || []);

self.addEventListener("push", (event: PushEvent) => {
  try {
    const data = event.data ? event.data.json() : {};
    const title = data.title || "CUI";
    const body = data.message || "";
    const tag = data.tag || "cui";
    const payloadData = data.data || {};
    const options: NotificationOptions = {
      body,
      tag,
      data: payloadData,
      icon: "/icon-192x192.png",
      badge: "/icon-192x192.png",
    };
    event.waitUntil(self.registration.showNotification(title, options));
  } catch (_err) {
    // no-op
  }
});

self.addEventListener("notificationclick", (event: NotificationEvent) => {
  event.notification.close();
  const url = "/";
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          const w = client as WindowClient;
          if ("focus" in w) {
            void w.focus();
            return;
          }
        }
        if (self.clients.openWindow) {
          void self.clients.openWindow(url);
        }
      }),
  );
});
