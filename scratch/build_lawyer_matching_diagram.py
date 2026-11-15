import xml.etree.ElementTree as ET

def build():
    mxfile = ET.Element('mxfile', host='app.diagrams.net', version='22.0.0', type='device')
    diagram = ET.SubElement(mxfile, 'diagram', id='lawyer-matching-appointments-pipeline', name='Lawyer Matching & Appointments')
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
        'Attorney.AI — Lawyer Matching & Appointment Consultation Lifecycle'
        '</div>'
        '<div style="font-size:11px;color:#64748B;margin-top:3px;">'
        'End-to-End Pipeline: AI Case Matching → Slot Calculation → Idempotent Booking → Video Consultation (Daily.co) → Outcome & Hire Unlock'
        '</div>'
    )
    add_node('hdr', title_html, 50, 25, 1720, 55, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#CBD5E1;strokeWidth=1.5;shadow=1;arcSize=6;align=left;spacingLeft=16;')

    # 2. Stage Columns
    columns = [
        ('col1', 'STAGE 1: DISCOVERY & AI MATCHING', 50, 310, '#EFF6FF', '#BAE6FD'),
        ('col2', 'STAGE 2: SLOT AVAILABILITY CALC', 400, 310, '#F0FDFA', '#99F6E4'),
        ('col3', 'STAGE 3: IDEMPOTENT BOOKING HOLD', 750, 310, '#FEF3C7', '#FDE68A'),
        ('col4', 'STAGE 4: TRIAGE & VIDEO SESSION', 1100, 340, '#F5F3FF', '#DDD6FE'),
        ('col5', 'STAGE 5: OUTCOME & HIRE UNLOCK', 1480, 290, '#ECFDF5', '#A7F3D0'),
    ]

    for cid, ctitle, cx, cw, cfill, cstroke in columns:
        c_style = f'swimlane;startSize=30;fillColor={cstroke};strokeColor={cstroke};fontColor=#0F172A;fontStyle=1;fontSize=11;rounded=1;arcSize=6;shadow=1;swimlaneFillColor={cfill};collapsible=0;'
        add_node(cid, f'  {ctitle}', cx, 95, cw, 960, c_style, parent='1')

    # Card styles
    ui_card = 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;'
    api_card = 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#64748B;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;'
    svc_card = 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#475569;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;'
    db_card = 'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;'

    # --- STAGE 1: DISCOVERY & MATCHING ---
    s1_ui_html = (
        '<b style="color:#0284C7;font-size:12px;">Client: Directory & Matching</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Browse Directory (/lawyers, 20 per page)<br/>'
        '• 7 Practice chips, Province filter, Leaflet map<br/>'
        '• <b>AI Match trigger</b>: ?case_id=... (from Intake)'
        '</div>'
    )
    add_node('s1_ui', s1_ui_html, 15, 45, 280, 85, ui_card, parent='col1')

    s1_api_html = (
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/api/v1/lawyers</b> (filters, q, sort)<br/>'
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/api/v1/lawyers/counts</b> (area chips)<br/>'
        '<span style="background:#EDE9FE;color:#6D28D9;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/lawyers/match/{case_id}</b> (AI match)'
    )
    add_node('s1_api', s1_api_html, 15, 160, 280, 80, api_card, parent='col1')

    s1_svc_html = (
        '<b>lawyer_service.py (Matching Engine)</b><br/>'
        '<div style="font-size:10px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Refuses draft cases (422 case_draft)<br/>'
        '• Vector search over lawyer_embeddings<br/>'
        '• Merges province, specialization & rating<br/>'
        '• Returns top 5 with match_score & match_reason'
        '</div>'
    )
    add_node('s1_svc', s1_svc_html, 15, 270, 280, 95, svc_card, parent='col1')

    s1_engine_box = (
        '<b>ChromaDB & User Directory</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;line-height:1.4;">'
        '• <b>lawyer_embeddings</b> vector collection<br/>'
        '• Embeds bio, specializations, years<br/>'
        '• Auto-filters unapproved/inactive KYC'
        '</div>'
    )
    add_node('s1_engine', s1_engine_box, 15, 400, 280, 80, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=left;spacingLeft=12;', 
             parent='col1')

    s1_db_html = (
        '<b style="color:#0369A1;">MongoDB: users</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• role: lawyer, kyc_verified: true<br/>'
        '• lawyer_profile (bar_number, hourly_rate)<br/>'
        '• lat/lng geocoded coordinates'
        '</div>'
    )
    add_node('s1_db', s1_db_html, 15, 840, 280, 85, db_card, parent='col1')

    # --- STAGE 2: SLOT AVAILABILITY CALC ---
    s2_ui_html = (
        '<b style="color:#0D9488;font-size:12px;">Booking Modal: Date & Slot Pick</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Modal opens with lawyer hourly fee<br/>'
        '• Queries free slots for chosen date (60 min)<br/>'
        '• <b>"Earliest open slot"</b> hint (scans 14 days)'
        '</div>'
    )
    add_node('s2_ui', s2_ui_html, 15, 45, 280, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0D9488;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col2')

    s2_api_html = (
        '<span style="background:#CCFBF1;color:#0F766E;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/lawyers/{id}/bookable-slots</b><br/>'
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/lawyers/{id}/availability</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;">'
        'Params: from, to, duration_minutes=60'
        '</div>'
    )
    add_node('s2_api', s2_api_html, 15, 160, 280, 80, api_card, parent='col2')

    s2_svc_html = (
        '<b>lawyer_availability_service.py</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.4;">'
        'Calculates real available slots via subtraction:<br/>'
        '<b>Working Hours</b><br/>'
        '− Exception days (holidays/leaves)<br/>'
        '− Existing pending/confirmed appointments<br/>'
        '− <b>Court hearings</b> (holds 3 hrs or full day)<br/>'
        '− Lawyer personal diary entries & past times'
        '</div>'
    )
    add_node('s2_svc', s2_svc_html, 15, 270, 280, 115, svc_card, parent='col2')

    s2_db_html = (
        '<b style="color:#0F766E;">MongoDB: lawyer_availability</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• _id: lawyer_id<br/>'
        '• working_hours (mon..sun start/end)<br/>'
        '• unavailable_dates & day-off reasons'
        '</div>'
    )
    add_node('s2_db', s2_db_html, 15, 840, 280, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#0D9488;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;', 
             parent='col2')

    # --- STAGE 3: IDEMPOTENT BOOKING HOLD ---
    s3_ui_html = (
        '<b style="color:#D97706;font-size:12px;">Submit Booking Request</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Choose Mode: <b>Video call</b> or <b>In person</b><br/>'
        '• Link confirmed Case ID (optional note ≤1000)<br/>'
        '• Generates unique <b>idempotency key</b>'
        '</div>'
    )
    add_node('s3_ui', s3_ui_html, 15, 45, 280, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#D97706;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col3')

    s3_api_html = (
        '<span style="background:#FEF3C7;color:#B45309;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/api/v1/appointments</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;line-height:1.4;">'
        '• Headers: Idempotency-Key<br/>'
        '• Body: {lawyer_id, scheduled_at, mode, case_id}<br/>'
        '• Rejects double-click (409 if slot taken)'
        '</div>'
    )
    add_node('s3_api', s3_api_html, 15, 160, 280, 80, api_card, parent='col3')

    s3_svc_html = (
        '<b>appointment_service.book_appointment</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Validates future :00/:30 UTC offset<br/>'
        '• Case ownership guard (refuses draft cases)<br/>'
        '• Checks lawyer KYC approved & active<br/>'
        '• Atomically locks timeslot for both parties<br/>'
        '• Dispatches WebSocket notification to lawyer'
        '</div>'
    )
    add_node('s3_svc', s3_svc_html, 15, 270, 280, 105, svc_card, parent='col3')

    s3_state_box = (
        '<b>Status: PENDING</b><br/>'
        '<div style="font-size:9px;color:#B45309;margin-top:3px;line-height:1.3;">'
        '• Client can reschedule / withdraw<br/>'
        '• Client can attach up to 5 case files<br/>'
        '• Auto-expires if lawyer does not answer'
        '</div>'
    )
    add_node('s3_state', s3_state_box, 15, 405, 280, 75, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFBEB;strokeColor=#FDE68A;fontSize=10;align=left;spacingLeft=12;', 
             parent='col3')

    s3_db_html = (
        '<b style="color:#D97706;">MongoDB: appointments</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• status: <b>pending</b><br/>'
        '• Unique index on (lawyer_id, scheduled_at)<br/>'
        '• Unique index on (client_id, scheduled_at)'
        '</div>'
    )
    add_node('s3_db', s3_db_html, 15, 840, 280, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#D97706;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;', 
             parent='col3')

    # --- STAGE 4: TRIAGE & VIDEO SESSION ---
    s4_ui_html = (
        '<b style="color:#6D28D9;font-size:12px;">Lawyer Triage & Meeting Session</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Lawyer /lawyer/appointments: Accept / Decline<br/>'
        '• <b>Accept</b>: creates Daily.co video room / link<br/>'
        '• In-app chat thread opens between client & lawyer'
        '</div>'
    )
    add_node('s4_ui', s4_ui_html, 15, 45, 310, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col4')

    s4_api_html = (
        '<span style="background:#EDE9FE;color:#6D28D9;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">PATCH</span> <b>/appointments/{id}/accept</b> (link/Daily)<br/>'
        '<span style="background:#FEE2E2;color:#991B1B;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">PATCH</span> <b>/appointments/{id}/decline</b><br/>'
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/appointments/{id}/propose-reschedule</b>'
    )
    add_node('s4_api', s4_api_html, 15, 160, 310, 80, api_card, parent='col4')

    s4_svc_html = (
        '<b>Consultation Session Coordinator</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Status updates to: <b>confirmed</b><br/>'
        '• Generates .ics calendar invite download<br/>'
        '• Opens shared private messaging channel<br/>'
        '• Daily.co video token minted with expiry<br/>'
        '• Cancellation locked inside 2h of start'
        '</div>'
    )
    add_node('s4_svc', s4_svc_html, 15, 270, 310, 100, svc_card, parent='col4')

    # Video & Messaging Sub-Box
    s4_box_html = (
        '<b>Active Meeting Session (60 mins)</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:3px;line-height:1.4;">'
        '• <b>Video</b>: In-app WebRTC / Daily.co pre-join camera check<br/>'
        '• <b>Phone</b>: Lawyer phone number revealed to client<br/>'
        '• <b>In-person</b>: Office address & map coordinates shown<br/>'
        '• Real-time appointment thread WebSocket messaging'
        '</div>'
    )
    add_node('s4_session_box', s4_box_html, 15, 395, 310, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=left;spacingLeft=12;', 
             parent='col4')

    s4_db_html = (
        '<b style="color:#6D28D9;">Daily.co Video & Messages</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• appointment_messages collection<br/>'
        '• Daily.co room token & video log<br/>'
        '• status: <b>confirmed ➔ ended</b>'
        '</div>'
    )
    add_node('s4_db', s4_db_html, 15, 840, 310, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;', 
             parent='col4')

    # --- STAGE 5: OUTCOME & HIRE UNLOCK ---
    s5_ui_html = (
        '<b style="color:#059669;font-size:12px;">Outcome & Client Unlocks</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Lawyer marks: <b>Completed</b> or <b>No-Show</b><br/>'
        '• Adds consultation outcome & notes<br/>'
        '• Unlocks client: <b>Hire</b> & <b>Leave Review</b>'
        '</div>'
    )
    add_node('s5_ui', s5_ui_html, 15, 45, 260, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col5')

    s5_api_html = (
        '<span style="background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/appointments/{id}/outcome</b><br/>'
        '<span style="background:#FEF3C7;color:#B45309;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/lawyers/{id}/review</b> (1-5 stars)<br/>'
        '<span style="background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/engagements/hire</b> (Doc 15)'
    )
    add_node('s5_api', s5_api_html, 15, 160, 260, 80, api_card, parent='col5')

    s5_svc_html = (
        '<b>Post-Consultation Engine</b><br/>'
        '<div style="font-size:10px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Sets appointment status = <b>completed</b><br/>'
        '• <b>review-eligibility</b> becomes true<br/>'
        '• Recalculates lawyer average rating<br/>'
        '• <b>CRITICAL</b>: Completed consultation is mandatory prerequisite to send Hire Request'
        '</div>'
    )
    add_node('s5_svc', s5_svc_html, 15, 270, 260, 105, svc_card, parent='col5')

    s5_next_html = (
        '<b style="color:#059669;">Unlocks Next Journey Steps</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.5;">'
        '➔ <b>Hire Lawyer (Doc 15)</b>: Fee proposal<br/>'
        '➔ <b>Case Milestone (Doc 16)</b>: Formal Case<br/>'
        '➔ <b>Public Review</b>: Rating added to directory'
        '</div>'
    )
    add_node('s5_next', s5_next_html, 15, 400, 260, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#ECFDF5;strokeColor=#A7F3D0;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col5')

    s5_db_html = (
        '<b style="color:#059669;">MongoDB: reviews & engagements</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• reviews: stars, comment, client_id<br/>'
        '• lawyer_profile.rating re-averaged<br/>'
        '• engagements collection unlocked'
        '</div>'
    )
    add_node('s5_db', s5_db_html, 15, 840, 260, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=2;shadow=1;align=left;spacingLeft=12;', 
             parent='col5')

    # --- TOP HORIZONTAL PIPELINE CONNECTORS (LEFT TO RIGHT) ---
    add_edge('flow_1_2', 's1_ui', 's2_ui', 'strokeColor=#0284C7;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_2_3', 's2_ui', 's3_ui', 'strokeColor=#0D9488;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_3_4', 's3_ui', 's4_ui', 'strokeColor=#D97706;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_4_5', 's4_ui', 's5_ui', 'strokeColor=#7C3AED;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')

    # --- VERTICAL INTERNAL ARROWS (NO CROSSING!) ---
    # Col 1
    add_edge('e1_v1', 's1_ui', 's1_api', 'strokeColor=#0284C7;strokeWidth=2;', parent='col1')
    add_edge('e1_v2', 's1_api', 's1_svc', 'strokeColor=#0284C7;strokeWidth=2;', parent='col1')
    add_edge('e1_v3', 's1_svc', 's1_engine', 'strokeColor=#0284C7;strokeWidth=2;', parent='col1')
    add_edge('e1_v4', 's1_engine', 's1_db', 'strokeColor=#0284C7;strokeWidth=1.5;dashed=1;', parent='col1')

    # Col 2
    add_edge('e2_v1', 's2_ui', 's2_api', 'strokeColor=#0D9488;strokeWidth=2;', parent='col2')
    add_edge('e2_v2', 's2_api', 's2_svc', 'strokeColor=#0D9488;strokeWidth=2;', parent='col2')
    add_edge('e2_v3', 's2_svc', 's2_db', 'strokeColor=#0D9488;strokeWidth=1.5;dashed=1;', parent='col2')

    # Col 3
    add_edge('e3_v1', 's3_ui', 's3_api', 'strokeColor=#D97706;strokeWidth=2;', parent='col3')
    add_edge('e3_v2', 's3_api', 's3_svc', 'strokeColor=#D97706;strokeWidth=2;', parent='col3')
    add_edge('e3_v3', 's3_svc', 's3_state', 'strokeColor=#D97706;strokeWidth=2;', parent='col3')
    add_edge('e3_v4', 's3_state', 's3_db', 'strokeColor=#D97706;strokeWidth=1.5;dashed=1;', parent='col3')

    # Col 4
    add_edge('e4_v1', 's4_ui', 's4_api', 'strokeColor=#7C3AED;strokeWidth=2;', parent='col4')
    add_edge('e4_v2', 's4_api', 's4_svc', 'strokeColor=#7C3AED;strokeWidth=2;', parent='col4')
    add_edge('e4_v3', 's4_svc', 's4_session_box', 'strokeColor=#7C3AED;strokeWidth=2;', parent='col4')
    add_edge('e4_v4', 's4_session_box', 's4_db', 'strokeColor=#7C3AED;strokeWidth=1.5;dashed=1;', parent='col4')

    # Col 5
    add_edge('e5_v1', 's5_ui', 's5_api', 'strokeColor=#059669;strokeWidth=2;', parent='col5')
    add_edge('e5_v2', 's5_api', 's5_svc', 'strokeColor=#059669;strokeWidth=2;', parent='col5')
    add_edge('e5_v3', 's5_svc', 's5_next', 'strokeColor=#059669;strokeWidth=2;', parent='col5')
    add_edge('e5_v4', 's5_next', 's5_db', 'strokeColor=#059669;strokeWidth=1.5;dashed=1;', parent='col5')

    # Cross Stage 4 to Stage 3 DB (Accepting appointment updates status in DB)
    add_edge('e_cross_conf', 's4_svc', 's3_db', 
             'strokeColor=#7C3AED;strokeWidth=2;dashed=1;exitX=0;exitY=0.5;entryX=1;entryY=0.5;')

    xml_str = ET.tostring(mxfile, encoding='utf-8').decode('utf-8')
    with open('docs/flows/lawyer_matching_appointments_perfect.drawio', 'w', encoding='utf-8') as f:
        f.write(xml_str)
    print("SUCCESS: Perfect Lawyer Matching & Appointments Draw.io diagram generated!")

build()
