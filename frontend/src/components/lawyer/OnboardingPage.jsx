import { useState, useEffect, useRef } from "react";
import { getMe, updateMe, updateLawyerProfile, listMyKycDocuments, uploadKycDocument } from "@/lib/api.js";
import { toPkPhone } from "@/lib/phone.js";

// localStorage cache ONLY — never the source of truth. See isLawyerOnboarded.
export const ONBOARDED_KEY = "lawyer_onboarded";

/**
 * Has this lawyer completed onboarding? Answered from the SERVER's copy of the
 * profile, not from localStorage.
 *
 * This gate used to read localStorage alone, and the key was written only when
 * the lawyer clicked one specific button on the final wizard screen. So a lawyer
 * whose profile was fully saved server-side — but who cleared site data, switched
 * browser or device, or simply navigated away before clicking that button — was
 * pushed back into onboarding on every visit, forever, with every lawyer route
 * (Drafter, Payments, Cause List, Case Law) redirecting there. The data was safe;
 * the gate just never asked the server.
 *
 * Completeness = the two fields the platform actually needs to function: the bar
 * number (identity/verification) and at least one specialization (client matching).
 */
export function isLawyerOnboarded(me) {
  const profile = me?.lawyer_profile;
  return Boolean(profile?.bar_number && profile?.specializations?.length);
}

// Mirrors LawyerProfileUpdate.bar_number (backend/app/schemas/user.py): 4–64
// chars, alphanumeric at both ends. Checked here so Step 1 cannot be passed with
// a value the server will 422 — or with a blank that it silently drops, which
// finishes the wizard into a profile isLawyerOnboarded then rejects.
const BAR_NUMBER_RE = /^[A-Za-z0-9][A-Za-z0-9\-/ .]*[A-Za-z0-9]$/;
export function stepOneProblem({ license, specs }) {
  const bar = (license || "").trim();
  if (bar.length < 4 || bar.length > 64 || !BAR_NUMBER_RE.test(bar)) {
    return "Enter your bar license number (at least 4 letters or digits, e.g. PBC/12345/2019).";
  }
  if (!specs?.length) return "Select at least one specialization.";
  return null;
}

// ─── Styles ───────────────────────────────────────────────────────────────────
// Same tokens as the auth pages (components/auth/AuthShell.jsx), which are the
// refined client theme. The mode follows the lawyer app's own toggle (t.mode).
const CSS = `@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700&family=Literata:opsz,wght@7..72,500;7..72,600&display=swap');
.aai-ob{--bg:#0B1B1F;--card:#183840;--input:#16323A;--line:rgba(150,215,220,.11);--line-strong:rgba(150,215,220,.22);
  --ink:#F1F5F6;--muted:#BFCACC;--faint:#A7B6BA;--brand:linear-gradient(135deg,#3EE0A1,#2EC4D6);--on-brand:#04212A;--brand-text:#5EE6B0;
  --brand-soft:rgba(62,224,161,.13);--focus:rgba(62,224,161,.28);--danger:#FF9090;--danger-soft:rgba(255,120,120,.10);--warn:#F2C35B;--warn-soft:rgba(242,195,91,.13);
  --shadow:0 1px 0 rgba(255,255,255,.05) inset,0 20px 36px -18px rgba(0,0,0,.7);
  --body:'Hanken Grotesk',system-ui,-apple-system,'Segoe UI',sans-serif;--display:'Literata',Georgia,serif;
  height:100%;min-height:0;flex:1;background:var(--bg);color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.5;
  display:grid;grid-template-columns:380px minmax(0,1fr);gap:20px;padding:20px;box-sizing:border-box;overflow:hidden}
.aai-ob[data-mode="light"]{--bg:#EEF3F1;--card:#FFFFFF;--input:#FFFFFF;--line:#DFDCE3;--line-strong:#C9C5CE;--ink:#1E1C21;--muted:#5A5660;--faint:#625E68;
  --brand:linear-gradient(135deg,#0E8A5F,#0B7A8C);--on-brand:#FFFFFF;--brand-text:#0E7A55;--brand-soft:rgba(14,138,95,.10);--focus:rgba(14,138,95,.22);
  --danger:#B42318;--danger-soft:rgba(180,35,24,.07);--warn:#8A5A00;--warn-soft:rgba(196,140,20,.12);
  --shadow:0 2px 4px rgba(10,30,40,.04),0 18px 34px -16px rgba(10,40,50,.28)}
:where(.aai-ob) *,:where(.aai-ob) *::before,:where(.aai-ob) *::after{box-sizing:border-box}
:where(.aai-ob) :where(button){font:inherit;color:inherit}
:where(.aai-ob) :focus-visible{outline:2px solid var(--brand-text);outline-offset:2px}
.ob-card{border-radius:28px;background:var(--card);border:1px solid var(--line);box-shadow:var(--shadow)}
.ob-left{display:grid;grid-template-rows:minmax(0,1fr) auto;gap:20px;min-height:0}
.ob-steps{padding:26px 24px;display:grid;grid-template-rows:auto auto 1fr auto;gap:22px;min-height:0;overflow:auto}
.ob-brand{display:flex;align-items:center;gap:12px}
.ob-brand img{width:40px;height:40px;object-fit:contain}
.ob-brand b{font-family:var(--display);font-weight:600;font-size:22px}
.ob-brand em{font-style:normal;color:var(--brand-text)}
.ob-ring{display:flex;gap:14px;align-items:center}
.ob-ring svg{flex:none;color:var(--ink)}
.ob-ring b{display:block;font-size:16px}
.ob-ring small{color:var(--muted);font-size:13px}
.ob-list{display:grid;align-content:start;gap:2px;list-style:none;margin:0;padding:0}
.ob-st{display:grid;grid-template-columns:40px 1fr;gap:12px;align-items:center;padding:10px 12px;border-radius:16px;position:relative}
.ob-st .c{width:40px;height:40px;border-radius:13px;border:1px solid var(--line-strong);display:grid;place-items:center;color:var(--faint)}
.ob-st.on{background:var(--brand-soft)}
.ob-st.on::before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:3px;border-radius:3px;background:var(--brand)}
.ob-st.on .c,.ob-st.done .c{background:var(--brand);border-color:transparent;color:var(--on-brand)}
.ob-st b{display:block;font-size:14.5px}
.ob-st small{font-size:12.5px;color:var(--faint)}
.ob-help{font-size:13px;color:var(--muted);padding:14px;border-radius:16px;border:1px dashed var(--line-strong)}
.ob-help b{display:block;color:var(--ink)}
.ob-pv{overflow:hidden}
.ob-pv .cover{height:76px;background:url('/auth/lahore-high-court.jpg') center 35%/cover no-repeat;position:relative}
.ob-pv .cover::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,transparent,rgba(6,24,27,.45))}
.ob-pv .cap{position:absolute;left:12px;top:10px;z-index:1;color:#F1F5F6;font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;background:rgba(5,20,22,.62);padding:4px 10px;border-radius:999px}
.ob-pv .cred{position:absolute;right:10px;bottom:6px;z-index:1;color:rgba(241,245,246,.8);font-size:9.5px}
.ob-pv .body{padding:0 20px 18px;display:grid;gap:10px}
.ob-pv .top{display:flex;justify-content:space-between;align-items:flex-end}
.ob-av{width:58px;height:58px;margin-top:-29px;border-radius:50%;background:var(--brand);color:var(--on-brand);display:grid;place-items:center;font-weight:700;font-size:18px;border:3px solid var(--card);position:relative;z-index:1}
.ob-pend{font-size:12px;font-weight:700;color:var(--warn);background:var(--warn-soft);padding:4px 10px;border-radius:999px}
.ob-pv b{display:block;font-size:16px}
.ob-pv small{color:var(--muted);font-size:13px}
.ob-tags{display:flex;gap:8px;flex-wrap:wrap;min-height:24px}
.ob-tags span{font-size:12.5px;font-weight:700;padding:4px 10px;border-radius:999px;background:var(--brand-soft);color:var(--brand-text)}
.ob-tags em{font-style:normal;font-size:13px;color:var(--faint)}
.ob-main{display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:20px;padding:30px 36px 24px;min-height:0;overflow:hidden}
.ob-eyebrow{font-size:12.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--brand-text)}
.ob-main h1{font-family:var(--display);font-weight:600;font-size:clamp(26px,2.4vw,34px);line-height:1.12;letter-spacing:-.015em;margin:6px 0 6px}
.ob-main .lead{margin:0;color:var(--muted);max-width:66ch}
.ob-body{overflow:auto;min-height:0;padding:2px 4px 6px 2px}
.ob-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-content:start}
.ob-full{grid-column:1/-1}
.ob-fl{display:grid;gap:8px}
.ob-fl>label,.ob-lab{font-size:13.5px;font-weight:600;display:flex;justify-content:space-between;gap:12px}
.ob-fl>label span,.ob-lab span{font-weight:500;color:var(--faint)}
.ob-pill{height:50px;border-radius:999px;background:var(--input);border:1px solid var(--line-strong);display:flex;align-items:center;overflow:hidden;transition:border-color .15s,box-shadow .15s}
.ob-pill:focus-within{border-color:var(--brand-text);box-shadow:0 0 0 4px var(--focus)}
.ob-pill .ic{width:54px;height:100%;display:grid;place-items:center;color:var(--faint);border-right:1px solid var(--line-strong);flex:none;font-weight:700;font-size:14px}
.ob-pill input{all:unset;flex:1;min-width:0;height:100%;padding:0 18px;font:inherit;font-size:15px;color:var(--ink)}
.ob-pill input::placeholder{color:var(--faint)}
.ob-area{all:unset;box-sizing:border-box;display:block;width:100%;min-height:86px;border-radius:18px;background:var(--input);border:1px solid var(--line-strong);padding:12px 16px;font:inherit;font-size:15px;color:var(--ink);white-space:pre-wrap}
.ob-area:focus{border-color:var(--brand-text);box-shadow:0 0 0 4px var(--focus)}
.ob-hint{font-size:13px;color:var(--faint);display:flex;gap:6px;align-items:center}
.ob-tiles{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.ob-tile{all:unset;box-sizing:border-box;cursor:pointer;border:1px solid var(--line-strong);border-radius:18px;padding:13px 16px;display:grid;grid-template-columns:1fr auto;gap:2px 10px;background:var(--input);text-align:left}
.ob-tile .t{font-size:15px;font-weight:700}
.ob-tile small{grid-column:1;font-size:12.5px;color:var(--muted)}
.ob-tile .bx{grid-row:1/3;grid-column:2;align-self:center;width:20px;height:20px;border-radius:6px;border:1.5px solid var(--line-strong);display:grid;place-items:center;color:var(--on-brand)}
.ob-tile[aria-pressed="true"]{border-color:var(--brand-text);box-shadow:0 0 0 1px var(--brand-text) inset;background:var(--brand-soft)}
.ob-tile[aria-pressed="true"] .bx{background:var(--brand);border-color:transparent}
.ob-up{display:grid;grid-template-columns:48px 1fr auto;gap:16px;align-items:center;padding:16px 18px;border-radius:20px;border:1.5px dashed var(--line-strong)}
.ob-up.done{border-style:solid;border-color:var(--line);background:var(--brand-soft)}
.ob-up .ic{width:48px;height:48px;border-radius:14px;background:var(--brand-soft);color:var(--brand-text);display:grid;place-items:center;overflow:hidden}
.ob-up .ic img{width:100%;height:100%;object-fit:cover}
.ob-up b{display:block;font-size:15px}
.ob-up small{font-size:13px;color:var(--faint);display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ob-up small.ok{color:var(--brand-text);font-weight:600}
.ob-up small.bad{color:var(--danger);font-weight:600;white-space:normal}
.ob-up .acts{display:flex;gap:8px}
.ob-stack{display:grid;gap:12px}
.ob-note{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:16px;background:var(--brand-soft);font-size:13.5px;line-height:1.5}
.ob-note.warn{background:var(--warn-soft)}
.ob-note svg{flex:none;margin-top:2px;color:var(--brand-text)}
.ob-note.warn svg{color:var(--warn)}
.ob-fee{font-family:var(--display);font-size:28px;font-weight:600}
.ob-range{width:100%;accent-color:#2EC4D6}
.ob-foot{display:flex;justify-content:space-between;align-items:center;gap:14px;padding-top:18px;border-top:1px solid var(--line)}
.ob-foot .r{display:flex;align-items:center;gap:14px;flex-wrap:wrap;justify-content:flex-end}
.ob-btn{all:unset;box-sizing:border-box;cursor:pointer;height:50px;padding:0 26px;border-radius:999px;background:var(--brand);color:var(--on-brand);font-weight:700;font-size:15.5px;display:inline-flex;align-items:center;justify-content:center;gap:10px;box-shadow:0 14px 28px -14px rgba(46,196,214,.65);white-space:nowrap}
.ob-btn:hover{filter:brightness(1.06)}
.ob-btn[disabled]{opacity:.65;cursor:progress}
.ob-btn.sm{height:40px;padding:0 18px;font-size:14px}
.ob-ghost{all:unset;box-sizing:border-box;cursor:pointer;height:50px;padding:0 22px;border-radius:999px;border:1px solid var(--line-strong);display:inline-flex;align-items:center;gap:8px;font-weight:600}
.ob-ghost.sm{height:40px;padding:0 16px;font-size:14px}
.ob-ghost[disabled]{opacity:.45;cursor:not-allowed}
.ob-link{all:unset;cursor:pointer;color:var(--brand-text);font-weight:700}
.ob-err{color:var(--danger);font-weight:600;font-size:13.5px;max-width:52ch}
.ob-tl{display:grid;gap:0;list-style:none;margin:0;padding:0}
.ob-tl li{display:grid;grid-template-columns:38px 1fr;gap:16px;padding-bottom:24px;position:relative}
.ob-tl li:not(:last-child)::after{content:"";position:absolute;left:18px;top:40px;bottom:4px;width:2px;background:var(--line-strong)}
.ob-tl .tc{width:38px;height:38px;border-radius:50%;border:1.5px solid var(--line-strong);display:grid;place-items:center;font-weight:700;color:var(--faint);background:var(--card);position:relative;z-index:1}
.ob-tl .ok .tc{background:var(--brand);border-color:transparent;color:var(--on-brand)}
.ob-tl .now .tc{border-color:var(--brand-text);color:var(--brand-text);box-shadow:0 0 0 5px var(--focus)}
.ob-tl b{display:block;font-size:16.5px}
.ob-tl small{font-size:14px;color:var(--muted)}
.ob-spin{width:16px;height:16px;border-radius:50%;border:2.5px solid currentColor;border-right-color:transparent;animation:ob-sp .8s linear infinite}
@keyframes ob-sp{to{transform:rotate(360deg)}}
/* Compact layout (2026-10-19): narrower sidebar so all four steps show, smaller
   preview, 42px fields and footer button. Overrides the sizes above. */
.aai-ob{grid-template-columns:300px minmax(0,1fr);gap:16px;padding:16px}
.ob-left{gap:16px}
.ob-card{border-radius:24px}
.ob-steps{padding:18px 16px;gap:14px}
.ob-help{font-size:12px;padding:10px 12px;border-radius:12px;align-self:end}
.ob-brand img{width:32px;height:32px}
.ob-brand b{font-size:19px}
.ob-ring svg{width:52px;height:52px}
.ob-ring b{font-size:15px}
.ob-ring small{font-size:12px}
.ob-st{grid-template-columns:32px 1fr;gap:10px;padding:7px 10px;border-radius:13px}
.ob-st .c{width:32px;height:32px;border-radius:10px}
.ob-st .c svg{width:16px;height:16px}
.ob-st.on::before{top:8px;bottom:8px}
.ob-st b{font-size:13.5px}
.ob-st small{font-size:11.5px}
.ob-pv .cover{height:54px}
.ob-pv .cap{font-size:9.5px;padding:3px 8px;top:8px;left:10px}
.ob-pv .cred{font-size:8.5px;bottom:4px}
.ob-pv .body{padding:0 16px 14px;gap:6px}
.ob-av{width:44px;height:44px;margin-top:-22px;font-size:15px;border-width:2px}
.ob-pend{font-size:11px;padding:3px 8px}
.ob-pv b{font-size:14.5px}
.ob-pv small{font-size:12px}
.ob-tags{min-height:20px;gap:6px}
.ob-tags span{font-size:11.5px;padding:3px 8px}
.ob-tags em{font-size:12px}
.ob-main{gap:14px;padding:22px 28px 16px}
.ob-eyebrow{font-size:11.5px}
.ob-main h1{font-size:clamp(22px,2vw,28px);margin:4px 0}
.ob-main .lead{font-size:14px;max-width:none}
.ob-grid{gap:14px}
.ob-fl{gap:6px}
.ob-fl>label,.ob-lab{font-size:13px}
.ob-pill{height:42px}
.ob-pill .ic{width:44px}
.ob-pill .ic svg{width:16px;height:16px}
.ob-pill input{padding:0 14px;font-size:14px}
.ob-area{min-height:70px;border-radius:14px;padding:10px 14px;font-size:14px}
.ob-hint{font-size:12.5px}
.ob-tiles{gap:10px}
.ob-tile{padding:10px 14px;border-radius:14px}
.ob-tile .t{font-size:14px}
.ob-tile small{font-size:12px}
.ob-up{grid-template-columns:40px 1fr auto;gap:12px;padding:12px 14px;border-radius:16px}
.ob-up .ic{width:40px;height:40px;border-radius:12px}
.ob-up b{font-size:14px}
.ob-up small{font-size:12px}
.ob-note{padding:10px 12px;font-size:13px;border-radius:14px}
.ob-fee{font-size:24px}
.ob-foot{padding-top:12px;gap:12px}
.ob-btn{height:42px;padding:0 20px;font-size:14.5px}
.ob-ghost{height:42px;padding:0 18px;font-size:14px}
.ob-btn.sm,.ob-ghost.sm{height:36px}
.ob-tl li{grid-template-columns:32px 1fr;gap:12px;padding-bottom:18px}
.ob-tl li:not(:last-child)::after{left:15px;top:34px}
.ob-tl .tc{width:32px;height:32px}
.ob-tl b{font-size:15px}
.ob-tl small{font-size:13px}
.ob-pvwrap{position:relative}
.ob-chip{all:unset;box-sizing:border-box;cursor:pointer;width:100%;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:10px;padding:10px 14px;border-radius:18px;background:var(--card);border:1px solid var(--line);box-shadow:var(--shadow)}
.ob-chip:hover{border-color:var(--line-strong)}
.ob-chip .who b{display:block;font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ob-chip .who .st{font-size:11.5px;font-weight:700;color:var(--warn)}
.ob-chip .lk{font-size:12px;font-weight:700;color:var(--brand-text)}
.ob-av.sm{width:36px;height:36px;margin-top:0;font-size:13px;border:0}
.ob-pop{position:absolute;left:0;right:0;bottom:calc(100% + 10px);z-index:5;box-shadow:0 24px 50px -16px rgba(0,0,0,.7)}
/* Step icons without the tile around them (2026-10-19). */
.ob-st .c{border:0;background:none!important;border-radius:0;color:var(--faint)}
.ob-st.on .c,.ob-st.done .c{color:var(--brand-text)}
.ob-st .c svg{width:19px;height:19px}
/* Last step (2026-10-19). */
.ob-done{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(260px,.85fr);gap:22px;align-items:start}
.ob-sub{font-size:11.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin:0 0 10px}
.ob-next{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.ob-next li{display:grid;grid-template-columns:34px 1fr auto;gap:12px;align-items:center;padding:12px 14px;border-radius:16px;background:var(--input);border:1px solid var(--line)}
.ob-next .i{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:14px;color:var(--faint);border:1.5px solid var(--line-strong)}
.ob-next .ok .i{background:var(--brand);border-color:transparent;color:var(--on-brand)}
.ob-next .now{border-color:color-mix(in srgb,var(--brand-text) 55%,transparent);background:var(--brand-soft)}
.ob-next .now .i{border-color:var(--brand-text);color:var(--brand-text)}
.ob-next b{display:block;font-size:14.5px}
.ob-next small{font-size:12.5px;color:var(--muted)}
.ob-next .tag{font-size:10.5px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--brand-text)}
.ob-pub{border-radius:20px;background:var(--input);border:1px solid var(--line);overflow:hidden}
.ob-pub .cover{height:64px;background:url('/auth/lahore-high-court.jpg') center 35%/cover no-repeat}
.ob-pub .ob-av{border-color:var(--input)}
.ob-bar{font-size:12.5px;color:var(--muted)}
.ob-bar b{display:inline;font-size:12.5px;color:var(--ink)}
.ob-pend.ok{color:var(--brand-text);background:var(--brand-soft)}
.ob-chip .who .st.ok{color:var(--brand-text)}
@media (max-width:1300px){.ob-done{grid-template-columns:1fr}}
/* Glass (2026-10-19): the court photo behind the page, frosted cards over it,
   translucent fields inside. Tints keep text at full contrast. */
.aai-ob{background:radial-gradient(700px 500px at 85% 0%,rgba(62,224,161,.10),transparent 60%),radial-gradient(600px 500px at 0% 100%,rgba(46,196,214,.08),transparent 60%),linear-gradient(160deg,rgba(7,28,32,.66),rgba(5,18,22,.84)),url('/auth/lahore-high-court.jpg') center 30%/cover no-repeat}
.ob-card,.ob-chip{background:linear-gradient(160deg,rgba(255,255,255,.09),rgba(255,255,255,.02) 45%,rgba(255,255,255,.04)),rgba(14,44,50,.55);-webkit-backdrop-filter:blur(22px) saturate(140%);backdrop-filter:blur(22px) saturate(140%);border:1px solid rgba(255,255,255,.13);box-shadow:inset 0 1px 0 rgba(255,255,255,.16),0 30px 60px -28px rgba(0,0,0,.75)}
.ob-pop{background:linear-gradient(160deg,rgba(255,255,255,.10),rgba(255,255,255,.03)),rgba(12,38,44,.86)}
.ob-pill,.ob-area,.ob-tile,.ob-up,.ob-next li,.ob-pub{background:rgba(4,20,24,.42);border-color:rgba(255,255,255,.12)}
.ob-pill .ic{border-right-color:rgba(255,255,255,.10)}
.ob-tile[aria-pressed="true"],.ob-next .now,.ob-up.done{background:rgba(62,224,161,.14)}
.ob-st.on{background:rgba(62,224,161,.12)}
.ob-help{border-color:rgba(255,255,255,.14)}
.ob-av{border-color:rgba(14,44,50,.9)}
.aai-ob[data-mode="light"]{background:radial-gradient(700px 500px at 85% 0%,rgba(14,138,95,.10),transparent 60%),linear-gradient(160deg,rgba(238,243,241,.70),rgba(232,240,238,.86)),url('/auth/lahore-high-court.jpg') center 30%/cover no-repeat}
.aai-ob[data-mode="light"] .ob-card,.aai-ob[data-mode="light"] .ob-chip{background:linear-gradient(160deg,rgba(255,255,255,.82),rgba(255,255,255,.60));border-color:rgba(255,255,255,.85);box-shadow:inset 0 1px 0 #fff,0 30px 60px -28px rgba(10,40,50,.35)}
.aai-ob[data-mode="light"] .ob-pop{background:rgba(255,255,255,.94)}
.aai-ob[data-mode="light"] .ob-pill,.aai-ob[data-mode="light"] .ob-area,.aai-ob[data-mode="light"] .ob-tile,.aai-ob[data-mode="light"] .ob-up,.aai-ob[data-mode="light"] .ob-next li,.aai-ob[data-mode="light"] .ob-pub{background:rgba(255,255,255,.72);border-color:rgba(10,40,50,.12)}
.aai-ob[data-mode="light"] .ob-pill .ic{border-right-color:rgba(10,40,50,.10)}
.aai-ob[data-mode="light"] .ob-tile[aria-pressed="true"],.aai-ob[data-mode="light"] .ob-next .now,.aai-ob[data-mode="light"] .ob-up.done{background:rgba(14,138,95,.10)}
.aai-ob[data-mode="light"] .ob-av{border-color:#fff}
@media (max-width:1100px){.aai-ob{grid-template-columns:1fr;overflow:auto;height:auto}.ob-left{display:none}.ob-main{overflow:visible}.ob-body{overflow:visible}}
@media (max-width:700px){.ob-grid,.ob-tiles{grid-template-columns:1fr}.ob-main{padding:22px 18px}}
@media (prefers-reduced-motion:reduce){.aai-ob *{animation:none!important;transition:none!important}}
`;

// ─── Icons (currentColor) ─────────────────────────────────────────────────────
const Svg = ({ s = 18, w = 2, children }) => (
  <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
);
const Ic = {
  user: (s) => <Svg s={s}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></Svg>,
  shield: (s) => <Svg s={s}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></Svg>,
  pin: (s) => <Svg s={s}><path d="M12 22s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12z" /><circle cx="12" cy="10" r="2.5" /></Svg>,
  clock: (s) => <Svg s={s}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Svg>,
  doc: (s) => <Svg s={s}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></Svg>,
  cap: (s) => <Svg s={s}><path d="M2 10 12 5l10 5-10 5z" /><path d="M6 12v5c3 2 9 2 12 0v-5" /></Svg>,
  award: (s) => <Svg s={s}><circle cx="12" cy="9" r="6" /><path d="m8.5 14.5-1.5 7 5-3 5 3-1.5-7" /></Svg>,
  camera: (s) => <Svg s={s}><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" /><circle cx="12" cy="13" r="4" /></Svg>,
  upload: (s) => <Svg s={s}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" /></Svg>,
  info: (s = 16) => <Svg s={s}><circle cx="12" cy="12" r="10" /><path d="M12 16v-5M12 8h.01" /></Svg>,
  check: (s = 14) => <Svg s={s} w={3}><path d="m5 12 4.5 4.5L19 7" /></Svg>,
  send: (s) => <Svg s={s}><path d="m22 2-7 20-4-9-9-4z" /><path d="M22 2 11 13" /></Svg>,
  arrow: (s = 17) => <Svg s={s} w={2.4}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>,
  back: (s = 16) => <Svg s={s} w={2.4}><path d="M19 12H5M11 18l-6-6 6-6" /></Svg>,
};

// ─── Steps / data ─────────────────────────────────────────────────────────────
const STEPS = [
  { label: "Professional profile", sub: "Name, license, practice areas", icon: Ic.user },
  { label: "Credentials and photo", sub: "Optional · never shown to clients", icon: Ic.shield },
  { label: "Office and fees", sub: "City, address, consultation fee", icon: Ic.pin },
  { label: "Finished", sub: "Your profile goes live", icon: Ic.send },
];

// Labels map to the platform's case types — matching runs on these values
const SPECS_CORE = [
  ["Civil Litigation", "Property, contracts, recovery suits"],
  ["Criminal", "Bail, trials, FIR matters"],
  ["Family", "Divorce, khula, custody, maintenance"],
  ["Constitutional", "Writ petitions, fundamental rights"],
];
const SPEC_VALUE = { "Civil Litigation": "civil", Criminal: "criminal", Family: "family", Constitutional: "constitutional" };

const EMPTY_FORM = { name: "", exp: "", license: "", specLabels: [], address: "", city: "", phone: "", minFee: 5000, bio: "" };

const initialsOf = (name) => (name || "").replace(/^adv\.?\s*/i, "").trim().split(/\s+/).filter(Boolean)
  .slice(0, 2).map(w => w[0].toUpperCase()).join("") || "?";

// ─── Atoms ────────────────────────────────────────────────────────────────────
function Pill({ icon, prefix, value, onChange, ...input }) {
  return (
    <div className="ob-pill">
      <span className="ic">{prefix || icon}</span>
      <input value={value ?? ""} onChange={e => onChange(e.target.value)} {...input} />
    </div>
  );
}

function Ring({ step, submitted, live }) {
  const pct = submitted ? 100 : [25, 50, 75, 100][step];
  const C = 2 * Math.PI * 26;
  return (
    <div className="ob-ring">
      <svg width="62" height="62" viewBox="0 0 62 62" aria-hidden="true">
        <defs><linearGradient id="ob-rg"><stop offset="0" stopColor="#3EE0A1" /><stop offset="1" stopColor="#2EC4D6" /></linearGradient></defs>
        <circle cx="31" cy="31" r="26" fill="none" stroke="var(--line-strong)" strokeWidth="6" />
        <circle cx="31" cy="31" r="26" fill="none" stroke="url(#ob-rg)" strokeWidth="6" strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * C} ${C}`} transform="rotate(-90 31 31)" />
        <text x="31" y="36" textAnchor="middle" fontSize="15" fontWeight="700" fill="currentColor">{pct}%</text>
      </svg>
      <span>
        <b>{submitted ? "Profile complete" : "Profile setup"}</b>
        <small>{submitted ? (live ? "Clients can find you" : "Waiting for admin approval") : `Step ${step + 1} of ${STEPS.length} · about 5 minutes`}</small>
      </span>
    </div>
  );
}

function StepsCard({ step, submitted, live }) {
  return (
    <nav className="ob-card ob-steps" aria-label="Onboarding steps">
      <div className="ob-brand"><img src="/logo.png" alt="" /><b>Attorney<em>.AI</em></b></div>
      <Ring step={step} submitted={submitted} live={live} />
      <ol className="ob-list">
        {STEPS.map((s, i) => {
          const done = submitted || i < step;
          const on = !submitted && i === step;
          return (
            <li key={s.label} className={`ob-st${on ? " on" : ""}${done ? " done" : ""}`} aria-current={on ? "step" : undefined}>
              <span className="c">{done ? Ic.check(16) : s.icon(19)}</span>
              <span><b>{s.label}</b><small>{s.sub}</small></span>
            </li>
          );
        })}
      </ol>
      <div className="ob-help"><b>Need help?</b>You can go back to any finished step and change it before you submit.</div>
    </nav>
  );
}

// A small profile chip at the foot of the sidebar (2026-10-19); clicking it
// opens the full "What clients will see" card above it.
function PreviewCard({ form, step, submitted, live }) {
  const [open, setOpen] = useState(false);
  const specs = form.specLabels;
  const showFee = step >= 2 && form.minFee > 0;
  // "Registered", never "verified": nobody checks the Bar license
  // (LAWYER_AUTO_APPROVE). `live` comes from the saved profile.
  const status = submitted && live ? "Registered lawyer" : submitted ? "Awaiting approval" : "Not listed yet";
  const name = form.name.trim() || "Your name";
  return (
    <div className="ob-pvwrap">
      {open && (
        <aside className="ob-card ob-pv ob-pop" aria-label="What clients will see">
          <div className="cover"><span className="cap">What clients will see</span><span className="cred">Photo: MariyamAftab, CC BY-SA 4.0</span></div>
          <div className="body">
            <div className="top">
              {/* Initials, not the uploaded photo: the photo is private and never shown to clients. */}
              <span className="ob-av">{initialsOf(form.name)}</span>
              <span className={`ob-pend${submitted && live ? " ok" : ""}`}>{status}</span>
            </div>
            <div>
              <b>{name}</b>
              <small>
                {form.exp ? `${form.exp} years` : "Experience not set"} · {form.city.trim() || "City not set"}
                {showFee ? ` · From PKR ${Number(form.minFee).toLocaleString("en-US")}` : ""}
              </small>
            </div>
            <div className="ob-tags">{specs.length ? specs.map(s => <span key={s}>{s}</span>) : <em>No practice areas yet</em>}</div>
          </div>
        </aside>
      )}
      <button type="button" className="ob-card ob-chip" aria-expanded={open} onClick={() => setOpen(o => !o)}
        title={open ? "Hide the preview" : "See how clients will see your profile"}>
        <span className="ob-av sm">{initialsOf(form.name)}</span>
        <span className="who"><b>{name}</b><small className={`st${submitted && live ? " ok" : ""}`}>{status}</small></span>
        <span className="lk">{open ? "Hide" : "Preview"}</span>
      </button>
    </div>
  );
}

function StepFrame({ eyebrow, title, lead, children, foot }) {
  return (
    <section className="ob-card ob-main">
      <header>
        <div className="ob-eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p className="lead">{lead}</p>
      </header>
      <div className="ob-body">{children}</div>
      <footer className="ob-foot">{foot}</footer>
    </section>
  );
}

// ─── Step 1: Professional Profile ─────────────────────────────────────────────
function StepProfessional({ form, set, onNext }) {
  const [problem, setProblem] = useState(null);

  useEffect(() => {
    getMe().then(({ data }) => {
      if (data?.full_name) set("name", prev => prev || data.full_name);
      if (data?.lawyer_profile?.bar_number) set("license", prev => prev || data.lawyer_profile.bar_number);
    }).catch(() => { });
  }, []);

  const cont = () => {
    const specs = form.specLabels.map(s => SPEC_VALUE[s]).filter(Boolean);
    const p = stepOneProblem({ license: form.license, specs });
    setProblem(p);
    if (!p) onNext();
  };
  const togCore = (s) => set("specLabels", p => p.includes(s) ? p.filter(x => x !== s) : p.length < 3 ? [...p, s] : p);
  const full = form.specLabels.length >= 3;

  return (
    <StepFrame eyebrow="Step 1 of 4" title="Your professional profile"
      lead="Clients are matched to you using these details. You can change them later from Settings."
      foot={<>
        <span className="ob-hint">Bar license and at least one practice area are required</span>
        <div className="r">
          {/* No Skip on this step, deliberately. It collects the bar number and
              specializations — the two fields onboarding is CONSIDERED COMPLETE by
              (see isLawyerOnboarded). A "Skip" here would let a lawyer finish the
              wizard with a profile the gate then rejects, dropping them straight
              back into onboarding. Step 2 (uploads) is genuinely optional. */}
          {problem && <span role="alert" className="ob-err">{problem}</span>}
          <button type="button" className="ob-btn" onClick={cont}>Continue {Ic.arrow()}</button>
        </div>
      </>}>
      <div className="ob-grid">
        <div className="ob-fl">
          <label htmlFor="ob-name">Full name</label>
          <Pill icon={Ic.user()} id="ob-name" placeholder="Adv. Ahmad Khan" autoComplete="name"
            value={form.name} onChange={v => set("name", v)} />
        </div>
        <div className="ob-fl">
          <label htmlFor="ob-exp">Years of experience</label>
          <Pill icon={Ic.clock()} id="ob-exp" type="number" min="0" max="60" placeholder="e.g. 8"
            value={form.exp} onChange={v => set("exp", v)} />
        </div>
        <div className="ob-fl ob-full">
          <label htmlFor="ob-bar">Bar license number</label>
          <Pill icon={Ic.shield()} id="ob-bar" placeholder="e.g. PBC/12345/2019"
            value={form.license} onChange={v => set("license", v)} />
          <div className="ob-hint">{Ic.info()}Shown to clients on your profile. Attorney.AI does not check it with the Bar Council.</div>
        </div>
        <div className="ob-fl ob-full">
          <div className="ob-lab"><span style={{ color: "var(--ink)", fontWeight: 600 }}>Practice areas</span><span>{form.specLabels.length} of 3 chosen</span></div>
          <div className="ob-tiles" role="group" aria-label="Practice areas">
            {SPECS_CORE.map(([label, sub]) => {
              const on = form.specLabels.includes(label);
              return (
                <button type="button" key={label} className="ob-tile" aria-pressed={on} onClick={() => togCore(label)}>
                  <span className="t">{label}</span><small>{sub}</small>
                  <span className="bx">{on && Ic.check(12)}</span>
                </button>
              );
            })}
          </div>
          <div className="ob-hint">{Ic.info()}{full ? "You can choose up to 3. Remove one to pick another." : "Clients are matched to you by these practice areas."}</div>
        </div>
      </div>
    </StepFrame>
  );
}

// ─── Step 2: Credentials & Photo ──────────────────────────────────────────────
// Real uploads (POST /users/me/kyc/documents). Every file goes up as soon as it
// is chosen; the row then shows what the SERVER holds, or why it refused. The
// step stays optional (Skip), and an admin reviews whatever was sent.
const CRED_ACCEPT = "application/pdf,image/jpeg,image/png";

function UploadRow({ kind, icon, title, hint, doc, busy, issue, onPick, accept = CRED_ACCEPT, preview, extra, doneLabel = "Uploaded" }) {
  const inputRef = useRef();
  return (
    <div className={`ob-up${doc ? " done" : ""}`}>
      <span className="ic">{preview ? <img src={preview} alt="" /> : icon}</span>
      <span style={{ minWidth: 0 }}>
        <b>{title}</b>
        {issue ? <small role="alert" className="bad">{issue}</small>
          : doc ? <small className="ok">{doneLabel} · {doc.filename}</small>
            : <small>{hint}</small>}
      </span>
      <span className="acts">
        <input type="file" ref={inputRef} accept={accept} data-kind={kind} style={{ display: "none" }}
          onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onPick(kind, f); }} />
        {extra}
        <button type="button" className={doc ? "ob-ghost sm" : "ob-btn sm"} disabled={busy}
          onClick={() => !busy && inputRef.current?.click()}>
          {busy ? <><span className="ob-spin" aria-hidden="true" />Uploading…</> : doc ? "Replace" : <>{Ic.upload(16)}Upload</>}
        </button>
      </span>
    </div>
  );
}

function StepCredentials({ onNext, onBack }) {
  const cameraRef = useRef();
  const [docs, setDocs] = useState({});          // kind -> server metadata
  const [busy, setBusy] = useState(null);         // kind being uploaded
  const [issues, setIssues] = useState({});       // kind -> server's reason
  const [photoUrl, setPhotoUrl] = useState(null); // local preview of the uploaded photo
  // A failed read of what was uploaded is not "nothing uploaded".
  const [docsError, setDocsError] = useState(null);

  const loadDocs = () => {
    setDocsError(null);
    listMyKycDocuments().then(({ data, error }) => {
      if (error) { setDocsError(error.message || "Could not load your uploads."); return; }
      setDocs(data || {});
    });
  };
  useEffect(loadDocs, []);
  useEffect(() => () => { if (photoUrl) URL.revokeObjectURL(photoUrl); }, [photoUrl]);

  const pick = async (kind, file) => {
    setBusy(kind);
    setIssues(p => ({ ...p, [kind]: null }));
    const { data, error } = await uploadKycDocument(kind, file);
    setBusy(null);
    if (error || !data?.[kind]) {
      setIssues(p => ({ ...p, [kind]: error?.message || "Upload failed. Please try again." }));
      return;
    }
    setDocs(p => ({ ...p, ...data }));
    if (kind === "photo") setPhotoUrl(URL.createObjectURL(file));
  };

  const credCount = ["bar_certificate", "education", "professional"].filter(k => docs[k]).length;

  return (
    <StepFrame eyebrow="Step 2 of 4" title="Credentials and photo"
      lead="Optional. Keep your certificates on file with us. Files upload as soon as you pick them. Only you and the Attorney.AI admin team can open them; they are not shown to clients."
      foot={<>
        <button type="button" className="ob-ghost" onClick={onBack}>{Ic.back()}Back</button>
        <div className="r">
          {/* Uploads only, so skipping and continuing both advance without data.
              onNext() is called with no argument on purpose: passing the click
              event used to merge its fields into the form payload. */}
          <button type="button" className="ob-link" onClick={() => onNext()}>Skip for now</button>
          <button type="button" className="ob-btn" onClick={() => onNext()}>Continue {Ic.arrow()}</button>
        </div>
      </>}>
      <div className="ob-stack">
        <div className={`ob-note${docsError || credCount === 0 ? " warn" : ""}`}>
          {Ic.info(17)}
          {docsError ? (
            <span role="alert">Couldn&apos;t load your uploads: {docsError}{" "}
              <button type="button" className="ob-link" onClick={loadDocs}>Retry</button></span>
          ) : (
            <span><b>{credCount === 0 ? "No credentials uploaded yet" : `${credCount} of 3 credentials uploaded`}</b>
              {" "}· Optional · PDF, JPG or PNG, up to 5 MB each.</span>
          )}
        </div>
        <input type="file" ref={cameraRef} accept="image/jpeg,image/png" capture="user" data-kind="photo-camera" style={{ display: "none" }}
          onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f) pick("photo", f); }} />
        <UploadRow kind="photo" icon={Ic.camera(22)} title="Your photo" hint="Private · JPG or PNG" doneLabel="Photo uploaded"
          accept="image/jpeg,image/png" preview={photoUrl} doc={docs.photo} busy={busy === "photo"} issue={issues.photo} onPick={pick}
          extra={/* capture="user" opens the front camera on phones; elsewhere it is a file picker. */
            <button type="button" className="ob-ghost sm" disabled={busy === "photo"} onClick={() => cameraRef.current?.click()}>{Ic.camera(16)}Take photo</button>} />
        <UploadRow kind="bar_certificate" icon={Ic.shield(22)} title="Bar Council Certificate" hint="Official bar membership certificate"
          doc={docs.bar_certificate} busy={busy === "bar_certificate"} issue={issues.bar_certificate} onPick={pick} />
        <UploadRow kind="education" icon={Ic.cap(22)} title="Educational credentials" hint="LLB or equivalent law degree"
          doc={docs.education} busy={busy === "education"} issue={issues.education} onPick={pick} />
        <UploadRow kind="professional" icon={Ic.award(22)} title="Professional certificates" hint="Additional certifications or awards · optional"
          doc={docs.professional} busy={busy === "professional"} issue={issues.professional} onPick={pick} />
      </div>
    </StepFrame>
  );
}

// ─── Step 3: Office & Fees ────────────────────────────────────────────────────
function StepOffice({ form, set, onNext, onBack, saving, error }) {
  return (
    <StepFrame eyebrow="Step 3 of 4" title="Office and fees"
      lead="Where clients can meet you, and what a first consultation costs. Working hours are set later in Appointments."
      foot={<>
        <button type="button" className="ob-ghost" onClick={onBack}>{Ic.back()}Back</button>
        <div className="r">
          {error && <span role="alert" className="ob-err">{error}</span>}
          <button type="button" className="ob-btn" disabled={saving} onClick={() => !saving && onNext()}>
            {saving ? <><span className="ob-spin" aria-hidden="true" />Saving…</> : <>Finish profile {Ic.arrow()}</>}
          </button>
        </div>
      </>}>
      <div className="ob-grid">
        <div className="ob-fl">
          <label htmlFor="ob-city">City <span>e.g. Lahore, 54000</span></label>
          <Pill icon={Ic.pin()} id="ob-city" placeholder="Lahore, 54000" autoComplete="address-level2"
            value={form.city} onChange={v => set("city", v)} />
        </div>
        <div className="ob-fl">
          <label htmlFor="ob-phone">Office phone <span>Optional</span></label>
          <Pill prefix="+92" id="ob-phone" type="tel" placeholder="42 1234567" autoComplete="tel-national"
            value={form.phone} onChange={v => set("phone", v)} />
        </div>
        <div className="ob-fl ob-full">
          <label htmlFor="ob-addr">Office address <span>Optional</span></label>
          <Pill icon={Ic.pin()} id="ob-addr" placeholder="e.g. 14 Fane Road, near Lahore High Court" autoComplete="street-address"
            value={form.address} onChange={v => set("address", v)} />
        </div>
        <div className="ob-fl ob-full">
          <div className="ob-lab"><span style={{ color: "var(--ink)", fontWeight: 600 }}>Starting consultation fee</span><span>PKR 0 – 50,000</span></div>
          <div className="ob-fee" aria-live="polite">PKR {Number(form.minFee).toLocaleString("en-US")}</div>
          <input className="ob-range" type="range" min="0" max="50000" step="1000" value={form.minFee}
            aria-label="Starting consultation fee in PKR" onChange={e => set("minFee", +e.target.value)} />
        </div>
        <div className="ob-fl ob-full">
          <label htmlFor="ob-bio">Explain your fees <span>Optional</span></label>
          <textarea id="ob-bio" className="ob-area" rows={3} placeholder="e.g. First consultation includes a review of your documents."
            value={form.bio} onChange={e => set("bio", e.target.value)} />
        </div>
      </div>
    </StepFrame>
  );
}

// ─── Step 4: Submitted ────────────────────────────────────────────────────────
function StepSubmitted({ live, form, onBack, onComplete }) {
  // `live` is what the server saved (lawyer_profile.kyc_verified), not a
  // promise: with LAWYER_AUTO_APPROVE off the account still waits for an admin.
  const next = live
    ? [["ok", "Profile saved", "Your name, Bar license number and practice areas."],
       ["ok", "Listed in the directory", "Clients find you by practice area and city."],
       ["now", "Set your working hours", "In Appointments, so clients can book a time."]]
    : [["ok", "Profile saved", "Your name, Bar license number and practice areas."],
       ["now", "Admin approval", "An admin approves the account."],
       ["", "You go live", "Clients can find you and request consultations."]];
  const specs = form.specLabels;
  return (
    <StepFrame eyebrow="All steps complete" title={live ? "Your profile is live" : "Profile saved"}
      lead={live ? "Clients can now find you in the lawyer directory." : "An admin approves new lawyer accounts before they are listed."}
      foot={<>
        <button type="button" className="ob-ghost" onClick={onBack}>{Ic.back()}Back</button>
        <div className="r">
          <button type="button" className="ob-btn" onClick={onComplete}>Go to my workspace {Ic.arrow()}</button>
        </div>
      </>}>
      {/* Two columns (2026-10-19): what happens next, and the public profile as
          clients will see it, built from what was just saved. */}
      <div className="ob-done">
        <section>
          <div className="ob-sub">What happens next</div>
          <ol className="ob-next">
            {next.map(([state, title, text], i) => (
              <li key={title} className={state}>
                <span className="i">{state === "ok" ? Ic.check(16) : i + 1}</span>
                <span><b>{title}</b><small>{text}</small></span>
                {state === "now" && <span className="tag">Next</span>}
              </li>
            ))}
          </ol>
        </section>
        <section>
          <div className="ob-sub">Your public profile</div>
          <article className="ob-pv ob-pub">
            <div className="cover" />
            <div className="body">
              <div className="top">
                <span className="ob-av">{initialsOf(form.name)}</span>
                <span className={`ob-pend${live ? " ok" : ""}`}>{live ? "Registered lawyer" : "Awaiting approval"}</span>
              </div>
              <div>
                <b>{form.name.trim() || "Your name"}</b>
                <small>
                  {form.exp ? `${form.exp} years` : "Experience not set"} · {form.city.trim() || "City not set"}
                  {form.minFee > 0 ? ` · From PKR ${Number(form.minFee).toLocaleString("en-US")}` : ""}
                </small>
              </div>
              {form.license.trim() && <div className="ob-bar">Bar license: <b>{form.license.trim()}</b></div>}
              <div className="ob-tags">{specs.length ? specs.map(x => <span key={x}>{x}</span>) : <em>No practice areas yet</em>}</div>
            </div>
          </article>
        </section>
      </div>
    </StepFrame>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────
export function OnboardingPage({ onComplete, t }) {
  const [step, setStep] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const [live, setLive] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  // One copy of the form for every step, so going Back keeps what was typed
  // (each step used to hold its own state and reset on return).
  const [form, setForm] = useState(EMPTY_FORM);
  const set = (key, v) => setForm(f => ({ ...f, [key]: typeof v === "function" ? v(f[key]) : v }));

  const submit = async () => {
    setSaving(true);
    setError(null);
    const f = form;
    const specs = f.specLabels.map(s => SPEC_VALUE[s]).filter(Boolean);
    const [r1, r2] = await Promise.all([
      updateMe({
        full_name: f.name.trim() || null,
        phone: toPkPhone(f.phone),
      }),
      updateLawyerProfile({
        bar_number: f.license.trim() || null,
        specializations: specs.length ? specs : null,
        experience_years: f.exp ? parseInt(f.exp) : null,
        hourly_rate: f.minFee ? parseInt(f.minFee) : null,
        address: [f.address.trim(), f.city.trim()].filter(Boolean).join(", ") || null,
        bio: f.bio.trim() || null,
        availability: true,
      }),
    ]);
    setSaving(false);
    const err = r1.error || r2.error;
    if (err) {
      // `message` is always a string (formatResponseError). `detail` is the raw
      // body field — an ARRAY of objects on a 422 — and rendering it crashed React.
      setError(err?.message || "Submission failed — please try again.");
      return;
    }
    setLive(r2.data?.lawyer_profile?.kyc_verified === true);
    setSubmitted(true);
    setStep(3);
  };

  const next = () => {
    if (step === 2) submit();
    else setStep(s => Math.min(s + 1, 3));
  };
  const back = () => {
    if (step === 3) { setSubmitted(false); setStep(2); }
    else setStep(s => Math.max(s - 1, 0));
  };

  return (
    <>
      <style>{CSS}</style>
      <div className="aai-ob" data-mode={t?.mode === "light" ? "light" : "dark"}>
        <div className="ob-left">
          <StepsCard step={step} submitted={submitted} live={live} />
          <PreviewCard form={form} step={step} submitted={submitted} live={live} />
        </div>
        {step === 0 && <StepProfessional form={form} set={set} onNext={next} />}
        {step === 1 && <StepCredentials onNext={next} onBack={back} />}
        {step === 2 && <StepOffice form={form} set={set} onNext={next} onBack={back} saving={saving} error={error} />}
        {step === 3 && <StepSubmitted live={live} form={form} onBack={back} onComplete={onComplete} />}
      </div>
    </>
  );
}

export default OnboardingPage;
