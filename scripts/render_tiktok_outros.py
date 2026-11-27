"""Render 8 crisp 9:16 (1080x1920 @ 30fps, 6.0s) vertical TikTok outro cards for DUP Labs Chapters 01-08."""
import base64
import os
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
import imageio_ffmpeg

from visual_tokens import (  # noqa: E402  (single token source; item 8)
    BG,
    BG_GRADIENT_DEEP,
    BG_GRADIENT_MID,
    CARD_BG,
    FONT_MONO_CANVAS,
    FONT_UI_CANVAS,
    MUTED,
    TEXT,
)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ASSETS = Path(r"C:\Users\vovun\.cursor\projects\c-Users-vovun-Desktop-Absolute-Blockchain-Experimental\assets")
OUT = Path(r"C:\Users\vovun\Desktop\DUP_Projects\dup-presenter\public\cinema")

CHAPTERS = [
    ("01", "dup-protocol", "Гибридный L1: Rust + Python", "emb-dup-protocol.jpg", "#38bdf8", "#0284c7"),
    ("02", "dup-presenter", "Автономная 3D и киностудия", "emb-dup-presenter.jpg", "#f59e0b", "#ec4899"),
    ("03", "dup-market-radar", "Спотовый кокпит и телеметрия", "emb-dup-market-radar.jpg", "#10b981", "#059669"),
    ("04", "dup-skill-trust-plane", "Zero-Key доверие для ИИ", "emb-dup-skill-trust-plane.jpg", "#a855f7", "#7c3aed"),
    ("05", "dup-lab", "Портал запуска одной командой", "emb-dup-lab.jpg", "#60a5fa", "#2563eb"),
    ("06", "dup-policy-gate", "Детерминированный фаервол", "emb-dup-policy-gate.jpg", "#f43f5e", "#e11d48"),
    ("07", "dup-protocol-experimental", "Изолированный R&D реактор", "emb-dup-protocol-experimental.jpg", "#3b82f6", "#1d4ed8"),
    ("08", "dup-evidence-graph", "Машинная честность на диске", "emb-dup-evidence-graph.jpg", "#c084fc", "#9333ea"),
]


def img_b64(filename: str) -> str:
    raw = (ASSETS / filename).read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def make_html(ep: str, slug: str, role: str, emb_b64: str, c1: str, c2: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1080px; height:1920px; overflow:hidden; background:{BG}; }}
canvas {{ display:block; width:1080px; height:1920px; }}
</style></head>
<body>
<canvas id="c" width="1080" height="1920"></canvas>
<script>
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const W = 1080, H = 1920;
const CX = W / 2, CY = 690;

const emb = new Image();
emb.src = {emb_b64!r};

const stars = Array.from({{length: 200}}, (_, i) => ({{
  x: (Math.sin(i * 127.1) * 0.5 + 0.5) * W,
  y: (Math.sin(i * 311.7) * 0.5 + 0.5) * H,
  r: 0.9 + (i % 3) * 0.75,
  p: i * 0.5,
  c: i % 5 === 0 ? '{c1}' : (i % 7 === 0 ? '{c2}' : '{TEXT}')
}}));

function rr(x, y, w, h, r) {{
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}}

function drawCircleImg(img, x, y, r, color) {{
  ctx.save();
  ctx.shadowColor = color;
  ctx.shadowBlur = 46;
  ctx.beginPath();
  ctx.arc(x, y, r + 5, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.25;
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.restore();

  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.closePath();
  ctx.clip();
  ctx.drawImage(img, x - r, y - r, r * 2, r * 2);
  ctx.restore();

  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, r + 2, 0, Math.PI * 2);
  ctx.strokeStyle = color;
  ctx.lineWidth = 4;
  ctx.stroke();
  ctx.restore();
}}

window.renderFrame = function(t) {{
  ctx.clearRect(0, 0, W, H);

  // Deep vertical nebula backdrop
  const bg = ctx.createRadialGradient(CX, CY, 60, CX, CY + 120, 1100);
  bg.addColorStop(0, '{c1}26');
bg.addColorStop(0.45, '{BG_GRADIENT_MID}');
bg.addColorStop(1, '{BG_GRADIENT_DEEP}');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  for (const s of stars) {{
    ctx.globalAlpha = 0.28 + 0.58 * (0.5 + 0.5 * Math.sin(t * 2.2 + s.p));
    ctx.fillStyle = s.c;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
    ctx.fill();
  }}
  ctx.globalAlpha = 1;

  // Top safe header (below TikTok top UI)
  const topA = Math.min(1, t / 0.45);
  ctx.globalAlpha = topA;
  rr(CX - 250, 225, 500, 56, 28);
  ctx.fillStyle = '{CARD_BG}';
  ctx.fill();
  ctx.strokeStyle = '{c1}aa';
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.textAlign = 'center';
  ctx.fillStyle = '{c1}';
  ctx.font = '800 24px {FONT_UI_CANVAS}';
  ctx.fillText('DUP LABS  ·  ГЛАВА {ep} / 08', CX, 262);
  ctx.globalAlpha = 1;

  // Animated orbital rings around emblem
  for (let i = 0; i < 3; i++) {{
    ctx.save();
    ctx.translate(CX, CY);
    ctx.rotate(t * (0.35 + i * 0.22) * (i % 2 === 0 ? 1 : -1));
    ctx.strokeStyle = i === 0 ? '{c1}99' : (i === 1 ? '{c2}77' : 'rgba(255,255,255,0.22)');
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.ellipse(0, 0, 235 + i * 44, 155 + i * 32, i * 0.55, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }}

  const scale = 0.85 + 0.15 * Math.min(1, t / 0.55);
  drawCircleImg(emb, CX, CY, 168 * scale, '{c1}');

  // Title & role
  const txtA = Math.min(1, Math.max(0, (t - 0.35) / 0.5));
  ctx.globalAlpha = txtA;
  ctx.textAlign = 'center';

  const grad = ctx.createLinearGradient(140, 960, 940, 960);
  grad.addColorStop(0, '#ffffff');
  grad.addColorStop(0.5, '{c1}');
  grad.addColorStop(1, '{c2}');
  ctx.fillStyle = grad;
  const slugFont = '{slug}'.length > 18 ? 58 : 74;
  ctx.font = '900 ' + slugFont + 'px {FONT_UI_CANVAS}';
  ctx.fillText('{slug}', CX, 1020);

  ctx.fillStyle = '{TEXT}';
  ctx.font = '600 32px {FONT_UI_CANVAS}';
  ctx.fillText('{role}', CX, 1082);

  // URL Pill (well above TikTok bottom caption/UI safe zone)
  const pillW = 840, pillH = 88;
  rr(CX - pillW / 2, 1142, pillW, pillH, 44);
  ctx.fillStyle = '{CARD_BG}';
  ctx.fill();
  ctx.strokeStyle = '{c1}';
  ctx.lineWidth = 3;
  ctx.stroke();

  ctx.fillStyle = '#ffffff';
  const urlFont = '{slug}'.length > 18 ? 29 : 34;
  ctx.font = '700 ' + urlFont + 'px {FONT_MONO_CANVAS}';
  ctx.fillText('github.com/Gruver87/{slug}', CX, 1198);

  // Subtle studio credit pill
  ctx.fillStyle = '{MUTED}';
  ctx.font = '700 22px {FONT_UI_CANVAS}';
  ctx.fillText('СОЗДАНО АВТОНОМНО НА DUP-PRESENTER', CX, 1300);
  ctx.fillStyle = '{c1}cc';
  ctx.font = '700 22px {FONT_MONO_CANVAS}';
  ctx.fillText('github.com/Gruver87', CX, 1340);

  ctx.globalAlpha = 1;
}};
</script></body></html>"""


def main():
    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
    fps = 30
    dur = 6.0
    total = int(fps * dur)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for ep, slug, role, emb_file, c1, c2 in CHAPTERS:
            out_mp4 = OUT / f"tt_outro_{ep}.mp4"
            if ep == "01" and out_mp4.exists() and out_mp4.stat().st_size > 200_000:
                print(f"SKIP {out_mp4.name} (already rendered)")
                continue
            page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
            html = make_html(ep, slug, role, img_b64(emb_file), c1, c2)
            page.set_content(html, wait_until="load")
            page.wait_for_timeout(150)

            cmd = [
                FFMPEG, "-y",
                "-f", "image2pipe", "-vcodec", "png", "-r", str(fps), "-i", "-",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-profile:v", "high", "-level:v", "4.1",
                "-pix_fmt", "yuv420p", "-color_range", "tv",
                "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-movflags", "+faststart",
                str(out_mp4),
            ]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for i in range(total):
                page.evaluate(f"window.renderFrame({i / fps:.4f})")
                png = page.screenshot(type="png")
                proc.stdin.write(png)
            proc.stdin.close()
            ret = proc.wait()
            page.close()
            assert ret == 0, f"ffmpeg failed on {ep}"
            mb = out_mp4.stat().st_size / (1024 * 1024)
            assert mb > 0.3, f"Blank render detected on {out_mp4.name} ({mb:.2f} MB)"
            print(f"OK {out_mp4.name} ({mb:.2f} MB, 1080x1920 @ 30fps)")

        browser.close()


if __name__ == "__main__":
    main()
