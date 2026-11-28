/* ONE LOOK FOR THE SMALLER LAWYER PAGES (2026-11-27): Case law, Cause lists and
 * Overseas disputes used to sit in the old teal-wash theme, squeezed into the
 * left 860px. They now take the Agreements page's ground and spacing, with the
 * app's button roles: mint = the main action, teal = open / go somewhere,
 * filled neutral = everything else. Scoped to [data-lx-page]; the theme's
 * variables come from DRAFTING_TOKENS_CSS on the same element. */
export const LX_PAGE_CSS = `[data-lx-page]{flex:1;min-height:0;overflow-y:auto;box-sizing:border-box;padding:26px clamp(16px,3.2vw,40px) 64px;color:var(--ink);font:14px/1.45 "Hanken Grotesk",system-ui,sans-serif;background:radial-gradient(900px 360px at 25% -80px,var(--glow),transparent 70%) no-repeat,var(--bg);display:flex;flex-direction:column;gap:18px;-webkit-font-smoothing:antialiased}
[data-lx-page]>*{flex-shrink:0}
[data-lx-page] *{box-sizing:border-box}
[data-lx-page] .lx-crumbs{font-size:13px;color:var(--faint)}
[data-lx-page] .lx-crumbs b{color:var(--ink);font-weight:600}
[data-lx-page] .lx-head{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-top:-8px}
[data-lx-page] .lx-head h1{margin:0;font:600 36px/1.1 "Literata",Georgia,serif;letter-spacing:-.01em}
[data-lx-page] .lx-head p{margin:6px 0 0;font-size:14px;color:var(--muted)}
[data-lx-page] .lx-head-end{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
[data-lx-page] .lx-pill{height:32px;padding:0 12px;border-radius:999px;display:inline-flex;align-items:center;gap:6px;background:var(--chip-n);font-size:13px;color:var(--muted)}
[data-lx-page] .lx-pill b{color:var(--ink)}
[data-lx-page] .lx-card{border-radius:18px;background:var(--surface);border:1px solid var(--line);box-shadow:var(--shadow-rest)}
[data-lx-page] .lx-pad{padding:18px 20px;display:flex;flex-direction:column;gap:12px}
[data-lx-page] .lx-flush{overflow:hidden}
[data-lx-page] .lx-card-head{display:flex;align-items:center;gap:10px;padding:16px 20px}
[data-lx-page] .lx-card-head b,[data-lx-page] .lx-title{font-size:16px;font-weight:700;color:var(--ink)}
[data-lx-page] .lx-sub{font-size:13.5px;color:var(--muted);margin-top:2px}
[data-lx-page] .lx-count{height:22px;min-width:22px;padding:0 7px;border-radius:999px;background:var(--chip-n);color:var(--muted);font-size:12px;font-weight:800;display:inline-grid;place-items:center}
[data-lx-page] .lx-cols{display:grid;gap:14px;padding:11px 20px;background:var(--surface-2);font-size:11.5px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--faint)}
[data-lx-page] .lx-row{display:grid;gap:14px;align-items:center;padding:13px 20px;border-top:1px solid var(--line)}
[data-lx-page] .lx-empty{display:flex;flex-direction:column;align-items:center;gap:10px;padding:48px 32px;text-align:center}
[data-lx-page] .lx-empty b{font-size:17px}
[data-lx-page] .lx-empty span.t{max-width:520px;font-size:14px;color:var(--muted)}
[data-lx-page] .lx-empty-row{display:flex;align-items:center;gap:16px;padding:24px 20px;border-top:1px solid var(--line)}
[data-lx-page] .lx-tile{width:48px;height:48px;flex:none;border-radius:14px;display:grid;place-items:center;background:color-mix(in srgb,var(--teal-ink) 14%,transparent);color:var(--teal-ink)}
[data-lx-page] .lx-btn{height:40px;padding:0 18px;border-radius:999px;border:1px solid transparent;display:inline-flex;align-items:center;justify-content:center;gap:8px;font:inherit;font-size:13.5px;font-weight:700;white-space:nowrap;cursor:pointer;text-decoration:none;transition:filter .15s,background .15s}
[data-lx-page] .lx-btn:hover:not(:disabled){filter:brightness(1.06)}
[data-lx-page] .lx-btn:disabled{opacity:.5;cursor:not-allowed}
[data-lx-page] .lx-btn.sm{height:34px;padding:0 14px;font-size:13px}
[data-lx-page] .lx-btn.lg{height:48px;padding:0 26px;font-size:14.5px}
[data-lx-page] .lx-btn.mint{border:0;background:linear-gradient(135deg,#3EE0A1,#2EC4D6);color:#04212A}
[data-lx-page] .lx-btn.teal{border:0;background:linear-gradient(180deg,#8AE7F2 0%,#5BCFE2 55%,#3FBFD6 100%);color:#04212A}
[data-lx-page] .lx-btn.fill{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.12);color:var(--ink)}
[data-lx-page] .lx-btn.danger{background:var(--danger-soft);border-color:color-mix(in srgb,var(--danger) 45%,transparent);color:var(--danger)}
[data-lx-page][data-mode="light"] .lx-btn.fill{background:var(--chip-n);border-color:var(--line)}
[data-lx-page] .lx-field{display:flex;flex-direction:column;gap:6px}
[data-lx-page] .lx-field>span{font-size:13px;font-weight:700;color:var(--muted)}
[data-lx-page] .lx-field>span i{font-style:normal;font-weight:500;color:var(--faint)}
[data-lx-page] .lx-input{height:44px;width:100%;padding:0 14px;border-radius:12px;border:1px solid var(--line-strong);background:var(--input);color:var(--ink);font:inherit;font-size:14px;outline:none}
[data-lx-page] .lx-input:focus,[data-lx-page] .lx-search:focus-within{border-color:var(--focus);box-shadow:0 0 0 3px var(--brand-soft)}
[data-lx-page] .lx-input::placeholder,[data-lx-page] .lx-search input::placeholder{color:var(--faint)}
[data-lx-page] textarea.lx-input{height:auto;padding:14px 16px;resize:vertical;line-height:1.6}
[data-lx-page] .lx-search{flex:1;min-width:0;display:flex;align-items:center;gap:10px;height:38px;padding:0 14px;border-radius:12px;background:var(--input);border:1px solid var(--line-strong);color:var(--faint)}
[data-lx-page] .lx-search input{flex:1;min-width:0;border:0;outline:none;background:transparent;color:var(--ink);font:inherit;font-size:13.5px}
[data-lx-page] .lx-seg{display:flex;gap:4px;padding:4px;border-radius:999px;background:var(--surface-2);width:max-content}
[data-lx-page] .lx-seg button{height:34px;padding:0 16px;border-radius:999px;border:0;background:transparent;color:var(--ink);font:inherit;font-size:13.5px;font-weight:700;cursor:pointer}
[data-lx-page] .lx-seg button[aria-selected="true"]{background:#F3F2F4;color:#2A282C}
[data-lx-page] .lx-chip{height:30px;padding:0 12px;border-radius:999px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);color:var(--ink);font:inherit;font-size:12.5px;font-weight:600;cursor:pointer}
[data-lx-page] .lx-chip:hover{border-color:var(--hover-line)}
[data-lx-page] .lx-mono{font-family:"JetBrains Mono",monospace;font-weight:600;color:var(--brand-text)}
[data-lx-page] .lx-tag{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 10px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap;color:var(--brand-text);background:color-mix(in srgb,var(--brand-text) 13%,transparent)}
[data-lx-page] .lx-tag.gold{color:var(--gold);background:color-mix(in srgb,var(--gold) 14%,transparent)}
[data-lx-page] .lx-tag.teal{color:var(--teal-ink);background:color-mix(in srgb,var(--teal-ink) 14%,transparent)}
[data-lx-page] .lx-tag.muted{color:var(--muted);background:var(--chip-n)}
[data-lx-page] .lx-split{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:18px;align-items:start}
[data-lx-page] .lx-col{display:flex;flex-direction:column;gap:18px;min-width:0}
[data-lx-page] .lx-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
[data-lx-page] .lx-btn.teal-tint{border:1px solid color-mix(in srgb,var(--teal-ink) 45%,transparent);background:color-mix(in srgb,var(--teal-ink) 14%,transparent);color:var(--teal-ink)}
[data-lx-page] .lx-input.sm{height:40px;border-radius:10px;font-size:13.5px;padding:0 12px}
[data-lx-page] .lx-cols.light{background:transparent;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:9px 18px}
[data-lx-page] .lx-watch{display:flex;align-items:center;gap:10px;padding:9px 10px 9px 12px;border-radius:12px;background:var(--surface-2)}
[data-lx-page]:not([data-mode="light"]) .lx-watch{background:#24474F}
[data-lx-page] .lx-toast{position:fixed;bottom:24px;right:24px;background:var(--surface);border:1px solid var(--line);color:var(--ink);padding:10px 16px;border-radius:12px;font-size:13px;z-index:100}`;
