import xml.etree.ElementTree as ET

def build_enhanced():
    mxfile = ET.Element('mxfile', host='app.diagrams.net', version='22.0.0', type='device')
    diagram = ET.SubElement(mxfile, 'diagram', id='lawyer-matching-appointments-enhanced', name='Lawyer Matching & Appointments Flow')
    model = ET.SubElement(diagram, 'mxGraphModel', 
                         dx='1800', dy='1100', grid='1', gridSize='10', 
                         guides='1', tooltips='1', connect='1', arrows='1', 
                         fold='1', page='1', pageScale='1', 
                         pageWidth='2100', pageHeight='1200', 
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
        'Attorney.AI — Complete Lawyer Matching, Consultation &amp; Hire Journey'
        '</div>'
        '<div style="font-size:11px;color:#64748B;margin-top:3px;">'
        'Comprehensive 6-Stage Architecture: AI Vector Matching → Availability Subtraction → Idempotent Booking → Lawyer Decision Triage → Live Daily.co Session → Case Hire'
        '</div>'
    )
    add_node('hdr', title_html, 40, 20, 1980, 55, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#CBD5E1;strokeWidth=1.5;shadow=1;arcSize=6;align=left;spacingLeft=16;')

    # 6 Columns / Stages
    # Col 1: Discovery & Matching (x=40, w=310)
    # Col 2: Slot Availability Engine (x=370, w=310)
    # Col 3: Idempotent Booking Hold (x=700, w=310)
    # Col 4: Lawyer Triage & Branching (x=1030, w=350)
    # Col 5: Live Video Session (x=1400, w=310)
    # Col 6: Outcome & Hire Unlock (x=1730, w=290)

    columns = [
        ('col1', 'STAGE 1: AI CASE MATCHING', 40, 310, '#EFF6FF', '#BAE6FD'),
        ('col2', 'STAGE 2: SLOT AVAILABILITY ENGINE', 370, 310, '#F0FDFA', '#99F6E4'),
        ('col3', 'STAGE 3: IDEMPOTENT BOOKING HOLD', 700, 310, '#FEF3C7', '#FDE68A'),
        ('col4', 'STAGE 4: LAWYER TRIAGE & BRANCHING', 1030, 350, '#FAF5FF', '#DDD6FE'),
        ('col5', 'STAGE 5: LIVE VIDEO SESSION (DAILY.CO)', 1400, 310, '#FDF2F8', '#FBCFE8'),
        ('col6', 'STAGE 6: OUTCOME & HIRE UNLOCK', 1730, 290, '#ECFDF5', '#A7F3D0'),
    ]

    for cid, ctitle, cx, cw, cfill, cstroke in columns:
        c_style = f'swimlane;startSize=30;fillColor={cstroke};strokeColor={cstroke};fontColor=#0F172A;fontStyle=1;fontSize=11;rounded=1;arcSize=6;shadow=1;swimlaneFillColor={cfill};collapsible=0;'
        add_node(cid, f'  {ctitle}', cx, 90, cw, 1000, c_style, parent='1')

    # Card styles
    ui_card = 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;'
    api_card = 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#64748B;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;'
    svc_card = 'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#475569;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;'
    db_card = 'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;'

    # --- STAGE 1: AI MATCHING ---
    s1_ui_html = (
        '<b style="color:#0284C7;font-size:12px;">Client: Directory &amp; Matching</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Browse Directory (/lawyers, 20/page)<br/>'
        '• 7 Practice Area chips + Province filter<br/>'
        '• <b>AI Match trigger</b>: ?case_id=... (from Intake)<br/>'
        '• Fallback: "Describe problem" Roman Urdu box'
        '</div>'
    )
    add_node('s1_ui', s1_ui_html, 15, 45, 280, 90, ui_card, parent='col1')

    s1_api_html = (
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/api/v1/lawyers</b> (filters, q, sort)<br/>'
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/api/v1/lawyers/counts</b> (chips count)<br/>'
        '<span style="background:#EDE9FE;color:#6D28D9;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/lawyers/match/{case_id}</b> (AI match)'
    )
    add_node('s1_api', s1_api_html, 15, 160, 280, 80, api_card, parent='col1')

    s1_svc_html = (
        '<b>lawyer_service.py (Matching Engine)</b><br/>'
        '<div style="font-size:10px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Refuses draft cases (422 case_draft)<br/>'
        '• Queries <b>lawyer_embeddings</b> vector pool<br/>'
        '• Merges province, specialization &amp; rating<br/>'
        '• Returns top 5 with match_score &amp; reason'
        '</div>'
    )
    add_node('s1_svc', s1_svc_html, 15, 265, 280, 95, svc_card, parent='col1')

    s1_engine_box = (
        '<b>ChromaDB Vector Retrieval</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;line-height:1.4;">'
        '• Embeds bio, practice areas, experience<br/>'
        '• Real semantic similarity cosine scoring<br/>'
        '• Drops stale vectors / unapproved KYC'
        '</div>'
    )
    add_node('s1_engine', s1_engine_box, 15, 385, 280, 75, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F3FF;strokeColor=#C4B5FD;fontSize=10;align=left;spacingLeft=12;', 
             parent='col1')

    s1_db_html = (
        '<b style="color:#0369A1;">MongoDB: users</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• role: lawyer, kyc_verified: true<br/>'
        '• lawyer_profile (bar_number, hourly_rate)<br/>'
        '• Exact geocoded office coordinates (lat/lng)'
        '</div>'
    )
    add_node('s1_db', s1_db_html, 15, 870, 280, 85, db_card, parent='col1')

    # --- STAGE 2: SLOT AVAILABILITY ENGINE ---
    s2_ui_html = (
        '<b style="color:#0D9488;font-size:12px;">Booking Modal: Date &amp; Slot Pick</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Opens with lawyer consultation fee (PKR)<br/>'
        '• Date picker scans <b>14 days earliest open hint</b><br/>'
        '• Displays only real bookable 60-min slots'
        '</div>'
    )
    add_node('s2_ui', s2_ui_html, 15, 45, 280, 90, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0D9488;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col2')

    s2_api_html = (
        '<span style="background:#CCFBF1;color:#0F766E;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/lawyers/{id}/bookable-slots</b><br/>'
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/lawyers/{id}/availability</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;">'
        'Params: from, to, duration_minutes=60 (PKT tz)'
        '</div>'
    )
    add_node('s2_api', s2_api_html, 15, 160, 280, 80, api_card, parent='col2')

    s2_svc_html = (
        '<b>Slot Subtraction Math Engine</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.4;">'
        '<b>Working Hours (from availability config)</b><br/>'
        '− Exception days (leaves / court holidays)<br/>'
        '− Active pending / confirmed appointments<br/>'
        '− <b>Court Hearings</b>: holds 3 hrs (or full day)<br/>'
        '− Lawyer diary entries &amp; past timestamps'
        '</div>'
    )
    add_node('s2_svc', s2_svc_html, 15, 265, 280, 110, svc_card, parent='col2')

    s2_db_html = (
        '<b style="color:#0F766E;">MongoDB: lawyer_availability</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• _id: lawyer_id<br/>'
        '• working_hours (mon..sun start/end)<br/>'
        '• unavailable_dates &amp; exception reasons'
        '</div>'
    )
    add_node('s2_db', s2_db_html, 15, 870, 280, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#0D9488;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;', 
             parent='col2')

    # --- STAGE 3: IDEMPOTENT BOOKING HOLD ---
    s3_ui_html = (
        '<b style="color:#D97706;font-size:12px;">Submit Consultation Request</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Choose Mode: <b>Video call</b> or <b>In person</b><br/>'
        '• Link confirmed Case ID (notes ≤ 1,000 chars)<br/>'
        '• Generates unique <b>idempotency key</b>'
        '</div>'
    )
    add_node('s3_ui', s3_ui_html, 15, 45, 280, 90, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#D97706;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col3')

    s3_api_html = (
        '<span style="background:#FEF3C7;color:#B45309;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/api/v1/appointments</b><br/>'
        '<div style="font-size:9px;color:#64748B;margin-top:4px;line-height:1.3;">'
        '• Headers: Idempotency-Key<br/>'
        '• Body: {lawyer_id, scheduled_at, mode, case_id}<br/>'
        '• Rejects double-click (409 conflict if slot taken)'
        '</div>'
    )
    add_node('s3_api', s3_api_html, 15, 160, 280, 80, api_card, parent='col3')

    s3_svc_html = (
        '<b>appointment_service.book_appointment</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Validates future :00/:30 UTC offset<br/>'
        '• Verifies client case ownership (blocks draft)<br/>'
        '• Enforces lawyer KYC approval &amp; active status<br/>'
        '• Atomically holds timeslot for both parties<br/>'
        '• Dispatches WebSocket notification to lawyer'
        '</div>'
    )
    add_node('s3_svc', s3_svc_html, 15, 265, 280, 110, svc_card, parent='col3')

    s3_state_box = (
        '<b>Status: PENDING</b><br/>'
        '<div style="font-size:9px;color:#B45309;margin-top:3px;line-height:1.3;">'
        '• Client can reschedule or cancel request<br/>'
        '• Client can attach up to 5 case files<br/>'
        '• Private thread locked until lawyer confirms'
        '</div>'
    )
    add_node('s3_state', s3_state_box, 15, 395, 280, 75, 
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
    add_node('s3_db', s3_db_html, 15, 870, 280, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#D97706;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;', 
             parent='col3')

    # --- STAGE 4: LAWYER TRIAGE & BRANCHING ---
    s4_ui_html = (
        '<b style="color:#7C3AED;font-size:12px;">Lawyer Dashboard &amp; Decision Triage</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Lawyer views pending consultation in /lawyer<br/>'
        '• Reviews client story, case type &amp; documents<br/>'
        '• Three distinct decision actions available'
        '</div>'
    )
    add_node('s4_ui', s4_ui_html, 15, 45, 320, 90, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col4')

    s4_api_html = (
        '<span style="background:#EDE9FE;color:#6D28D9;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">PATCH</span> <b>/appointments/{id}/accept</b> (Daily/link)<br/>'
        '<span style="background:#FEE2E2;color:#991B1B;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">PATCH</span> <b>/appointments/{id}/decline</b><br/>'
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/appointments/{id}/propose-reschedule</b>'
    )
    add_node('s4_api', s4_api_html, 15, 160, 320, 80, api_card, parent='col4')

    # 3 Decision Branches
    branch_accept = (
        '<b style="color:#059669;">[PATH A] ACCEPT ➔ CONFIRMED</b><br/>'
        '<div style="font-size:9px;color:#334155;margin-top:3px;line-height:1.3;">'
        '• Creates <b>Daily.co video room</b> token<br/>'
        '• Generates <b>.ics</b> calendar invite download<br/>'
        '• Unlocks private in-app messaging thread'
        '</div>'
    )
    add_node('b_accept', branch_accept, 15, 260, 320, 75, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#ECFDF5;strokeColor=#A7F3D0;strokeWidth=1.5;fontSize=10;align=left;spacingLeft=10;', 
             parent='col4')

    branch_decline = (
        '<b style="color:#DC2626;">[PATH B] DECLINE ➔ CANCELLED</b><br/>'
        '<div style="font-size:9px;color:#334155;margin-top:3px;line-height:1.3;">'
        '• status: cancelled, cancelled_by: lawyer<br/>'
        '• Slot freed up immediately in calendar<br/>'
        '• Client receives instant lawyer re-match tips'
        '</div>'
    )
    add_node('b_decline', branch_decline, 15, 350, 320, 75, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FEF2F2;strokeColor=#FECACA;strokeWidth=1.5;fontSize=10;align=left;spacingLeft=10;', 
             parent='col4')

    branch_resched = (
        '<b style="color:#D97706;">[PATH C] PROPOSE NEW TIME</b><br/>'
        '<div style="font-size:9px;color:#334155;margin-top:3px;line-height:1.3;">'
        '• Lawyer suggests up to 3 alternate slots<br/>'
        '• Client selects slot ➔ updates scheduled_at<br/>'
        '• Old slot held until client responds'
        '</div>'
    )
    add_node('b_resched', branch_resched, 15, 440, 320, 75, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFBEB;strokeColor=#FDE68A;strokeWidth=1.5;fontSize=10;align=left;spacingLeft=10;', 
             parent='col4')

    s4_db_html = (
        '<b style="color:#7C3AED;">Status Transitions in DB</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• <b>confirmed</b>: meeting room generated<br/>'
        '• Cancellation locked inside 2h of start<br/>'
        '• Notifications broadcasted over WebSocket'
        '</div>'
    )
    add_node('s4_db', s4_db_html, 15, 870, 320, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;', 
             parent='col4')

    # --- STAGE 5: LIVE VIDEO SESSION (DAILY.CO) ---
    s5_ui_html = (
        '<b style="color:#DB2777;font-size:12px;">Active Consultation Experience</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Countdown timer ("Starts in 10 mins")<br/>'
        '• Pre-join hardware check (Mic/Camera test)<br/>'
        '• 60-min in-app WebRTC video room'
        '</div>'
    )
    add_node('s5_ui', s5_ui_html, 15, 45, 280, 90, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#DB2777;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col5')

    s5_api_html = (
        '<span style="background:#FCE7F3;color:#BE185D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">GET</span> <b>/appointments/{id}/video-token</b><br/>'
        '<span style="background:#E0F2FE;color:#0369A1;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/appointments/{id}/messages</b><br/>'
        '<span style="background:#EDE9FE;color:#6D28D9;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">WS</span> <b>/ws/chat (appointment thread)</b>'
    )
    add_node('s5_api', s5_api_html, 15, 160, 280, 80, api_card, parent='col5')

    s5_svc_html = (
        '<b>WebRTC Video &amp; Chat Engine</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Daily.co server integration (or external meeting link)<br/>'
        '• Ephemeral tokens minted with appointment expiry<br/>'
        '• Document previewing during active call<br/>'
        '• Auto-transitions to <b>ended</b> after 60 mins'
        '</div>'
    )
    add_node('s5_svc', s5_svc_html, 15, 265, 280, 100, svc_card, parent='col5')

    s5_db_html = (
        '<b style="color:#DB2777;">Media &amp; Message Storage</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• appointment_messages collection<br/>'
        '• Daily.co session log &amp; duration record<br/>'
        '• status: <b>confirmed ➔ ended</b>'
        '</div>'
    )
    add_node('s5_db', s5_db_html, 15, 870, 280, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#DB2777;strokeWidth=1.5;shadow=1;align=left;spacingLeft=12;', 
             parent='col5')

    # --- STAGE 6: OUTCOME & HIRE UNLOCK ---
    s6_ui_html = (
        '<b style="color:#059669;font-size:12px;">Outcome &amp; Critical Next Steps</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.4;">'
        '• Lawyer marks: <b>Completed</b> or <b>No-Show</b><br/>'
        '• Records consultation outcome &amp; next advice<br/>'
        '• Unlocks client: <b>Hire Lawyer</b> &amp; <b>Review</b>'
        '</div>'
    )
    add_node('s6_ui', s6_ui_html, 15, 45, 260, 90, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col6')

    s6_api_html = (
        '<span style="background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/appointments/{id}/outcome</b><br/>'
        '<span style="background:#FEF3C7;color:#B45309;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/lawyers/{id}/review</b> (1-5 stars)<br/>'
        '<span style="background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">POST</span> <b>/engagements/hire</b> (Doc 15)'
    )
    add_node('s6_api', s6_api_html, 15, 160, 260, 80, api_card, parent='col6')

    s6_svc_html = (
        '<b>Post-Consultation &amp; Hire Engine</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.4;">'
        '• Sets appointment status = <b>completed</b><br/>'
        '• <b>review-eligibility</b> becomes true<br/>'
        '• Recalculates lawyer public rating<br/>'
        '• <b>GATEWAY</b>: Completed consultation is mandatory prerequisite to send Hire Request'
        '</div>'
    )
    add_node('s6_svc', s6_svc_html, 15, 265, 260, 110, svc_card, parent='col6')

    s6_next_html = (
        '<b style="color:#059669;">Unlocks Next Journey Steps</b><br/>'
        '<div style="font-size:10px;color:#334155;margin-top:4px;line-height:1.5;">'
        '➔ <b>Hire Lawyer (Doc 15)</b>: Fee proposal<br/>'
        '➔ <b>Case Opened (Doc 16)</b>: Formal Case<br/>'
        '➔ <b>Public Review</b>: Directory rating updated'
        '</div>'
    )
    add_node('s6_next', s6_next_html, 15, 400, 260, 85, 
             'rounded=1;whiteSpace=wrap;html=1;fillColor=#ECFDF5;strokeColor=#A7F3D0;strokeWidth=1.5;shadow=1;arcSize=8;align=left;spacingLeft=12;', 
             parent='col6')

    s6_db_html = (
        '<b style="color:#059669;">MongoDB: reviews &amp; cases</b><br/>'
        '<div style="font-size:9px;color:#475569;margin-top:4px;line-height:1.3;">'
        '• reviews: stars, feedback, client_id<br/>'
        '• lawyer_profile.rating updated<br/>'
        '• engagements &amp; case retainer unlocked'
        '</div>'
    )
    add_node('s6_db', s6_db_html, 15, 870, 260, 85, 
             'shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#FFFFFF;strokeColor=#059669;strokeWidth=2;shadow=1;align=left;spacingLeft=12;', 
             parent='col6')

    # --- TOP HORIZONTAL PIPELINE CONNECTORS (LEFT TO RIGHT) ---
    add_edge('flow_1_2', 's1_ui', 's2_ui', 'strokeColor=#0284C7;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_2_3', 's2_ui', 's3_ui', 'strokeColor=#0D9488;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_3_4', 's3_ui', 's4_ui', 'strokeColor=#D97706;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_4_5', 'b_accept', 's5_ui', 'strokeColor=#059669;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')
    add_edge('flow_5_6', 's5_ui', 's6_ui', 'strokeColor=#DB2777;strokeWidth=2.5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;')

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

    # Col 4 (Triage Branches)
    add_edge('e4_v1', 's4_ui', 's4_api', 'strokeColor=#7C3AED;strokeWidth=2;', parent='col4')
    add_edge('e4_b1', 's4_api', 'b_accept', 'strokeColor=#059669;strokeWidth=2;', parent='col4')
    add_edge('e4_b2', 's4_api', 'b_decline', 'strokeColor=#DC2626;strokeWidth=2;', parent='col4')
    add_edge('e4_b3', 's4_api', 'b_resched', 'strokeColor=#D97706;strokeWidth=2;', parent='col4')
    add_edge('e4_v4', 'b_accept', 's4_db', 'strokeColor=#7C3AED;strokeWidth=1.5;dashed=1;', parent='col4')

    # Feedback loop if Declined (Path B back to Stage 1)
    add_edge('e_decline_feedback', 'b_decline', 's1_ui', 
             'strokeColor=#DC2626;strokeWidth=2;dashed=1;exitX=0;exitY=0.5;entryX=1;entryY=0.8;')

    # Col 5
    add_edge('e5_v1', 's5_ui', 's5_api', 'strokeColor=#DB2777;strokeWidth=2;', parent='col5')
    add_edge('e5_v2', 's5_api', 's5_svc', 'strokeColor=#DB2777;strokeWidth=2;', parent='col5')
    add_edge('e5_v3', 's5_svc', 's5_db', 'strokeColor=#DB2777;strokeWidth=1.5;dashed=1;', parent='col5')

    # Col 6
    add_edge('e6_v1', 's6_ui', 's6_api', 'strokeColor=#059669;strokeWidth=2;', parent='col6')
    add_edge('e6_v2', 's6_api', 's6_svc', 'strokeColor=#059669;strokeWidth=2;', parent='col6')
    add_edge('e6_v3', 's6_svc', 's6_next', 'strokeColor=#059669;strokeWidth=2;', parent='col6')
    add_edge('e6_v4', 's6_next', 's6_db', 'strokeColor=#059669;strokeWidth=1.5;dashed=1;', parent='col6')

    xml_str = ET.tostring(mxfile, encoding='utf-8').decode('utf-8')
    with open('docs/flows/lawyer_matching_appointments_enhanced.drawio', 'w', encoding='utf-8') as f:
        f.write(xml_str)
    print("SUCCESS: Enhanced 6-Stage Lawyer Matching & Appointments diagram generated!")

build_enhanced()
