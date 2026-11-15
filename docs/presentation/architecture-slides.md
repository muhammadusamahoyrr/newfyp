# Attorney.AI — Presentation Slides (content)

> Content for the FYP 60% evaluation: **Title & Team, Problem Statement, Proposed Solution, Architecture Diagram**.
> Covers only modules that are complete and visible in the UI: Legal Intake, AI Chat (client), AI Research (lawyer), Document Drafting & Review, Appointments → Hire → Case, Messaging & Notifications, Voice input.
> Each slide = title + diagram + 3–6 bullets. "Say" = what to say while presenting.
> **[ ]** = fill in yourself (names and roles are not recorded anywhere in the project).

---

## Slide A — Project Title & Team

**Attorney.AI**
*An AI-Powered Legal Assistance and Lawyer Collaboration Platform for Pakistan*

COMSATS University Islamabad · Department of Computer Science · Final Year Project

| Member | Registration No. | Role |
|---|---|---|
| Muhammad Usama | SP23-BCS-069 | [ e.g. Team Lead — Backend (FastAPI), AI pipelines (RAG / LangGraph), integration ] |
| [ Member 2 name ] | [ SP23-BCS-xxx ] | [ e.g. Frontend — client & lawyer portals (Next.js / React) ] |
| [ Member 3 name ] | [ SP23-BCS-xxx ] | [ e.g. Legal corpus, testing & documentation ] |

**Supervisor:** [ name ]

> Tip: name roles by **module** (e.g. "Appointments & Video", "Legal Intake"). The "Individual Contribution" slide later has to match these roles.

---

## Slide B — Problem Statement

**The problem**
- **Legal information is hard to reach.** Pakistani statutes (PPC, CrPC, Family Laws, Constitution …) are long and technical. An ordinary citizen cannot tell which law applies to their situation.
- **Language barrier.** Most citizens think and speak in Urdu or Roman Urdu, but laws and legal advice are mostly in English.
- **Finding the right lawyer is hard.** People rely on word of mouth, with no easy way to compare lawyers by area of practice, province or availability.
- **The first steps are confusing and costly.** People do not know which facts or documents matter, so the first consultation is spent just explaining the situation.
- **Lawyers lose time on repetitive work:** drafting standard documents, looking up sections, managing appointments and client communication across phone and WhatsApp.
- **Generic AI chatbots are risky for legal questions:** they can invent sections and citations, and they do not know Pakistani law specifically.

**Intended users (actors)**

| Actor | Who | Needs |
|---|---|---|
| **Client** | Ordinary citizen with a legal problem (family, criminal, civil, property, tenancy) | Understand their position in simple words, prepare their case, find and book a lawyer, get documents drafted and reviewed |
| **Lawyer** | Registered advocate | Manage consultations and clients, research the law quickly, draft documents faster, review client documents |
| **Admin** | Platform operator | Manage users and lawyer registrations |

*External systems:* LLM providers, speech-to-text, video-call service, email.

**Say:** "Our users are ordinary Pakistani citizens who need legal help, and the lawyers who serve them. The gap between the two is information, language and access. Attorney.AI closes that gap."

---

## Slide C — Proposed Solution

**Attorney.AI is one web platform with two portals, client and lawyer, that takes a legal problem from "I don't understand my situation" to "a lawyer is working on my case".**

```
Client describes problem ──► AI explains the law ──► Structured case ──► Find & book lawyer
   (text or voice,            (grounded in Pakistani     (Legal Intake)      (Appointments,
    English / Urdu)            statutes, with citations)                      video call)
                                                                                   │
        Documents drafted & reviewed ◄── Case managed together ◄── Hire lawyer ◄───┘
```

| Problem | How Attorney.AI solves it |
|---|---|
| Law is hard to understand | **AI Legal Chat** answers in plain language from a library of Pakistani statutes, cites the exact sections, and checks every claim against its source |
| Language barrier | Questions in **English, Urdu or Roman Urdu**; **voice input** for Urdu speakers |
| Confusing first steps | **Legal Intake** turns the client's story into a structured case: summary, applicable laws, recommended actions, risk level |
| Finding a lawyer | **Lawyer directory and matching** by area of law and province; **online booking** with an in-app **video consultation** |
| Hiring and case tracking | **Hire flow** (lawyer proposes terms, client accepts), then a shared **case** with meetings, messages and documents |
| Document work | **Templates + AI drafting** for clients and lawyers, with versions, PDF output and a **lawyer review / approval** loop |
| Lawyer workload | **AI Research assistant**, **Draft with AI**, a dashboard of pending actions, a clients page |
| Untrustworthy AI | **Retrieval-first design:** search the law, grade the evidence, then answer, ask or refuse. A hallucination check runs on every answer, and every answer is audited |

**Say:** "Attorney.AI is not just a chatbot. The AI explains the law and prepares the case, and then the platform connects the client to a real lawyer for the consultation, hiring, case and documents, all in one place."

---

## Slide 1 — System Architecture (Overview)

**Diagram (redraw as boxes in PowerPoint, top to bottom):**

```
┌──────────────────────── USERS ────────────────────────┐
│        Client (citizen)              Lawyer           │
└───────────────────────────┬───────────────────────────┘
                            │  Browser
┌───────────────────────────▼───────────────────────────┐
│  FRONTEND — Next.js 15 + React 19                      │
│  Client portal: Intake · AI Chat · Documents ·         │
│                 Lawyers · Appointments · Tracking      │
│  Lawyer portal: Dashboard · AI Research · Drafting ·   │
│                 Appointments · Clients · Cases         │
└──────────────┬─────────────────────────┬──────────────┘
     REST /api/v1 (JSON)          WebSockets
     via Next.js proxy            (AI chat stream, live notifications)
┌──────────────▼─────────────────────────▼──────────────┐
│  BACKEND — FastAPI (Python)                            │
│  Auth & Roles │ Intake │ Chat/Research │ Drafting &    │
│  Review │ Appointments & Video │ Hire & Cases │        │
│  Messaging & Notifications │ Background scheduler      │
│  ┌──────────────────────────────────────────────────┐ │
│  │ AI LAYER — LangGraph pipelines                   │ │
│  │ Chat/Research RAG graph · Intake graph ·          │ │
│  │ Drafting stream + Draft Guard                     │ │
│  └──────────────────────────────────────────────────┘ │
└───┬──────────────┬──────────────┬──────────────┬──────┘
    ▼              ▼              ▼              ▼
 MongoDB        ChromaDB        Redis        File storage
 (users, cases, (Pakistani law  (answer cache, (evidence,
  appointments,  corpus vectors, pub/sub,       generated
  documents,     4 collections)  scheduler      PDFs)
  audit trail)                   locks)
                            │
┌───────────────────────────▼───────────────────────────┐
│ EXTERNAL SERVICES                                      │
│ LLM APIs (Groq → Cerebras → Gemini failover)           │
│ Speech-to-text (Groq Whisper → local faster-whisper)   │
│ Video calls (Daily.co) · Email (SMTP)                  │
└────────────────────────────────────────────────────────┘
```

**Bullets:**
- **3-tier web architecture:** Next.js frontend → FastAPI backend → databases.
- **Two portals, one backend:** role checks (client / lawyer) on every API call.
- **AI layer** built as LangGraph pipelines. Each answer goes through retrieval, grading, generation and a hallucination check.
- **Three data stores**, each with one job: MongoDB for app data, ChromaDB for the law library, Redis for cache and real-time events.
- **External AI** with automatic failover, so if one provider is down another one answers.

**Say:** "The client and the lawyer use two separate portals. Both talk to one FastAPI backend through REST and WebSockets. The AI work happens in LangGraph pipelines, which search our Pakistani law library in ChromaDB before an LLM writes anything."

---

## Slide 2 — How a Request Travels (end to end)

```
Browser ──► Next.js proxy (/api/v1) ──► FastAPI route
                                          │  1. Auth: JWT check + role (client/lawyer)
                                          │  2. Validation (Pydantic schemas)
                                          ▼
                                       Service layer (business rules)
                                          │
                       ┌──────────────────┼──────────────────┐
                       ▼                  ▼                  ▼
                   Repository         AI pipeline        Notification
                   (MongoDB)          (LangGraph)        (Mongo + Redis pub/sub
                                                          → WebSocket → bell icon)
```

- **Layers:** Route → Service → Repository. Routes stay thin; the rules live in services.
- **Security:** short-lived access token plus a refresh token that is rotated on every use, with a server-side session that can be revoked. Every route checks the role.
- **Real-time:** an event is saved in MongoDB, published on Redis, and pushed over WebSocket to the right user (new appointment, message, review).
- **Safe retries:** create actions take an idempotency key, so a double click never makes two records.

---

## Slide 3 — AI Chat & Research Pipeline (RAG with LangGraph)

```
User question
   │
   ▼
Gatekeeper ──► blocks prompt-injection / misuse
   │
Classifier + Triage ──► language (EN / Urdu / Roman Urdu),
   │                    case type, province
   │──► (missing facts?) Clarification question to user
   ▼
Fact-gap check ──► Answer cache (Redis) ── hit ──► Finalizer
   │ miss
   ▼
Retrieval ──► Hybrid search: BM25 (0.6) + vector search (0.4)
   │          multilingual-e5 embeddings, ChromaDB, filtered by
   │          case type & province
   ▼
Retrieval Grader ──► scores relevance of each law section
   ▼
Decision Node ──► ANSWER / ASK / REFUSE (expected-loss rule)
   ▼
Generation (LLM) ──► structured answer citing law sections [1][2]
   ▼
Hallucination Check ──► every claim matched to a retrieved source
   │                    (unsupported → regenerate or warn)
   ▼
Finalizer ──► citations, disclaimer, audit record, cache write
```

- **Same engine, two surfaces:**
  - **Client chat:** plain language, WebSocket streaming, lawyer suggestions.
  - **Lawyer research:** legal depth, can be tied to a case, audit panel.
- **Grounded answers only:** the LLM answers from retrieved Pakistani statutes, not from memory. Every claim is checked against its source.
- **Honest fallback:** when the library has no support, the answer is clearly labelled *General information*, or the question is refused. No fake citations.
- **Audit trail (provenance):** sources, model used, and an answer hash are saved for every answer.

**Say:** "We do not trust the LLM by itself. First we search our law library, then a grader scores the evidence, then a decision node decides whether to answer, ask a question or refuse. After the answer is written, a hallucination check matches every claim to a source."

---

## Slide 4 — Legal Intake Pipeline

```
Client: 5-step form
 1 About you → 2 Story (+ voice, evidence files) → 3 AI questions → 4 Review → 5 Confirm
                                     │                    │
                       clarifying questions (LLM,          │ "Build my case"
                       client facts only, max 4)           ▼
                                              Intake graph (LangGraph)
   Retrieval → Grader → Evidence Gate → Intake LLM → Hallucination check → Finalizer
                                                             │
                                                             ▼
                                Structured case: summary, applicable laws,
                                recommended actions, risk level, grounding status
                                                             │
                                                             ▼
                                Case created (draft → open) → "Find a lawyer"
```

- **Turns a client's story into a structured legal case** that a lawyer can act on.
- **Evidence Gate:** the analysis only cites law that the search actually found. No admissible law means no citations and no risk score.
- **Safety:** checks that facts in the summary match the client's own words. Urdu output is available.
- **Saved progress:** the client can leave and resume later, even on another device.

---

## Slide 5 — Document Drafting & Review Pipeline

```
CLIENT                                      LAWYER
Template (fill fields)  or  "Draft with AI"     "Draft with AI" in editor
        │                         │                     │
        ▼                         ▼                     ▼
  Document V2 service      Draft plan (LLM asks   /ai/draft/stream (SSE)
  versioned revisions      ≤3 questions)          RAG: law sections retrieved
  v1, v2, v3 …                    │                     │
        │◄────────────────────────┘                     ▼
        ▼                                         Draft Guard: checks every
  PDF render + text (immutable revision)          citation, jurisdiction rules
        │                                               │
        ▼                                               ▼
  Send to lawyer for review ──────────────► Review queue
                                            Approve / Return / Return with edits
        ◄───────────────────────────────────────────────┘
  Client sees result (approval tied to the exact version reviewed)
```

- **Versioning:** every save is a new, read-only revision (vN). Old versions can be viewed or restored.
- **AI drafting is guarded:** a citation that cannot be verified is flagged or removed. The lawyer always reviews before anything is used.
- **Review loop:** the lawyer can approve, return, or edit and return. An approval is tied to the exact revision the lawyer saw, so a later edit needs approval again.

---

## Slide 6 — Appointment → Hire → Case Flow

```
Client books slot ──► PENDING ──► Lawyer: Accept / Decline / Suggest time
(30-min slots, clash-proof)            │
                                   CONFIRMED ──► reminders (scheduler)
                                       │
                                  Video call (Daily.co) + messages + files
                                       │
                          Lawyer records outcome: COMPLETED / NO-SHOW
                                       │
Client "Request to hire" ──► Lawyer sends terms (fee) ──► Client accepts
                                       │
                                CASE assigned to lawyer
                     (case meetings, documents, messages, hearings)
```

- **State machine:** every status change follows an allowed-transitions table, so no illegal jumps.
- **Clash-proof booking:** a unique slot index in MongoDB means two clients can never get the same lawyer slot.
- **Hire needs a completed consultation:** the client meets the lawyer first, then the lawyer proposes terms and the client accepts.
- **Lawyer dashboard** counts pending requests, outcomes to record and hire requests from one shared query, so every page shows the same numbers.

---

## Slide 7 — Tech Stack per Layer (one-line summary)

| Layer | Technology | Why |
|---|---|---|
| Frontend | Next.js 15, React 19 | Two role-based portals, fast page switches |
| Backend API | FastAPI (Python), Pydantic | Async, typed validation, auto API docs |
| AI orchestration | LangGraph + LangChain | Pipelines as graphs: branch, retry, ask the user mid-flow |
| LLMs | Groq `gpt-oss-120b` / `gpt-oss-20b` (failover: Cerebras, Gemini; optional local Ollama) | Fast inference; failover keeps the demo alive |
| Embeddings | `intfloat/multilingual-e5-base` | English + Urdu legal text in one vector space |
| Vector DB | ChromaDB (civil / criminal / family / constitutional) | Semantic search over Pakistani statutes |
| Database | MongoDB (replica set) | Flexible documents + transactions for bookings/approvals |
| Cache / real-time | Redis | Answer cache, WebSocket pub/sub, scheduler locks |
| Speech-to-text | Groq Whisper large-v3 → local faster-whisper | Urdu and English voice input |
| Video | Daily.co | In-app consultation calls |

---

### Tips for the slides
- Slide 1 is the main architecture slide. Draw it as **coloured layers**: Users, then Frontend, then Backend + AI layer, then Data stores, then External services.
- Slides 3 to 6 can be one slide each, or put on backup slides for technical questions.
- Use **arrows labelled REST / WebSocket** between frontend and backend. Examiners look for "how components interact".
