'use client';
import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

// Shared layout for the sign-in, sign-up and password-reset pages: a visual
// card on the left and the app-theme form card on the right. Colours are the
// refined client tokens (client/clientTheme.js); the mode follows the app's
// own saved preference ('aai-theme') so a user sees the same theme before and
// after signing in.

const FONTS = "@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700&family=Literata:opsz,wght@7..72,500;7..72,600&display=swap');";

const CSS = `${FONTS}
.aai-auth{--bg:#0B1B1F;--card:#183840;--input:#16323A;--line:rgba(150,215,220,.11);--line-strong:rgba(150,215,220,.22);
  --ink:#F1F5F6;--muted:#BFCACC;--faint:#A7B6BA;--brand:linear-gradient(135deg,#3EE0A1,#2EC4D6);--on-brand:#04212A;--brand-text:#5EE6B0;
  --brand-soft:rgba(62,224,161,.13);--focus:rgba(62,224,161,.28);--danger:#FF9090;--danger-soft:rgba(255,120,120,.10);--warn:#F2C35B;--warn-soft:rgba(242,195,91,.13);
  --glow:rgba(62,224,161,.09);--shadow:0 1px 0 rgba(255,255,255,.05) inset,0 20px 36px -18px rgba(0,0,0,.7);
  --body:'Hanken Grotesk',system-ui,-apple-system,'Segoe UI',sans-serif;--display:'Literata',Georgia,serif;
  height:100vh;height:100dvh;overflow:hidden;background:var(--bg);color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.5;
  display:grid;grid-template-columns:minmax(0,1fr) clamp(420px,36vw,540px);gap:28px;padding:20px;box-sizing:border-box}
.aai-auth[data-mode="light"]{--bg:#EEF3F1;--card:#FFFFFF;--input:#FFFFFF;--line:#DFDCE3;--line-strong:#C9C5CE;--ink:#1E1C21;--muted:#5A5660;--faint:#625E68;
  --brand:linear-gradient(135deg,#0E8A5F,#0B7A8C);--on-brand:#FFFFFF;--brand-text:#0E7A55;--brand-soft:rgba(14,138,95,.10);--focus:rgba(14,138,95,.22);
  --danger:#B42318;--danger-soft:rgba(180,35,24,.07);--warn:#8A5A00;--warn-soft:rgba(196,140,20,.12);--glow:rgba(14,138,95,.07);
  --shadow:0 2px 4px rgba(10,30,40,.04),0 18px 34px -16px rgba(10,40,50,.28)}
:where(.aai-auth) *,:where(.aai-auth) *::before,:where(.aai-auth) *::after{box-sizing:border-box}
:where(.aai-auth) :where(button){font:inherit;color:inherit}
:where(.aai-auth) :focus-visible{outline:2px solid var(--brand-text);outline-offset:2px}
.aa-col{position:relative;z-index:1;display:grid;grid-template-rows:minmax(0,1fr);min-height:0;height:100%;overflow:hidden}
/* One screen tall; a long form (lawyer sign-up) scrolls INSIDE the card, centred
   when it fits (margin:auto on the form), with a thin themed bar as the cue. */
.aa-card{position:relative;border-radius:30px;background:var(--card);border:1px solid var(--line);box-shadow:var(--shadow);display:flex;flex-direction:column;min-height:0;height:100%;overflow-x:hidden;overflow-y:auto;padding:28px 28px;scrollbar-width:thin;scrollbar-color:var(--line-strong) transparent}
.aa-card::-webkit-scrollbar{width:6px}
.aa-card::-webkit-scrollbar-thumb{background:var(--line-strong);border-radius:6px}
.aa-card::-webkit-scrollbar-track{background:transparent}
/* The corner glow is part of the background: as an overhanging ::after it would make the scrolling card scroll for nothing. */
.aa-card{background:radial-gradient(260px 240px at 0% 100%,var(--glow),transparent 70%) no-repeat,var(--card)}
.aa-form{position:relative;z-index:1;width:100%;max-width:350px;margin:auto;display:grid;gap:11px;text-align:center}
.aa-brand{display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:4px}
.aa-brand img{width:52px;height:52px;object-fit:contain;filter:drop-shadow(0 6px 14px rgba(0,0,0,.3))}
.aa-brand b{font-family:var(--display);font-weight:600;font-size:27px;letter-spacing:-.01em}
.aa-brand em{font-style:normal;color:var(--brand-text)}
.aa-title{font-family:var(--display);font-weight:600;font-size:clamp(24px,2.1vw,32px);line-height:1.12;letter-spacing:-.015em;margin:0}
.aa-sub{color:var(--muted);font-size:14.5px;line-height:1.5;margin:-4px auto 4px;max-width:38ch}
.aa-pill{height:44px;border-radius:999px;background:var(--input);border:1px solid var(--line-strong);display:flex;align-items:center;text-align:left;overflow:hidden;transition:border-color .15s,box-shadow .15s}
.aa-pill:focus-within{border-color:var(--brand-text);box-shadow:0 0 0 4px var(--focus)}
.aa-pill.bad{border-color:var(--danger)}
.aa-pill .ic{width:46px;height:100%;display:grid;place-items:center;color:var(--faint);border-right:1px solid var(--line-strong);flex:none;font-weight:700;font-size:14px}
.aa-pill input{all:unset;flex:1;min-width:0;height:100%;padding:0 16px;font:inherit;font-size:14.5px;color:var(--ink)}
.aa-pill input::placeholder{color:var(--faint)}
.aa-pill input:-webkit-autofill,.aa-pill input:-webkit-autofill:hover,.aa-pill input:-webkit-autofill:focus{-webkit-text-fill-color:var(--ink);-webkit-box-shadow:0 0 0 1000px var(--input) inset;caret-color:var(--ink);transition:background-color 9999s}
.aa-pill .side{padding-right:16px;display:flex;align-items:center}
.aa-link{all:unset;cursor:pointer;color:var(--brand-text);font-weight:700}
.aa-link:hover{text-decoration:underline}
.aa-row{display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:14px;color:var(--muted);padding:0 6px}
.aa-check{position:relative;display:flex;align-items:center;gap:9px;cursor:pointer;user-select:none}
.aa-check input{position:absolute;opacity:0;width:1px;height:1px}
.aa-check .box{width:19px;height:19px;border-radius:6px;border:1.5px solid var(--line-strong);display:grid;place-items:center;flex:none}
.aa-check input:checked+.box{background:var(--brand);border-color:transparent}
.aa-check input:focus-visible+.box{outline:2px solid var(--brand-text);outline-offset:2px}
.aa-btn{all:unset;box-sizing:border-box;cursor:pointer;height:46px;border-radius:999px;background:var(--brand);color:var(--on-brand);font-weight:700;font-size:15px;display:flex;align-items:center;justify-content:center;gap:10px;box-shadow:0 14px 28px -14px rgba(46,196,214,.65);transition:filter .15s,transform .15s}
.aa-btn:hover{filter:brightness(1.06)}
.aa-btn:active{transform:translateY(1px)}
.aa-btn[disabled]{opacity:.7;cursor:progress}
.aa-ghost{all:unset;box-sizing:border-box;cursor:pointer;height:44px;border-radius:999px;border:1px solid var(--line-strong);display:flex;align-items:center;justify-content:center;gap:8px;font-weight:600}
.aa-ghost[disabled]{cursor:default;opacity:.85}
.aa-notice{display:flex;gap:10px;align-items:flex-start;text-align:left;padding:12px 14px;border-radius:16px;background:var(--danger-soft);border:1px solid var(--danger);font-size:14px;line-height:1.45}
.aa-notice svg{flex:none;color:var(--danger);margin-top:1px}
.aa-notice.info{background:var(--brand-soft);border-color:var(--brand-text)}
.aa-notice.info svg{color:var(--brand-text)}
.aa-hint{font-size:13px;color:var(--faint);display:flex;gap:6px;align-items:center;justify-content:center}
.aa-hint svg{flex:none;margin-top:2px}
.aa-hint.ok{color:var(--brand-text)}
.aa-hero{justify-self:center;width:56px;height:56px;border-radius:22px;background:var(--brand-soft);color:var(--brand-text);display:grid;place-items:center;margin-bottom:2px}
.aa-hero.warn{background:var(--warn-soft);color:var(--warn)}
.aa-back{justify-self:center;display:flex;gap:6px;align-items:center;font-size:14px}
.aa-role{display:grid;grid-template-columns:1fr 1fr;padding:4px;border-radius:999px;background:var(--input);border:1px solid var(--line-strong)}
.aa-role button{all:unset;cursor:pointer;height:34px;border-radius:999px;display:grid;place-items:center;font-weight:600;font-size:14px;color:var(--muted)}
.aa-role button[aria-pressed="true"]{background:var(--brand);color:var(--on-brand)}
.aa-rules{display:flex;justify-content:center;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--faint)}
.aa-rules span{display:flex;align-items:center;gap:6px}
.aa-rules span.ok{color:var(--brand-text)}
.aa-rules .dot{width:15px;height:15px;border-radius:50%;border:1.5px solid var(--line-strong);display:grid;place-items:center}
.aa-rules .ok .dot{background:var(--brand-text);border-color:transparent}
.aa-meter{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;padding:0 8px}
.aa-meter i{height:4px;border-radius:4px;background:var(--line)}
.aa-meter i.on{background:var(--brand)}
.aa-alt{margin:4px 0 0;font-size:14px;color:var(--muted)}
.aa-alt .aa-link{display:inline-flex;align-items:center;gap:4px;margin-left:4px}
.aa-next{border-radius:26px;background:var(--card);border:1px solid var(--line);box-shadow:var(--shadow);min-height:76px;display:flex;align-items:center;gap:16px;padding:14px 22px;text-align:left}
.aa-next .stack{display:flex}
.aa-next .stack span{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;border:2px solid var(--card);margin-left:-12px;color:var(--on-brand);background:var(--brand)}
.aa-next .stack span:first-child{margin-left:0}
.aa-next .stack span:nth-child(2){background:#2EC4D6}
.aa-next .stack span:nth-child(3){background:#1C434B;color:#5EE6B0}
.aai-auth[data-mode="light"] .aa-next .stack span:nth-child(3){background:#DCEFE6;color:#0E7A55}
.aa-next b{display:block;font-size:15px}
.aa-next small{color:var(--muted);font-size:13.5px}
.aa-next .aa-link{margin-left:auto;display:flex;gap:6px;align-items:center;white-space:nowrap}
.aa-spin{width:18px;height:18px;border-radius:50%;border:2.5px solid currentColor;border-right-color:transparent;animation:aa-sp .8s linear infinite}
@keyframes aa-sp{to{transform:rotate(360deg)}}
/* left visual cards (always dark, they sit on photos/video) */
.aa-vis{position:relative;z-index:0;color:#F1F5F6;height:100%;min-height:0}
/* Full-bleed (2026-10-19): the photo, video and tint fill the whole page with no
   frame; the headline and panels still sit in the left half. The form card on
   the right is the only container. */
.aa-vis video,.aa-vis .still,.aa-vis .duo,.aa-vis .tint,.aa-rec .bgimg,.aa-rec .shade{position:fixed!important}
@media (min-width:1025px){.aai-auth{background:#0A0F10}}
.aa-vis video,.aa-vis .still{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.aa-vis .slide{opacity:0;transition:opacity 1.4s ease}
.aa-vis .slide.on{opacity:1}
.aa-vis video{filter:grayscale(1) contrast(1.15) brightness(.85)}
.aa-vis .still{inset:-4%;width:auto;height:auto;background:center top/cover no-repeat}
@media (prefers-reduced-motion:no-preference){.aa-vis .still.on,.aa-vis .still.kb{animation:aa-kb 14s ease-in-out infinite alternate}}
@keyframes aa-kb{from{transform:scale(1)}to{transform:scale(1.12) translate(-1.5%,2%)}}
.aa-vis .duo{position:absolute;inset:0;background:linear-gradient(160deg,#1F6B66,#0E3B40);mix-blend-mode:color;opacity:.95}
.aa-vis .tint{position:absolute;inset:0;background:linear-gradient(180deg,rgba(6,24,27,.15),rgba(6,24,27,0) 40%,rgba(6,24,27,.35) 72%,rgba(6,24,27,.80))}
.aa-vis .tint.top{background:linear-gradient(180deg,rgba(6,24,27,.88) 0%,rgba(6,24,27,.6) 30%,rgba(6,24,27,.12) 52%,rgba(6,24,27,.35) 64%,rgba(6,24,27,.94))}
.aa-vis .cap{position:absolute;left:22px;top:20px;font-size:11.5px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:rgba(241,245,246,.9);background:rgba(5,20,22,.45);padding:5px 12px;border-radius:999px;z-index:2}
.aa-vis .cred{position:absolute;right:18px;top:20px;font-size:11px;color:rgba(241,245,246,.85);background:rgba(5,20,22,.45);padding:4px 10px;border-radius:999px;z-index:2;transition:opacity .8s}
.aa-vis .badge{position:absolute;right:20px;top:18px;font-size:12.5px;font-weight:700;color:#04212A;background:linear-gradient(135deg,#3EE0A1,#2EC4D6);padding:6px 14px;border-radius:999px;z-index:2}
.aa-vis .ribbon{position:absolute;left:-60px;right:-60px;top:52%;transform:rotate(-8deg);background:rgba(241,245,246,.10);border-top:1px solid rgba(241,245,246,.22);border-bottom:1px solid rgba(241,245,246,.22);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);overflow:hidden;height:44px}
.aa-vis .ribbon div{display:flex;gap:28px;white-space:nowrap;line-height:44px;font-size:15px;font-weight:600;color:rgba(241,245,246,.85);letter-spacing:.04em;width:max-content}
.aa-vis .ribbon i{font-style:normal;color:#5EE6B0}
@media (prefers-reduced-motion:no-preference){.aa-vis .ribbon div{animation:aa-mq 28s linear infinite}}
@keyframes aa-mq{to{transform:translateX(-50%)}}
.aa-vis .lv-cta{position:absolute;left:28px;right:28px;bottom:76px;z-index:2;display:grid;gap:12px}
.aa-vis .lv-cta p{margin:0;font-size:15px;color:rgba(241,245,246,.88)}
.aa-vis .lv-cta div{display:flex;flex-wrap:wrap;gap:10px}
.aa-vis .lv-cta span{height:34px;padding:0 14px;border-radius:999px;display:inline-flex;align-items:center;gap:8px;font-size:13.5px;font-weight:600;color:#F1F5F6;background:rgba(8,28,32,.40);border:1px solid rgba(241,245,246,.32);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}
.aa-vis .lv-cta span svg{color:#5EE6B0}
.aa-vis .lv-ticker{position:absolute;left:28px;right:28px;bottom:24px;z-index:2;overflow:hidden;-webkit-mask-image:linear-gradient(90deg,transparent,#000 48px,#000 calc(100% - 48px),transparent);mask-image:linear-gradient(90deg,transparent,#000 48px,#000 calc(100% - 48px),transparent)}
.aa-vis .lv-ticker div{display:flex;gap:10px;padding-right:10px;width:max-content}
.aa-vis .lv-ticker span{height:32px;padding:0 14px;border-radius:999px;display:inline-flex;align-items:center;white-space:nowrap;font-size:13px;font-weight:600;letter-spacing:.02em;color:rgba(241,245,246,.9);background:rgba(241,245,246,.08);border:1px solid rgba(241,245,246,.2);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
@media (prefers-reduced-motion:no-preference){.aa-vis .lv-ticker div{animation:aa-mq 30s linear infinite}}
.aa-vis .glass{position:absolute;left:16px;right:16px;bottom:16px;border-radius:24px;padding:18px;background:rgba(12,34,38,.50);border:1px solid rgba(241,245,246,.18);backdrop-filter:blur(14px) saturate(1.2);-webkit-backdrop-filter:blur(14px) saturate(1.2);display:grid;gap:12px;z-index:2}
.aa-vis .glass .pills{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.aa-vis .glass .pills span{height:40px;border-radius:999px;border:1px solid rgba(241,245,246,.45);display:flex;align-items:center;justify-content:center;gap:9px;font-weight:600;font-size:14px}
.aa-vis .glass p{margin:0 4px;color:rgba(241,245,246,.85);font-size:15px}
.aa-vis .dots{position:absolute;left:50%;transform:translateX(-50%);bottom:186px;display:flex;gap:7px;z-index:2}
.aa-vis .dots i{width:7px;height:7px;border-radius:999px;background:rgba(241,245,246,.45);transition:width .4s,background .4s}
.aa-vis .dots i.on{width:22px;background:#5EE6B0}
.aa-vis .say{position:absolute;left:34px;right:34px;top:76px;display:grid;gap:12px;z-index:2}
.aa-vis .say h2{font-family:var(--display);font-weight:600;font-size:clamp(34px,3.2vw,46px);line-height:1.06;letter-spacing:-.015em;margin:0;max-width:13ch}
.aa-vis .say h2 em{font-style:normal;color:#5EE6B0}
.aa-vis .say p{margin:0;color:rgba(241,245,246,.82);font-size:16px;max-width:38ch}
/* Steps as a grid of tiles (2026-10-19): 2x2 for the lawyer's four steps, 3 across
   for the client's points. No outer panel; each tile is its own frosted card. */
.aa-vis .glass.list{display:grid;grid-template-columns:repeat(var(--cols,2),minmax(0,1fr));gap:10px;padding:0;background:none;border:0;border-radius:0;-webkit-backdrop-filter:none;backdrop-filter:none}
.aa-vis .gi{display:grid;grid-template-columns:auto 1fr;grid-template-areas:"n you" "t t";align-content:start;gap:6px 8px;padding:10px 12px;border-radius:14px;background:rgba(8,28,32,.48);border:1px solid rgba(241,245,246,.14);-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px)}
.aa-vis .gi>.gn{grid-area:n}.aa-vis .gi>span:nth-child(2){grid-area:t}.aa-vis .gi>span:nth-child(3){grid-area:you;justify-self:end;align-self:center}
.aa-vis .gi.here{background:rgba(62,224,161,.16);border-color:rgba(94,230,176,.5)}
.aa-vis .gn{display:grid;place-items:center;color:#5EE6B0;font-weight:800;font-size:15px;line-height:1}
.aa-vis .gi.here .gn{color:#5EE6B0}
.aa-vis .gi b{display:block;font-size:13.5px;line-height:1.3}
.aa-vis .gi small{display:none} /* titles only on the tiles (2026-10-19) */
.aa-vis .you{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#5EE6B0}
/* recovery panel */
.aa-rec{display:grid;grid-template-rows:auto auto 1fr auto;gap:22px;padding:38px 40px 32px;background:transparent}
.aa-rec .bgimg{position:absolute;inset:0;background:center top/cover no-repeat;filter:grayscale(1) contrast(1.1);opacity:.22}
.aa-rec .shade{position:absolute;inset:0;background:radial-gradient(520px 420px at 50% 22%,rgba(62,224,161,.20),transparent 65%),linear-gradient(180deg,rgba(10,34,38,.55),rgba(10,34,38,.88) 45%,rgba(8,26,30,.98))}
.aa-rec>:not(.bgimg):not(.shade){position:relative;z-index:1}
.aa-orb{justify-self:center;position:relative;width:168px;height:168px;display:grid;place-items:center}
.aa-orb i{position:absolute;inset:0;border-radius:50%;border:1px solid rgba(94,230,176,.30)}
.aa-orb i:nth-child(2){inset:22px;border-color:rgba(94,230,176,.22)}
@media (prefers-reduced-motion:no-preference){.aa-orb i{animation:aa-ring 3.2s ease-out infinite}.aa-orb i:nth-child(2){animation-delay:1.6s}}
@keyframes aa-ring{0%{transform:scale(.82);opacity:0}30%{opacity:1}100%{transform:scale(1.12);opacity:0}}
/* No box around the icon (2026-10-19): the icon alone, larger, with a soft glow. */
.aa-orb span{display:grid;place-items:center;color:#5EE6B0;filter:drop-shadow(0 0 18px rgba(62,224,161,.45))}
.aa-orb.warn span{color:#F2C35B;filter:drop-shadow(0 0 18px rgba(242,195,91,.45))}
.aa-rec .head{text-align:center}
.aa-rec .eyeb{font-size:12.5px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#5EE6B0}
.aa-rec h2{font-family:var(--display);font-weight:600;font-size:clamp(30px,2.8vw,38px);line-height:1.1;letter-spacing:-.015em;margin:8px auto 0;max-width:16ch}
.aa-track{align-self:center;position:relative}
.aa-track ol{display:grid;grid-template-columns:repeat(4,1fr);list-style:none;margin:0;padding:0;position:relative}
.aa-track::before{content:"";position:absolute;left:12.5%;right:12.5%;top:21px;height:2px;background:rgba(150,215,220,.2)}
.aa-track .fill{position:absolute;left:12.5%;top:21px;height:2px;background:linear-gradient(90deg,#3EE0A1,#2EC4D6);transition:width .5s}
.aa-track li{display:grid;justify-items:center;text-align:center;gap:10px;position:relative;padding:0 6px}
.aa-track .tc{width:44px;height:44px;border-radius:50%;border:1.5px solid rgba(150,215,220,.3);display:grid;place-items:center;font-weight:700;color:#A7B6BA;background:#0D2B30}
.aa-track .done .tc{background:linear-gradient(135deg,#3EE0A1,#2EC4D6);border-color:transparent;color:#04212A}
.aa-track .now .tc{border-color:#5EE6B0;color:#5EE6B0;box-shadow:0 0 0 6px rgba(62,224,161,.16)}
.aa-track .warn .tc{border-color:#F2C35B;color:#F2C35B;box-shadow:0 0 0 6px rgba(242,195,91,.14)}
.aa-track b{font-size:14px;line-height:1.3}
.aa-track small{color:#A7B6BA;font-size:12px;line-height:1.35}
.aa-facts{display:flex;justify-content:center;flex-wrap:wrap;gap:10px}
.aa-facts span{display:flex;gap:8px;align-items:center;font-size:13px;font-weight:600;padding:8px 12px;border-radius:999px;background:rgba(241,245,246,.07);border:1px solid rgba(241,245,246,.14);color:#DCE6E8}
.aa-facts svg{color:#5EE6B0}
/* Glass form card (2026-10-19): the page photo shows through, frosted. Kept dark
   enough (55% tint + blur) that the form reads at full contrast. Highlights are
   inset shadows (74% tint: over the bright court photo, 58% left the grey
   subtitle at ~2.5:1), not a pseudo-element: the card scrolls, and an absolutely
   placed layer would scroll away with its content. */
.aa-card{
  background:
    radial-gradient(280px 240px at 0% 100%,rgba(62,224,161,.16),transparent 70%) no-repeat,
    linear-gradient(160deg,rgba(255,255,255,.11),rgba(255,255,255,.02) 42%,rgba(255,255,255,.05)),
    rgba(10,34,40,.74);
  -webkit-backdrop-filter:blur(26px) saturate(150%);backdrop-filter:blur(26px) saturate(150%);
  border:1px solid rgba(255,255,255,.16);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.22),inset 0 0 0 1px rgba(255,255,255,.04),0 40px 80px -30px rgba(0,0,0,.7)}
.aa-card .aa-pill,.aa-card .aa-role{background:rgba(4,20,24,.5);border-color:rgba(255,255,255,.13)}
.aa-card .aa-pill .ic{border-right-color:rgba(255,255,255,.12)}
.aa-card .aa-pill input:-webkit-autofill,.aa-card .aa-pill input:-webkit-autofill:hover,.aa-card .aa-pill input:-webkit-autofill:focus{-webkit-box-shadow:0 0 0 1000px #0E2A30 inset}
.aai-auth[data-mode="light"] .aa-card{
  background:
    radial-gradient(280px 240px at 0% 100%,rgba(14,138,95,.12),transparent 70%) no-repeat,
    linear-gradient(160deg,rgba(255,255,255,.80),rgba(255,255,255,.58));
  border-color:rgba(255,255,255,.75);
  box-shadow:inset 0 1px 0 #fff,0 40px 80px -30px rgba(10,40,50,.38)}
.aai-auth[data-mode="light"] .aa-card .aa-pill,.aai-auth[data-mode="light"] .aa-card .aa-role{background:rgba(255,255,255,.72);border-color:rgba(10,40,50,.14)}
.aai-auth[data-mode="light"] .aa-card .aa-pill .ic{border-right-color:rgba(10,40,50,.12)}
.aai-auth[data-mode="light"] .aa-card .aa-pill input:-webkit-autofill,.aai-auth[data-mode="light"] .aa-card .aa-pill input:-webkit-autofill:hover,.aai-auth[data-mode="light"] .aa-card .aa-pill input:-webkit-autofill:focus{-webkit-box-shadow:0 0 0 1000px #F4F8F7 inset}
@media (max-width:1024px){
  .aai-auth{grid-template-columns:1fr;padding:16px}
  .aa-vis{display:none}
  .aa-col{min-height:0}
  .aa-card{padding:32px 18px}
  .aa-next{padding:16px 18px}
  .aa-next .stack{display:none}
}
@media (prefers-reduced-motion:reduce){.aai-auth *{animation:none!important;transition:none!important}}
`;

/* ─── icons ─────────────────────────────────────────────────────── */
const Svg = ({ s = 19, w = 2, children, ...p }) => (
  <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}>{children}</svg>
);
function MaskIcon({ src, s }) {
  const px = Math.round(s * 1.45);
  const mask = `url(${src}) center / contain no-repeat`;
  return <span aria-hidden="true" style={{ display: 'inline-block', width: px, height: px, backgroundColor: 'currentColor', WebkitMask: mask, mask }} />;
}
export const Icon = {
  mail: (s) => <Svg s={s}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></Svg>,
  lock: (s) => <Svg s={s}><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></Svg>,
  user: (s) => <Svg s={s}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></Svg>,
  shield: (s) => <Svg s={s}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></Svg>,
  book: (s) => <Svg s={s}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z" /></Svg>,
  chat: (s) => <Svg s={s}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></Svg>,
  people: (s) => <Svg s={s}><circle cx="9" cy="8" r="4" /><path d="M2 21a7 7 0 0 1 14 0M17 11a3 3 0 1 0 0-6M22 21a6 6 0 0 0-4-5.6" /></Svg>,
  arrow: (s = 18) => <Svg s={s} w={2.4}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>,
  back: (s = 16) => <Svg s={s} w={2.4}><path d="M19 12H5M11 18l-6-6 6-6" /></Svg>,
  ne: (s = 18) => <Svg s={s} w={2.2}><path d="M7 17 17 7M8 7h9v9" /></Svg>,
  warn: (s = 18) => <Svg s={s}><circle cx="12" cy="12" r="10" /><path d="M12 7v6M12 17h.01" /></Svg>,
  info: (s = 16) => <Svg s={s}><circle cx="12" cy="12" r="10" /><path d="M12 16v-5M12 8h.01" /></Svg>,
  check: (s = 15) => <Svg s={s} w={3}><path d="m5 12 4.5 4.5L19 7" /></Svg>,
  key: (s) => <Svg s={s} w={1.8}><circle cx="8" cy="15" r="4" /><path d="m10.8 12.2 9.2-9.2M17 6l3 3M14 9l2 2" /></Svg>,
  // The user's own icon files in public/auth/, used as MASKS so they take the
  // box's colour (currentColor) like the line icons instead of being black.
  // Shown ~45% larger than the line icons so their detail stays legible.
  recover: (s = 19) => <MaskIcon src="/auth/account-recovery.png" s={s} />,  // lock, person, gear, cycle
  mailSent: (s = 19) => <MaskIcon src="/auth/mail-sent.png" s={s} />,        // open envelope, megaphone
  done: (s) => <Svg s={s}><circle cx="12" cy="12" r="10" /><path d="m7.5 12 3 3 6-6" /></Svg>,
  hour: (s) => <Svg s={s} w={1.8}><path d="M6 2h12M6 22h12M7 2v4l5 6-5 6v4M17 2v4l-5 6 5 6v4" /></Svg>,
};
const Tick = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4.5 4.5L19 7" fill="none" stroke="var(--on-brand)" strokeWidth="3.6" strokeLinecap="round" /></svg>
);

/* ─── theme mode ────────────────────────────────────────────────── */
function useAuthMode() {
  const [mode, setMode] = useState('dark');
  useEffect(() => {
    let m = null;
    try { m = localStorage.getItem('aai-theme'); } catch { /* storage blocked */ }
    if (m !== 'light' && m !== 'dark') {
      m = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    setMode(m);
  }, []);
  return mode;
}

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const q = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!q) return undefined;
    setReduced(q.matches);
    const on = (e) => setReduced(e.matches);
    q.addEventListener?.('change', on);
    return () => q.removeEventListener?.('change', on);
  }, []);
  return reduced;
}

/* ─── layout ────────────────────────────────────────────────────── */
const AUTH_ROUTES = ['/login', '/register', '/reset-password'];

export function AuthShell({ visual, next, children }) {
  const mode = useAuthMode();
  // Load the sibling auth pages in the background (2026-10-19): a click on
  // "Sign up" or "Forgot password?" then opens at once instead of waiting
  // for that page's code.
  const router = useRouter();
  useEffect(() => { AUTH_ROUTES.forEach(r => { try { router.prefetch?.(r); } catch { /* best effort */ } }); }, [router]);
  return (
    <>
      <style>{CSS}</style>
      <main className="aai-auth" data-mode={mode}>
        {visual}
        <div className="aa-col">
          {/* data-lenis-prevent: the site-wide smooth scroller swallows wheel events,
              so without it the card scrolled only by dragging its bar. */}
          <section className="aa-card" data-lenis-prevent><div className="aa-form">{children}{next}</div></section>
        </div>
      </main>
    </>
  );
}

export const Brand = () => (
  <div className="aa-brand"><img src="/logo.png" alt="" /><b>Attorney<em>.AI</em></b></div>
);

// "New to Attorney.AI? Sign up": one line at the foot of the form card (2026-10-19;
// it used to be a second card under it). `sub` and `icons` are no longer shown.
export function NextCard({ title, cta, onClick }) {
  return (
    <p className="aa-alt">{title}<button type="button" className="aa-link" onClick={onClick}>{cta}{Icon.ne()}</button></p>
  );
}

export function PillInput({ icon, prefix, label, error, side, inputRef, ...input }) {
  return (
    <div className={`aa-pill${error ? ' bad' : ''}`}>
      <span className="ic">{prefix || icon}</span>
      <input aria-label={label} aria-invalid={error ? 'true' : undefined} ref={inputRef} {...input} />
      {side && <span className="side">{side}</span>}
    </div>
  );
}

export function ShowToggle({ shown, onToggle }) {
  return (
    <button type="button" className="aa-link" style={{ fontSize: 13 }} onClick={onToggle}
      aria-label={shown ? 'Hide password' : 'Show password'}>{shown ? 'Hide' : 'Show'}</button>
  );
}

export function Checkbox({ checked, onChange, children }) {
  return (
    <label className="aa-check">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
      <span className="box">{checked && <Tick />}</span>
      <span>{children}</span>
    </label>
  );
}

export function PrimaryButton({ busy, busyLabel, children, ...p }) {
  return (
    <button className="aa-btn" disabled={busy} aria-busy={busy || undefined} {...p}>
      {busy ? <><span className="aa-spin" aria-hidden="true" />{busyLabel}</> : <>{children}{Icon.arrow()}</>}
    </button>
  );
}

export function Notice({ children, tone = 'error' }) {
  if (!children) return null;
  if (tone === 'info') {
    return <div className="aa-notice info" role="status">{Icon.check(16)}<span>{children}</span></div>;
  }
  return <div className="aa-notice" role="alert">{Icon.warn()}<span>{children}</span></div>;
}

export function HeroIcon({ name, warn }) {
  return <div className={`aa-hero${warn ? ' warn' : ''}`} aria-hidden="true">{Icon[name](30)}</div>;
}

// Mirrors backend validate_password_strength: 8+ chars, a digit, an uppercase.
export const passwordRules = (pw) => [
  ['8+ characters', pw.length >= 8],
  ['A capital letter', /[A-Z]/.test(pw)],
  ['A number', /\d/.test(pw)],
];
// The server also caps the password at 72 BYTES (bcrypt; utils/validators.py),
// not 72 characters: Urdu letters take 2 bytes each in UTF-8 and emoji take 4.
export const PASSWORD_MAX_BYTES = 72;
export const passwordBytes = (pw) => new TextEncoder().encode(pw).length;

export const passwordProblem = (pw) => {
  if (pw.length < 8) return 'Use at least 8 characters.';
  if (passwordBytes(pw) > PASSWORD_MAX_BYTES) {
    return 'This password is too long. Use a shorter one (up to 72 letters or numbers; Urdu letters and emoji count as more).';
  }
  if (!/[0-9]/.test(pw)) return 'Include at least one number.';
  if (!/[A-Z]/.test(pw)) return 'Include at least one capital letter.';
  return null;
};

export function PasswordRules({ value }) {
  const rules = passwordRules(value);
  const n = rules.filter(r => r[1]).length + (value.length >= 12 ? 1 : 0);
  return (
    <>
      <div className="aa-meter" aria-hidden="true">{[0, 1, 2, 3].map(i => <i key={i} className={i < n ? 'on' : ''} />)}</div>
      <div className="aa-rules">
        {rules.map(([label, ok]) => (
          <span key={label} className={ok ? 'ok' : ''}><span className="dot">{ok && <Tick />}</span>{label}</span>
        ))}
      </div>
      {passwordBytes(value) > PASSWORD_MAX_BYTES && (
        <div className="aa-hint" role="status" style={{ color: 'var(--danger)' }}>{Icon.warn(15)}Too long. Use a shorter password.</div>
      )}
    </>
  );
}

/* ─── left visuals ──────────────────────────────────────────────── */
const COURT = '/auth/lahore-high-court.jpg';
const RIBBON = ['PPC', 'CrPC', 'Constitution of Pakistan', 'Family law', 'Registered lawyers'];

// One straight row of separate chips that drifts sideways (was a tilted band).
// The list is doubled so the -50% loop is seamless; reduced motion stops it.
function Ticker() {
  const words = [...RIBBON, ...RIBBON];
  return (
    <div className="lv-ticker" aria-hidden="true">
      <div>{words.map((w, i) => <span key={i}>{w}</span>)}</div>
    </div>
  );
}

const SLIDES = [
  { kind: 'still', cap: 'Lahore High Court', credit: true },
  { kind: 'video', src: '/auth/flag.mp4', cap: 'Pakistan' },
  { kind: 'video', src: '/auth/law-book.mp4', cap: 'Law and justice' },
];

// Sign-in: Lahore High Court (slow zoom), the national flag and a law book, in turn.
export function LoginVisual() {
  const reduced = usePrefersReducedMotion();
  const [cur, setCur] = useState(0);
  const vids = useRef([]);
  useEffect(() => {
    if (reduced) return undefined;
    const id = setInterval(() => setCur(c => (c + 1) % SLIDES.length), 7000);
    return () => clearInterval(id);
  }, [reduced]);
  useEffect(() => {
    vids.current.forEach((v, i) => {
      if (!v) return;
      if (i === cur && !reduced) { try { v.currentTime = 0; } catch { /* not loaded yet */ } v.play?.().catch(() => {}); }
      else v.pause?.();
    });
  }, [cur, reduced]);
  const slide = SLIDES[cur];
  return (
    <section className="aa-vis" aria-label="Pakistani law: Lahore High Court, the national flag and a law book">
      {SLIDES.map((s, i) => s.kind === 'still'
        ? <div key={i} className={`still slide${i === cur ? ' on' : ''}`} style={{ backgroundImage: `url(${COURT})` }} />
        : <video key={i} ref={el => { vids.current[i] = el; }} className={`slide${i === cur ? ' on' : ''}`} src={s.src}
            muted playsInline loop preload="metadata" aria-hidden="true" />)}
      {/* "top": darker at the top, where the headline sits (bright court photo). */}
      <div className="duo" aria-hidden="true" /><div className="tint top" aria-hidden="true" />
      <span className="cap">{slide.cap}</span>
      {/* The photo credit (CC BY-SA 4.0) is on /terms under "Image credits" (2026-10-19). */}
      {/* Same headline block as the sign-up visual (2026-10-19). Worded for both
          roles: clients and lawyers sign in here. */}
      <div className="say">
        <h2>Your legal matters, <em>in one place.</em></h2>
        <p>Pick up where you left off: your cases, documents and conversations with your lawyer.</p>
      </div>
      <span className="dots" aria-hidden="true">{SLIDES.map((_, i) => <i key={i} className={i === cur ? 'on' : ''} />)}</span>
      {/* No panel around these (2026-10-19): a line of text and two small chips. */}
      <div className="lv-cta">
        <p>Guiding you through Pakistani law, step by step.</p>
        <div><span>{Icon.book(15)}Legal guidance</span><span>{Icon.people(15)}Registered lawyers</span></div>
      </div>
      <Ticker />
    </section>
  );
}

const CLIENT_POINTS = [
  ['chat', 'Explain your problem in plain words', 'No legal terms needed'],
  ['shield', 'Guidance that shows its sources', 'PPC, CrPC and the Constitution'],
  ['user', 'A lawyer when you need one', 'Matched by practice area and city'],
];
const LAWYER_STEPS = [
  ['Create your account', 'About a minute'],
  ['Complete your profile', 'Bar license number and practice areas'],
  ['Add office and fees', 'What clients see before they book'],
  ['Go live', 'Clients can find and book you'],
];

// Sign-up: Islamabad for clients; Lahore High Court plus the lawyer journey for lawyers.
export function SignupVisual({ role }) {
  const law = role === 'lawyer';
  return (
    <section className="aa-vis" aria-label={law ? 'Lahore High Court' : 'Islamabad from above'}>
      {law
        ? <div className="still kb" style={{ backgroundImage: `url(${COURT})` }} />
        : <video src="/auth/islamabad.mp4" autoPlay muted loop playsInline preload="metadata" aria-hidden="true" />}
      <div className="duo" aria-hidden="true" /><div className="tint top" aria-hidden="true" />
      <span className="cap">{law ? 'Lahore High Court' : 'Islamabad'}</span>
      <span className="badge">Free to join</span>
      <div className="say">
        {law
          ? <><h2>Grow your practice <em>across Pakistan.</em></h2><p>Clients find you by practice area and city. Your cases, hearings and documents in one place.</p></>
          : <><h2>Legal help for <em>every Pakistani.</em></h2><p>Explain your problem in your own words and get guidance grounded in Pakistani law.</p></>}
      </div>
      <div className="glass list" style={{ "--cols": law ? 2 : 3 }}>
        {law
          ? LAWYER_STEPS.map(([t, s], i) => (
            <div key={t} className={`gi${i === 0 ? ' here' : ''}`}>
              <span className="gn">{i + 1}</span><span><b>{t}</b><small>{s}</small></span>
              {i === 0 ? <span className="you">You are here</span> : <span />}
            </div>))
          : CLIENT_POINTS.map(([ic, t, s]) => (
            <div key={t} className="gi"><span className="gn">{Icon[ic](17)}</span><span><b>{t}</b><small>{s}</small></span><span /></div>))}
      </div>
    </section>
  );
}

const REC_STEPS = [
  ['Request a link', 'Your email'],
  ['Check your email', 'Valid for 1 hour'],
  ['New password', 'Strong and new'],
  ['All set', 'Signed out elsewhere'],
];
const REC_ORDER = { request: 0, sent: 1, reset: 2, done: 3 };
const REC_ICON = { request: 'recover', sent: 'mailSent', reset: 'lock', done: 'done', expired: 'hour' };
const REC_HEAD = {
  request: 'Locked out? We’ve got you.', sent: 'Check your inbox.', reset: 'Almost there.',
  done: 'You’re back in control.', expired: 'Let’s get you a fresh link.',
};

// Password reset: where the user is in the four-step recovery.
export function RecoveryVisual({ stage }) {
  const expired = stage === 'expired';
  const at = expired ? -1 : REC_ORDER[stage] ?? 0;
  const fill = expired ? 0 : (Math.min(at, 3) / 3) * 75;
  return (
    <section className="aa-vis aa-rec" aria-label="Account recovery progress">
      <div className="bgimg" style={{ backgroundImage: `url(${COURT})` }} aria-hidden="true" />
      <div className="shade" aria-hidden="true" />
      <div className={`aa-orb${expired ? ' warn' : ''}`} aria-hidden="true"><i /><i /><span>{Icon[REC_ICON[stage] || 'key'](64)}</span></div>
      <div className="head"><div className="eyeb">Account recovery</div><h2>{REC_HEAD[stage] || REC_HEAD.request}</h2></div>
      <div className="aa-track">
        <span className="fill" style={{ width: `${fill}%` }} aria-hidden="true" />
        <ol>
        {REC_STEPS.map(([t, s], i) => {
          const c = expired ? (i === 0 ? 'warn' : '') : (i < at || at === 3 ? 'done' : i === at ? 'now' : '');
          return (
            <li key={t} className={c} aria-current={c === 'now' || c === 'warn' ? 'step' : undefined}>
              <span className="tc">{c === 'done' ? Icon.check() : i + 1}</span>
              <b>{t}</b><small>{expired && i === 0 ? 'Link expired' : s}</small>
            </li>
          );
        })}
        </ol>
      </div>
      <div className="aa-facts">
        <span>{Icon.check()}Single-use links</span><span>{Icon.check()}Expire in 1 hour</span><span>{Icon.check()}Email never revealed</span>
      </div>
    </section>
  );
}

const CONF_STEPS = [
  ['Create account', 'Done'],
  ['Check your email', 'Link valid for 24 hours'],
  ['Confirm', 'One click'],
  ['Sign in', 'Start using Attorney.AI'],
];
const CONF_ORDER = { sent: 1, request: 1, checking: 2, done: 3 };
const CONF_ICON = { sent: 'mailSent', request: 'mailSent', checking: 'mailSent', done: 'done', expired: 'hour' };
const CONF_HEAD = {
  sent: 'One last step.', request: 'Get a new link.', checking: 'Confirming…',
  done: 'Your email is confirmed.', expired: 'Let’s get you a fresh link.',
};

// Sign-up email confirmation: same tracker as recovery, its own four steps.
export function ConfirmVisual({ stage }) {
  const expired = stage === 'expired';
  const at = expired ? 1 : CONF_ORDER[stage] ?? 1;
  const fill = (Math.min(at, 3) / 3) * 75;
  return (
    <section className="aa-vis aa-rec" aria-label="Email confirmation progress">
      <div className="bgimg" style={{ backgroundImage: `url(${COURT})` }} aria-hidden="true" />
      <div className="shade" aria-hidden="true" />
      <div className={`aa-orb${expired ? ' warn' : ''}`} aria-hidden="true"><i /><i /><span>{Icon[CONF_ICON[stage] || 'mail'](64)}</span></div>
      <div className="head"><div className="eyeb">Confirm your email</div><h2>{CONF_HEAD[stage] || CONF_HEAD.sent}</h2></div>
      <div className="aa-track">
        <span className="fill" style={{ width: `${fill}%` }} aria-hidden="true" />
        <ol>
        {CONF_STEPS.map(([t, s], i) => {
          const c = expired && i === 1 ? 'warn' : (i < at || at === 3 ? 'done' : i === at ? 'now' : '');
          return (
            <li key={t} className={c} aria-current={c === 'now' || c === 'warn' ? 'step' : undefined}>
              <span className="tc">{c === 'done' ? Icon.check() : i + 1}</span>
              <b>{t}</b><small>{expired && i === 1 ? 'Link expired' : s}</small>
            </li>
          );
        })}
        </ol>
      </div>
      <div className="aa-facts">
        <span>{Icon.check()}Single-use link</span><span>{Icon.check()}Expires in 24 hours</span><span>{Icon.check()}Check spam if missing</span>
      </div>
    </section>
  );
}
