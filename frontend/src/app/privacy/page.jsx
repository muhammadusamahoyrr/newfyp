'use client';
import React from 'react';
import LegalDocument, { PRIVACY_VERSION } from '@/components/shared/LegalDocument';

const SECTIONS = [
  {
    id: 'collect', title: 'What we collect',
    body: [[
      'Account details: your name, email, phone number if you give one, and your password. The password is stored only as a one-way hash, never as text.',
      'For lawyers: Bar license number, practice areas, office address, fees, and any certificates or photo you upload during onboarding.',
      'What you write and upload: legal questions, intake answers, case details, messages and documents.',
      'Sign-in records: when you signed in and the browser you used, so you can see and end your sessions.',
      'When you agreed to these terms and this policy, and which versions.',
    ]],
  },
  {
    id: 'use', title: 'Why we use it',
    body: [[
      'To run your account and keep it secure.',
      'To answer your legal questions and to suggest lawyers who handle your kind of matter.',
      'To send you emails you need: confirming your address, resetting your password, and updates about your cases and agreements.',
    ]],
  },
  {
    id: 'ai', title: 'AI processing',
    body: [
      'To write an answer, the text of your question and the relevant case details are sent to an AI model. Depending on how the service is set up, that model runs on our own server or with an external AI provider. We do not use your data to advertise to you.',
    ],
  },
  {
    id: 'share', title: 'Who can see your information',
    body: [[
      'Lawyers see the details and documents you share with them, for example when you book a consultation or engage them.',
      'Clients see a lawyer\'s profile, including the lawyer\'s name, email, phone number, Bar license number, practice areas, office address, fees and ratings. Lawyer certificates and photos uploaded during onboarding are not shown to clients.',
      'The Attorney.AI admin team, when they need to run or support the service.',
    ], 'We do not sell your personal information.'],
  },
  {
    id: 'keep', title: 'How long we keep it',
    body: [
      'We keep your information while your account is open. When you close your account, your name, email, phone number and password are removed from it. Records other people depend on, such as a case or agreement you were part of, can remain without your personal details.',
      'An account cannot be closed while it still has open obligations, such as an active engagement. Settle or cancel those first.',
    ],
  },
  {
    id: 'security', title: 'Security',
    body: [
      'Passwords are hashed, sign-in sessions can be ended from your account, and email links for confirming your address or resetting your password work once and expire. No system is perfectly secure, so use a password you do not use anywhere else.',
    ],
  },
  {
    id: 'changes', title: 'Changes to this policy',
    body: [
      'When this policy changes, the version date above changes. Your account records the version you agreed to when you signed up.',
    ],
  },
];

export default function PrivacyPage() {
  return (
    <LegalDocument eyebrow="Privacy" title="Privacy Policy" version={PRIVACY_VERSION}
      intro="This policy explains what information Attorney.AI keeps about you, why, and who can see it."
      sections={SECTIONS} other={{ href: '/terms', label: 'Terms of Use' }} />
  );
}
