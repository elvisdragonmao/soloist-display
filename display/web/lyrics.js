// Synced lyrics in the style of Spicy Lyrics: the active line is lit word by word,
// the rest dim and blur with distance, and every line glides to its place with a
// small stagger. LRCLIB lyrics are line-synced, so word timing is estimated from
// the line's length unless the LRC carries <mm:ss.xx> word tags.

const LINE_TAG = /^\[(\d+):(\d+(?:[.:]\d+)?)\]/;
const WORD_TAG = /<(\d+):(\d+(?:\.\d+)?)>/g;
const CJK = /[぀-ヿ㐀-鿿가-힯豈-﫿]/;
/** A gap this long between lines gets the three-dot interlude. */
const INTERLUDE_MS = 4500;

const toMs = (m, s) => Math.round((Number(m) * 60 + Number(s.replace(":", "."))) * 1000);
const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

/** Rough time to sing `text`, for lines followed by a long instrumental gap. */
function singMs(text) {
  let ms = 0;
  for (const part of text.split(/\s+/)) {
    if (!part) continue;
    const cjk = [...part].filter((c) => CJK.test(c)).length;
    ms += cjk ? cjk * 320 : 380;
  }
  return Math.max(ms, 1500);
}

const segmenter = typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "word" }) : null;

/** Split a line into words, keeping spaces and punctuation with the word before. */
function splitWords(text) {
  const parts = segmenter
    ? [...segmenter.segment(text)].map((s) => ({ text: s.segment, word: s.isWordLike }))
    : text.split(/(\s+)/).map((t) => ({ text: t, word: /\S/.test(t) }));
  const words = [];
  for (const p of parts) {
    if (!p.text) continue;
    if (!p.word && words.length) words[words.length - 1].text += p.text;
    else words.push({ text: p.text });
  }
  return words;
}

const weight = (word) => {
  const t = word.trim();
  const cjk = [...t].filter((c) => CJK.test(c)).length;
  return cjk || 0.7 + t.length * 0.08;
};

/** Spread the line's words over its sung part, by length. */
function timeWords(words, start, end) {
  const total = words.reduce((sum, w) => sum + weight(w.text), 0) || 1;
  const fill = Math.min((end - start) * 0.92, singMs(words.map((w) => w.text).join("")) * 1.6);
  let t = start;
  for (const w of words) {
    w.start = t;
    t += (weight(w.text) / total) * fill;
    w.end = t;
  }
  return words;
}

/** Words from enhanced LRC: `<00:12.30>word <00:12.80>word`. */
function taggedWords(text, lineEnd, offset) {
  const marks = [...text.matchAll(WORD_TAG)];
  if (!marks.length) return null;
  const words = [];
  marks.forEach((m, i) => {
    const from = m.index + m[0].length;
    const to = i + 1 < marks.length ? marks[i + 1].index : text.length;
    const word = text.slice(from, to);
    if (word.trim()) words.push({ text: word, start: toMs(m[1], m[2]) - offset });
  });
  words.forEach((w, i) => (w.end = words[i + 1]?.start ?? Math.min(lineEnd, w.start + 1000)));
  return words;
}

/**
 * Parse LRC into timed lines. Blank lines only mark where the line before ends.
 * Lines with a long silence after them end early, and the silence gets dots.
 */
export function parseLrc(lrc, durationMs = 0) {
  let offset = 0;
  const rows = [];
  for (const row of lrc.split(/\r?\n/)) {
    const off = row.match(/^\[offset:\s*([+-]?\d+)\]/i);
    if (off) offset = Number(off[1]);
    let rest = row;
    const times = [];
    for (let m; (m = rest.match(LINE_TAG)); rest = rest.slice(m[0].length)) times.push(toMs(m[1], m[2]));
    for (const t of times) rows.push({ start: t, raw: rest });
  }
  rows.sort((a, b) => a.start - b.start);

  const lines = [];
  rows.forEach((row, i) => {
    const text = row.raw.replace(WORD_TAG, "").trim();
    if (!text) return;
    const start = Math.max(0, row.start - offset);
    const next = rows[i + 1] ? rows[i + 1].start - offset : durationMs || start + 8000;
    let end = next;
    const sing = singMs(text);
    if (end - start > sing * 1.6 + INTERLUDE_MS) end = start + sing * 1.6;
    const words = taggedWords(row.raw.trim(), end, offset) ?? timeWords(splitWords(text), start, end);
    lines.push({ start, end, text, words });
  });

  const out = [];
  let prevEnd = 0;
  for (const line of lines) {
    if (line.start - prevEnd >= INTERLUDE_MS) {
      out.push({ dots: true, start: prevEnd + (out.length ? 300 : 800), end: line.start - 400 });
    }
    out.push(line);
    prevEnd = line.end;
  }
  return out;
}

export class LyricsView {
  constructor(root) {
    this.root = root;
    this.clear();
    new ResizeObserver(() => this.measure()).observe(root);
  }

  clear() {
    this.root.replaceChildren();
    this.root.classList.remove("static");
    this.lines = [];
    this.els = [];
    this.heights = [];
    this.isStatic = false;
    this.focus = -2;
    this.activeDots = false;
    this.staticY = null;
  }

  /** Show `lines` from parseLrc, or `plain` text when only unsynced lyrics exist. */
  set({ lines = null, plain = null } = {}) {
    this.clear();
    if (plain) {
      this.isStatic = true;
      this.root.classList.add("static");
      lines = plain.split(/\r?\n/).filter((t) => t.trim()).map((text) => ({ text }));
    }
    if (!lines?.length) return false;
    this.lines = lines;
    this.els = lines.map((line) => {
      const el = document.createElement("div");
      el.className = "line";
      if (line.dots) {
        el.classList.add("dots");
        for (let i = 0; i < 3; i++) el.append(Object.assign(document.createElement("span"), { className: "dot" }));
      } else if (line.words) {
        line.wordEls = line.words.map((w) => {
          const span = Object.assign(document.createElement("span"), { className: "w", textContent: w.text });
          el.append(span);
          return span;
        });
      } else {
        el.textContent = line.text;
      }
      Object.assign(el.style, { position: "absolute", top: "0", left: "0", right: "0" });
      return el;
    });
    this.root.replaceChildren(...this.els);
    this.measure();
    return true;
  }

  measure() {
    this.heights = this.els.map((el) => {
      if (!el.classList.contains("dots")) return el.offsetHeight;
      const size = parseFloat(getComputedStyle(el).fontSize);
      return size * 1.8;
    });
    this.layout(false);
  }

  /** Stack the lines and move the focused one to the focus point. */
  layout(stagger = true) {
    if (!this.els.length) return;
    const view = this.root.clientHeight;
    const ys = [];
    let y = 0;
    this.els.forEach((el, i) => {
      ys[i] = y;
      const shown = !this.lines[i].dots || (i === this.focus && this.activeDots);
      if (shown) y += this.heights[i];
    });

    if (this.isStatic) {
      this.staticOffset = { total: y, view };
      this.staticY = null;
      return this.scrollStatic(this.staticProgress ?? 0, false);
    }

    const f = Math.max(0, this.focus);
    const target = view * 0.36 - (ys[f] + this.heights[f] / 2);
    this.els.forEach((el, i) => {
      const d = i - f;
      el.style.transitionDelay = stagger && d >= -1 ? `${Math.min((d + 1) * 45, 450)}ms` : "0ms";
      const scale = i === f && this.focus >= 0 ? 1 : 0.96;
      el.style.transform = `translateY(${ys[i] + target}px) scale(${scale})`;
      el.style.setProperty("--blur", `${Math.min(Math.abs(d) * 1.3, 7)}px`);
    });
  }

  scrollStatic(progress, animate = true) {
    this.staticProgress = progress;
    const { total, view } = this.staticOffset ?? { total: 0, view: 0 };
    const target = Math.round(view * 0.25 - progress * Math.max(0, total - view * 0.5));
    if (target === this.staticY) return;
    this.staticY = target;
    let y = 0;
    this.els.forEach((el, i) => {
      el.style.transitionDelay = "0ms";
      el.style.transitionDuration = animate ? "2s" : "0s";
      el.style.transform = `translateY(${y + target}px)`;
      y += this.heights[i];
    });
  }

  /** Called every frame with the playback position in ms. */
  update(pos, duration) {
    if (!this.lines.length) return;
    if (this.isStatic) {
      if (duration) this.scrollStatic(clamp01(pos / duration));
      return;
    }

    let focus = -1;
    for (let i = 0; i < this.lines.length; i++) {
      if (this.lines[i].start <= pos) focus = i;
      else break;
    }
    const current = this.lines[focus];
    const isActive = !!current && pos < current.end;
    // Before the first line, or after a line with nothing new yet, stay put.
    if (focus !== this.focus || isActive !== this.isActive) {
      const jump = Math.abs(focus - this.focus) > 2;
      this.focus = focus;
      this.isActive = isActive;
      this.activeDots = !!current?.dots && isActive;
      this.els.forEach((el, i) => {
        el.classList.toggle("active", i === focus && isActive);
        el.classList.toggle("past", i < focus || (i === focus && !isActive));
        if (i === focus) return;
        this.lines[i].wordEls?.forEach((w) => {
          w.classList.toggle("sung", i < focus);
          w._p = undefined;
        });
      });
      this.layout(!jump);
    }

    if (!isActive) return;
    if (current.dots) {
      const t = clamp01((pos - current.start) / (current.end - current.start));
      this.els[focus].querySelectorAll(".dot").forEach((dot, k) => dot.style.setProperty("--d", clamp01(t * 3 - k).toFixed(3)));
      return;
    }
    current.words.forEach((w, k) => {
      const p = clamp01((pos - w.start) / (w.end - w.start || 1));
      const el = current.wordEls[k];
      if (Math.abs((el._p ?? -1) - p) < 0.002) return;
      el._p = p;
      el.style.setProperty("--p", p.toFixed(3));
      el.classList.toggle("sung", p > 0);
    });
  }
}
