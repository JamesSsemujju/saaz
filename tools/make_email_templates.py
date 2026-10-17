#!/usr/bin/env python3
"""Make the 4 Saaz Supabase Auth email templates from supabase/email-templates/email-config.json.

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
    for s in CFG["social"]:
        if not s["url"]:
            continue
        icon = ROOT / "src/assets/img" / s["icon"]
        if icon.exists():  # official icon dropped in from the platform's brand resources
            inner = f'<img src="{IMG}{s["icon"]}" width="28" height="28" alt="{esc(s["name"])}" style="display:block;border:0">'
            cell = f'<td style="padding-right:8px"><a href="{esc(s["url"])}">{inner}</a></td>'
        else:  # round black button with the name
            cell = (f'<td style="padding-right:8px"><a href="{esc(s["url"])}" style="display:inline-block;background:{BLACK};color:#FFFFFF;'
                    f'font-size:12px;font-weight:bold;text-decoration:none;padding:7px 12px;border-radius:999px">{esc(s["name"])}</a></td>')
        cells.append(cell)
    if not cells:
        return ""
    return (f'<tr><td style="padding:6px 0"><table role="presentation" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="font-size:13px;color:{INK};padding-right:12px">Follow us</td>{"".join(cells)}</tr></table></td></tr>')

def link_action(button, note):
    return (f'<tr><td style="padding:24px 32px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="background:{BLACK};border-radius:6px">'
            f'<a href="{{{{ .ConfirmationURL }}}}" style="display:block;padding:14px 20px;color:#FFFFFF;font-size:16px;font-weight:bold;text-decoration:none">{esc(button)}</a></td></tr></table></td></tr>'
            f'<tr><td style="padding:16px 32px 0;font-size:13px;line-height:20px;color:{MUT}">{esc(note)} If the button doesn\'t work, copy this link into your browser:<br>'
            f'<a href="{{{{ .ConfirmationURL }}}}" style="color:{LINK};word-break:break-all">{{{{ .ConfirmationURL }}}}</a></td></tr>')

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
    help_line = f'Our team is here to help. <a href="mailto:{esc(CFG["help_email"])}" style="color:{LINK}">Write to us</a>'
    phones = CFG["phone"] if isinstance(CFG["phone"], list) else [CFG["phone"]]
    phones = [p for p in phones if p]
    if phones:
        links = " or ".join(f'<a href="tel:{esc(p.replace(" ", ""))}" style="color:{LINK};white-space:nowrap">{esc(p)}</a>' for p in phones)
        help_line += f' or call us on {links}'
    site = CFG["site_url"].replace("https://", "").rstrip("/")
    rows = [
        f'<tr><td style="padding:6px 0;font-size:13px;color:{INK}">{help_line}.</td></tr>',
        f'<tr><td style="padding:6px 0;font-size:13px"><a href="{esc(CFG["site_url"])}" style="color:{LINK}">{esc(site)}</a></td></tr>',
        social_buttons(),
        f'<tr><td style="padding:10px 0 4px;font-size:13px;color:{INK}">{esc(CFG["legal_name"])}, {esc(CFG["address"])}</td></tr>',
        f'<tr><td style="padding:0 0 4px;font-size:11px;color:{MUT}">Copyright &copy; {esc(CFG["year"])} {esc(CFG["legal_name"])}. '
        f'Saaz will never ask for your password or for payment by email. This email was sent to {{{{ .Email }}}} because of an action on your Saaz account.</td></tr>',
    ]
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin-top:16px;background:#F7F8FA;'
            f'border:1px solid {LINE};border-radius:8px"><tr><td style="padding:16px 24px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            + "".join(rows) + "</table></td></tr></table>")

def code_block():
    return (f'<tr><td style="padding:24px 32px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td align="center" style="background:{SOFT};border-radius:6px;padding:16px;font-size:30px;letter-spacing:8px;font-weight:bold;color:{BLACK};font-family:Courier New,monospace">{{{{ .Token }}}}</td>'
            f'</tr></table></td></tr>')

def page(title, heading, body, button, note, code_only=False):
    if code_only:
        action = code_block() + f'<tr><td style="padding:16px 32px 0;font-size:13px;line-height:20px;color:{MUT}">{esc(note)}</td></tr>'
    else:
        action = None
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title></head>
<body style="margin:0;padding:0;background:{SOFT};font-family:Arial,Helvetica,sans-serif;color:#1F2937">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{SOFT}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#FFFFFF;border-radius:10px">
<tr><td style="padding:28px 32px 0"><img src="{IMG}brand/saaz-wordmark-black-240.png" width="120" height="34" alt="Saaz" style="display:block;border:0"></td></tr>
<tr><td style="padding:24px 32px 0"><h1 style="margin:0;font-size:26px;font-weight:normal;color:#111827">{esc(heading)}</h1></td></tr>
<tr><td style="padding:16px 32px 0;font-size:16px;line-height:24px;color:{INK}">{body}</td></tr>
{action or link_action(button, note)}
<tr><td style="padding:24px 32px 28px;font-size:16px;line-height:24px;color:{INK}">Thank you,<br>The Saaz team</td></tr>
</table>
{footer()}
</td></tr></table></body></html>
"""

TEMPLATES = {
    "confirm-signup.html": ("Confirm your Saaz email", "Confirm your email",
        "Welcome to Saaz. Confirm this email address to finish creating your account. After that you're signed in and can buy or sell cars with a Saaz inspection.",
        "Confirm my email", "If you didn't create a Saaz account, you can ignore this email."),
    "invite-user.html": ("You're invited to Saaz", "Set up your garage account",
        "You've been added to a certified garage on Saaz. Set your password to verify this email and open your garage dashboard, where you'll see cars to inspect.",
        "Set my password", "This link works once."),
    "reset-password.html": ("Reset your Saaz password", "Reset your password",
        "We received a request to reset the password for your Saaz account. If you didn't ask for this, you can safely ignore this email; your password stays the same.",
        "Reset my password", "This link works once and expires soon."),
    "change-email.html": ("Confirm your new Saaz email", "Confirm your new email",
        "You asked to change the email on your Saaz account to {{ .NewEmail }}. Confirm to finish the change.",
        "Confirm new email", "If you didn't ask for this, sign in and change your password."),
    # Not used by Saaz today (no sign-in links), branded so nothing unbranded can ever go out
    "magic-link.html": ("Your Saaz sign-in link", "Sign in to Saaz",
        "Use the button to sign in to your Saaz account. You don't need your password for this.",
        "Sign in to Saaz", "If you didn't ask to sign in, you can ignore this email. This link works once."),
    # Sent when Saaz asks you to confirm it's you before a sensitive change (password change)
    "reauthentication.html": ("Your Saaz security code", "Confirm it's you",
        "Enter this code in Saaz to finish changing your password or other sensitive details.",
        "", "If you didn't try to change anything, change your password. Never share this code; Saaz will never ask you for it.", True),
}
prepare_icons()
for name, t in TEMPLATES.items():
    (OUT / name).write_text(page(*t), encoding="utf-8")
print(f"Wrote {len(TEMPLATES)} templates to {OUT}")
