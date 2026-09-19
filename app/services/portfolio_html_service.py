"""
Employee Profile & Portfolio HTML Service
Renders a modern, responsive, mobile-first bilingual (Khmer/English)
employee profile portfolio page directly from FastAPI.
"""

from typing import Any, Dict, Optional
import html as htmllib
from datetime import date, datetime


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return htmllib.escape(str(value))


def _calculate_service_duration(start_work: Optional[Any]) -> Dict[str, Any]:
    if not start_work:
        return {"years": 0, "months": 0, "text_km": "មិនមានទិន្នន័យ", "text_en": "Not recorded"}

    d: Optional[date] = None
    if isinstance(start_work, date):
        d = start_work
    elif isinstance(start_work, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                d = datetime.strptime(start_work.split()[0], fmt).date()
                break
            except Exception:
                continue

    if not d:
        return {"years": 0, "months": 0, "text_km": "មិនមានទិន្នន័យ", "text_en": "Not recorded"}

    today = date.today()
    total_months = (today.year - d.year) * 12 + (today.month - d.month)
    if today.day < d.day:
        total_months = max(0, total_months - 1)

    years = total_months // 12
    months = total_months % 12

    km_parts = []
    en_parts = []
    if years > 0:
        km_parts.append(f"{years} ឆ្នាំ")
        en_parts.append(f"{years} yr{'s' if years > 1 else ''}")
    if months > 0 or years == 0:
        km_parts.append(f"{months} ខែ")
        en_parts.append(f"{months} mo{'s' if months > 1 else ''}")

    return {
        "years": years,
        "months": months,
        "text_km": " ".join(km_parts) or "ទើបតែចូលបម្រើការ",
        "text_en": " ".join(en_parts) or "Newly joined",
    }


def render_portfolio_html(data: Dict[str, Any]) -> str:
    k_name = _esc(data.get("khmerName") or "បុគ្គលិកអប់រំ")
    e_name = _esc(data.get("latinName") or "Staff Member")
    pos_kh = _esc(data.get("positionKhmer") or "បុគ្គលិក")
    pos_en = _esc(data.get("positionLatin") or "Faculty Member")
    dept_kh = _esc(data.get("departmentKhmer") or "ផ្នែកអប់រំ")
    dept_en = _esc(data.get("departmentLatin") or "Academic Department")
    branch = _esc(data.get("branchName") or "Main Campus")
    code = _esc(data.get("employeeId") or data.get("cardNo") or data.get("uniqueId") or "EMP-001")
    uid = _esc(data.get("uniqueId") or code)
    phone = _esc(data.get("phone") or "")
    email = _esc(data.get("email") or "")
    telegram = _esc(data.get("telegram") or "")
    gender_km = _esc(data.get("gender") or "មិនបានបញ្ជាក់")
    gender_en = _esc(data.get("genderLatin") or ("Female" if gender_km in ["ស្រី", "Female"] else "Male"))
    dob = _esc(data.get("dob") or "N/A")
    nationality = _esc(data.get("nationality") or "ខ្មែរ")
    religion = _esc(data.get("religion") or "ព្រះពុទ្ធ")
    id_num = _esc(data.get("identityNumber") or "N/A")
    start_work = _esc(data.get("startWork") or "N/A")
    education = _esc(data.get("education") or "បរិញ្ញាបត្រ (Bachelor Degree)")
    address = _esc(data.get("address") or "រាជធានីភ្នំពេញ, ប្រទេសកម្ពុជា")
    p_address = _esc(data.get("pAddress") or address)
    bio = _esc(data.get("bio") or f"សមាជិកបុគ្គលិកផ្លូវការនៃផ្នែក {dept_kh} ប្រកបដោយការប្តេជ្ញាចិត្តខ្ពស់ក្នុងការអភិវឌ្ឍគុណភាពអប់រំ និងសេវាកម្មសិក្សា។")
    status = _esc(data.get("status") or "មន្ត្រីពេញសិទ្ធិ (Active)")

    # School
    school_kh = _esc(data.get("schoolNameKhmer") or "សាលាអន្តរជាតិ ប៉ាម៉ា")
    school_en = _esc(data.get("schoolNameLatin") or "PAMA International School")
    school_logo = data.get("schoolLogo") or ""
    school_phone = _esc(data.get("schoolPhone") or "")
    school_website = _esc(data.get("schoolWebsite") or "https://pamais.duckdns.org")
    director_name = _esc(data.get("directorName") or "PHON Hoklaim")

    # Logo HTML
    if school_logo:
        school_logo_html = f'<img src="{_esc(school_logo)}" alt="{school_en}" class="school-logo">'
    else:
        school_logo_html = '<div class="school-logo-fallback">P</div>'

    # Photo avatar
    photo_url = data.get("photoUrl") or ""
    initials = e_name[:2].upper()
    if not photo_url:
        avatar_html = f'<div class="avatar-fallback">{initials}</div>'
        pvc_photo_html = f'<div class="pvc-photo" style="display:flex;align-items:center;justify-content:center;color:white;font-size:32px;">{initials}</div>'
    else:
        avatar_html = f'<img src="{_esc(photo_url)}" alt="{e_name}" class="avatar-img">'
        pvc_photo_html = f'<img src="{_esc(photo_url)}" alt="{e_name}" class="pvc-photo">'

    og_image_tag = f'<meta property="og:image" content="{_esc(photo_url)}">' if photo_url else ""

    service = _calculate_service_duration(data.get("startWork"))
    service_km = service["text_km"]
    service_en = service["text_en"]
    clean_tg = telegram.lstrip("@")
    file_ename = e_name.replace(" ", "_")

    return f"""<!DOCTYPE html>
<html lang="km">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>{k_name} ({e_name}) – {pos_en} | {school_en}</title>
  <meta name="description" content="Official Verified Employee Profile for {e_name} ({pos_en}) at {school_en}.">
  
  <meta property="og:title" content="{k_name} ({e_name}) – {school_en}">
  <meta property="og:description" content="Official Employee Profile Portfolio. Code: {code}">
  <meta property="og:type" content="profile">
  {og_image_tag}

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Siemreap&family=Battambang:wght@400;700&display=swap" rel="stylesheet">

  <style>
    :root {{
      --primary: #059669;
      --primary-dark: #047857;
      --accent: #38bdf8;
      --bg: #0b1329;
      --card-bg: #111e38;
      --card-inner: #162646;
      --border: rgba(255, 255, 255, 0.08);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --radius-lg: 20px;
      --radius-md: 14px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Plus Jakarta Sans', 'Siemreap', 'Battambang', -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding-bottom: 60px;
      -webkit-font-smoothing: antialiased;
    }}
    .bg-glow {{
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: 0;
      overflow: hidden;
    }}
    .glow-1 {{
      position: absolute;
      top: -100px;
      left: 50%;
      transform: translateX(-50%);
      width: 500px;
      height: 400px;
      background: radial-gradient(circle, rgba(5, 150, 105, 0.25) 0%, rgba(11, 19, 41, 0) 70%);
      filter: blur(60px);
    }}
    .container {{
      width: 100%;
      max-width: 640px;
      padding: 16px;
      position: relative;
      z-index: 1;
    }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: rgba(17, 30, 56, 0.7);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      margin-bottom: 16px;
    }}
    .school-brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .school-logo {{
      width: 42px;
      height: 42px;
      border-radius: 10px;
      object-fit: cover;
      background: #ffffff;
      padding: 2px;
    }}
    .school-logo-fallback {{
      width: 42px;
      height: 42px;
      border-radius: 10px;
      background: linear-gradient(135deg, #059669, #0284c7);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      color: white;
      font-size: 16px;
    }}
    .school-names h2 {{
      font-size: 14px;
      font-weight: 700;
      color: #fff;
      line-height: 1.3;
    }}
    .school-names p {{
      font-size: 11px;
      color: var(--text-muted);
    }}
    .lang-toggle {{
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--border);
      color: #fff;
      font-size: 12px;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 20px;
      cursor: pointer;
    }}
    .hero-card {{
      background: linear-gradient(180deg, #162646 0%, #111e38 100%);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 28px 20px 20px;
      text-align: center;
      position: relative;
      overflow: hidden;
      margin-bottom: 16px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }}
    .avatar-wrapper {{
      position: relative;
      width: 108px;
      height: 108px;
      margin: 0 auto 16px;
    }}
    .avatar-img {{
      width: 100%;
      height: 100%;
      border-radius: 50%;
      object-fit: cover;
      border: 4px solid #162646;
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
      background: #1e293b;
    }}
    .avatar-fallback {{
      width: 100%;
      height: 100%;
      border-radius: 50%;
      border: 4px solid #162646;
      background: linear-gradient(135deg, #059669, #047857);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 36px;
      font-weight: 800;
      color: white;
    }}
    .status-badge-dot {{
      position: absolute;
      bottom: 4px;
      right: 4px;
      width: 18px;
      height: 18px;
      background: #10b981;
      border: 3px solid #162646;
      border-radius: 50%;
      box-shadow: 0 0 10px #10b981;
    }}
    .k-name {{
      font-size: 22px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 2px;
    }}
    .e-name {{
      font-size: 16px;
      font-weight: 600;
      color: #38bdf8;
      margin-bottom: 8px;
    }}
    .position-pill {{
      display: inline-block;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
      font-size: 13px;
      font-weight: 600;
      padding: 4px 14px;
      border-radius: 20px;
      margin-bottom: 12px;
    }}
    .meta-info {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 16px;
      flex-wrap: wrap;
      color: var(--text-muted);
      font-size: 12px;
    }}
    .meta-item {{
      display: flex;
      align-items: center;
      gap: 5px;
    }}
    .verified-chip {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: #7dd3fc;
      padding: 3px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
    }}
    .actions-grid {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
      margin-bottom: 16px;
    }}
    .action-btn {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 6px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 12px 6px;
      color: var(--text);
      text-decoration: none;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .action-btn:hover, .action-btn:active {{
      background: var(--card-inner);
      border-color: rgba(255, 255, 255, 0.2);
    }}
    .action-icon {{
      font-size: 18px;
    }}
    .tabs-nav {{
      display: flex;
      gap: 6px;
      background: rgba(17, 30, 56, 0.8);
      padding: 5px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
      margin-bottom: 16px;
      overflow-x: auto;
    }}
    .tab-btn {{
      flex: 1;
      white-space: nowrap;
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 12px;
      font-weight: 600;
      padding: 8px 12px;
      border-radius: 10px;
      cursor: pointer;
      text-align: center;
    }}
    .tab-btn.active {{
      background: var(--primary);
      color: #ffffff;
      box-shadow: 0 2px 10px rgba(5, 150, 105, 0.4);
    }}
    .tab-panel {{
      display: none;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 20px;
    }}
    .tab-panel.active {{ display: block; }}
    .section-title {{
      font-size: 15px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }}
    .stats-row {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    }}
    .stat-box {{
      background: var(--card-inner);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 12px 10px;
      text-align: center;
    }}
    .stat-val {{
      font-size: 15px;
      font-weight: 700;
      color: #38bdf8;
      margin-bottom: 2px;
    }}
    .stat-lbl {{
      font-size: 11px;
      color: var(--text-muted);
    }}
    .detail-list {{
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .detail-item {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 8px 12px;
      background: var(--card-inner);
      border-radius: 10px;
      font-size: 13px;
    }}
    .detail-item .lbl {{
      color: var(--text-muted);
      min-width: 110px;
      font-weight: 500;
    }}
    .detail-item .val {{
      color: #f1f5f9;
      font-weight: 600;
      text-align: right;
      word-break: break-word;
    }}
    .card-3d-wrapper {{
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 10px 0;
    }}
    .pvc-card {{
      width: 100%;
      max-width: 310px;
      height: 460px;
      background: linear-gradient(135deg, #064e3b 0%, #022c22 100%);
      border: 1px solid rgba(52, 211, 153, 0.3);
      border-radius: 16px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
      padding: 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: space-between;
    }}
    .pvc-header {{ text-align: center; width: 100%; }}
    .pvc-school {{ font-size: 12px; font-weight: 700; color: #a7f3d0; }}
    .pvc-sub {{ font-size: 9px; color: #6ee7b7; text-transform: uppercase; }}
    .pvc-photo {{
      width: 110px;
      height: 130px;
      border-radius: 10px;
      object-fit: cover;
      border: 3px solid #34d399;
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
      background: #064e3b;
    }}
    .pvc-name-km {{ font-size: 18px; font-weight: 700; color: #ffffff; margin-top: 8px; }}
    .pvc-name-en {{ font-size: 13px; font-weight: 600; color: #38bdf8; }}
    .pvc-role {{ font-size: 11px; color: #fbbf24; font-weight: 600; }}
    .pvc-footer {{
      width: 100%;
      border-top: 1px solid rgba(255, 255, 255, 0.15);
      padding-top: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 10px;
      color: #d1fae5;
    }}
    .pvc-code {{ font-family: monospace; font-size: 12px; font-weight: 700; }}
    .footer {{ text-align: center; margin-top: 30px; color: #64748b; font-size: 11px; }}
    .footer a {{ color: #38bdf8; text-decoration: none; }}
    @media print {{
      body {{ background: #fff; color: #000; padding: 0; }}
      .bg-glow, .actions-grid, .tabs-nav, .lang-toggle, .footer {{ display: none !important; }}
      .hero-card, .tab-panel {{ background: #fff; border: 1px solid #ccc; color: #000; box-shadow: none; }}
      .tab-panel {{ display: block !important; margin-bottom: 20px; }}
      .k-name, .e-name, .section-title {{ color: #000 !important; }}
      .detail-item {{ background: #f8fafc; border: 1px solid #e2e8f0; color: #000; }}
      .detail-item .lbl {{ color: #475569; }}
      .detail-item .val {{ color: #000; }}
    }}
  </style>
</head>
<body>
  <div class="bg-glow"><div class="glow-1"></div></div>

  <div class="container">
    <header class="header">
      <div class="school-brand">
        {school_logo_html}
        <div class="school-names">
          <h2 class="lang-text" data-km="{school_kh}" data-en="{school_en}">{school_kh}</h2>
          <p class="lang-text" data-km="ប្រព័ន្ធគ្រប់គ្រងសាលារៀនឌីជីថល" data-en="Digital School Management System">ប្រព័ន្ធគ្រប់គ្រងសាលារៀនឌីជីថល</p>
        </div>
      </div>
      <button class="lang-toggle" onclick="toggleLanguage()">
        🌐 <span id="langLabel">English</span>
      </button>
    </header>

    <section class="hero-card">
      <div class="avatar-wrapper">
        {avatar_html}
        <div class="status-badge-dot" title="Active Faculty"></div>
      </div>

      <div class="names-section">
        <h1 class="k-name">{k_name}</h1>
        <div class="e-name">{e_name}</div>
        <div class="position-pill lang-text" data-km="{pos_kh}" data-en="{pos_en}">{pos_kh}</div>
        
        <div class="meta-info">
          <div class="meta-item">
            <span>🏢</span>
            <span class="lang-text" data-km="{dept_kh}" data-en="{dept_en}">{dept_kh}</span>
          </div>
          <div class="meta-item">
            <span>📍</span>
            <span>{branch}</span>
          </div>
          <div class="verified-chip">
            <span>✔</span>
            <span class="lang-text" data-km="ផ្ទៀងផ្ទាត់ផ្លូវការ" data-en="Verified Staff">ផ្ទៀងផ្ទាត់ផ្លូវការ</span>
          </div>
        </div>
      </div>
    </section>

    <div class="actions-grid">
      <a href="tel:{phone}" class="action-btn" style="color:#10b981;" title="Call">
        <span class="action-icon">📞</span>
        <span class="lang-text" data-km="ទូរស័ព្ទ" data-en="Call">ទូរស័ព្ទ</span>
      </a>

      <a href="mailto:{email}" class="action-btn" style="color:#f59e0b;" title="Email">
        <span class="action-icon">✉️</span>
        <span class="lang-text" data-km="អ៊ីមែល" data-en="Email">អ៊ីមែល</span>
      </a>

      <a href="https://t.me/{clean_tg}" target="_blank" rel="noopener" class="action-btn" style="color:#38bdf8;" title="Telegram">
        <span class="action-icon">✈️</span>
        <span>Telegram</span>
      </a>

      <button onclick="downloadVCard()" class="action-btn" style="color:#a855f7;" title="Save to Contacts">
        <span class="action-icon">💾</span>
        <span class="lang-text" data-km="រក្សាទុក" data-en="Save">រក្សាទុក</span>
      </button>

      <button onclick="shareProfile()" class="action-btn" style="color:#ec4899;" title="Share Profile">
        <span class="action-icon">🔗</span>
        <span class="lang-text" data-km="ចែករំលែក" data-en="Share">ចែករំលែក</span>
      </button>
    </div>

    <div class="tabs-nav">
      <button class="tab-btn active" onclick="switchTab(event, 'tab-overview')">
        <span class="lang-text" data-km="ទិដ្ឋភាពទូទៅ" data-en="Overview">ទិដ្ឋភាពទូទៅ</span>
      </button>
      <button class="tab-btn" onclick="switchTab(event, 'tab-work')">
        <span class="lang-text" data-km="ការងារ" data-en="Work">ការងារ</span>
      </button>
      <button class="tab-btn" onclick="switchTab(event, 'tab-education')">
        <span class="lang-text" data-km="សញ្ញាបត្រ" data-en="Education">សញ្ញាបត្រ</span>
      </button>
      <button class="tab-btn" onclick="switchTab(event, 'tab-personal')">
        <span class="lang-text" data-km="ផ្ទាល់ខ្លួន" data-en="Personal">ផ្ទាល់ខ្លួន</span>
      </button>
      <button class="tab-btn" onclick="switchTab(event, 'tab-card')">
        <span class="lang-text" data-km="បណ្ណសម្គាល់" data-en="ID Card">បណ្ណសម្គាល់</span>
      </button>
    </div>

    <div id="tab-overview" class="tab-panel active">
      <h3 class="section-title">
        <span>📋</span>
        <span class="lang-text" data-km="ព័ត៌មានសង្ខេប & សមិទ្ធផល" data-en="Summary & Overview">ព័ត៌មានសង្ខេប & សមិទ្ធផល</span>
      </h3>

      <div class="stats-row">
        <div class="stat-box">
          <div class="stat-val lang-text" data-km="{service_km}" data-en="{service_en}">{service_km}</div>
          <div class="stat-lbl lang-text" data-km="អតីតភាពការងារ" data-en="Service Time">អតីតភាពការងារ</div>
        </div>
        <div class="stat-box">
          <div class="stat-val">{code}</div>
          <div class="stat-lbl lang-text" data-km="លេខកូដសម្គាល់" data-en="ID Number">លេខកូដសម្គាល់</div>
        </div>
        <div class="stat-box">
          <div class="stat-val" style="color:#10b981;">100%</div>
          <div class="stat-lbl lang-text" data-km="ស្ថានភាព" data-en="Status">ស្ថានភាព</div>
        </div>
      </div>

      <div class="detail-list">
        <div class="detail-item">
          <span class="lbl lang-text" data-km="អំពីបុគ្គលិក" data-en="About">អំពីបុគ្គលិក</span>
          <span class="val" style="text-align:left;">{bio}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ស្ថានភាពការងារ" data-en="Duty Status">ស្ថានភាពការងារ</span>
          <span class="val" style="color:#34d399;">{status}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ស្ថាប័ន / សាលា" data-en="Institution">ស្ថាប័ន / សាលា</span>
          <span class="val lang-text" data-km="{school_kh}" data-en="{school_en}">{school_kh}</span>
        </div>
      </div>
    </div>

    <div id="tab-work" class="tab-panel">
      <h3 class="section-title">
        <span>💼</span>
        <span class="lang-text" data-km="ប្រវត្តិការងារ និងតួនាទី" data-en="Work Dossier & Role">ប្រវត្តិការងារ និងតួនាទី</span>
      </h3>

      <div class="detail-list">
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ដេប៉ាតឺម៉ង់ / ផ្នែក" data-en="Department">ដេប៉ាតឺម៉ង់ / ផ្នែក</span>
          <span class="val lang-text" data-km="{dept_kh}" data-en="{dept_en}">{dept_kh}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="មុខតំណែង" data-en="Position">មុខតំណែង</span>
          <span class="val lang-text" data-km="{pos_kh}" data-en="{pos_en}">{pos_kh}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ទីតាំង / សាខា" data-en="Branch / Campus">ទីតាំង / សាខា</span>
          <span class="val">{branch}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="កាលបរិច្ឆេទចូលធ្វើការ" data-en="Joined Date">កាលបរិច្ឆេទចូលធ្វើការ</span>
          <span class="val">{start_work}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ថិរវេលាបម្រើការ" data-en="Duration">ថិរវេលាបម្រើការ</span>
          <span class="val lang-text" data-km="{service_km}" data-en="{service_en}">{service_km}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="លេខបណ្ណបុគ្គលិក" data-en="Card Number">លេខបណ្ណបុគ្គលិក</span>
          <span class="val" style="font-family:monospace;color:#38bdf8;">{code}</span>
        </div>
      </div>
    </div>

    <div id="tab-education" class="tab-panel">
      <h3 class="section-title">
        <span>🎓</span>
        <span class="lang-text" data-km="កម្រិតវប្បធម៌ & សញ្ញាបត្រ" data-en="Education & Qualifications">កម្រិតវប្បធម៌ & សញ្ញាបត្រ</span>
      </h3>

      <div class="detail-list">
        <div class="detail-item">
          <span class="lbl lang-text" data-km="កម្រិតវប្បធម៌ខ្ពស់បំផុត" data-en="Highest Degree">កម្រិតវប្បធម៌ខ្ពស់បំផុត</span>
          <span class="val">{education}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ការផ្ទៀងផ្ទាត់សញ្ញាបត្រ" data-en="Accreditation">ការផ្ទៀងផ្ទាត់សញ្ញាបត្រ</span>
          <span class="val" style="color:#10b981;">✔ បានផ្ទៀងផ្ទាត់ (Verified)</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ភាសា" data-en="Languages">ភាសា</span>
          <span class="val">ភាសាខ្មែរ (Khmer), អង់គ្លេស (English)</span>
        </div>
      </div>
    </div>

    <div id="tab-personal" class="tab-panel">
      <h3 class="section-title">
        <span>👤</span>
        <span class="lang-text" data-km="ព័ត៌មានផ្ទាល់ខ្លួន & ទំនាក់ទំនង" data-en="Personal Information">ព័ត៌មានផ្ទាល់ខ្លួន & ទំនាក់ទំនង</span>
      </h3>

      <div class="detail-list">
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ភេទ" data-en="Gender">ភេទ</span>
          <span class="val lang-text" data-km="{gender_km}" data-en="{gender_en}">{gender_km}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ថ្ងៃខែឆ្នាំកំណើត" data-en="Date of Birth">ថ្ងៃខែឆ្នាំកំណើត</span>
          <span class="val">{dob}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="សញ្ជាតិ" data-en="Nationality">សញ្ជាតិ</span>
          <span class="val">{nationality}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="សាសនា" data-en="Religion">សាសនា</span>
          <span class="val">{religion}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="អត្តសញ្ញាណប័ណ្ណ" data-en="National ID">អត្តសញ្ញាណប័ណ្ណ</span>
          <span class="val" style="font-family:monospace;">{id_num}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ទូរស័ព្ទ" data-en="Phone">ទូរស័ព្ទ</span>
          <span class="val"><a href="tel:{phone}" style="color:#38bdf8;text-decoration:none;">{phone or "N/A"}</a></span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="អ៊ីមែល" data-en="Email">អ៊ីមែល</span>
          <span class="val"><a href="mailto:{email}" style="color:#38bdf8;text-decoration:none;">{email or "N/A"}</a></span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="អាសយដ្ឋានបច្ចុប្បន្ន" data-en="Address">អាសយដ្ឋានបច្ចុប្បន្ន</span>
          <span class="val">{address}</span>
        </div>
        <div class="detail-item">
          <span class="lbl lang-text" data-km="ទីកន្លែងកំណើត" data-en="Place of Birth">ទីកន្លែងកំណើត</span>
          <span class="val">{p_address}</span>
        </div>
      </div>
    </div>

    <div id="tab-card" class="tab-panel">
      <h3 class="section-title">
        <span>🪪</span>
        <span class="lang-text" data-km="បណ្ណសម្គាល់ខ្លួនឌីជីថល (CR80)" data-en="Official Digital ID Card">បណ្ណសម្គាល់ខ្លួនឌីជីថល (CR80)</span>
      </h3>

      <div class="card-3d-wrapper">
        <div class="pvc-card">
          <div class="pvc-header">
            <div class="pvc-school">{school_kh}</div>
            <div class="pvc-sub">{school_en}</div>
          </div>

          <div style="text-align:center;margin:12px 0;">
            {pvc_photo_html}
            <div class="pvc-name-km">{k_name}</div>
            <div class="pvc-name-en">{e_name}</div>
            <div class="pvc-role">{pos_kh}</div>
          </div>

          <div class="pvc-footer">
            <div>
              <div>ID NO: <span class="pvc-code">{code}</span></div>
              <div style="font-size:8px;color:#94a3b8;">KAMPUL SECURE SIS</div>
            </div>
            <div style="text-align:right;">
              <div>{director_name}</div>
              <div style="font-size:8px;color:#94a3b8;">PRINCIPAL</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <footer class="footer">
      <p class="lang-text" data-km="ព័ត៌មានផ្លូវការចេញផ្សាយដោយ {school_kh} តាមរយៈ KAMPUL SIS" data-en="Official profile issued by {school_en} via KAMPUL SIS">
        ព័ត៌មានផ្លូវការចេញផ្សាយដោយ {school_kh} តាមរយៈ KAMPUL SIS
      </p>
      <p style="margin-top:6px;">
        <a href="{school_website}" target="_blank">{school_website}</a>
      </p>
    </footer>
  </div>

  <script>
    let currentLang = 'km';

    function toggleLanguage() {{
      currentLang = currentLang === 'km' ? 'en' : 'km';
      document.getElementById('langLabel').textContent = currentLang === 'km' ? 'English' : 'ភាសាខ្មែរ';
      
      document.querySelectorAll('.lang-text').forEach(el => {{
        const text = el.getAttribute('data-' + currentLang);
        if (text) el.textContent = text;
      }});
    }}

    function switchTab(e, tabId) {{
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
      
      e.currentTarget.classList.add('active');
      const target = document.getElementById(tabId);
      if (target) target.classList.add('active');
    }}

    function downloadVCard() {{
      const vcard = [
        'BEGIN:VCARD',
        'VERSION:3.0',
        'N:{e_name};;;;',
        'FN:{e_name} ({k_name})',
        'ORG:{school_en};{dept_en}',
        'TITLE:{pos_en}',
        'TEL;TYPE=CELL:{phone}',
        'EMAIL:{email}',
        'NOTE:Official Verified Faculty Member. ID: {code}',
        'URL:{school_website}',
        'END:VCARD'
      ].join('\\r\\n');

      const blob = new Blob([vcard], {{ type: 'text/vcard;charset=utf-8;' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = '{file_ename}_Contact.vcf';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }}

    function shareProfile() {{
      if (navigator.share) {{
        navigator.share({{
          title: '{k_name} ({e_name}) – {pos_en}',
          text: 'Official Employee Portfolio for {e_name} at {school_en}',
          url: window.location.href
        }}).catch(() => {{}});
      }} else {{
        navigator.clipboard.writeText(window.location.href).then(() => {{
          alert(currentLang === 'km' ? 'បានចម្លងតំណភ្ជាប់ដោយជោគជ័យ!' : 'Portfolio link copied to clipboard!');
        }}).catch(() => {{}});
      }}
    }}
  </script>
</body>
</html>"""


def render_not_found_html(identifier: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="km">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>រកមិនឃើញព័ត៌មានបុគ្គលិក / Employee Not Found</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0b1329; color: #f8fafc;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; padding: 24px; text-align: center;
    }}
    .box {{
      background: #111e38; border: 1px solid rgba(255,255,255,0.1);
      border-radius: 20px; padding: 40px 24px; max-width: 420px; width: 100%;
    }}
    .icon {{ font-size: 54px; margin-bottom: 16px; }}
    h1 {{ font-size: 18px; margin-bottom: 8px; color: #38bdf8; }}
    p {{ font-size: 13px; color: #94a3b8; line-height: 1.6; margin-bottom: 20px; }}
    .badge {{ display: inline-block; background: #1e293b; padding: 6px 14px; border-radius: 8px; font-family: monospace; color: #fbbf24; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">🔍</div>
    <h1>រកមិនឃើញព័ត៌មានបុគ្គលិក</h1>
    <p>មិនមានទិន្នន័យបុគ្គលិកដែលត្រូវនឹងលេខកូដនេះក្នុងប្រព័ន្ធឡើយ។<br>Employee record could not be found for:</p>
    <div class="badge">{_esc(identifier)}</div>
  </div>
</body>
</html>"""
