/* sky_tonight — an all-sky chart of what is actually above you.

   The server hands over positions already projected into a 1000-unit horizon
   circle, so this file only draws. Stereographic from the zenith: centre is
   straight up, the rim is the horizon, North is up and East is LEFT, because
   you are looking up at the sky rather than down at a map.

   Sizes are in viewBox units rather than px so the chart scales with the cell;
   a star's radius falls off geometrically with magnitude, which is what makes a
   star field read as depth rather than as scattered dots. */

const esc = (s) =>
  String(s == null ? '' : s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);

/* Palettes live in JS, not CSS, and are applied as custom properties: the sheet
   then refers only to var(--sky-*) and stays free of literal colour. */
const THEMES = {
  chart:     { paper: '#ffffff', ink: '#0a0a0a', soft: '#7a7a7a', line: '#4a4a4a', faint: '#c8c8c8' },
  night:     { paper: '#0d0d0d', ink: '#ffffff', soft: '#a8a8a8', line: '#c4c4c4', faint: '#454545' },
  blueprint: { paper: '#12304f', ink: '#f4faff', soft: '#9dc2e0', line: '#b9d6ee', faint: '#2b5478' },
};

const R_HORIZON = 1000;
const VIEW = 1155;                    // leaves room for the cardinal letters

/* alt -> radius, matching the server's r = tan(z/2) */
const altR = (alt) => Math.tan(((90 - alt) / 2) * Math.PI / 180) * R_HORIZON;

/* A star's disc shrinks geometrically with magnitude, which is what makes a
   field read as depth. The floor matters as much as the curve: below about
   1 px a star dithers away to nothing on e-ink, so the faintest still get a
   dot you can actually see. */
const starR = (m) => Math.max(5.6, Math.min(34, 30 * Math.pow(0.76, m + 1.5)));

function moonPath(r, illum, waxing, flip) {
  /* Outer limb plus the terminator ellipse. The terminator's semi-axis is
     r*|1-2f|, and it curves with the limb past half phase and against it
     before, which is the whole difference between a crescent and a gibbous. */
  const b = r * Math.abs(1 - 2 * illum);
  const lit = flip ? !waxing : waxing;
  const outer = lit ? 1 : 0;
  const inner = illum > 0.5 ? outer : 1 - outer;
  return `M0 ${-r} A ${r} ${r} 0 0 ${outer} 0 ${r} A ${b} ${r} 0 0 ${inner} 0 ${-r} Z`;
}

/* Past about 60% of the way out, a label set to the right runs off the disc and
   into the cardinal letter. Those flip and open back toward the centre. */
function sideText(x, y, text, gap, cls) {
  const flip = x > R_HORIZON * 0.55;
  return `<text${cls ? ` class="${cls}"` : ''} x="${flip ? x - gap : x + gap}" y="${y}"`
    + `${flip ? ' text-anchor="end"' : ''}>${esc(text)}</text>`;
}

function chartSvg(d, bleed) {
  const parts = [];
  const ring = (alt) => `<circle class="ring" cx="0" cy="0" r="${altR(alt).toFixed(1)}"/>`;

  parts.push(`<circle class="disc" cx="0" cy="0" r="${R_HORIZON}"/>`);
  if (!bleed) {
    parts.push(ring(30), ring(60));
    parts.push(`<circle class="horizon" cx="0" cy="0" r="${R_HORIZON}"/>`);
  }

  if (d.show_lines !== false && d.lines) {
    parts.push(`<path class="figures" d="${d.lines}"/>`);
  }

  /* stars, faintest first so the bright ones sit on top */
  const stars = (d.stars || []).slice().sort((a, b) => b[2] - a[2]);
  parts.push('<g class="stars">' + stars.map(
    (s) => `<circle cx="${s[0]}" cy="${s[1]}" r="${starR(s[2]).toFixed(1)}"/>`).join('') + '</g>');

  if (d.show_labels !== false && !bleed) {
    parts.push('<g class="clabel">' + (d.labels || []).map(
      (l) => `<text x="${l.x}" y="${l.y}">${esc(l.t)}</text>`).join('') + '</g>');
  }
  if (d.show_star_names !== false && !bleed) {
    parts.push('<g class="slabel">' + (d.starnames || []).map(
      (s) => sideText(s.x, s.y + 13, s.t, 28)).join('') + '</g>');
  }

  if (d.show_planets !== false) {
    parts.push('<g class="planets">' + (d.planets || []).filter((p) => p.m < 6).map((p) => `
      <circle class="pdot" cx="${p.x}" cy="${p.y}" r="${starR(Math.max(p.m, 0.2)).toFixed(1)}"/>
      <circle class="pring" cx="${p.x}" cy="${p.y}" r="${(starR(Math.max(p.m, 0.2)) + 12).toFixed(1)}"/>
      ${bleed || p.lbl === false ? '' : sideText(p.x, p.y - 16, p.n, 34, 'pname')}`).join('') + '</g>');
  }

  const m = d.moon || {};
  if (m.up && m.x != null) {
    parts.push(`<g class="moon" transform="translate(${m.x} ${m.y})">
      <circle class="mdisc" cx="0" cy="0" r="34"/>
      <path class="mlit" d="${moonPath(34, m.illum, m.waxing, m.flip)}"/>
    </g>`);
  }
  const s = d.sun || {};
  if (s.x != null) {
    parts.push(`<g class="sun" transform="translate(${s.x} ${s.y})">
      <circle cx="0" cy="0" r="34"/>${bleed ? '' : '<text y="-52">Sun</text>'}</g>`);
  }

  const card = bleed ? [] : [['N', 0, -1], ['E', -1, 0], ['S', 0, 1], ['W', 1, 0]];
  parts.push('<g class="cardinal">' + card.map(
    ([t, dx, dy]) => `<text x="${dx * 1090}" y="${dy * 1090 + (dy === 0 ? 26 : dy > 0 ? 62 : -10)}">${t}</text>`
  ).join('') + '</g>');

  return `<svg class="chart" viewBox="${-VIEW} ${-VIEW} ${VIEW * 2} ${VIEW * 2}"
    preserveAspectRatio="xMidYMid meet">${parts.join('')}</svg>`;
}

function moonGlyph(m) {
  /* The same terminator maths the chart uses, at readout size. A drawn phase
     says more at a glance than the words next to it. */
  const r = 42;
  return `<svg class="mglyph${m.up ? '' : ' down'}" viewBox="-50 -50 100 100" aria-hidden="true">
    <circle class="mg-disc" cx="0" cy="0" r="${r}"/>
    <path class="mg-lit" d="${moonPath(r, m.illum, m.waxing, m.flip)}"/>
  </svg>`;
}

function sidePanel(d) {
  /* Ordered by what you actually look for: when is this, what is the Moon
     doing, what is up, and only then the housekeeping. */
  const m = d.moon || {};
  const planets = (d.planets || []).filter((p) => p.m < 4.0).slice(0, 5);

  const planetRows = planets.length
    ? planets.map((p) => `
        <div class="prow">
          <span class="psym">${esc(p.s)}</span>
          <span class="pnm">${esc(p.n)}</span>
          <span class="palt">${p.alt}\u00b0</span>
        </div>`).join('')
    : '<div class="pnone">None above the horizon</div>';

  return `
    <div class="side">
      <div class="loc">${esc(d.label)}</div>
      <div class="sub">${esc(d.date)} \u00b7 ${esc(d.time)}${d.is_now ? '' : ' \u00b7 nightly'}</div>

      <div class="rule"></div>

      <div class="mblock">
        ${moonGlyph(m)}
        <div class="mtext">
          <div class="mphase">${esc(m.phase)}</div>
          <div class="mnote">${d.moon_illum}% lit${m.up ? `, ${m.alt}\u00b0 up` : ', below horizon'}</div>
        </div>
      </div>

      <div class="rule"></div>

      <div class="plist">${planetRows}</div>

      <div class="rule rule-b"></div>

      <div class="stats">
        <div class="stat"><div class="sv">${esc(d.dark ? 'Night' : d.twilight)}</div><div class="sk">Sky</div></div>
        <div class="stat"><div class="sv">${d.star_count}</div><div class="sk">Stars to mag ${d.mag}</div></div>
      </div>
    </div>`;
}

export default function render(shadow, ctx) {
  const d = (ctx && ctx.data) || {};
  const fragment = (ctx && ctx.cell && ctx.cell.fragment) || 'full';
  /* Fragments are only offered by the canvas picker, so the same three modes
     are also a cell option. An explicitly chosen fragment wins; otherwise the
     option decides, which is what makes full bleed reachable in the plain
     widget view. */
  const mode = fragment === 'chart' || fragment === 'bleed' ? fragment : (d.layout || 'board');
  const bleed = mode === 'bleed';
  const bare = mode === 'chart' || bleed;
  const pal = THEMES[d.theme] || THEMES.chart;

  const body = d.error
    ? `<div class="msg"><div class="msg-t">Tonight's sky</div><div class="msg-b">${esc(d.error)}</div></div>`
    : `<div class="wrap${bare ? ' bare' : ''}${bleed ? ' bleed' : ''}">
         <div class="chartbox">${chartSvg(d, bleed)}</div>
         ${bare ? '' : sidePanel(d)}
       </div>`;

  shadow.innerHTML = `
    <link rel="stylesheet" href="/static/style/spectra-widgets.css">
    <div class="sky">${body}</div>
    <style>
      :host { display: block; height: 100%; }
      .sky {
        container-type: size; height: 100%; width: 100%;
        background: var(--sky-paper); color: var(--sky-ink);
        font-family: var(--font-family, inherit);
        font-variant-numeric: tabular-nums;
        overflow: hidden;
      }
      .wrap { display: flex; height: 100%; width: 100%; align-items: stretch; }
      .chartbox {
        flex: 0 0 auto; height: 100%; aspect-ratio: 1 / 1;
        display: flex; align-items: center; justify-content: center;
        padding: 1.5cqmin; box-sizing: border-box;
      }
      .wrap.bare .chartbox { flex: 1 1 auto; width: 100%; aspect-ratio: auto; }
      .wrap.bleed .chartbox { padding: 0; }
      .chart { width: 100%; height: 100%; display: block; }

      .disc { fill: var(--sky-paper); }
      .ring {
        fill: none; stroke: var(--sky-faint); stroke-width: 3; stroke-dasharray: 14 16;
      }
      .horizon { fill: none; stroke: var(--sky-ink); stroke-width: 11; }
      .figures {
        fill: none; stroke: var(--sky-line); stroke-width: 7;
        stroke-linecap: round; stroke-linejoin: round;
      }
      .stars circle { fill: var(--sky-ink); }
      .clabel text {
        fill: var(--sky-soft); font-size: 42px; font-weight: 700;
        letter-spacing: 5px; text-anchor: middle; text-transform: uppercase;
      }
      .slabel text { fill: var(--sky-ink); font-size: 40px; font-weight: 800; }
      .pdot { fill: var(--sky-ink); }
      .pring { fill: none; stroke: var(--sky-ink); stroke-width: 4; }
      .pname { fill: var(--sky-ink); font-size: 44px; font-weight: 800; letter-spacing: 1px; }
      .moon .mdisc { fill: var(--sky-faint); stroke: var(--sky-ink); stroke-width: 5; }
      .moon .mlit { fill: var(--sky-ink); }
      .sun circle { fill: none; stroke: var(--sky-ink); stroke-width: 6; stroke-dasharray: 10 10; }
      .sun text { fill: var(--sky-ink); font-size: 44px; font-weight: 800; text-anchor: middle; }
      .cardinal text {
        fill: var(--sky-ink); font-size: 74px; font-weight: 800;
        text-anchor: middle; letter-spacing: 2px;
      }

      .side {
        flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column;
        padding: 3.6cqmin 3.6cqmin 3.2cqmin 0; box-sizing: border-box;
      }
      .loc {
        font-size: 8cqmin; font-weight: 800; line-height: 1.02; letter-spacing: -0.015em;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .sub {
        font-size: 2.6cqmin; font-weight: 700; letter-spacing: 0.1em;
        text-transform: uppercase; color: var(--sky-soft); margin-top: 1cqmin;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      /* a painted hairline rather than a border, so the rule is a deliberate
         element of the instrument face and not incidental chrome */
      .rule { height: 3px; background: var(--sky-faint); margin: 3cqmin 0; }

      .mblock { display: flex; align-items: center; gap: 3cqmin; }
      .mglyph { width: 12cqmin; height: 12cqmin; flex: 0 0 auto; }
      .mglyph.down { opacity: 0.42; }
      .mg-disc { fill: var(--sky-faint); stroke: var(--sky-soft); stroke-width: 4; }
      .mg-lit { fill: var(--sky-ink); }
      .mtext { min-width: 0; }
      .mphase { font-size: 4.4cqmin; font-weight: 800; line-height: 1.1; }
      .mnote {
        font-size: 2.7cqmin; font-weight: 700; color: var(--sky-soft);
        margin-top: 0.5cqmin; letter-spacing: 0.04em;
      }

      .plist { display: flex; flex-direction: column; gap: 1.4cqmin; }
      .prow { display: flex; align-items: baseline; gap: 2cqmin; }
      .psym { font-size: 4.4cqmin; line-height: 1; width: 1.3em; flex: 0 0 auto; }
      .pnm { font-size: 3.6cqmin; font-weight: 800; flex: 1 1 auto; min-width: 0;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .palt { font-size: 2.8cqmin; font-weight: 700; color: var(--sky-soft); }
      .pnone { font-size: 3.2cqmin; font-weight: 700; color: var(--sky-soft); }

      .rule-b { margin-top: auto; }
      .stats { display: flex; gap: 5cqmin; align-items: flex-end; }
      .sv { font-size: 4.6cqmin; font-weight: 800; line-height: 1.05; }
      .sk {
        font-size: 2.3cqmin; font-weight: 700; letter-spacing: 0.16em;
        text-transform: uppercase; color: var(--sky-soft); margin-top: 0.4cqmin;
      }

      .msg {
        height: 100%; display: flex; flex-direction: column; justify-content: center;
        gap: 1.6cqmin; padding: 5cqmin;
      }
      .msg-t {
        font-size: 3.2cqmin; font-weight: 800; letter-spacing: 0.18em;
        text-transform: uppercase; color: var(--sky-soft);
      }
      .msg-b { font-size: 6cqmin; font-weight: 800; line-height: 1.18; }

      /* Portrait or square: the chart takes the width and the readout sits under
         it, rather than squeezing a square chart into a narrow column. */
      @container (max-aspect-ratio: 5 / 4) {
        .wrap { flex-direction: column; }
        .chartbox { flex: 0 0 auto; width: 100%; height: auto; aspect-ratio: 1 / 1; }
        .side { padding: 0 4cqmin 3cqmin; gap: 1.5cqmin; }
        .loc { font-size: 6cqmin; }
        .sub { font-size: 2.6cqmin; }
        .rule { margin: 2cqmin 0; }
        .mblock { gap: 2cqmin; }
        .mglyph { width: 9cqmin; height: 9cqmin; }
        .mphase { font-size: 3.4cqmin; }
        .mnote { font-size: 2.1cqmin; }
        .plist { flex-direction: row; flex-wrap: wrap; gap: 1cqmin 4cqmin; }
        .prow { flex: 0 0 auto; }
        .pnm { font-size: 2.8cqmin; }
        .psym { font-size: 3.4cqmin; }
        .sv { font-size: 3.4cqmin; }
        .foot { display: none; }
      }
    </style>`;

  const root = shadow.querySelector('.sky');
  for (const [k, v] of Object.entries(pal)) root.style.setProperty(`--sky-${k}`, v);

  /* Full bleed: a circle only covers a rectangle if its radius reaches the
     corners, so the horizon has to circumscribe the cell rather than fit inside
     it. That needs the real aspect ratio, which only exists after layout —
     hence measuring here instead of hard-coding a viewBox. The visible sky is
     then the middle of the dome, which is the part worth looking at anyway. */
  if (bleed && !d.error) {
    const svg = shadow.querySelector('.chart');
    const box = root.getBoundingClientRect();
    const w = box.width || 800;
    const h = box.height || 480;
    const k = R_HORIZON / (Math.hypot(w, h) / 2);
    if (svg) {
      svg.setAttribute('viewBox',
        `${(-w / 2 * k).toFixed(1)} ${(-h / 2 * k).toFixed(1)} ${(w * k).toFixed(1)} ${(h * k).toFixed(1)}`);
    }
  }
}
