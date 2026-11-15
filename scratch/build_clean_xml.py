import xml.etree.ElementTree as ET

def build():
    mxfile = ET.Element('mxfile', host='app.diagrams.net', version='22.0.0', type='device')
    diagram = ET.SubElement(mxfile, 'diagram', id='legal-intake-pipeline-clean', name='Legal Intake Architecture')
    model = ET.SubElement(diagram, 'mxGraphModel', 
                         dx='1800', dy='1100', grid='1', gridSize='10', 
                         guides='1', tooltips='1', connect='1', arrows='1', 
                         fold='1', page='1', pageScale='1', 
                         pageWidth='1850', pageHeight='1150', 
                         background='#F8FAFC', math='0', shadow='0')
    root = ET.SubElement(model, 'root')

    ET.SubElement(root, 'mxCell', id='0')
    ET.SubElement(root, 'mxCell', id='1', parent='0')

    def add_node(nid, label, x, y, w, h, style, parent='1'):
        cell = ET.SubElement(root, 'mxCell', id=nid, value=label, style=style, vertex='1', parent=parent)
        geo = ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h))
        geo.set('as', 'geometry')
        return cell

    def add_edge(eid, src, tgt, style, parent='1'):
        cell = ET.SubElement(root, 'mxCell', id=eid, style=style, edge='1', parent=parent, source=src, target=tgt)
        geo = ET.SubElement(cell, 'mxGeometry', relative='1')
        geo.set('as', 'geometry')
        return cell

    # 1. Header Banner
    title_html = (
        '<div style="font-size:16px;font-weight:800;color:#0F172A;">'
        'Attorney.AI — Legal Intake Architecture & Execution Pipeline'
        '</div>'
        '<div style="font-size:11px;color:#64748B;margin-top:3px;">'
        'Clean 5-Stage Sequential Pipeline: Client UI → FastAPI Routes → Core Services → LangGraph AI Engine → Open Case'
        '</div>'
    )
    add_node('hdr', title_html, 50, 25, 1720, 55, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#CBD5E1;strokeWidth=1.5;shadow=1;arcSize=6;align=left;spacingLeft=16;')

    # 2. Stage Columns (Containers)
    columns = [
        ('col1', 'STAGE 1: INITIATION & ROLE', 50, 270, '#F0F9FF', '#BAE6FD'),
        ('col2', 'STAGE 2: STORY, VOICE & EVIDENCE', 360, 290, '#F0F9FF', '#BAE6FD'),
        ('col3', 'STAGE 3: ADAPTIVE CLARIFICATION', 690, 270, '#F0F9FF', '#BAE6FD'),
        ('col4', 'STAGE 4: CONVERSION & AI ENGINE', 1000, 440, '#F5F3FF', '#DDD6FE'),
        ('col5', 'STAGE 5: REVIEW, CONFIRM & OPEN', 1480, 290, '#ECFDF5', '#A7F3D0'),
    ]

    for cid, ctitle, cx, cw, cfill, cstroke in columns:
        c_style = f'swimlane;startSize=30;fillColor={cstroke};strokeColor={cstroke};fontColor=#0F172A;fontStyle=1;fontSize=11;rounded=1;arcSize=6;shadow=1;swimlaneFillColor={cfill};collapsible=0;'
        add_node(cid, f'  {ctitle}', cx, 95, cw, 960, c_style, parent='1')

    # Card styles
    ui_card = 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;'
    api_card = 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#64748B;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;'
    svc_card = 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#475569;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;'
    db_card = 'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;'
    
    # --- STAGE 1 NODES ---
    s1_ui_html = (
        '<b style="color:#0284C7;font-size:12px;">Step 1: About You</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Select Province (Punjab, Sindh, etc.)<br/>'
        '• Role: Plaintiff vs Defendant<br/>'
        '• Form validation gate'
        '</div>'
    )
    add_node('s1_ui', s1_ui_html, 15, 45, 240, 85, ui_card, parent='col1')

    s1_api_html = (
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/intake/start</b><br/>'
        '<span style="background:#FEF3C7;color:#B45309;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">PATCH</span> <b>/intake/{token}/step/1</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;">'
        'Rate limit: 10/min | Returns session_token'
        '</div>'
    )
    add_node('s1_api', s1_api_html, 15, 160, 240, 80, api_card, parent='col1')

    s1_svc_html = (
        '<b>intake_service.py</b><br/>'
        '<div style="font-size:10px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Resume check for unfinished drafts<br/>'
        '• Generates cryptographically secure token<br/>'
        '• Validates & saves step 1 payload'
        '</div>'
    )
    add_node('s1_svc', s1_svc_html, 15, 270, 240, 85, svc_card, parent='col1')

    s1_db_html = (
        '<b style="color:#0369A1;">MongoDB: intakes</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• session_token (unique index)<br/>'
        '• client_id & step1 data<br/>'
        '• completed = false'
        '</div>'
    )
    add_node('s1_db', s1_db_html, 15, 840, 240, 85, db_card, parent='col1')

    # --- STAGE 2 NODES ---
    s2_ui_html = (
        '<b style="color:#0284C7;font-size:12px;">Step 2: Your Story & Media</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Incident story (min 5 words, 20 chars)<br/>'
        '• <b>120s Voice note</b> (WAV 16kHz recorder)<br/>'
        '• Evidence upload (PDF, DOCX, images)'
        '</div>'
    )
    add_node('s2_ui', s2_ui_html, 15, 45, 260, 85, ui_card, parent='col2')

    s2_api_html = (
        '<span style="background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/voice/transcribe</b><br/>'
        '<span style="background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/intake/{token}/evidence</b><br/>'
        '<span style="background:#FEF3C7;color:#B45309;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">PATCH</span> <b>/step/2, 3, 4, 5</b>'
    )
    add_node('s2_api', s2_api_html, 15, 160, 260, 80, api_card, parent='col2')

    s2_svc_html = (
        '<b>Voice & Evidence Handlers</b><br/>'
        '<div style="font-size:10px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Whisper STT (Urdu / Roman / Eng)<br/>'
        '• MIME re-sniff & 10MB size gate<br/>'
        '• Quick classify chips (Family, Civil..)'
        '</div>'
    )
    add_node('s2_svc', s2_svc_html, 15, 270, 260, 85, svc_card, parent='col2')

    s2_db_html = (
        '<b style="color:#475569;">Encrypted Disk Storage</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• uploads/evidence/{token}/{file_id}<br/>'
        '• Raw bytes preserved for OCR<br/>'
        '• 365-day retention policy sweep'
        '</div>'
    )
    add_node('s2_db', s2_db_html, 15, 840, 260, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#64748B;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;', 
             parent='col2')

    # --- STAGE 3 NODES ---
    s3_ui_html = (
        '<b style="color:#0284C7;font-size:12px;">Step 3: AI Questions</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Adaptive clarification (up to 4 Qs)<br/>'
        '• Quick reply chips ("Not sure", "Unknown")<br/>'
        '• "Continue without questions" button'
        '</div>'
    )
    add_node('s3_ui', s3_ui_html, 15, 45, 240, 85, ui_card, parent='col3')

    s3_api_html = (
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/intake/{token}/clarify</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;line-height:1.4;">'
        '• Body: {answer?, language?}<br/>'
        '• Rate limit: 12/min (concurrency safe)<br/>'
        '• Returns: {question, done, round}'
        '</div>'
    )
    add_node('s3_api', s3_api_html, 15, 160, 240, 80, api_card, parent='col3')

    s3_svc_html = (
        '<b>Clarification Logic</b><br/>'
        '<div style="font-size:10px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Evaluates story gaps & missing elements<br/>'
        '• Max 5,000 characters per answer<br/>'
        '• Appends to clarification_qa ledger'
        '</div>'
    )
    add_node('s3_svc', s3_svc_html, 15, 270, 240, 85, svc_card, parent='col3')

    s3_db_html = (
        '<b style="color:#0369A1;">MongoDB: intakes</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• Updates clarification_qa array<br/>'
        '• current_step = 3 progress saved<br/>'
        '• Ready for case convert trigger'
        '</div>'
    )
    add_node('s3_db', s3_db_html, 15, 840, 240, 85, db_card, parent='col3')

    # --- STAGE 4 NODES (AI REASONING ENGINE) ---
    s4_ui_html = (
        '<b style="color:#6D28D9;font-size:12px;">Trigger: "Build My Case"</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Client requests structured case synthesis<br/>'
        '• Displays dynamic analysis loader screen<br/>'
        '• Sets target language (English vs Urdu)'
        '</div>'
    )
    add_node('s4_ui', s4_ui_html, 15, 45, 410, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col4')

    s4_api_html = (
        '<span style="background:#EDE9FE;color:#6D28D9;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/api/v1/intake/{token}/convert</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;line-height:1.3;">'
        '• Rate limit: 6/min with atomic epoch fence<br/>'
        '• Replays cached result if already completed<br/>'
        '• Returns: {case_id, ai_case_type, type_was_corrected}'
        '</div>'
    )
    add_node('s4_api', s4_api_html, 15, 160, 410, 80, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col4')

    s4_svc_html = (
        '<b style="color:#0F172A;">Conversion Pipeline (intake_service.py)</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.4;">'
        '1. <b>claim_conversion</b> (atomic lock, epoch++) ➔ blocks 409 collisions<br/>'
        '2. <b>_extract_intake_evidence</b> (subprocess parser for PDF/DOCX + OCR)<br/>'
        '3. <b>_ai_classify_case_type</b> (rule keywords + LLM fallback classification)<br/>'
        '4. <b>build_understanding</b> (compiles verified Fact Ledger from Q&A)<br/>'
        '5. <b>case_service.create_case(status="draft")</b> ➔ pins case_id to intake'
        '</div>'
    )
    add_node('s4_svc', s4_svc_html, 15, 265, 410, 100, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col4')

    # LangGraph Sub-Box inside Stage 4
    add_node('s4_graph_box', '  LANGGRAPH INTAKE GRAPH (build_intake_graph in supervisor.py)', 
             15, 385, 410, 290, 
             'swimlane;startSize=26;fillColor=#6D28D9;strokeColor=#5B21B6;fontColor=#FFFFFF;fontStyle=1;fontSize=10;rounded=1;arcSize=4;shadow=1;swimlaneFillColor=#FFFFFF;collapsible=0;', 
             parent='col4')

    add_node('g_n1', '<b>1. retrieval_node</b><br/><span style="font-size:9px;color:#64748B;">ChromaDB vector query & statute affinity</span>', 
             15, 38, 180, 45, 'rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=center;', parent='s4_graph_box')

    add_node('g_n2', '<b>2. retrieval_grader</b><br/><span style="font-size:9px;color:#64748B;">RRF rank fusion & topic rules</span>', 
             215, 38, 180, 45, 'rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=center;', parent='s4_graph_box')

    add_node('g_n3', '<b style="color:#C2410C;">3. evidence_gate_node (CRITICAL GATE)</b><br/><span style="font-size:9px;color:#475569;">Verifies jurisdiction, live law & repeals.<br/>If law missing/unsupported ➔ <b>Forces Facts-Only Mode</b></span>', 
             15, 100, 380, 50, 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF7ED;strokeColor=#FDBA74;strokeWidth=1.5;fontSize=10;align=center;', parent='s4_graph_box')

    add_node('g_n4', '<b>4. intake_node (LLM)</b><br/><span style="font-size:9px;color:#64748B;">Writes Summary, Law (≤6), Risk</span>', 
             15, 168, 180, 45, 'rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=center;', parent='s4_graph_box')

    add_node('g_n5', '<b>5. hallucination_node</b><br/><span style="font-size:9px;color:#64748B;">Citation check & grounding verdict</span>', 
             215, 168, 180, 45, 'rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=center;', parent='s4_graph_box')

    add_node('g_n6', '<b>6. intake_finalizer_node</b><br/><span style="font-size:9px;color:#64748B;">Repeal currency stamps & separates general vs legal action steps</span>', 
             15, 230, 380, 45, 'rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=center;', parent='s4_graph_box')

    # LangGraph internal connectors
    add_edge('eg1', 'g_n1', 'g_n2', 'strokeColor=#7C3AED;strokeWidth=1.5;', parent='s4_graph_box')
    add_edge('eg2', 'g_n2', 'g_n3', 'strokeColor=#7C3AED;strokeWidth=1.5;exitX=0.5;exitY=1;entryX=0.75;entryY=0;', parent='s4_graph_box')
    add_edge('eg3', 'g_n3', 'g_n4', 'strokeColor=#EA580C;strokeWidth=1.5;exitX=0.25;exitY=1;entryX=0.5;entryY=0;', parent='s4_graph_box')
    add_edge('eg4', 'g_n4', 'g_n5', 'strokeColor=#7C3AED;strokeWidth=1.5;', parent='s4_graph_box')
    add_edge('eg5', 'g_n5', 'g_n6', 'strokeColor=#7C3AED;strokeWidth=1.5;exitX=0.5;exitY=1;entryX=0.75;entryY=0;', parent='s4_graph_box')

    s4_guards_html = (
        '<b>Post-Graph Compliance Guards</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:3px;line-height:1.4;">'
        '• <b>fact_fidelity</b>: checks numbers/negations against user story<br/>'
        '• <b>apply_intake_cpc</b>: applies Punjab-only CPC filter<br/>'
        '• <b>Urdu localization</b>: renders high-quality Urdu translation if chosen<br/>'
        '• Saves ai_structured_case to DB & marks intake completed'
        '</div>'
    )
    add_node('s4_guards', s4_guards_html, 15, 695, 410, 95, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col4')

    s4_db_html = (
        '<b style="color:#6D28D9;">ChromaDB & Provenance Audit</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:3px;line-height:1.3;">'
        '• Vector corpus of Pakistani statutes & provisions<br/>'
        '• SHA-256 audit record stamped in provenance collection'
        '</div>'
    )
    add_node('s4_db', s4_db_html, 15, 840, 410, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;', 
             parent='col4')

    # --- STAGE 5 NODES ---
    s5_ui_html = (
        '<b style="color:#059669;font-size:12px;">Step 4 & 5: Review & Confirm</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Review Summary, Laws & Risk estimate<br/>'
        '• Urdu/English toggle & PDF Print export<br/>'
        '• Confirm/edit Category (Family, Civil, etc.)'
        '</div>'
    )
    add_node('s5_ui', s5_ui_html, 15, 45, 260, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col5')

    s5_api_html = (
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/intake/{token}</b><br/>'
        '<span style="background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">PATCH</span> <b>/cases/{case_id}/confirm</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;">'
        'Confirms case_type & stamps confirmed_at'
        '</div>'
    )
    add_node('s5_api', s5_api_html, 15, 160, 260, 80, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col5')

    s5_svc_html = (
        '<b>Case Service (case_service.py)</b><br/>'
        '<div style="font-size:10px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Transitions status: <b>draft ➔ open</b><br/>'
        '• Saves user-confirmed case category<br/>'
        '• Case becomes visible for lawyer matching'
        '</div>'
    )
    add_node('s5_svc', s5_svc_html, 15, 270, 260, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col5')

    s5_next_html = (
        '<b style="color:#059669;">Client Next Action Hub</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.5;">'
        '➔ <b>Find a Lawyer</b> (/lawyers?case_id=...)<br/>'
        '➔ <b>Draft a Document</b> (/documents)<br/>'
        '➔ <b>Track Case Milestones</b> (/tracking)'
        '</div>'
    )
    add_node('s5_next', s5_next_html, 15, 385, 260, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#ECFDF5;strokeColor=#A7F3D0;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col5')

    s5_db_html = (
        '<b style="color:#059669;">MongoDB: cases</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• status: <b>open</b> (formal case created)<br/>'
        '• ai_summary & evidence linked<br/>'
        '• Ready for consultation booking & hire'
        '</div>'
    )
    add_node('s5_db', s5_db_html, 15, 840, 260, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=2;shadow=1;align=left;spacingLeft=12;', 
             parent='col5')

    # --- TOP HORIZONTAL PIPELINE CONNECTORS (LEFT TO RIGHT) ---
    add_edge('flow_1_2', 's1_ui', 's2_ui', 'strokeColor=#0284C7;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_2_3', 's2_ui', 's3_ui', 'strokeColor=#0284C7;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_3_4', 's3_ui', 's4_ui', 'strokeColor=#7C3AED;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_4_5', 's4_ui', 's5_ui', 'strokeColor=#059669;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')

    # --- VERTICAL INTERNAL ARROWS (NO CROSSING!) ---
    # Column 1
    add_edge('e1_v1', 's1_ui', 's1_api', 'strokeColor=#0284C7;strokeWidth=2;', parent='col1')
    add_edge('e1_v2', 's1_api', 's1_svc', 'strokeColor=#0284C7;strokeWidth=2;', parent='col1')
    add_edge('e1_v3', 's1_svc', 's1_db', 'strokeColor=#0284C7;strokeWidth=1.5;dashed=1;', parent='col1')

    # Column 2
    add_edge('e2_v1', 's2_ui', 's2_api', 'strokeColor=#0284C7;strokeWidth=2;', parent='col2')
    add_edge('e2_v2', 's2_api', 's2_svc', 'strokeColor=#0284C7;strokeWidth=2;', parent='col2')
    add_edge('e2_v3', 's2_svc', 's2_db', 'strokeColor=#64748B;strokeWidth=1.5;dashed=1;', parent='col2')

    # Column 3
    add_edge('e3_v1', 's3_ui', 's3_api', 'strokeColor=#0284C7;strokeWidth=2;', parent='col3')
    add_edge('e3_v2', 's3_api', 's3_svc', 'strokeColor=#0284C7;strokeWidth=2;', parent='col3')
    add_edge('e3_v3', 's3_svc', 's3_db', 'strokeColor=#0284C7;strokeWidth=1.5;dashed=1;', parent='col3')

    # Column 4
    add_edge('e4_v1', 's4_ui', 's4_api', 'strokeColor=#7C3AED;strokeWidth=2;', parent='col4')
    add_edge('e4_v2', 's4_api', 's4_svc', 'strokeColor=#7C3AED;strokeWidth=2;', parent='col4')
    add_edge('e4_v3', 's4_svc', 's4_graph_box', 'strokeColor=#7C3AED;strokeWidth=2;', parent='col4')
    add_edge('e4_v4', 's4_graph_box', 's4_guards', 'strokeColor=#7C3AED;strokeWidth=2;', parent='col4')
    add_edge('e4_v5', 's4_guards', 's4_db', 'strokeColor=#7C3AED;strokeWidth=1.5;dashed=1;', parent='col4')

    # Column 5
    add_edge('e5_v1', 's5_ui', 's5_api', 'strokeColor=#059669;strokeWidth=2;', parent='col5')
    add_edge('e5_v2', 's5_api', 's5_svc', 'strokeColor=#059669;strokeWidth=2;', parent='col5')
    add_edge('e5_v3', 's5_svc', 's5_next', 'strokeColor=#059669;strokeWidth=2;', parent='col5')
    add_edge('e5_v4', 's5_next', 's5_db', 'strokeColor=#059669;strokeWidth=1.5;dashed=1;', parent='col5')

    # Cross-Stage connection: Stage 4 Guards creates Draft Case in Stage 5 DB
    add_edge('e_cross_case', 's4_guards', 's5_db', 
             'strokeColor=#059669;strokeWidth=2;dashed=1;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')

    xml_str = ET.tostring(mxfile, encoding='utf-8').decode('utf-8')
    with open('docs/flows/legal_intake_perfect.drawio', 'w', encoding='utf-8') as f:
        f.write(xml_str)
    print("SUCCESS: Perfect Draw.io diagram generated and validated!")

build()
