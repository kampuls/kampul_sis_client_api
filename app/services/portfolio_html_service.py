"""
Employee Profile & Portfolio HTML Service
Renders an executive, institutional, mobile-first bilingual (Khmer/English)
employee credentials portfolio page directly from FastAPI.
Uses Kantumruy Pro typography exclusively and crisp SVG vector icons throughout.
Zero animations, zero emoji icons, zero vibe-code aesthetic.
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

    # School information
    school_kh = _esc(data.get("schoolNameKhmer") or "សាលាអន្តរជាតិ ប៉ាម៉ា")
    school_en = _esc(data.get("schoolNameLatin") or "PAMA International School")
    school_logo = data.get("schoolLogo") or ""
    school_phone = _esc(data.get("schoolPhone") or "012/093 746046")
    school_website = _esc(data.get("schoolWebsite") or "https://pamais.duckdns.org")
    director_name = _esc(data.get("directorName") or "PHON Hoklaim")

    # School Logo HTML
    if school_logo:
        school_logo_html = f'<img src="{_esc(school_logo)}" alt="{school_en}" class="school-logo">'
    else:
        school_logo_html = f'<div class="school-logo-fallback">{school_en[:1].upper()}</div>'

    # Photo avatar
    photo_url = data.get("photoUrl") or ""
    initials = e_name[:2].upper()
    if not photo_url:
        avatar_html = f'<div class="avatar-fallback">{initials}</div>'
        pvc_photo_html = f'<div class="pvc-photo pvc-photo-fallback">{initials}</div>'
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
  <meta name="description" content="Official Institutional Employee Credential for {e_name} ({pos_en}) at {school_en}.">
  
  <meta property="og:title" content="{k_name} ({e_name}) – {school_en}">
  <meta property="og:description" content="Official Employee Profile & Verification. ID: {code}">
  <meta property="og:type" content="profile">
  {og_image_tag}

  <!-- Kantumruy Pro exclusively for all Khmer and Latin typography -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Kantumruy+Pro:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400;1,600&display=swap" rel="stylesheet">

  <style>
    :root {{
      --primary-navy: #0f2942;
      --secondary-navy: #1e3a5f;
      --accent-blue: #1d4ed8;
      --text-main: #0f172a;
      --text-muted: #334155;
      --text-subtle: #64748b;
      --bg-page: #f8fafc;
      --bg-card: #ffffff;
      --border-color: #e2e8f0;
      --border-subtle: #f1f5f9;
      --emerald-accent: #059669;
      --emerald-bg: #ecfdf5;
      --emerald-border: #a7f3d0;
      --emerald-text: #065f46;
    }}

    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: 'Kantumruy Pro', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}

    body {{
      background-color: var(--bg-page);
      color: var(--text-main);
      line-height: 1.55;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 0 0 50px 0;
    }}

    .top-navy-stripe {{
      width: 100%;
      height: 4px;
      background: var(--primary-navy);
    }}

    .container {{
      width: 100%;
      max-width: 680px;
      padding: 20px 16px;
    }}

    /* Header */
    .institutional-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      margin-bottom: 16px;
    }}

    .brand-cluster {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .school-logo {{
      width: 44px;
      height: 44px;
      border-radius: 8px;
      object-fit: contain;
      background: #ffffff;
      border: 1px solid var(--border-color);
      padding: 2px;
    }}

    .school-logo-fallback {{
      width: 44px;
      height: 44px;
      border-radius: 8px;
      background: var(--primary-navy);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      color: #ffffff;
      font-size: 18px;
    }}

    .school-title-km {{
      font-size: 14px;
      font-weight: 700;
      color: var(--primary-navy);
      line-height: 1.3;
    }}

    .school-title-en {{
      font-size: 11px;
      color: var(--text-subtle);
      font-weight: 500;
    }}

    .lang-switcher-btn {{
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      color: var(--text-main);
      font-size: 11.5px;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}

    /* Profile Dossier Card */
    .profile-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      overflow: hidden;
      margin-bottom: 16px;
    }}

    .profile-card-header-bar {{
      height: 72px;
      background: var(--primary-navy);
      border-bottom: 3px solid #047857;
    }}

    .profile-card-body {{
      padding: 0 20px 20px;
      text-align: center;
    }}

    .avatar-frame {{
      width: 104px;
      height: 104px;
      margin: -52px auto 12px;
      position: relative;
    }}

    .avatar-img {{
      width: 100%;
      height: 100%;
      border-radius: 50%;
      object-fit: cover;
      border: 4px solid #ffffff;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
      background: #f1f5f9;
    }}

    .avatar-fallback {{
      width: 100%;
      height: 100%;
      border-radius: 50%;
      border: 4px solid #ffffff;
      background: var(--primary-navy);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 32px;
      font-weight: 700;
      color: #ffffff;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    }}

    .avatar-verified-mark {{
      position: absolute;
      bottom: 2px;
      right: 2px;
      width: 20px;
      height: 20px;
      background: #059669;
      border: 2px solid #ffffff;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    .avatar-verified-mark svg {{
      width: 10px;
      height: 10px;
      fill: #ffffff;
    }}

    .faculty-name-km {{
      font-size: 22px;
      font-weight: 700;
      color: var(--text-main);
      margin-bottom: 2px;
    }}

    .faculty-name-en {{
      font-size: 15px;
      font-weight: 600;
      color: var(--secondary-navy);
      margin-bottom: 10px;
    }}

    .role-badge {{
      display: inline-block;
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      color: #1d4ed8;
      font-size: 12.5px;
      font-weight: 600;
      padding: 3px 14px;
      border-radius: 4px;
      margin-bottom: 12px;
    }}

    .verification-chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--emerald-bg);
      border: 1px solid var(--emerald-border);
      color: var(--emerald-text);
      font-size: 11.5px;
      font-weight: 600;
      padding: 4px 14px;
      border-radius: 4px;
      margin-bottom: 14px;
    }}

    .verification-chip svg {{
      width: 14px;
      height: 14px;
      fill: var(--emerald-accent);
      flex-shrink: 0;
    }}

    .meta-data-strip {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 18px;
      flex-wrap: wrap;
      color: var(--text-subtle);
      font-size: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--border-subtle);
    }}

    .meta-data-item {{
      display: flex;
      align-items: center;
      gap: 5px;
    }}

    .meta-data-item svg {{
      width: 14px;
      height: 14px;
      fill: var(--text-subtle);
      flex-shrink: 0;
    }}

    /* Action Buttons (Strict Vector Icons, No Emojis, No Vibe-Code) */
    .actions-row {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
      margin-bottom: 16px;
    }}

    .action-tile {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 6px;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 10px 4px;
      color: var(--text-main);
      text-decoration: none;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
    }}

    .action-tile:hover {{
      background: #f1f5f9;
      border-color: #cbd5e1;
    }}

    .action-tile svg {{
      width: 17px;
      height: 17px;
      fill: #1e3a5f;
    }}

    /* Navigation Tabs */
    .dossier-nav {{
      display: flex;
      gap: 4px;
      background: #e2e8f0;
      padding: 3px;
      border-radius: 8px;
      margin-bottom: 16px;
      overflow-x: auto;
    }}

    .dossier-tab-btn {{
      flex: 1;
      white-space: nowrap;
      background: transparent;
      border: none;
      color: var(--text-subtle);
      font-size: 12px;
      font-weight: 600;
      padding: 8px 10px;
      border-radius: 6px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    }}

    .dossier-tab-btn.active {{
      background: #ffffff;
      color: var(--text-main);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }}

    .dossier-tab-btn svg {{
      width: 14px;
      height: 14px;
      fill: currentColor;
    }}

    /* Tab Content Cards */
    .dossier-panel {{
      display: none;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 20px;
    }}

    .dossier-panel.active {{
      display: block;
    }}

    .dossier-section-title {{
      font-size: 14.5px;
      font-weight: 700;
      color: var(--primary-navy);
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border-color);
    }}

    .dossier-section-title svg {{
      width: 16px;
      height: 16px;
      fill: var(--primary-navy);
    }}

    /* Stats Grid */
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    }}

    .metric-cell {{
      background: #f8fafc;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 12px 8px;
      text-align: center;
    }}

    .metric-number {{
      font-size: 14.5px;
      font-weight: 700;
      color: var(--primary-navy);
      margin-bottom: 2px;
    }}

    .metric-caption {{
      font-size: 10.5px;
      color: var(--text-subtle);
      font-weight: 500;
    }}

    /* Structured Dossier Rows */
    .dossier-table {{
      display: flex;
      flex-direction: column;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      overflow: hidden;
    }}

    .dossier-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      background: #ffffff;
      border-bottom: 1px solid var(--border-color);
      font-size: 12.5px;
    }}

    .dossier-row:nth-child(even) {{
      background: #f8fafc;
    }}

    .dossier-row:last-child {{
      border-bottom: none;
    }}

    .dossier-label {{
      color: var(--text-subtle);
      font-weight: 500;
      min-width: 120px;
    }}

    .dossier-value {{
      color: var(--text-main);
      font-weight: 600;
      text-align: right;
      word-break: break-word;
    }}

    .dossier-value a {{
      color: var(--accent-blue);
      text-decoration: none;
    }}

    .dossier-value a:hover {{
      text-decoration: underline;
    }}

    /* Official PVC Card Preview */
    .pvc-preview-center {{
      display: flex;
      justify-content: center;
      padding: 10px 0;
    }}

    .pvc-card-container {{
      width: 100%;
      max-width: 310px;
      height: 470px;
      background: #0f2942;
      border: 1px solid #1e3a5f;
      border-radius: 12px;
      padding: 20px 16px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
      position: relative;
    }}

    .pvc-header {{
      text-align: center;
      width: 100%;
    }}

    .pvc-school-km {{
      font-size: 12px;
      font-weight: 700;
      color: #ffffff;
    }}

    .pvc-school-en {{
      font-size: 9px;
      color: #93c5fd;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}

    .pvc-photo {{
      width: 100px;
      height: 122px;
      border-radius: 6px;
      object-fit: cover;
      border: 2px solid #ffffff;
      background: #1e293b;
    }}

    .pvc-photo-fallback {{
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 28px;
      font-weight: 700;
      color: #ffffff;
      background: #1e3a5f;
    }}

    .pvc-name-km {{
      font-size: 16px;
      font-weight: 700;
      color: #ffffff;
      margin-top: 8px;
    }}

    .pvc-name-en {{
      font-size: 12.5px;
      font-weight: 600;
      color: #93c5fd;
    }}

    .pvc-role {{
      display: inline-block;
      font-size: 11px;
      color: #fef08a;
      font-weight: 600;
      margin-top: 4px;
    }}

    .pvc-footer {{
      width: 100%;
      border-top: 1px solid rgba(255, 255, 255, 0.15);
      padding-top: 8px;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      font-size: 10px;
      color: #cbd5e1;
    }}

    .pvc-code {{
      font-family: 'Kantumruy Pro', monospace !important;
      font-weight: 700;
      color: #ffffff;
      font-size: 11.5px;
    }}

    /* Official Certification Statement */
    .institutional-statement {{
      margin-top: 16px;
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      border-left: 4px solid var(--primary-navy);
      border-radius: 6px;
      padding: 12px 14px;
      display: flex;
      align-items: flex-start;
      gap: 10px;
    }}

    .institutional-statement svg {{
      width: 20px;
      height: 20px;
      fill: var(--primary-navy);
      flex-shrink: 0;
      margin-top: 2px;
    }}

    .institutional-statement p {{
      font-size: 11.5px;
      color: var(--text-subtle);
      line-height: 1.5;
    }}

    /* Footer */
    .footer-section {{
      text-align: center;
      margin-top: 20px;
      color: #64748b;
      font-size: 11px;
      line-height: 1.6;
    }}

    .footer-section a {{
      color: var(--accent-blue);
      text-decoration: none;
      font-weight: 500;
    }}

    .footer-section a:hover {{
      text-decoration: underline;
    }}

    /* Toast Notification (Solid, No Animations) */
    .system-toast {{
      display: none;
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      background: #0f172a;
      color: #ffffff;
      padding: 9px 18px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      z-index: 9999;
      align-items: center;
      gap: 8px;
    }}

    .system-toast.visible {{
      display: flex;
    }}

    /* Print Setup */
    @media print {{
      body {{
        background: #ffffff !important;
        color: #000000 !important;
        padding: 0 !important;
      }}
      .top-navy-stripe, .actions-row, .dossier-nav, .lang-switcher-btn, .footer-section, .system-toast {{
        display: none !important;
      }}
      .container {{
        max-width: 100% !important;
        padding: 0 !important;
      }}
      .dossier-panel {{
        display: block !important;
        margin-bottom: 16px !important;
        page-break-inside: avoid;
        border: 1px solid #cbd5e1 !important;
      }}
    }}
  </style>
</head>
<body>
  <div class="top-navy-stripe"></div>

  <div class="container">
    <!-- Header -->
    <header class="institutional-header">
      <div class="brand-cluster">
        {school_logo_html}
        <div>
          <div class="school-title-km lang-text" data-km="{school_kh}" data-en="{school_en}">{school_kh}</div>
          <div class="school-title-en lang-text" data-km="ប្រព័ន្ធផ្ទៀងផ្ទាត់បុគ្គលិកផ្លូវការ" data-en="Official Faculty Verification Portal">ប្រព័ន្ធផ្ទៀងផ្ទាត់បុគ្គលិកផ្លូវការ</div>
        </div>
      </div>
      <button class="lang-switcher-btn" onclick="toggleLanguage()" aria-label="Toggle Language">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
        <span id="langLabel">English</span>
      </button>
    </header>

    <!-- Faculty Profile Summary Card -->
    <section class="profile-card">
      <div class="profile-card-header-bar"></div>
      <div class="profile-card-body">
        <div class="avatar-frame">
          {avatar_html}
          <div class="avatar-verified-mark" title="Verified Staff">
            <svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
          </div>
        </div>

        <h1 class="faculty-name-km">{k_name}</h1>
        <div class="faculty-name-en">{e_name}</div>
        
        <div class="role-badge lang-text" data-km="{pos_kh}" data-en="{pos_en}">{pos_kh}</div>

        <div>
          <div class="verification-chip">
            <svg viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"/></svg>
            <span class="lang-text" data-km="វិញ្ញាបនបត្របុគ្គលិកផ្លូវការ • ផ្ទៀងផ្ទាត់រួចរាល់" data-en="Official Faculty Credential • Verified">វិញ្ញាបនបត្របុគ្គលិកផ្លូវការ • ផ្ទៀងផ្ទាត់រួចរាល់</span>
          </div>
        </div>

        <div class="meta-data-strip">
          <div class="meta-data-item">
            <svg viewBox="0 0 24 24"><path d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"/></svg>
            <span class="lang-text" data-km="{dept_kh}" data-en="{dept_en}">{dept_kh}</span>
          </div>
          <div class="meta-data-item">
            <svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>
            <span>{branch}</span>
          </div>
          <div class="meta-data-item">
            <svg viewBox="0 0 24 24"><path d="M20 4H4c-1.11 0-1.99.89-1.99 2L2 18c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm-1 14H5c-.55 0-1-.45-1-1V7c0-.55.45-1 1-1h14c.55 0 1 .45 1 1v10c0 .55-.45 1-1 1zm-7-2h6v-2h-6v2zm0-4h6v-2h-6v2zm-4 4h2v-6H8v6z"/></svg>
            <span>{code}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Professional Actions Row (Clean Vector Icons, No Emojis) -->
    <div class="actions-row">
      <a href="tel:{phone}" class="action-tile" title="Call">
        <svg viewBox="0 0 24 24"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg>
        <span class="lang-text" data-km="ទូរស័ព្ទ" data-en="Call">ទូរស័ព្ទ</span>
      </a>

      <a href="mailto:{email}" class="action-tile" title="Email">
        <svg viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
        <span class="lang-text" data-km="អ៊ីមែល" data-en="Email">អ៊ីមែល</span>
      </a>

      <a href="https://t.me/{clean_tg}" target="_blank" rel="noopener" class="action-tile" title="Telegram">
        <svg viewBox="0 0 24 24"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg>
        <span>Telegram</span>
      </a>

      <button onclick="downloadVCard()" class="action-tile" title="Save Contact (vCard)">
        <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>
        <span class="lang-text" data-km="រក្សាទុក" data-en="Save">រក្សាទុក</span>
      </button>

      <button onclick="shareProfile()" class="action-tile" title="Share Profile">
        <svg viewBox="0 0 24 24"><path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92c0-1.61-1.31-2.92-2.92-2.92z"/></svg>
        <span class="lang-text" data-km="ចែករំលែក" data-en="Share">ចែករំលែក</span>
      </button>
    </div>

    <!-- Dossier Tabs -->
    <div class="dossier-nav">
      <button class="dossier-tab-btn active" onclick="switchTab(event, 'tab-overview')">
        <svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
        <span class="lang-text" data-km="ទិដ្ឋភាពទូទៅ" data-en="Overview">ទិដ្ឋភាពទូទៅ</span>
      </button>
      <button class="dossier-tab-btn" onclick="switchTab(event, 'tab-work')">
        <svg viewBox="0 0 24 24"><path d="M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-6 0h-4V4h4v2z"/></svg>
        <span class="lang-text" data-km="ការងារ" data-en="Work">ការងារ</span>
      </button>
      <button class="dossier-tab-btn" onclick="switchTab(event, 'tab-education')">
        <svg viewBox="0 0 24 24"><path d="M5 13.18v4L12 21l7-3.82v-4L12 17l-7-3.82zM12 3L1 9l11 6 9-4.91V17h2V9L12 3z"/></svg>
        <span class="lang-text" data-km="សញ្ញាបត្រ" data-en="Education">សញ្ញាបត្រ</span>
      </button>
      <button class="dossier-tab-btn" onclick="switchTab(event, 'tab-personal')">
        <svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
        <span class="lang-text" data-km="ផ្ទាល់ខ្លួន" data-en="Personal">ផ្ទាល់ខ្លួន</span>
      </button>
      <button class="dossier-tab-btn" onclick="switchTab(event, 'tab-card')">
        <svg viewBox="0 0 24 24"><path d="M20 4H4c-1.11 0-1.99.89-1.99 2L2 18c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm-1 14H5c-.55 0-1-.45-1-1V7c0-.55.45-1 1-1h14c.55 0 1 .45 1 1v10c0 .55-.45 1-1 1zm-7-2h6v-2h-6v2zm0-4h6v-2h-6v2zm-4 4h2v-6H8v6z"/></svg>
        <span class="lang-text" data-km="បណ្ណសម្គាល់" data-en="ID Card">បណ្ណសម្គាល់</span>
      </button>
    </div>

    <!-- TAB 1: OVERVIEW -->
    <div id="tab-overview" class="dossier-panel active">
      <div class="dossier-section-title">
        <svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
        <span class="lang-text" data-km="ព័ត៌មានសង្ខេប & អតីតភាពការងារ" data-en="Executive Summary & Tenure">ព័ត៌មានសង្ខេប & អតីតភាពការងារ</span>
      </div>

      <div class="metrics-grid">
        <div class="metric-cell">
          <div class="metric-number lang-text" data-km="{service_km}" data-en="{service_en}">{service_km}</div>
          <div class="metric-caption lang-text" data-km="អតីតភាពការងារ" data-en="Service Tenure">អតីតភាពការងារ</div>
        </div>
        <div class="metric-cell">
          <div class="metric-number">{code}</div>
          <div class="metric-caption lang-text" data-km="អត្តលេខសម្គាល់" data-en="Staff ID">អត្តលេខសម្គាល់</div>
        </div>
        <div class="metric-cell">
          <div class="metric-number" style="color:#059669;">100%</div>
          <div class="metric-caption lang-text" data-km="សុពលភាព" data-en="Status">សុពលភាព</div>
        </div>
      </div>

      <div class="dossier-table">
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="អំពីបុគ្គលិក" data-en="Summary">អំពីបុគ្គលិក</span>
          <span class="dossier-value" style="text-align:left;max-width:70%;">{bio}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ស្ថានភាពការងារ" data-en="Duty Status">ស្ថានភាពការងារ</span>
          <span class="dossier-value" style="color:#059669;">{status}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ស្ថាប័ន / សាលា" data-en="Institution">ស្ថាប័ន / សាលា</span>
          <span class="dossier-value lang-text" data-km="{school_kh}" data-en="{school_en}">{school_kh}</span>
        </div>
      </div>
    </div>

    <!-- TAB 2: WORK & ROLE -->
    <div id="tab-work" class="dossier-panel">
      <div class="dossier-section-title">
        <svg viewBox="0 0 24 24"><path d="M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-6 0h-4V4h4v2z"/></svg>
        <span class="lang-text" data-km="ប្រវត្តិការងារ & បេសកកម្ម" data-en="Employment Dossier & Role">ប្រវត្តិការងារ & បេសកកម្ម</span>
      </div>

      <div class="dossier-table">
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ដេប៉ាតឺម៉ង់ / ផ្នែក" data-en="Department">ដេប៉ាតឺម៉ង់ / ផ្នែក</span>
          <span class="dossier-value lang-text" data-km="{dept_kh}" data-en="{dept_en}">{dept_kh}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="មុខតំណែង" data-en="Position">មុខតំណែង</span>
          <span class="dossier-value lang-text" data-km="{pos_kh}" data-en="{pos_en}">{pos_kh}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ទីតាំង / សាខា" data-en="Campus / Branch">ទីតាំង / សាខា</span>
          <span class="dossier-value">{branch}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="កាលបរិច្ឆេទចូលធ្វើការ" data-en="Joined Date">កាលបរិច្ឆេទចូលធ្វើការ</span>
          <span class="dossier-value">{start_work}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ថិរវេលាបម្រើការ" data-en="Service Duration">ថិរវេលាបម្រើការ</span>
          <span class="dossier-value lang-text" data-km="{service_km}" data-en="{service_en}">{service_km}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="លេខកូដបណ្ណបុគ្គលិក" data-en="Staff Card ID">លេខកូដបណ្ណបុគ្គលិក</span>
          <span class="dossier-value" style="color:#0f2942;">{code}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="នាយកគ្រប់គ្រង" data-en="Principal / Director">នាយកគ្រប់គ្រង</span>
          <span class="dossier-value">{director_name}</span>
        </div>
      </div>
    </div>

    <!-- TAB 3: EDUCATION & QUALIFICATIONS -->
    <div id="tab-education" class="dossier-panel">
      <div class="dossier-section-title">
        <svg viewBox="0 0 24 24"><path d="M5 13.18v4L12 21l7-3.82v-4L12 17l-7-3.82zM12 3L1 9l11 6 9-4.91V17h2V9L12 3z"/></svg>
        <span class="lang-text" data-km="កម្រិតវប្បធម៌ & សញ្ញាបត្រ" data-en="Education & Qualifications">កម្រិតវប្បធម៌ & សញ្ញាបត្រ</span>
      </div>

      <div class="dossier-table">
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="កម្រិតវប្បធម៌ខ្ពស់បំផុត" data-en="Highest Degree">កម្រិតវប្បធម៌ខ្ពស់បំផុត</span>
          <span class="dossier-value">{education}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ការផ្ទៀងផ្ទាត់ផ្លូវការ" data-en="Accreditation Status">ការផ្ទៀងផ្ទាត់ផ្លូវការ</span>
          <span class="dossier-value" style="color:#059669;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#059669" style="vertical-align:middle;margin-right:4px;"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
            បានផ្ទៀងផ្ទាត់ផ្លូវការ (Verified)
          </span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ភាសា" data-en="Languages">ភាសា</span>
          <span class="dossier-value">ភាសាខ្មែរ (Khmer), អង់គ្លេស (English)</span>
        </div>
      </div>
    </div>

    <!-- TAB 4: PERSONAL INFORMATION -->
    <div id="tab-personal" class="dossier-panel">
      <div class="dossier-section-title">
        <svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
        <span class="lang-text" data-km="ព័ត៌មានផ្ទាល់ខ្លួន & ទំនាក់ទំនង" data-en="Personal & Contact Information">ព័ត៌មានផ្ទាល់ខ្លួន & ទំនាក់ទំនង</span>
      </div>

      <div class="dossier-table">
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ភេទ" data-en="Gender">ភេទ</span>
          <span class="dossier-value lang-text" data-km="{gender_km}" data-en="{gender_en}">{gender_km}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ថ្ងៃខែឆ្នាំកំណើត" data-en="Date of Birth">ថ្ងៃខែឆ្នាំកំណើត</span>
          <span class="dossier-value">{dob}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="សញ្ជាតិ" data-en="Nationality">សញ្ជាតិ</span>
          <span class="dossier-value">{nationality}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="សាសនា" data-en="Religion">សាសនា</span>
          <span class="dossier-value">{religion}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="អត្តសញ្ញាណប័ណ្ណ" data-en="National ID">អត្តសញ្ញាណប័ណ្ណ</span>
          <span class="dossier-value">{id_num}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ទូរស័ព្ទផ្លូវការ" data-en="Telephone">ទូរស័ព្ទផ្លូវការ</span>
          <span class="dossier-value"><a href="tel:{phone}">{phone or "N/A"}</a></span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="អ៊ីមែលផ្លូវការ" data-en="Email Address">អ៊ីមែលផ្លូវការ</span>
          <span class="dossier-value"><a href="mailto:{email}">{email or "N/A"}</a></span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="អាសយដ្ឋានបច្ចុប្បន្ន" data-en="Current Address">អាសយដ្ឋានបច្ចុប្បន្ន</span>
          <span class="dossier-value">{address}</span>
        </div>
        <div class="dossier-row">
          <span class="dossier-label lang-text" data-km="ទីកន្លែងកំណើត" data-en="Place of Birth">ទីកន្លែងកំណើត</span>
          <span class="dossier-value">{p_address}</span>
        </div>
      </div>
    </div>

    <!-- TAB 5: DIGITAL PVC CARD -->
    <div id="tab-card" class="dossier-panel">
      <div class="dossier-section-title">
        <svg viewBox="0 0 24 24"><path d="M20 4H4c-1.11 0-1.99.89-1.99 2L2 18c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm-1 14H5c-.55 0-1-.45-1-1V7c0-.55.45-1 1-1h14c.55 0 1 .45 1 1v10c0 .55-.45 1-1 1zm-7-2h6v-2h-6v2zm0-4h6v-2h-6v2zm-4 4h2v-6H8v6z"/></svg>
        <span class="lang-text" data-km="បណ្ណសម្គាល់ខ្លួនផ្លូវការ (CR80 PVC)" data-en="Official Faculty PVC ID Card">បណ្ណសម្គាល់ខ្លួនផ្លូវការ (CR80 PVC)</span>
      </div>

      <div class="pvc-preview-center">
        <div class="pvc-card-container">
          <div class="pvc-header">
            <div class="pvc-school-km">{school_kh}</div>
            <div class="pvc-school-en">{school_en}</div>
          </div>

          <div style="text-align:center;margin:10px 0;">
            {pvc_photo_html}
            <div class="pvc-name-km">{k_name}</div>
            <div class="pvc-name-en">{e_name}</div>
            <div class="pvc-role">{pos_kh}</div>
          </div>

          <div class="pvc-footer">
            <div>
              <div>ID NO: <span class="pvc-code">{code}</span></div>
              <div style="font-size:8px;color:#93c5fd;">KAMPUL SECURE SIS</div>
            </div>
            <div style="text-align:right;">
              <div style="font-weight:600;">{director_name}</div>
              <div style="font-size:8px;color:#93c5fd;">PRINCIPAL</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Official Certification Statement -->
    <div class="institutional-statement">
      <svg viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"/></svg>
      <p class="lang-text" data-km="ទិន្នន័យនេះត្រូវបានផ្ទៀងផ្ទាត់ដោយផ្ទាល់ពីមូលដ្ឋានទិន្នន័យនៃប្រព័ន្ធគ្រប់គ្រងសាលារៀនឌីជីថល KAMPUL SIS។ រាល់ព័ត៌មានទាំងអស់មានសុពលភាពផ្លូវការស្របច្បាប់។" data-en="This credential record is verified directly from the school's central database via KAMPUL SIS. All data fields are officially authenticated.">
        ទិន្នន័យនេះត្រូវបានផ្ទៀងផ្ទាត់ដោយផ្ទាល់ពីមូលដ្ឋានទិន្នន័យនៃប្រព័ន្ធគ្រប់គ្រងសាលារៀនឌីជីថល KAMPUL SIS។ រាល់ព័ត៌មានទាំងអស់មានសុពលភាពផ្លូវការស្របច្បាប់។
      </p>
    </div>

    <!-- Footer -->
    <footer class="footer-section">
      <p class="lang-text" data-km="ព័ត៌មានផ្លូវការចេញផ្សាយដោយ {school_kh} តាមរយៈ KAMPUL SIS" data-en="Official credential record issued by {school_en} via KAMPUL SIS">
        ព័ត៌មានផ្លូវការចេញផ្សាយដោយ {school_kh} តាមរយៈ KAMPUL SIS
      </p>
      <p style="margin-top:4px;">
        <a href="{school_website}" target="_blank" rel="noopener">{school_website}</a>
      </p>
    </footer>
  </div>

  <!-- Toast (Strictly Solid) -->
  <div id="systemToast" class="system-toast">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="#10b981"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
    <span id="systemToastText">បានចម្លងតំណភ្ជាប់ដោយជោគជ័យ</span>
  </div>

  <script>
    let currentLang = 'km';

    function showToast(msg) {{
      const t = document.getElementById('systemToast');
      const m = document.getElementById('systemToastText');
      if (t && m) {{
        m.textContent = msg;
        t.classList.add('visible');
        setTimeout(() => {{
          t.classList.remove('visible');
        }}, 2200);
      }}
    }}

    function toggleLanguage() {{
      currentLang = currentLang === 'km' ? 'en' : 'km';
      document.getElementById('langLabel').textContent = currentLang === 'km' ? 'English' : 'ភាសាខ្មែរ';
      
      document.querySelectorAll('.lang-text').forEach(el => {{
        const text = el.getAttribute('data-' + currentLang);
        if (text) el.textContent = text;
      }});
    }}

    function switchTab(e, tabId) {{
      document.querySelectorAll('.dossier-tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.dossier-panel').forEach(panel => panel.classList.remove('active'));
      
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
      showToast(currentLang === 'km' ? 'បានរក្សាទុកទំនាក់ទំនងដោយជោគជ័យ' : 'Contact file downloaded');
    }}

    function shareProfile() {{
      if (navigator.share) {{
        navigator.share({{
          title: '{k_name} ({e_name}) – {pos_en}',
          text: 'Official Employee Credential for {e_name} at {school_en}',
          url: window.location.href
        }}).catch(() => {{}});
      }} else {{
        navigator.clipboard.writeText(window.location.href).then(() => {{
          showToast(currentLang === 'km' ? 'បានចម្លងតំណភ្ជាប់ដោយជោគជ័យ' : 'Link copied to clipboard');
        }}).catch(() => {{
          showToast('Failed to copy');
        }});
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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Kantumruy+Pro:ital,wght@0,400;0,600;0,700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: 'Kantumruy Pro', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }}
    body {{
      background: #f8fafc;
      color: #0f172a;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
      text-align: center;
    }}
    .box {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 40px 24px;
      max-width: 420px;
      width: 100%;
    }}
    .icon {{
      width: 48px;
      height: 48px;
      border-radius: 50%;
      background: #fef2f2;
      color: #ef4444;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 16px;
    }}
    .icon svg {{
      width: 24px;
      height: 24px;
      fill: #ef4444;
    }}
    h1 {{
      font-size: 17px;
      font-weight: 700;
      margin-bottom: 8px;
      color: #0f172a;
    }}
    p {{
      font-size: 13px;
      color: #64748b;
      line-height: 1.5;
      margin-bottom: 18px;
    }}
    .badge {{
      display: inline-block;
      background: #f1f5f9;
      border: 1px solid #cbd5e1;
      padding: 6px 14px;
      border-radius: 6px;
      font-weight: 600;
      color: #334155;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">
      <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
    </div>
    <h1>រកមិនឃើញព័ត៌មានបុគ្គលិក</h1>
    <p>មិនមានទិន្នន័យបុគ្គលិកដែលត្រូវនឹងលេខកូដនេះក្នុងប្រព័ន្ធឡើយ។<br>Employee record could not be found for:</p>
    <div class="badge">{_esc(identifier)}</div>
  </div>
</body>
</html>"""
