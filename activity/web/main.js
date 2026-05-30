import { radioBackgrounds } from "./backgrounds.config.js";

const titleEl = document.getElementById("song-title");
const previousTitleEl = document.getElementById("previous-title");
const nextTitleEl = document.getElementById("next-title");
const queueNextBtn = document.getElementById("skip-btn");
const refreshBtn = document.getElementById("refresh-btn");
const queueBackBtn = document.getElementById("play-btn");
const volumeSlider = document.getElementById("volume-slider");
const progressFill = document.getElementById("progress-fill");
const clockEl = document.getElementById("clock");
const meridiemEl = document.getElementById("clock-meridiem");
const activityAudio = document.getElementById("activity-audio");
const currentBackgroundImg = document.getElementById("current-background-img");
const currentBackgroundTitle = document.getElementById("current-background-title");
const previousBackgroundBtn = document.getElementById("previous-background-btn");
const previousBackgroundImg = document.getElementById("previous-background-img");
const previousBackgroundTitle = document.getElementById("previous-background-title");
const nextBackgroundBtn = document.getElementById("next-background-btn");
const nextBackgroundImg = document.getElementById("next-background-img");
const nextBackgroundTitle = document.getElementById("next-background-title");

const discordClientId = globalThis.__SABA_DISCORD_CLIENT_ID__ || import.meta.env?.VITE_DISCORD_CLIENT_ID || "";
let discordSdk = null;
let latestStreamUrl = null;
let currentDuration = 0;
let currentStartedAt = null;
let currentProgress = 0;
let queueWindow = [];
let queueOffset = 0;
let activeBackgroundIndex = 0;

async function authenticateWithDiscord() {
  if (!discordClientId) return;

  const { DiscordSDK } = await import("https://esm.sh/@discord/embedded-app-sdk@1.5.0");
  discordSdk = new DiscordSDK(discordClientId);
  await discordSdk.ready();

  const { code } = await discordSdk.commands.authorize({
    client_id: discordClientId,
    response_type: "code",
    state: "saba-radio-state",
    prompt: "none",
    scope: ["identify", "guilds", "applications.commands"],
  });

  const tokenRes = await fetch("/api/discord/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });

  if (!tokenRes.ok) {
    throw new Error(`Token exchange failed: ${tokenRes.status}`);
  }

  const { access_token: accessToken } = await tokenRes.json();

  await discordSdk.commands.authenticate({
    access_token: accessToken,
  });
}

function formatDisplay(value, fallback) {
  return value || fallback;
}

function setAudioSource(streamUrl, startAtSeconds = 0) {
  if (!streamUrl || streamUrl === latestStreamUrl) return;

  latestStreamUrl = streamUrl;
  const mediaStart = Math.max(0, Math.floor(startAtSeconds));
  activityAudio.src = `${streamUrl}?t=${Date.now()}#t=${mediaStart}`;
  activityAudio.volume = Number(volumeSlider.value) / 100;

  activityAudio.play().catch((err) => {
    console.warn("Activity audio autoplay was blocked until user interaction:", err);
  });
}

function startActivityAudio() {
  if (latestStreamUrl && activityAudio.paused) {
    activityAudio.play().catch((err) => {
      console.warn("Activity audio still cannot start:", err);
    });
  }
}

function queueDisplayName(offset, fallback) {
  return queueWindow[offset]?.display_name || fallback;
}

function renderQueue(offset = queueOffset) {
  if (!queueWindow.length) return;

  queueOffset = Math.max(0, Math.min(offset, queueWindow.length - 1));
  previousTitleEl.textContent = queueDisplayName(Math.max(0, queueOffset - 1), "Nothing yet");
  titleEl.textContent = queueDisplayName(queueOffset, "No song running");
  nextTitleEl.textContent = queueDisplayName(Math.min(queueWindow.length - 1, queueOffset + 1), "Looping soon");
}

function updateProgressBar() {
  let progress = currentProgress;
  if (currentDuration > 0 && currentStartedAt) {
    progress = Math.min(1, Math.max(0, (Date.now() / 1000 - currentStartedAt) / currentDuration));
  }
  progressFill.style.width = `${Math.max(0, Math.min(100, progress * 100))}%`;
}

function renderBackgrounds() {
  if (!radioBackgrounds.length) return;

  const current = radioBackgrounds[activeBackgroundIndex];
  const previous = radioBackgrounds[(activeBackgroundIndex - 1 + radioBackgrounds.length) % radioBackgrounds.length];
  const next = radioBackgrounds[(activeBackgroundIndex + 1) % radioBackgrounds.length];

  document.body.style.backgroundImage = `url("${current.background}")`;
  currentBackgroundImg.src = current.image;
  currentBackgroundImg.alt = current.title;
  currentBackgroundTitle.textContent = current.title;
  previousBackgroundImg.src = previous.image;
  previousBackgroundImg.alt = previous.title;
  previousBackgroundTitle.textContent = previous.title;
  nextBackgroundImg.src = next.image;
  nextBackgroundImg.alt = next.title;
  nextBackgroundTitle.textContent = next.title;
}

function switchBackground(direction) {
  if (!radioBackgrounds.length) return;
  activeBackgroundIndex = (activeBackgroundIndex + direction + radioBackgrounds.length) % radioBackgrounds.length;
  renderBackgrounds();
}

async function fetchNowPlaying() {
  const res = await fetch("/api/now-playing");
  if (!res.ok) throw new Error(`Now-playing request failed: ${res.status}`);

  const data = await res.json();
  currentDuration = Number(data.current_duration) || 0;
  currentStartedAt = Number(data.current_started_at) || null;
  currentProgress = Number(data.current_progress) || 0;
  queueWindow = Array.isArray(data.queue_window) ? data.queue_window.slice(0, 5) : [];

  if (queueOffset >= queueWindow.length) queueOffset = 0;
  if (queueOffset === 0) {
    titleEl.textContent = formatDisplay(data.display_name, "No song running");
    previousTitleEl.textContent = formatDisplay(data.previous_display_name, "Nothing yet");
    nextTitleEl.textContent = formatDisplay(data.next_display_name, "Looping soon");
  } else {
    renderQueue(queueOffset);
  }

  if (typeof data.volume === "number") {
    volumeSlider.value = Math.round(data.volume * 100);
    activityAudio.volume = data.volume;
  }

  updateProgressBar();

  setAudioSource(data.stream_url, data.current_elapsed);
}

function showNextQueueItem() {
  if (!queueWindow.length) return;
  renderQueue((queueOffset + 1) % queueWindow.length);
}

function returnToCurrentQueueItem() {
  renderQueue(0);
}

let volumeTimer;
function updateVolume() {
  const val = Number(volumeSlider.value) / 100;
  activityAudio.volume = val;
  clearTimeout(volumeTimer);
  volumeTimer = setTimeout(async () => {
    await fetch(`/api/volume?value=${encodeURIComponent(val)}`, { method: "POST" });
  }, 120);
}

function updateClock() {
  const now = new Date();
  clockEl.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  meridiemEl.textContent = now.toLocaleTimeString([], { hour: "numeric", hour12: true }).split(" ").pop() || "";
}

queueNextBtn.addEventListener("click", () => {
  startActivityAudio();
  showNextQueueItem();
});
refreshBtn.addEventListener("click", fetchNowPlaying);
queueBackBtn.addEventListener("click", () => {
  startActivityAudio();
  returnToCurrentQueueItem();
});
previousBackgroundBtn.addEventListener("click", () => {
  startActivityAudio();
  switchBackground(-1);
});
nextBackgroundBtn.addEventListener("click", () => {
  startActivityAudio();
  switchBackground(1);
});
volumeSlider.addEventListener("input", updateVolume);
window.addEventListener("keydown", (event) => {
  if (event.key === "Enter") fetchNowPlaying();
});
activityAudio.addEventListener("ended", fetchNowPlaying);

async function bootstrap() {
  updateClock();
  renderBackgrounds();
  setInterval(updateClock, 1000);
  setInterval(updateProgressBar, 500);

  try {
    await authenticateWithDiscord();
    console.log("Discord activity auth complete.");
  } catch (err) {
    console.warn("Discord auth skipped/failed (still usable in browser):", err);
  }

  await fetchNowPlaying();
  setInterval(fetchNowPlaying, 5000);
}

bootstrap();
