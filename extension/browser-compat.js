// Hashtagger — browser API compatibility shim.
//
// Chrome exposes `chrome.*`; Firefox exposes `browser.*` (promise-based). In
// Firefox, `chrome` is aliased to `browser`, but the callback style differs.
// This shim gives one `api` object that works in both.
//
// Loaded before background.js / popup.js / content.js in the Firefox build.

const api = (typeof browser !== "undefined" && browser.runtime) ? browser : chrome;

// Promise-returning wrappers so callers don't branch on browser.
const ext = {
  isFirefox: typeof browser !== "undefined" && !!browser.runtime,

  async storageGet(keys) {
    if (ext.isFirefox) return api.storage.local.get(keys);
    return new Promise((resolve) => api.storage.local.get(keys, resolve));
  },

  async storageSet(obj) {
    if (ext.isFirefox) return api.storage.local.set(obj);
    return new Promise((resolve) => api.storage.local.set(obj, resolve));
  },

  // sendMessage from a page/popup to the background
  sendMessage(msg) {
    if (ext.isFirefox) return api.runtime.sendMessage(msg);
    return new Promise((resolve) => {
      api.runtime.sendMessage(msg, (resp) => {
        if (api.runtime.lastError) resolve(null);
        else resolve(resp);
      });
    });
  },

  // sendMessage from background to a specific tab
  sendToTab(tabId, msg) {
    if (ext.isFirefox) return api.tabs.sendMessage(tabId, msg);
    return new Promise((resolve) => {
      api.tabs.sendMessage(tabId, msg, (resp) => {
        if (api.runtime.lastError) resolve(null);
        else resolve(resp);
      });
    });
  },

  // Query the active tab in the current window.
  async activeTab() {
    if (ext.isFirefox) {
      const [tab] = await api.tabs.query({ active: true, currentWindow: true });
      return tab;
    }
    return new Promise((resolve) =>
      api.tabs.query({ active: true, currentWindow: true }, (tabs) => resolve(tabs[0]))
    );
  },

  // Register a message listener (top-level only, for MV3 cold starts).
  onMessage(handler) {
    api.runtime.onMessage.addListener(handler);
  },
};
