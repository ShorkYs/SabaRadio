import { DiscordSDK } from "@discord/embedded-app-sdk";

const titleEl = document.getElementById("song-title");
const miniTitleEl = document.getElementById("mini-title");
const skipBtn = document.getElementById("skip-btn");
const refreshBtn = document.getElementById("refresh-btn");
const volumeSlider = document.getElementById("volume-slider");

const discordSdk = new DiscordSDK(import.meta.env.VITE_DISCORD_CLIENT_ID);

async function authenticateWithDiscord() {
  await discordSdk.ready();

  const { code } = await discordSdk.commands.authorize({
    client_id: import.meta.env.VITE_DISCORD_CLIENT_ID,
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

async function fetchNowPlaying() {
  const res = await fetch("/api/now-playing");
  if (!res.ok) throw new Error(`Now-playing request failed: ${res.status}`);

  const data = await res.json();
  const display = data.display_name || "No song running";
  titleEl.textContent = display;
  miniTitleEl.textContent = display;

  if (typeof data.volume === "number") {
    volumeSlider.value = Math.round(data.volume * 100);
  }
}

async function skipTrack() {
  await fetch("/api/skip", { method: "POST" });
  setTimeout(fetchNowPlaying, 500);
}

let volumeTimer;
function updateVolume() {
  clearTimeout(volumeTimer);
  volumeTimer = setTimeout(async () => {
    const val = Number(volumeSlider.value) / 100;
    await fetch(`/api/volume?value=${encodeURIComponent(val)}`, { method: "POST" });
  }, 120);
}

skipBtn.addEventListener("click", skipTrack);
refreshBtn.addEventListener("click", fetchNowPlaying);
volumeSlider.addEventListener("input", updateVolume);

async function bootstrap() {
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
