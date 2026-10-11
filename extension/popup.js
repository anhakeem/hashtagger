// Hashtagger — popup controller.
//
// The popup reads the current tab's composer text (via a content-script
// message), lets the user generate hashtags, and copies them to the clipboard.

const $ = (id) => document.getElementById(id);
const PLATFORM = "x"; // popup is X/Twitter-focused for v1

function sendToTab(tabId, msg) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, msg, (resp) => {
      if (chrome.runtime.lastError) resolve(null);
      else resolve(resp);
    });
  });
}

function sendToBackground(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (resp) => resolve(resp));
  });
}

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function loadComposerText() {
  const tab = await currentTab();
  if (!tab) return;
  const resp = await sendToTab(tab.id, { type: "GET_COMPOSER_TEXT" });
  if (resp?.text) $("text").value = resp.text;
}

function renderTags(hashtags) {
  const box = $("results");
  if (!hashtags?.length) {
    box.innerHTML = '<div class="meta">No hashtags returned.</div>';
    return;
  }
  box.innerHTML = hashtags
    .map((h) => {
      const cls = h.trending ? "tag trending" : "tag";
      return `<span class="${cls}">${h.tag} <span class="score">${Math.round(
        (h.score || 0) * 100
      )}%</span></span>`;
    })
    .join("");
  $("copy").style.display = "block";
  $("copy").dataset.tags = hashtags.map((h) => h.tag).join(" ");
}

async function generate() {
  const btn = $("go");
  const status = $("status");
  const text = $("text").value.trim();
  if (!text) {
    status.innerHTML = '<span class="error">Enter or capture a post first.</span>';
    return;
  }
  btn.disabled = true;
  status.textContent = "Generating…";
  const resp = await sendToBackground({
    type: "GENERATE",
    payload: { text, platform: PLATFORM, maxTags: parseInt($("max").value, 10) || undefined },
  });
  btn.disabled = false;
  if (!resp?.ok) {
    status.innerHTML = `<span class="error">${resp?.error || "Failed"}</span>`;
    return;
  }
  status.textContent = "Done.";
  renderTags(resp.data.hashtags);
}

async function checkHealth() {
  const resp = await sendToBackground({ type: "HEALTH" });
  $("badge").textContent = resp?.ok ? "API online" : "API offline";
}

$("go").addEventListener("click", generate);
$("capture").addEventListener("click", loadComposerText);
$("copy").addEventListener("click", async (e) => {
  await navigator.clipboard.writeText(e.target.dataset.tags || "");
  $("status").textContent = "Copied!";
});

loadComposerText();
checkHealth();
