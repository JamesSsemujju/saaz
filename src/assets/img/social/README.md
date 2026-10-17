# Social icons for emails

Put the official icons here, downloaded from each platform's own brand page (they set how their logo may be used):
- TikTok: TikTok brand guidelines, the TikTok icon
- Instagram: Meta brand resources, the Instagram glyph
- YouTube: YouTube brand resources, the YouTube icon

Save them as `tiktok.png`, `instagram.png`, `youtube.png` (PNG, any size; square works best).
Then run `python3 tools/make_email_templates.py`: it resizes each to 56 x 56 (shown at 28 px) and puts it in the emails. Ship the site so email apps can download them.
Without a file, the email shows a round black button with the platform's name.
