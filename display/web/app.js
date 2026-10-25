import Kawarp from "./vendor/kawarp.js";
import { LyricsView, parseLrc } from "./lyrics.js";

const $ = (id) => document.getElementById(id);
const body = document.body;
const params = new URLSearchParams(location.search);
// Shift lyrics by this many ms; positive shows them earlier.
const LYRICS_OFFSET = Number(params.get("offset") ?? 0);
// After this long paused, fall back to the idle clock.
const IDLE_AFTER_PAUSE_MS = 15 * 60 * 1000;

let playback = null;
let isActive = false;
let trackUri = null;
let duration = 0;
let pausedSince = null;
const lyrics = new LyricsView($("lyrics-lines"));

// ─── Background ──────────────────────────────────────────────────────────────

const canvas = $("bg");
let kawarp = null;
try {
  kawarp = new Kawarp(canvas, {
    warpIntensity: 1,
    blurPasses: 8,
    animationSpeed: 1,
    saturation: 1.5,
    tintIntensity: 0,
    dithering: 0.008,
    transitionDuration: 1500,
  });
  // The effect is a blur, so a quarter of the screen's pixels is plenty.
  const size = () => {
    canvas.width = Math.round(innerWidth / 2);
    canvas.height = Math.round(innerHeight / 2);
    kawarp.resize();
  };
  addEventListener("resize", size);
  size();
  kawarp.loadGradient(["#1b2a4a", "#3b1f4f", "#0d3b3b"], 45);
  kawarp.start();
} catch (error) {
  console.warn("WebGL background unavailable", error);
  body.classList.add("no-webgl");
}

function setBackground(url) {
  $("bg-fallback").style.setProperty("--cover", `url("${url}")`);
  kawarp?.loadImage(url).catch((error) => console.warn("background image", error));
}

// ─── Soloist WebSocket ───────────────────────────────────────────────────────

async function connect() {
  let url = null;
  try {
    url = (await (await fetch("/api/config")).json()).ws;
  } catch {}
  if (!url) return setTimeout(connect, 2000);

  const ws = new WebSocket(url);
  ws.onopen = () => body.classList.remove("offline");
  ws.onmessage = (event) => {
    try {
      handle(JSON.parse(event.data));
    } catch (error) {
      console.warn("bad message", error, event.data);
    }
  };
  // Soloist gets a new port when it restarts (e.g. after an update), so start over.
  ws.onclose = () => {
    body.classList.add("offline");
    setTimeout(connect, 2000);
  };
}

function handle(msg) {
  if (msg.type === "auth_state") {
    isActive = !!msg.is_active;
    $("device").textContent = msg.device_name ?? "";
  } else if (msg.type === "playback_state") {
    playback = msg;
    isActive = msg.is_active ?? isActive;
  } else {
    return;
  }
  render();
}

// ─── Now playing ─────────────────────────────────────────────────────────────

const name = (entity) => entity?.decorations?.identity?.name ?? "";

function coverUrl(item, ...sizes) {
  const covers = item.decorations?.visual_identity?.cover ?? [];
  for (const size of sizes) {
    const cover = covers.find((c) => c.size === size);
    if (cover) return cover.url;
  }
  return covers.at(-1)?.url ?? null;
}

function render() {
  const item = playback?.item;
  const playing = playback?.status === "playing";
  if (playing || !item) pausedSince = null;
  else pausedSince ??= Date.now();

  body.classList.toggle("paused", !playing);
  if (kawarp) kawarp.animationSpeed = playing ? 1 : 0.15;
  updateIdle();
  if (!item || item.uri === trackUri) return;

  trackUri = item.uri;
  const d = item.decorations ?? {};
  duration = d.playback?.duration_ms ?? 0;
  const artists = (d.creators ?? []).map((c) => name(c.entity)).filter(Boolean);
  const album = name(d.parent?.entity);

  $("title").textContent = name(item);
  $("artist").textContent = artists.join(", ");
  $("album").textContent = album;
  $("time-dur").textContent = formatTime(duration);
  document.title = `${name(item)} — ${artists.join(", ")}`;

  const big = coverUrl(item, "xlarge", "large", "default");
  if (big) swapCover(big);
  const small = coverUrl(item, "default", "large");
  if (small) setBackground(small);

  loadLyrics(item.uri, name(item), artists[0] ?? "", album, duration);
}

function updateIdle() {
  const idle =
    !isActive || !playback?.item || (pausedSince !== null && Date.now() - pausedSince > IDLE_AFTER_PAUSE_MS);
  if (idle !== body.classList.contains("idle")) {
    body.classList.toggle("idle", idle);
    if (idle) kawarp?.loadGradient(["#1b2a4a", "#3b1f4f", "#0d3b3b"], 45);
    else if (playback?.item) setBackground(coverUrl(playback.item, "default", "large"));
  }
}

function swapCover(url) {
  const old = $("cover-img");
  const img = new Image();
  img.id = "cover-img";
  img.alt = "";
  img.onload = () => {
    old.id = "";
    old.classList.add("leaving");
    old.after(img);
    setTimeout(() => old.remove(), 700);
  };
  img.src = url;
}

// ─── Lyrics ──────────────────────────────────────────────────────────────────

async function loadLyrics(uri, track, artist, album, durationMs) {
  // The layout stays as it is until we know whether this track has lyrics.
  lyrics.clear();
  const q = new URLSearchParams({ id: uri, track, artist, album, duration: String(durationMs / 1000) });
  let data = {};
  try {
    data = await (await fetch(`/api/lyrics?${q}`)).json();
  } catch (error) {
    console.warn("lyrics", error);
  }
  if (uri !== trackUri) return;
  let shown = false;
  if (data.found && !data.instrumental) {
    if (data.synced) shown = lyrics.set({ lines: parseLrc(data.synced, durationMs) });
    else if (data.plain) shown = lyrics.set({ plain: data.plain });
  }
  body.classList.toggle("no-lyrics", !shown);
}

// ─── Frame loop ──────────────────────────────────────────────────────────────

function position() {
  const p = playback?.position;
  if (!p) return 0;
  let ms = p.position_ms;
  if (playback.status === "playing") ms += (Date.now() - p.timestamp_ms) * (p.speed ?? 1);
  return Math.max(0, duration ? Math.min(ms, duration) : ms);
}

function formatTime(ms) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

let lastSecond = -1;
function frame() {
  const pos = position();
  if (!body.classList.contains("idle")) {
    $("bar-fill").style.transform = `scaleX(${duration ? pos / duration : 0})`;
    const second = Math.floor(pos / 1000);
    if (second !== lastSecond) {
      lastSecond = second;
      $("time-pos").textContent = formatTime(pos);
    }
    lyrics.update(pos + LYRICS_OFFSET, duration);
  }
  requestAnimationFrame(frame);
}

function tick() {
  const now = new Date();
  $("clock").textContent = now.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
  updateIdle();
}

// ─── Full screen ─────────────────────────────────────────────────────────────
//
// The clubroom only has a mouse: moving it shows a hint, and a click leaves full
// screen, or goes back to it. The display opens in the browser's own full screen
// (--start-fullscreen), which a page cannot leave by script, so the server presses
// the full-screen key for us. Where it can't, the page's Fullscreen API is used.

const POINTER_HIDE_MS = 3000;
let pointerTimer = null;
let toggling = false;

function isFullscreen() {
  return !!document.fullscreenElement || (innerWidth >= screen.width - 1 && innerHeight >= screen.height - 1);
}

function updateFullscreen() {
  const full = isFullscreen();
  body.classList.toggle("fullscreen", full);
  $("fs-hint").textContent = full ? "點一下離開全螢幕" : "點一下回到全螢幕";
}

addEventListener("resize", updateFullscreen);
document.addEventListener("fullscreenchange", updateFullscreen);
updateFullscreen();

addEventListener("mousemove", () => {
  body.classList.add("pointer");
  clearTimeout(pointerTimer);
  pointerTimer = setTimeout(() => body.classList.remove("pointer"), POINTER_HIDE_MS);
});

async function toggleFullscreen() {
  if (document.fullscreenElement) return document.exitFullscreen();
  try {
    const res = await fetch("/api/fullscreen", { method: "POST" });
    if (res.ok) return;
  } catch {}
  if (!isFullscreen()) return document.documentElement.requestFullscreen();
  $("fs-hint").textContent = "按 F11（macOS：⌃⌘F）離開全螢幕";
}

addEventListener("click", async () => {
  if (toggling) return;
  toggling = true;
  try {
    await toggleFullscreen();
  } catch (error) {
    console.warn("fullscreen", error);
  }
  setTimeout(() => (toggling = false), 800);
});

// Lets soloist-display-open see that the display is already open.
const ping = () => fetch("/api/ping", { method: "POST" }).catch(() => {});

// ?demo&track=…&artist=…&album=…&duration=197&cover=…&at=60 plays a fake track,
// for working on the UI (or taking screenshots) without touching the real player.
function demo(q) {
  const image = (size) => ({ url: q.get("cover") || "", size });
  const artists = (q.get("artist") || "Artist").split(/\s*,\s*/);
  handle({ type: "auth_state", is_active: true, device_name: "Demo" });
  handle({
    type: "playback_state",
    status: q.get("status") || "playing",
    is_active: true,
    position: { position_ms: Number(q.get("at") || 0) * 1000, timestamp_ms: Date.now(), speed: 1 },
    item: {
      uri: `spotify:track:demo${(q.get("track") || "").replace(/\W/g, "")}`,
      decorations: {
        identity: { name: q.get("track") || "Track" },
        visual_identity: { cover: [image("default"), image("xlarge")] },
        creators: artists.map((name) => ({ entity: { decorations: { identity: { name } } } })),
        parent: { entity: { decorations: { identity: { name: q.get("album") || "" } } } },
        playback: { duration_ms: Number(q.get("duration") || 200) * 1000 },
      },
    },
  });
}

setInterval(tick, 1000);
tick();
if (params.has("demo")) demo(params);
else {
  body.classList.add("offline");
  connect();
  setInterval(ping, 15000);
  ping();
}
requestAnimationFrame(frame);
