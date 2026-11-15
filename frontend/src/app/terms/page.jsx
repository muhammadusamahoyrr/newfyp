'use client';
import React from 'react';
import LegalDocument, { TERMS_VERSION } from '@/components/shared/LegalDocument';

const SECTIONS = [
  {
    id: 'service', title: 'What Attorney.AI is',
    body: [
      'Attorney.AI gives general legal information about Pakistani law and helps people find and work with lawyers. It is not a law firm and it does not give legal advice.',
      'Answers written by the AI can be wrong or out of date. Check the sources it shows, and speak to a qualified lawyer before you act on anything important.',
    ],
  },
  {
    id: 'account', title: 'Your account',
    body: [[
      'Give your real name and an email address you own. New accounts confirm their email before they can sign in.',
      'Keep your password private. You are responsible for what is done with your account.',
      'One account per person. Do not sign up as somebody else.',
    ]],
  },
  {
    id: 'lawyers', title: 'Lawyers on the platform',
    body: [
      'A lawyer listed on Attorney.AI is a registered account that has entered a Bar license number and at least one practice area. Attorney.AI does not check these details with any Bar Council. Confirm a lawyer\'s enrolment yourself before you hire them.',
      'Lawyers are responsible for the advice they give and the work they do. Fees are set by each lawyer and agreed between the lawyer and the client.',
    ],
  },
  {
    id: 'content', title: 'What you upload and write',
    body: [
      'Only upload documents you have the right to share. Your documents and case details are shown to the people you choose to share them with, such as a lawyer you engage, and to the Attorney.AI admin team when they need to run the service.',
    ],
  },
  {
    id: 'use', title: 'Acceptable use',
    body: [[
      'Do not use Attorney.AI for anything unlawful, to harass anyone, or to pretend to be someone else.',
      'Do not try to get into accounts or data that are not yours, or to disrupt the service.',
    ]],
  },
  {
    id: 'ending', title: 'Closing your account',
    body: [
      'You can close your account from your settings. The admin team can deactivate an account that breaks these terms.',
    ],
  },
  {
    id: 'changes', title: 'Changes to these terms',
    body: [
      'When these terms change, the version date above changes. Your account records the version you agreed to when you signed up.',
    ],
  },
  {
    // The licence asks for the author to be named; the sign-in pages show the photo without a caption.
    id: 'credits', title: 'Image credits',
    body: [[
      'Lahore High Court, used on the sign-in pages: photo by MariyamAftab, licensed CC BY-SA 4.0 (Wikimedia Commons). Shown recoloured.',
      'Videos on the sign-in pages: Pexels (Pexels License).',
    ]],
  },
];

export default function TermsPage() {
  return (
    <LegalDocument eyebrow="Terms" title="Terms of Use" version={TERMS_VERSION}
      intro="These terms explain what Attorney.AI does, what it does not do, and what we expect from everyone who uses it."
      sections={SECTIONS} other={{ href: '/privacy', label: 'Privacy Policy' }} />
  );
}
