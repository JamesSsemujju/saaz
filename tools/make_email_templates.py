#!/usr/bin/env python3
"""Make the 6 Saaz Supabase Auth email templates from supabase/email-templates/email-config.json.

Usage:  python3 tools/make_email_templates.py
Writes supabase/email-templates/{confirm-signup,invite-user,reset-password,change-email}.html.
Paste each into Supabase: Authentication > Emails > Templates.
Email apps ignore most CSS, so everything is tables with inline styles. Images load from the live site (image_base).
"""
import html, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "supabase/email-templates"
CFG = json.loads((OUT / "email-config.json").read_text(encoding="utf-8"))
IMG = CFG["image_base"]
esc = html.escape
BLACK, INK, MUT, LINE, SOFT, LINK = "#0B0B0C", "#374151", "#6B7280", "#E5E7EB", "#F1F3F6", "#0B0B0C"

def social_buttons():
    cells = []
    for x in CFG["social"]:
        if not x["url"]:
            continue
        if (ROOT / "src/assets/img" / x["icon"]).exists():
            cells.append(f'<td style="padding-left:8px"><a href="{esc(x["url"])}"><img src="{IMG}{x["icon"]}" width="22" height="22" alt="{esc(x["name"])}" style="display:block;border:0"></a></td>')
        else:
            cells.append(f'<td style="padding-left:8px"><a href="{esc(x["url"])}" style="color:{BLACK};font-weight:bold">{esc(x["name"])}</a></td>')
    if not cells:
        return ""
    return (f'<tr><td style="padding:4px 0"><table role="presentation" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="font-size:13px;color:{INK}">Follow us</td>{"".join(cells)}</tr></table></td></tr>')

def link_action(button, note, kind):
    # One-time code in the address; the app page uses it only when the person taps (scanners don't tap)
    href = f'{esc(CFG["app_url"])}?token_hash={{{{ .TokenHash }}}}&amp;type={kind}#/confirm'
    return (f'<tr><td style="padding:22px 32px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="background:{BLACK};border-radius:6px">'
            f'<a href="{href}" style="display:block;padding:13px 20px;color:#FFFFFF;font-size:15px;font-weight:bold;text-decoration:none">{esc(button)}</a></td></tr></table></td></tr>'
            f'<tr><td style="padding:14px 32px 0;font-size:13px;line-height:20px;color:{MUT}">{esc(note)}</td></tr>')

def nolink(text):
    """Stop Gmail turning addresses into blue map links: a zero-width space after each digit run."""
    import re
    return re.sub(r"(\d+)", r"\1&#8203;", esc(text))

def prepare_icons():
    """Official icons dropped into src/assets/img/social/ in any size are resized to 56 x 56 PNG (shown at 28 px)."""
    try:
        from PIL import Image
    except ImportError:
        return
    for s in CFG["social"]:
        f = ROOT / "src/assets/img" / s["icon"]
        if f.exists():
            im = Image.open(f).convert("RGBA")
            if im.size != (56, 56):
                im.thumbnail((56, 56), Image.LANCZOS)
                sq = Image.new("RGBA", (56, 56), (0, 0, 0, 0)); sq.paste(im, ((56 - im.width) // 2, (56 - im.height) // 2), im)
                sq.save(f, optimize=True)

def footer():
    phones = CFG["phone"] if isinstance(CFG["phone"], list) else [CFG["phone"]]
    phones = [p for p in phones if p]
    help_line = f'Our team is here to help. <a href="mailto:{esc(CFG["help_email"])}" style="color:{BLACK}">Write to us</a>'
    if phones:
        help_line += " or call " + " / ".join(f'<a href="tel:{esc(p.replace(" ", ""))}" style="color:{BLACK};white-space:nowrap">{esc(p)}</a>' for p in phones)
    site = CFG["site_url"].replace("https://", "").rstrip("/")
    rows = [
        f'<tr><td style="padding:4px 0;font-size:13px;line-height:20px;color:{INK}">{help_line}.</td></tr>',
        f'<tr><td style="padding:4px 0;font-size:13px"><a href="{esc(CFG["site_url"])}" style="color:{BLACK}">{esc(site)}</a></td></tr>',
        social_buttons(),
        f'<tr><td style="padding:8px 0 2px;font-size:12px;line-height:18px;color:{INK}">{esc(CFG["legal_name"])}, {nolink(CFG["address"])}</td></tr>',
        f'<tr><td style="padding:2px 0 0;font-size:11px;line-height:16px;color:{MUT}">Copyright &copy; {esc(CFG["year"])} {esc(CFG["legal_name"])}. '
        f'Saaz never asks for your password or payment by email.</td></tr>',
    ]
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin-top:12px;background:#F7F8FA;border:1px solid {LINE};border-radius:8px">'
            f'<tr><td style="padding:12px 24px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">' + "".join(rows) + "</table></td></tr></table>")

def code_block():
    return (f'<tr><td style="padding:24px 32px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td align="center" style="background:{SOFT};border-radius:6px;padding:16px;font-size:30px;letter-spacing:8px;font-weight:bold;color:{BLACK};font-family:Courier New,monospace">{{{{ .Token }}}}</td>'
            f'</tr></table></td></tr>')

def page(title, heading, body, button, note, kind=None, code_only=False):
    if code_only:
        action = code_block() + f'<tr><td style="padding:14px 32px 0;font-size:13px;line-height:20px;color:{MUT}">{esc(note)}</td></tr>'
    else:
        action = None
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title></head>
<body style="margin:0;padding:0;background:{SOFT};font-family:Arial,Helvetica,sans-serif;color:#1F2937">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{SOFT}"><tr><td align="center" style="padding:16px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#FFFFFF;border-radius:10px">
<tr><td style="padding:24px 32px 0"><img src="{IMG}brand/saaz-wordmark-email.png" width="120" height="40" alt="Saaz" style="display:block;border:0"></td></tr>
<tr><td style="padding:20px 32px 0"><h1 style="margin:0;font-size:24px;font-weight:normal;color:#111827">{esc(heading)}</h1></td></tr>
<tr><td style="padding:12px 32px 0;font-size:15px;line-height:22px;color:{INK}">{body}</td></tr>
{action or link_action(button, note, kind)}
<tr><td style="padding:20px 32px 24px;font-size:15px;line-height:22px;color:{INK}">Thank you,<br>The Saaz team</td></tr>
</table>
{footer()}
</td></tr></table></body></html>
"""

LH = CFG["link_hours"]
TEMPLATES = {
    "confirm-signup.html": ("Confirm your Saaz email", "Confirm your email",
        "Welcome to Saaz. Confirm your email to finish creating your account and start buying or selling inspected cars.",
        "Confirm my email", f"This link works once and expires {LH} hours after it was sent. Didn't sign up? Ignore this email.", "signup"),
    "invite-user.html": ("You're invited to Saaz", "Set up your garage account",
        "You've been added to a certified Saaz garage. Set your password to open your garage dashboard and see cars to inspect.",
        "Set my password", f"This link works once and expires {LH} hours after it was sent. If it has expired, ask your garage owner to resend it.", "invite"),
    "reset-password.html": ("Reset your Saaz password", "Reset your password",
        "We received a request to reset your Saaz password. If you didn't ask for this, you can safely ignore this email.",
        "Reset my password", f"This link works once and expires {LH} hours after it was sent.", "recovery"),
    "change-email.html": ("Confirm your new Saaz email", "Confirm your new email",
        "You asked to change the email on your Saaz account to {{ .NewEmail }}. Confirm to finish the change.",
        "Confirm new email", f"This link expires {LH} hours after it was sent. If you didn't ask for this, sign in and change your password.", "email_change"),
    # Not used by Saaz today (no sign-in links), branded so nothing unbranded can ever go out
    "magic-link.html": ("Your Saaz sign-in link", "Sign in to Saaz",
        "Use the button to sign in to your Saaz account. You don't need your password for this.",
        "Sign in to Saaz", f"This link works once and expires {LH} hours after it was sent. If you didn't ask to sign in, ignore this email.", "magiclink"),
    # Sent when Saaz asks you to confirm it's you before a sensitive change (password change)
    "reauthentication.html": ("Your Saaz security code", "Confirm it's you",
        "Enter this code in Saaz to finish changing your password or other sensitive details.",
        "", "If you didn't try to change anything, change your password. Never share this code; Saaz will never ask you for it.", None, True),
}
prepare_icons()
for name, t in TEMPLATES.items():
    (OUT / name).write_text(page(*t), encoding="utf-8")
print(f"Wrote {len(TEMPLATES)} templates to {OUT}")
