'use client';
import React from 'react';
import PublicLayout from '@/components/shared/PublicLayout';

/* The /terms and /privacy pages (2026-10-18). Their versions must match
 * TERMS_VERSION / PRIVACY_VERSION in backend app/core/constants.py, which
 * registration stores with the account; bump both together when a text changes.
 * Every statement here describes what the code actually does — a claim the
 * product cannot back does not belong in a document people agree to. */
export const TERMS_VERSION = '2026-10-18';
export const PRIVACY_VERSION = '2026-10-18';

export function LegalDocument({ eyebrow, title, version, intro, sections, other }) {
  return (
    <PublicLayout>
      <section className="pt-32 pb-10 bg-gradient-to-b from-[#f4f9f8] to-white">
        <div className="mx-auto max-w-3xl px-6">
          <span className="inline-block bg-[#E8F5E9] text-[#025E56] text-xs font-bold uppercase tracking-widest px-4 py-1.5 rounded-full mb-5">
            {eyebrow}
          </span>
          <h1 className="text-4xl font-bold text-[#004743] sm:text-5xl leading-tight">{title}</h1>
          <p className="mt-3 text-sm text-gray-500">Version {version}</p>
          <div role="note" className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm leading-relaxed text-amber-900">
            <b>Draft for a university project.</b> Attorney.AI is a final-year project at COMSATS University
            Islamabad. This text has not been reviewed by a lawyer and is not a legally reviewed agreement.
          </div>
          <p className="mt-6 text-base leading-relaxed text-gray-600">{intro}</p>
        </div>
      </section>

      <section className="pb-20 bg-white">
        <div className="mx-auto max-w-3xl px-6">
          <nav aria-label="On this page" className="mb-10 rounded-2xl border border-[#E8F5E9] bg-[#f4f9f8] px-5 py-4">
            <p className="text-xs font-bold uppercase tracking-widest text-[#025E56] mb-2">On this page</p>
            <ol className="grid gap-1 sm:grid-cols-2 text-sm">
              {sections.map((s, i) => (
                <li key={s.id}><a className="text-[#004743] hover:underline" href={`#${s.id}`}>{i + 1}. {s.title}</a></li>
              ))}
            </ol>
          </nav>
          {sections.map((s, i) => (
            <article key={s.id} id={s.id} className="mb-9 scroll-mt-28">
              <h2 className="text-xl font-bold text-[#004743] mb-3">{i + 1}. {s.title}</h2>
              {s.body.map((p, j) => Array.isArray(p)
                ? <ul key={j} className="list-disc pl-6 space-y-1.5 text-gray-700 leading-relaxed mb-3">{p.map((li, k) => <li key={k}>{li}</li>)}</ul>
                : <p key={j} className="text-gray-700 leading-relaxed mb-3">{p}</p>)}
            </article>
          ))}
          <p className="mt-12 border-t border-gray-100 pt-6 text-sm text-gray-500">
            See also: <a className="font-semibold text-[#025E56] hover:underline" href={other.href}>{other.label}</a>
          </p>
        </div>
      </section>
    </PublicLayout>
  );
}

export default LegalDocument;
