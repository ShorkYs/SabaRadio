const titleEl = document.getElementById("song-title");
const previousTitleEl = document.getElementById("previous-title");
const nextTitleEl = document.getElementById("next-title");
const skipBtn = document.getElementById("skip-btn");
const refreshBtn = document.getElementById("refresh-btn");
const playBtn = document.getElementById("play-btn");
const volumeSlider = document.getElementById("volume-slider");
const progressFill = document.getElementById("progress-fill");
const clockEl = document.getElementById("clock");
const meridiemEl = document.getElementById("clock-meridiem");
const activityAudio = document.getElementById("activity-audio");

const discordClientId = globalThis.__SABA_DISCORD_CLIENT_ID__ || import.meta.env?.VITE_DISCORD_CLIENT_ID || "";
let discordSdk = null;
let latestStreamUrl = null;

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

function setAudioSource(streamUrl) {
  if (!streamUrl || streamUrl === latestStreamUrl) return;

  latestStreamUrl = streamUrl;
  activityAudio.src = `${streamUrl}?t=${Date.now()}`;
  activityAudio.volume = Number(volumeSlider.value) / 100;

  if (playBtn.dataset.playing === "true") {
    activityAudio.play().catch((err) => {
      console.warn("Activity audio autoplay was blocked:", err);
      playBtn.dataset.playing = "false";
      playBtn.textContent = "▶";
    });
  }
}

async function fetchNowPlaying() {
  const res = await fetch("/api/now-playing");
  if (!res.ok) throw new Error(`Now-playing request failed: ${res.status}`);

  const data = await res.json();
  titleEl.textContent = formatDisplay(data.display_name, "No song running");
  previousTitleEl.textContent = formatDisplay(data.previous_display_name, "Nothing yet");
  nextTitleEl.textContent = formatDisplay(data.next_display_name, "Looping soon");

  if (typeof data.volume === "number") {
    volumeSlider.value = Math.round(data.volume * 100);
    activityAudio.volume = data.volume;
  }

  if (data.total_songs > 0 && data.current_index >= 0) {
    const progress = ((data.current_index + 1) / data.total_songs) * 100;
    progressFill.style.width = `${Math.max(4, Math.min(100, progress))}%`;
  }

  setAudioSource(data.stream_url);
}

async function skipTrack() {
  await fetch("/api/skip", { method: "POST" });
  latestStreamUrl = null;
  activityAudio.pause();
  setTimeout(fetchNowPlaying, 700);
}

function toggleActivityAudio() {
  if (!activityAudio.src && latestStreamUrl) {
    setAudioSource(latestStreamUrl);
  }

  if (activityAudio.paused) {
    activityAudio.play();
    playBtn.dataset.playing = "true";
    playBtn.textContent = "Ⅱ";
  } else {
    activityAudio.pause();
    playBtn.dataset.playing = "false";
    playBtn.textContent = "▶";
  }
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

skipBtn.addEventListener("click", skipTrack);
refreshBtn.addEventListener("click", fetchNowPlaying);
playBtn.addEventListener("click", toggleActivityAudio);
volumeSlider.addEventListener("input", updateVolume);
window.addEventListener("keydown", (event) => {
  if (event.key === "Enter") fetchNowPlaying();
});
activityAudio.addEventListener("ended", fetchNowPlaying);

async function bootstrap() {
  updateClock();
  setInterval(updateClock, 1000);

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
