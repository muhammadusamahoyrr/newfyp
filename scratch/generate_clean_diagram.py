import html
import xml.etree.ElementTree as ET

def generate():
    # 5 Stages (Columns)
    # Col 1: STAGE 1 - INITIATION (x = 50, w = 290)
    # Col 2: STAGE 2 - STORY & EVIDENCE (x = 380, w = 310)
    # Col 3: STAGE 3 - AI CLARIFICATION (x = 730, w = 290)
    # Col 4: STAGE 4 - CONVERSION & AI REASONING (x = 1060, w = 420)
    # Col 5: STAGE 5 - CONFIRMATION & MATCHING (x = 1520, w = 310)
    
    # Layers (Y coordinates):
    # Title & Legend: y = 30 to 90
    # Layer 1: Client Frontend (UI Step): y = 120, h = 120
    # Layer 2: API Endpoints (FastAPI): y = 280, h = 110
    # Layer 3: Service Layer (Business Logic): y = 430, h = 140
    # Layer 4: Deep Processing / LangGraph: y = 610, h = 260
    # Layer 5: Data Persistence: y = 910, h = 120

    nodes = []
    edges = []

    # Title Banner
    nodes.append('''<mxCell id="title" value="&lt;div style=&quot;font-size:18px;font-weight:800;color:#0F172A;&quot;&gt;Attorney.AI — Legal Intake Architecture &amp; Execution Pipeline&lt;/div&gt;&lt;div style=&quot;font-size:12px;color:#64748B;margin-top:4px;&quot;&gt;End-to-end request lifecycle: From Client UI steps, FastAPI endpoints, and Core Services to LangGraph RAG reasoning &amp; Case Opening&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#CBD5E1;strokeWidth=1.5;shadow=1;arcSize=6;align=left;spacingLeft=18;" vertex="1" parent="1">
      <mxGeometry x="50" y="30" width="1780" height="60" as="geometry" />
    </mxCell>''')

    # Columns / Stages Background Containers (Subtle, clean cards)
    stages = [
        ("stage1", "STAGE 1: INITIATION & ROLE", 50, 290, "#EFF6FF", "#BFDBFE"),
        ("stage2", "STAGE 2: STORY, VOICE & EVIDENCE", 380, 310, "#EFF6FF", "#BFDBFE"),
        ("stage3", "STAGE 3: ADAPTIVE CLARIFICATION", 730, 290, "#EFF6FF", "#BFDBFE"),
        ("stage4", "STAGE 4: CONVERSION & AI REASONING", 1060, 420, "#F5F3FF", "#DDD6FE"),
        ("stage5", "STAGE 5: CONFIRMATION & MATCHING", 1520, 310, "#ECFDF5", "#A7F3D0")
    ]

    for sid, stitle, sx, sw, sfill, sstroke in stages:
        nodes.append(f'''<mxCell id="{sid}" value="  {stitle}" style="swimlane;startSize=32;fillColor={sstroke};strokeColor={sstroke};fontColor=#0F172A;fontStyle=1;fontSize=11;rounded=1;arcSize=6;shadow=1;swimlaneFillColor={sfill};collapsible=0;" vertex="1" parent="1">
          <mxGeometry x="{sx}" y="110" width="{sw}" height="950" as="geometry" />
        </mxCell>''')

    # --- STAGE 1 ELEMENTS ---
    nodes.append('''<mxCell id="s1_ui" value="&lt;b style=&quot;color:#0284C7;&quot;&gt;[UI] Step 1: About You&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:11px;color:#334155;margin-top:4px;&quot;&gt;• Select Province&lt;br/&gt;• Select Role (Plaintiff / Defendant)&lt;br/&gt;• Validation: Province required&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage1">
      <mxGeometry x="20" y="45" width="250" height="90" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s1_api" value="&lt;span style=&quot;background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;&quot;&gt;POST&lt;/span&gt; &lt;b&gt;/intake/start&lt;/b&gt;&lt;br/&gt;&lt;span style=&quot;background:#FEF3C7;color:#B45309;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;&quot;&gt;PATCH&lt;/span&gt; &lt;b&gt;/intake/{token}/step/1&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#64748B;margin-top:4px;&quot;&gt;• Rate limit: 10/min (start), 60/min (step)&lt;br/&gt;• Returns: session_token&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#94A3B8;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage1">
      <mxGeometry x="20" y="175" width="250" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s1_svc" value="&lt;b style=&quot;color:#0F172A;&quot;&gt;intake_service.py&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• Checks for resumable drafts&lt;br/&gt;• Generates secure session_token&lt;br/&gt;• Stores step1 province &amp;amp; role&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#94A3B8;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage1">
      <mxGeometry x="20" y="300" width="250" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s1_db" value="&lt;b style=&quot;color:#0369A1;&quot;&gt;MongoDB: intakes&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• session_token (unique index)&lt;br/&gt;• client_id &amp;amp; step1 data&lt;br/&gt;• completed = false&lt;/div&gt;" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;" vertex="1" parent="stage1">
      <mxGeometry x="20" y="800" width="250" height="90" as="geometry" />
    </mxCell>''')

    # --- STAGE 2 ELEMENTS ---
    nodes.append('''<mxCell id="s2_ui" value="&lt;b style=&quot;color:#0284C7;&quot;&gt;[UI] Step 2: Story &amp;amp; Evidence&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:11px;color:#334155;margin-top:4px;&quot;&gt;• Incident Story (min 5 words, 20 chars)&lt;br/&gt;• &lt;b&gt;120s Voice Input&lt;/b&gt; (WAV converter)&lt;br/&gt;• Evidence files (PDF / DOCX / JPG)&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage2">
      <mxGeometry x="20" y="45" width="270" height="90" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s2_api" value="&lt;span style=&quot;background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;&quot;&gt;POST&lt;/span&gt; &lt;b&gt;/voice/transcribe&lt;/b&gt;&lt;br/&gt;&lt;span style=&quot;background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;&quot;&gt;POST&lt;/span&gt; &lt;b&gt;/intake/{token}/evidence&lt;/b&gt;&lt;br/&gt;&lt;span style=&quot;background:#FEF3C7;color:#B45309;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;&quot;&gt;PATCH&lt;/span&gt; &lt;b&gt;/intake/{token}/step/2,3,4,5&lt;/b&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#94A3B8;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage2">
      <mxGeometry x="20" y="175" width="270" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s2_svc" value="&lt;b style=&quot;color:#0F172A;&quot;&gt;Media &amp;amp; Story Handlers&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• Whisper STT (Urdu / Roman / Eng)&lt;br/&gt;• MIME re-sniff &amp;amp; 10MB size limit&lt;br/&gt;• Saves story, outcome, urgency&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#94A3B8;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage2">
      <mxGeometry x="20" y="300" width="270" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s2_db" value="&lt;b style=&quot;color:#475569;&quot;&gt;Encrypted Disk Storage&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• uploads/evidence/{token}/{file_id}&lt;br/&gt;• Original evidence bytes stored&lt;br/&gt;• Auto-retention purge at 365 days&lt;/div&gt;" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#64748B;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;" vertex="1" parent="stage2">
      <mxGeometry x="20" y="800" width="270" height="90" as="geometry" />
    </mxCell>''')

    # --- STAGE 3 ELEMENTS ---
    nodes.append('''<mxCell id="s3_ui" value="&lt;b style=&quot;color:#0284C7;&quot;&gt;[UI] Step 3: Questions&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:11px;color:#334155;margin-top:4px;&quot;&gt;• AI asks up to 4 follow-up Qs&lt;br/&gt;• Dynamic chips ('I don't know')&lt;br/&gt;• 'Continue without questions' option&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage3">
      <mxGeometry x="20" y="45" width="250" height="90" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s3_api" value="&lt;span style=&quot;background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;&quot;&gt;POST&lt;/span&gt; &lt;b&gt;/intake/{token}/clarify&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#64748B;margin-top:4px;&quot;&gt;• Payload: {answer?, language?}&lt;br/&gt;• Returns: {question, done, round}&lt;br/&gt;• Rate limit: 12/min&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#94A3B8;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage3">
      <mxGeometry x="20" y="175" width="250" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s3_svc" value="&lt;b style=&quot;color:#0F172A;&quot;&gt;Clarification Engine&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• Generates context-aware questions&lt;br/&gt;• Capped at 5,000 chars per answer&lt;br/&gt;• Appends to clarification_qa array&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#94A3B8;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage3">
      <mxGeometry x="20" y="300" width="250" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s3_db" value="&lt;b style=&quot;color:#0369A1;&quot;&gt;MongoDB: intakes&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• Updates clarification_qa array&lt;br/&gt;• Saves current_step = 3&lt;br/&gt;• Ready for case conversion&lt;/div&gt;" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;" vertex="1" parent="stage3">
      <mxGeometry x="20" y="800" width="250" height="90" as="geometry" />
    </mxCell>''')

    # --- STAGE 4 ELEMENTS (DEEP AI PIPELINE) ---
    nodes.append('''<mxCell id="s4_ui" value="&lt;b style=&quot;color:#6D28D9;&quot;&gt;[Trigger] Click 'Build Case'&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:11px;color:#334155;margin-top:4px;&quot;&gt;• User requests case structuring&lt;br/&gt;• Displays 'Analysing your case...' loader&lt;br/&gt;• Passes output language (en / ur)&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage4">
      <mxGeometry x="20" y="45" width="380" height="90" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s4_api" value="&lt;span style=&quot;background:#EDE9FE;color:#6D28D9;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;&quot;&gt;POST&lt;/span&gt; &lt;b&gt;/api/v1/intake/{token}/convert&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#64748B;margin-top:4px;&quot;&gt;• Body: {language: en|ur, urgency?}&lt;br/&gt;• Rate limit: 6/min with epoch fence (prevents race)&lt;br/&gt;• Returns: {case_id, ai_case_type, type_was_corrected}&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage4">
      <mxGeometry x="20" y="175" width="380" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s4_svc" value="&lt;b style=&quot;color:#0F172A;&quot;&gt;Conversion Orchestrator (intake_service.py)&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;1. &lt;b&gt;claim_conversion&lt;/b&gt; (atomic lock, epoch++) ➔ Rejects parallel saves (409)&lt;br/&gt;2. &lt;b&gt;extract_evidence&lt;/b&gt; (PDF / DOCX subprocess text extraction &amp;amp; OCR)&lt;br/&gt;3. &lt;b&gt;_ai_classify_case_type&lt;/b&gt; (Keyword rules + LLM classification)&lt;br/&gt;4. &lt;b&gt;build_understanding&lt;/b&gt; (Compiles verified Fact Ledger from Q&amp;amp;A)&lt;br/&gt;5. &lt;b&gt;case_service.create_case(status='draft')&lt;/b&gt; ➔ Pins case_id to intake&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage4">
      <mxGeometry x="20" y="285" width="380" height="115" as="geometry" />
    </mxCell>''')

    # LangGraph Sub-Box inside Stage 4
    nodes.append('''<mxCell id="s4_graph_box" value="  LANGGRAPH INTAKE GRAPH (supervisor.py)" style="swimlane;startSize=26;fillColor=#6D28D9;strokeColor=#5B21B6;fontColor=#FFFFFF;fontStyle=1;fontSize=10;rounded=1;arcSize=4;shadow=1;swimlaneFillColor=#FFFFFF;collapsible=0;" vertex="1" parent="stage4">
      <mxGeometry x="20" y="420" width="380" height="230" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="g_node1" value="&lt;b&gt;1. retrieval_node&lt;/b&gt;&lt;br/&gt;Vector search &amp;amp; statute affinity" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=center;" vertex="1" parent="s4_graph_box">
      <mxGeometry x="15" y="38" width="160" height="42" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="g_node2" value="&lt;b&gt;2. retrieval_grader&lt;/b&gt;&lt;br/&gt;RRF &amp;amp; topic rules" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=center;" vertex="1" parent="s4_graph_box">
      <mxGeometry x="205" y="38" width="160" height="42" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="g_node3" value="&lt;b style=&quot;color:#C2410C;&quot;&gt;3. evidence_gate_node&lt;/b&gt;&lt;br/&gt;Jurisdiction check. If fails ➔ Facts only" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF7ED;strokeColor=#FDBA74;fontSize=10;align=center;" vertex="1" parent="s4_graph_box">
      <mxGeometry x="15" y="100" width="350" height="42" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="g_node4" value="&lt;b&gt;4. intake_node (LLM)&lt;/b&gt;&lt;br/&gt;Writes Summary, Law (≤6), Risk" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=center;" vertex="1" parent="s4_graph_box">
      <mxGeometry x="15" y="162" width="160" height="48" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="g_node5" value="&lt;b&gt;5. hallucination &amp;amp; 6. finalizer&lt;/b&gt;&lt;br/&gt;Citations verdict &amp;amp; currency link" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=center;" vertex="1" parent="s4_graph_box">
      <mxGeometry x="205" y="162" width="160" height="48" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s4_guards" value="&lt;b style=&quot;color:#0F172A;&quot;&gt;Post-Graph Guards &amp;amp; Storage Dispatch&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• &lt;b&gt;fact_fidelity&lt;/b&gt; (Checks facts against client words)&lt;br/&gt;• &lt;b&gt;apply_intake_cpc&lt;/b&gt; (Punjab-only CPC filter)&lt;br/&gt;• &lt;b&gt;localization&lt;/b&gt; (Urdu rendering if selected)&lt;br/&gt;• Saves structured case to mongo &amp;amp; marks intake complete&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage4">
      <mxGeometry x="20" y="670" width="380" height="95" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s4_db" value="&lt;b style=&quot;color:#6D28D9;&quot;&gt;ChromaDB &amp;amp; Provenance&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• Vector search across Pakistani Acts&lt;br/&gt;• Provenance audit record logged&lt;br/&gt;• SHA-256 output verification hash&lt;/div&gt;" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;" vertex="1" parent="stage4">
      <mxGeometry x="20" y="800" width="380" height="90" as="geometry" />
    </mxCell>''')

    # --- STAGE 5 ELEMENTS ---
    nodes.append('''<mxCell id="s5_ui" value="&lt;b style=&quot;color:#059669;&quot;&gt;[UI] Step 4 &amp;amp; Step 5: Review &amp;amp; Confirm&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:11px;color:#334155;margin-top:4px;&quot;&gt;• Review Summary, Applicable Laws, Risk&lt;br/&gt;• Urdu / English toggle &amp;amp; PDF Print export&lt;br/&gt;• Confirm/Edit Category (Civil, Family, etc.)&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage5">
      <mxGeometry x="20" y="45" width="270" height="90" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s5_api" value="&lt;span style=&quot;background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;&quot;&gt;GET&lt;/span&gt; &lt;b&gt;/intake/{token}&lt;/b&gt; (reads analysis)&lt;br/&gt;&lt;span style=&quot;background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;&quot;&gt;PATCH&lt;/span&gt; &lt;b&gt;/cases/{case_id}/confirm&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#64748B;margin-top:4px;&quot;&gt;• Finalizes case_type in MongoDB&lt;br/&gt;• Adds confirmed_at timestamp&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage5">
      <mxGeometry x="20" y="175" width="270" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s5_svc" value="&lt;b style=&quot;color:#0F172A;&quot;&gt;Case Confirmation Service&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• Transitions case: &lt;b&gt;draft ➔ open&lt;/b&gt;&lt;br/&gt;• Records client confirm event&lt;br/&gt;• Unlocks lawyer directory match&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage5">
      <mxGeometry x="20" y="300" width="270" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s5_next" value="&lt;b style=&quot;color:#059669;&quot;&gt;Post-Intake Destinations&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#334155;margin-top:4px;line-height:1.5;&quot;&gt;• &lt;b&gt;Find a Lawyer&lt;/b&gt; (/lawyers?case_id=...)&lt;br/&gt;• &lt;b&gt;Draft Document&lt;/b&gt; (/documents)&lt;br/&gt;• &lt;b&gt;Track Case&lt;/b&gt; (/tracking)&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ECFDF5;strokeColor=#A7F3D0;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;" vertex="1" parent="stage5">
      <mxGeometry x="20" y="440" width="270" height="85" as="geometry" />
    </mxCell>''')

    nodes.append('''<mxCell id="s5_db" value="&lt;b style=&quot;color:#059669;&quot;&gt;MongoDB: cases&lt;/b&gt;&lt;br/&gt;&lt;div style=&quot;font-size:10px;color:#475569;margin-top:4px;&quot;&gt;• Status updated: &lt;b&gt;open&lt;/b&gt;&lt;br/&gt;• ai_summary &amp;amp; actions stored&lt;br/&gt;• Case ready for consultation &amp;amp; hire&lt;/div&gt;" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;" vertex="1" parent="stage5">
      <mxGeometry x="20" y="800" width="270" height="90" as="geometry" />
    </mxCell>''')

    # --- CLEAN CONNECTING ARROWS ---
    # Top Sequential Flow (Left-to-Right between UI Steps)
    edges.append('''<mxCell id="e_ui1_2" edge="1" source="s1_ui" target="s2_ui" parent="1" style="strokeColor=#0284C7;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e_ui2_3" edge="1" source="s2_ui" target="s3_ui" parent="1" style="strokeColor=#0284C7;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e_ui3_4" edge="1" source="s3_ui" target="s4_ui" parent="1" style="strokeColor=#6D28D9;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e_ui4_5" edge="1" source="s4_ui" target="s5_ui" parent="1" style="strokeColor=#059669;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')

    # Stage 1 Vertical (UI ➔ API ➔ SVC ➔ DB)
    edges.append('''<mxCell id="e1_v1" edge="1" source="s1_ui" target="s1_api" parent="stage1" style="strokeColor=#0284C7;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e1_v2" edge="1" source="s1_api" target="s1_svc" parent="stage1" style="strokeColor=#0284C7;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e1_v3" edge="1" source="s1_svc" target="s1_db" parent="stage1" style="strokeColor=#0284C7;strokeWidth=2;dashed=1;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')

    # Stage 2 Vertical (UI ➔ API ➔ SVC ➔ Disk)
    edges.append('''<mxCell id="e2_v1" edge="1" source="s2_ui" target="s2_api" parent="stage2" style="strokeColor=#0284C7;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e2_v2" edge="1" source="s2_api" target="s2_svc" parent="stage2" style="strokeColor=#0284C7;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e2_v3" edge="1" source="s2_svc" target="s2_db" parent="stage2" style="strokeColor=#64748B;strokeWidth=2;dashed=1;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')

    # Stage 3 Vertical (UI ➔ API ➔ SVC ➔ DB)
    edges.append('''<mxCell id="e3_v1" edge="1" source="s3_ui" target="s3_api" parent="stage3" style="strokeColor=#0284C7;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e3_v2" edge="1" source="s3_api" target="s3_svc" parent="stage3" style="strokeColor=#0284C7;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e3_v3" edge="1" source="s3_svc" target="s3_db" parent="stage3" style="strokeColor=#0284C7;strokeWidth=2;dashed=1;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')

    # Stage 4 Vertical (UI ➔ API ➔ SVC ➔ LangGraph ➔ Guards ➔ DB)
    edges.append('''<mxCell id="e4_v1" edge="1" source="s4_ui" target="s4_api" parent="stage4" style="strokeColor=#6D28D9;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e4_v2" edge="1" source="s4_api" target="s4_svc" parent="stage4" style="strokeColor=#6D28D9;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e4_v3" edge="1" source="s4_svc" target="s4_graph_box" parent="stage4" style="strokeColor=#6D28D9;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e4_v4" edge="1" source="s4_graph_box" target="s4_guards" parent="stage4" style="strokeColor=#6D28D9;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e4_v5" edge="1" source="s4_guards" target="s4_db" parent="stage4" style="strokeColor=#6D28D9;strokeWidth=2;dashed=1;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')

    # LangGraph Inner Chain
    edges.append('''<mxCell id="eg_1_2" edge="1" source="g_node1" target="g_node2" parent="s4_graph_box" style="strokeColor=#7C3AED;strokeWidth=1.5;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="eg_2_3" edge="1" source="g_node2" target="g_node3" parent="s4_graph_box" style="strokeColor=#7C3AED;strokeWidth=1.5;exitX=0.5;exitY=1;entryX=0.5;entryY=0;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="eg_3_4" edge="1" source="g_node3" target="g_node4" parent="s4_graph_box" style="strokeColor=#EA580C;strokeWidth=1.5;exitX=0.25;exitY=1;entryX=0.5;entryY=0;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="eg_4_5" edge="1" source="g_node4" target="g_node5" parent="s4_graph_box" style="strokeColor=#7C3AED;strokeWidth=1.5;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')

    # Stage 5 Vertical (UI ➔ API ➔ SVC ➔ Next Actions ➔ DB)
    edges.append('''<mxCell id="e5_v1" edge="1" source="s5_ui" target="s5_api" parent="stage5" style="strokeColor=#059669;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e5_v2" edge="1" source="s5_api" target="s5_svc" parent="stage5" style="strokeColor=#059669;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e5_v3" edge="1" source="s5_svc" target="s5_next" parent="stage5" style="strokeColor=#059669;strokeWidth=2;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')
    edges.append('''<mxCell id="e5_v4" edge="1" source="s5_next" target="s5_db" parent="stage5" style="strokeColor=#059669;strokeWidth=2;dashed=1;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')

    # Connecting AI Guards (Stage 4) to Draft Case (Stage 5 DB)
    edges.append('''<mxCell id="e_ai_to_case" edge="1" source="s4_guards" target="s5_db" parent="1" style="strokeColor=#059669;strokeWidth=2;dashed=1;exitX=1;exitY=0.5;entryX=0;entryY=0.5;">
      <mxGeometry relative="1" as="geometry" />
    </mxCell>''')

    xml_content = f'''<mxfile host="app.diagrams.net" modified="2026-10-20T22:30:00.000Z" agent="Antigravity Enterprise Pipeline" version="22.0.0" type="device">
  <diagram id="attorney-ai-intake-pipeline" name="Legal Intake - Clean Pipeline Flow">
    <mxGraphModel dx="1800" dy="1200" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1900" pageHeight="1200" background="#F8FAFC" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        {' '.join(nodes)}
        {' '.join(edges)}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>'''

    # Validate XML
    ET.fromstring(xml_content)
    print("SUCCESS: Generated XML is 100% valid!")
    with open("docs/flows/legal_intake_clean.drawio", "w", encoding="utf-8") as f:
        f.write(xml_content)

generate()
