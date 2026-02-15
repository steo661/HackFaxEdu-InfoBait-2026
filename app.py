#Flask File

from flask import Flask, request, render_template_string
import os
from io import BytesIO
from PIL import Image
import pytesseract
import cohere
import base64
import platform
import re
import socket

app = Flask(__name__)

# ----------------------------
# Cohere setup
# ----------------------------
COHERE_API_KEY = os.environ.get("COHERE_API_KEY", "F2ahifI4wPh18RvXrbQnEd17WlL8avVAJfl3HQ2d")  # Replace or set env
# Allow model override via env var for faster/cheaper options
COHERE_MODEL = os.environ.get("COHERE_MODEL", "command-r7b-12-2024")
co = cohere.Client(COHERE_API_KEY)

# ----------------------------
# Tesseract setup (cross-platform)
# Attempts to locate a sensible tesseract binary on macOS, Windows, or Linux
# ----------------------------
tesseract_cmd = None
system = platform.system()
if system == "Darwin":
    # common Homebrew and default paths on macOS
    for p in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract"):
        if os.path.exists(p):
            tesseract_cmd = p
            break
elif system == "Windows":
    # common install locations on Windows
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if os.path.exists(p):
            tesseract_cmd = p
            break
else:
    # On Linux, assume `tesseract` is on PATH
    tesseract_cmd = "tesseract"

if tesseract_cmd and os.path.exists(tesseract_cmd):
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
else:
    # leave default (requires tesseract on PATH) and warn
    print("Warning: tesseract binary not found at common locations; ensure tesseract is installed and on PATH")

# Performance tunables
# Maximum image dimension (pixels). Images larger than this will be downscaled before OCR.
MAX_IMAGE_DIM = int(os.environ.get("MAX_IMAGE_DIM", "1200"))
# Tesseract config for faster OCR (OEM 1 = LSTM engine, PSM 3 = Fully automatic page segmentation)
TESSERACT_CONFIG = os.environ.get("TESSERACT_CONFIG", "--oem 1 --psm 3")

# ----------------------------
# Text Cleanup Function
# ----------------------------
def clean_text(raw_text: str) -> str:
    """Use Cohere to spell-check and make OCR text coherent."""
    if not raw_text or not raw_text.strip():
        return raw_text
    
    try:
        cleanup_prompt = (
            "You are a text cleanup assistant. Given OCR-extracted text that may contain spelling errors, "
            "missing spaces, or formatting issues, correct all spelling mistakes and make the text coherent and readable. "
            "Preserve the original meaning and structure. Only fix errors - do not add, remove, or rephrase content unnecessarily. "
            "Output ONLY the corrected text without any preamble or explanation.\\n\\n"
            f"Text to clean:\\n{raw_text}"
        )
        
        response = co.chat(
            model=COHERE_MODEL,
            message=cleanup_prompt,
            max_tokens=500
        )
        
        cleaned = response.text.strip()
        return cleaned if cleaned else raw_text
        
    except Exception as e:
        print(f"Text cleanup error: {e}")
        return raw_text  # fallback to original text on error

# ----------------------------
# HTML page
# ----------------------------
HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Upload — InfoBait</title>
    <style>
        :root{--bg:#0b0f12;--card:#0f1720;--muted:#9aa4ad;--accent:#7c5cff;--glass:rgba(255,255,255,0.03)}
        :root.light{--bg:#f5f7fa;--card:#ffffff;--muted:#5a6c7d;--accent:#7c5cff;--glass:rgba(0,0,0,0.03)}
        html,body{height:100%;margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial;font-size:16px}
        /* animated gradient background */
        body::before{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:
                radial-gradient(ellipse 80% 50% at 20% 80%, rgba(124,92,255,0.15), transparent),
                radial-gradient(ellipse 60% 40% at 80% 20%, rgba(59,130,246,0.12), transparent),
                radial-gradient(ellipse 50% 60% at 50% 50%, rgba(139,92,246,0.08), transparent),
                linear-gradient(140deg,#04060a 0%,#070d1e 20%,#0b0f1a 40%,#0a0e1d 60%,#070c18 80%,#04060a 100%);
            background-size:200% 200%;
            animation:bgShift 20s ease infinite;
        }
        body::after{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:
                radial-gradient(circle 320px at 15% 85%, rgba(124,92,255,0.1), transparent 70%),
                radial-gradient(circle 280px at 85% 15%, rgba(59,100,246,0.08), transparent 70%);
            animation:orbFloat 12s ease-in-out infinite alternate;
            pointer-events:none;
        }
        :root.light body::before{
            background:
                radial-gradient(ellipse 80% 50% at 20% 80%, rgba(124,92,255,0.06), transparent),
                radial-gradient(ellipse 60% 40% at 80% 20%, rgba(59,130,246,0.05), transparent),
                linear-gradient(140deg,#eef2f7 0%,#f0f4f8 25%,#f5f7fa 50%,#f0f4f8 75%,#eef2f7 100%);
            background-size:200% 200%;
        }
        :root.light body::after{
            background:
                radial-gradient(circle 320px at 15% 85%, rgba(124,92,255,0.04), transparent 70%),
                radial-gradient(circle 280px at 85% 15%, rgba(59,100,246,0.03), transparent 70%);
        }
        @keyframes bgShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
        @keyframes orbFloat{0%{transform:translate(0,0) scale(1)}100%{transform:translate(30px,-20px) scale(1.08)}}
        .wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:36px}

        /* Animations */
        @keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(124,92,255,0.35); } 70% { box-shadow: 0 0 0 10px rgba(124,92,255,0); } 100% { box-shadow: 0 0 0 0 rgba(124,92,255,0); } }

        .card{width:100%;max-width:820px;background:linear-gradient(180deg,var(--card),#0d1319);border-radius:14px;padding:32px;box-shadow:0 8px 36px rgba(2,6,23,0.6);color:#e6eef6;animation:fadeUp .42s ease-out both}
        :root.light .card{background:linear-gradient(180deg,var(--card),#fafbfc);box-shadow:0 8px 36px rgba(0,0,0,0.08);color:#1a2332}
        h1{margin:0 0 12px;font-weight:600;font-size:22px;font-family:'Times New Roman',Times,serif}
        p.lead{margin:0 0 18px;color:var(--muted);font-size:14px;font-family:'Times New Roman',Times,serif}
        .typewriter-cursor{display:inline-block;width:2px;height:1em;background:#b8a8ff;margin-left:2px;vertical-align:text-bottom;animation:blink .6s step-end infinite}
        :root.light .typewriter-cursor{background:#7c5cff}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
        form{display:flex;gap:12px;align-items:center}
        .file-input{flex:1;display:flex;align-items:center;gap:12px;padding:12px 14px;background:var(--glass);border-radius:12px;border:1px solid rgba(255,255,255,0.04);transition:box-shadow .18s ease,transform .12s ease}
        :root.light .file-input{border:1px solid rgba(0,0,0,0.08)}
        .file-input input[type=file]{background:transparent;color:inherit;font-size:14px}
        .file-input input[type=file]::file-selector-button{
            margin-right:12px;
            padding:8px 14px;
            border-radius:10px;
            border:1px solid rgba(124,92,255,0.45);
            background:linear-gradient(135deg,#8b6cff 0%,#6a4cdb 100%);
            color:#fff;
            font-weight:600;
            cursor:pointer;
            transition:transform .15s ease,box-shadow .2s ease,filter .2s ease;
            box-shadow:0 4px 15px rgba(124,92,255,0.25),inset 0 1px 0 rgba(255,255,255,0.1);
        }
        .file-input input[type=file]::file-selector-button:hover{
            transform:translateY(-1px);
            box-shadow:0 8px 25px rgba(124,92,255,0.35),0 0 20px rgba(124,92,255,0.2),inset 0 1px 0 rgba(255,255,255,0.15);
            filter:brightness(1.03);
        }
        .file-input input[type=file]::file-selector-button:active{
            transform:translateY(0);
            box-shadow:0 4px 15px rgba(124,92,255,0.3);
        }
        .file-input input[type=file]::-webkit-file-upload-button{
            margin-right:12px;
            padding:8px 14px;
            border-radius:10px;
            border:1px solid rgba(124,92,255,0.45);
            background:linear-gradient(135deg,#8b6cff 0%,#6a4cdb 100%);
            color:#fff;
            font-weight:600;
            cursor:pointer;
            transition:transform .15s ease,box-shadow .2s ease,filter .2s ease;
            box-shadow:0 4px 15px rgba(124,92,255,0.25),inset 0 1px 0 rgba(255,255,255,0.1);
        }
        .file-input:hover{box-shadow:0 6px 20px rgba(2,6,23,0.6);transform:translateY(-2px)}
        .btn{position:relative;background:linear-gradient(135deg,#8b6cff 0%,#6a4cdb 100%);border:none;color:white;padding:12px 20px;border-radius:12px;font-weight:600;cursor:pointer;transition:all .2s ease;box-shadow:0 4px 15px rgba(124,92,255,0.25),inset 0 1px 0 rgba(255,255,255,0.1);overflow:hidden}
        .btn::before{content:"";position:absolute;top:0;left:-100%;width:100%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.2),transparent);transition:left .5s ease}
        .btn:hover{transform:translateY(-3px);box-shadow:0 8px 25px rgba(124,92,255,0.35),0 0 20px rgba(124,92,255,0.2),inset 0 1px 0 rgba(255,255,255,0.15)}
        .btn:hover::before{left:100%}
        .btn:active{transform:translateY(-1px);box-shadow:0 4px 15px rgba(124,92,255,0.3)}
        .settings-btn{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,rgba(124,92,255,0.1),rgba(106,76,219,0.15));border:1px solid rgba(124,92,255,0.3);color:#b8a8ff;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:20px;transition:all .2s ease}
        .settings-btn:hover{background:linear-gradient(135deg,rgba(124,92,255,0.18),rgba(106,76,219,0.25));border-color:rgba(124,92,255,0.5);transform:rotate(90deg) scale(1.05);box-shadow:0 4px 12px rgba(124,92,255,0.2)}
        .settings-dropdown{position:fixed;top:62px;right:24px;width:320px;background:linear-gradient(180deg,#0f1720,#0d1319);border-radius:12px;border:1px solid rgba(255,255,255,0.06);box-shadow:0 12px 48px rgba(2,6,23,0.8);display:none;z-index:99;overflow:hidden;animation:fadeUp .3s ease-out}
        .settings-dropdown.show{display:block}
        .settings-section{border-bottom:1px solid rgba(255,255,255,0.03);padding:16px}
        .settings-section:last-child{border-bottom:none}
        .settings-section h3{margin:0 0 10px;font-size:13px;font-weight:600;color:#b8a8ff;text-transform:uppercase;letter-spacing:0.5px}
        .theme-toggle-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:4px 0}
        .theme-toggle-label{color:#dce9f5;font-size:14px}
        .theme-switch{position:relative;display:inline-block;width:64px;height:34px}
        .theme-switch input{opacity:0;width:0;height:0}
        .theme-slider{position:absolute;inset:0;cursor:pointer;background:linear-gradient(135deg,rgba(124,92,255,0.25),rgba(106,76,219,0.3));border:1px solid rgba(124,92,255,0.35);border-radius:999px;transition:all .2s ease;display:flex;align-items:center;justify-content:space-between;padding:0 9px;font-size:13px}
        .theme-slider::before{content:"";position:absolute;height:26px;width:26px;left:3px;top:3px;background:#ffffff;border-radius:50%;box-shadow:0 3px 10px rgba(2,6,23,0.35);transition:transform .2s ease}
        .theme-switch input:checked + .theme-slider::before{transform:translateX(30px)}
        .theme-switch input:focus-visible + .theme-slider{outline:2px solid rgba(124,92,255,0.65);outline-offset:2px}
        .theme-sun,.theme-moon{position:relative;z-index:1;opacity:0.9}
        .theme-switch input:checked + .theme-slider .theme-sun{opacity:1}
        .theme-switch input:checked + .theme-slider .theme-moon{opacity:0.55}
        .theme-switch input:not(:checked) + .theme-slider .theme-moon{opacity:1}
        .theme-switch input:not(:checked) + .theme-slider .theme-sun{opacity:0.55}
        .help-text{color:var(--muted);font-size:13px;line-height:1.6}
        @keyframes ttsShimmer{0%{background-position:200% center}100%{background-position:-200% center}}
        @keyframes ttsPulse{0%,100%{box-shadow:0 0 8px rgba(124,92,255,0.15),0 0 0 rgba(124,92,255,0)}50%{box-shadow:0 0 16px rgba(124,92,255,0.3),0 4px 24px rgba(124,92,255,0.12)}}
        @keyframes ttsActivePulse{0%,100%{box-shadow:0 0 8px rgba(220,80,80,0.2),0 0 0 rgba(220,80,80,0)}50%{box-shadow:0 0 18px rgba(220,80,80,0.35),0 4px 24px rgba(220,80,80,0.15)}}
        .tts-btn{position:relative;padding:9px 20px;border-radius:12px;background:linear-gradient(135deg,#7c5cff,#6a4cdb,#8b6aff);background-size:200% 200%;border:1px solid rgba(124,92,255,0.45);color:#fff;cursor:pointer;font-size:13px;font-weight:600;transition:all .3s cubic-bezier(.4,0,.2,1);display:inline-flex;align-items:center;gap:8px;overflow:hidden;backdrop-filter:blur(8px);letter-spacing:0.4px;text-shadow:0 1px 3px rgba(0,0,0,0.2);animation:ttsShimmer 4s ease-in-out infinite}
        .tts-btn::before{content:"";position:absolute;top:0;left:-100%;width:100%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.18),transparent);transition:left .6s cubic-bezier(.4,0,.2,1)}
        .tts-btn::after{content:"";position:absolute;inset:0;border-radius:inherit;background:linear-gradient(135deg,rgba(255,255,255,0.12) 0%,transparent 50%);pointer-events:none}
        .tts-btn:hover{background:linear-gradient(135deg,#8b6aff,#7c5cff,#9b7aff);border-color:rgba(139,106,255,0.7);transform:translateY(-3px) scale(1.03);box-shadow:0 8px 28px rgba(124,92,255,0.35),0 0 20px rgba(124,92,255,0.15);color:#fff}
        .tts-btn:hover::before{left:100%}
        .tts-btn:active{transform:translateY(-1px) scale(0.98);box-shadow:0 2px 10px rgba(124,92,255,0.25);transition:all .1s ease}
        :root.light .tts-btn{background:linear-gradient(135deg,#7c5cff,#6a4cdb,#8b6aff);background-size:200% 200%;border-color:rgba(124,92,255,0.35);color:#fff;text-shadow:0 1px 2px rgba(0,0,0,0.15)}
        :root.light .tts-btn:hover{background:linear-gradient(135deg,#8b6aff,#7c5cff,#9b7aff);border-color:rgba(139,106,255,0.6);box-shadow:0 8px 28px rgba(124,92,255,0.25),0 0 16px rgba(124,92,255,0.1);color:#fff}
        .tts-btn.tts-active{background:linear-gradient(135deg,#dc4444,#c83030,#e85555);background-size:200% 200%;border-color:rgba(220,68,68,0.5);color:#fff;animation:ttsShimmer 3s ease-in-out infinite,ttsActivePulse 1.5s ease-in-out infinite}
        .tts-btn.tts-active:hover{background:linear-gradient(135deg,#e85555,#dc4444,#f06666);box-shadow:0 8px 28px rgba(220,68,68,0.35),0 0 20px rgba(220,68,68,0.15);color:#fff}
        :root.light .tts-btn.tts-active{background:linear-gradient(135deg,#dc4444,#c83030,#e85555);border-color:rgba(220,68,68,0.4);color:#fff}
        :root.light .tts-btn.tts-active:hover{box-shadow:0 8px 28px rgba(220,68,68,0.25)}
        .meta{margin-top:18px;display:flex;gap:16px;align-items:center}
        .preview{width:160px;height:120px;border-radius:10px;overflow:hidden;background:#091216;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.03);transition:transform .18s ease,box-shadow .18s ease}
        :root.light .preview{background:#f0f4f8;border:1px solid rgba(0,0,0,0.06)}
        .preview img{max-width:100%;max-height:100%;display:block;transition:transform .25s ease,filter .25s ease}
        .preview:hover{transform:translateY(-6px);box-shadow:0 18px 46px rgba(2,6,23,0.5)}
        .preview:hover img{transform:scale(1.04);filter:brightness(1.03)}
        .note{color:var(--muted);font-size:13px}
        footer{margin-top:18px;color:var(--muted);font-size:12px;text-align:right}
        .top-banner{position:fixed;top:0;left:0;right:0;height:56px;background:#000;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid rgba(255,255,255,0.06);box-shadow:0 2px 16px rgba(0,0,0,0.4)}
        :root.light .top-banner{background:#111;border-bottom:1px solid rgba(255,255,255,0.08)}
        .logo{text-decoration:none;transition:all .25s ease}
        .logo:hover{transform:translateY(-2px);filter:drop-shadow(0 4px 18px rgba(124,92,255,0.35))}
        .logo-text{font-size:26px;font-weight:800;letter-spacing:-0.5px;background:linear-gradient(135deg,#b8a8ff 0%,#7c5cff 50%,#6a4cdb 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
        :root.light .logo-text{background:linear-gradient(135deg,#7c5cff 0%,#6a4cdb 50%,#5a3bcc 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
        body{padding-top:56px}
        @media (max-width:520px){.card{padding:18px}.meta{flex-direction:column;align-items:flex-start}.preview{width:100%;height:auto}}
        .faq-link{display:inline-flex;align-items:center;gap:6px;color:#b8a8ff;font-size:13px;cursor:pointer;padding:8px 14px;border-radius:10px;border:1px solid rgba(124,92,255,0.25);background:linear-gradient(135deg,rgba(124,92,255,0.06),rgba(106,76,219,0.1));transition:all .2s ease;font-weight:500;width:100%;justify-content:center}
        .faq-link:hover{background:linear-gradient(135deg,rgba(124,92,255,0.12),rgba(106,76,219,0.18));border-color:rgba(124,92,255,0.4);color:#d0c4ff;transform:translateY(-1px);box-shadow:0 4px 12px rgba(124,92,255,0.15)}
        .faq-overlay{display:none;position:fixed;inset:0;background:rgba(3,6,10,0.7);backdrop-filter:blur(6px);z-index:200;align-items:center;justify-content:center;padding:24px;animation:fadeUp .25s ease-out}
        .faq-overlay.show{display:flex}
        .faq-modal{width:100%;max-width:600px;max-height:80vh;overflow-y:auto;background:linear-gradient(180deg,#0f1720,#0d1319);border-radius:14px;border:1px solid rgba(255,255,255,0.06);box-shadow:0 24px 64px rgba(2,6,23,0.8);padding:28px;animation:fadeUp .3s ease-out}
        :root.light .faq-modal{background:linear-gradient(180deg,#ffffff,#fafbfc);border:1px solid rgba(0,0,0,0.08);box-shadow:0 24px 64px rgba(0,0,0,0.12)}
        .faq-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
        .faq-header h2{margin:0;font-size:20px;font-weight:600;color:#e6eef6}
        :root.light .faq-header h2{color:#1a2332}
        .faq-close{width:36px;height:36px;border-radius:10px;border:1px solid rgba(255,255,255,0.06);background:rgba(255,255,255,0.03);color:#9aa4ad;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;transition:all .2s ease}
        .faq-close:hover{background:rgba(220,60,60,0.12);border-color:rgba(220,60,60,0.3);color:#ff9a9a;transform:scale(1.05)}
        :root.light .faq-close{border-color:rgba(0,0,0,0.08);background:rgba(0,0,0,0.03);color:#5a6c7d}
        :root.light .faq-close:hover{background:rgba(220,60,60,0.08);color:#dc4444}
        .faq-item{border-radius:10px;border:1px solid rgba(255,255,255,0.04);background:rgba(255,255,255,0.02);margin-bottom:10px;overflow:hidden;transition:all .2s ease}
        :root.light .faq-item{border-color:rgba(0,0,0,0.06);background:rgba(0,0,0,0.02)}
        .faq-item:hover{border-color:rgba(124,92,255,0.2);background:rgba(124,92,255,0.03)}
        .faq-q{padding:14px 16px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:12px;font-weight:600;font-size:14px;color:#dce9f5;transition:color .2s ease;user-select:none}
        :root.light .faq-q{color:#2a3a4a}
        .faq-q:hover{color:#b8a8ff}
        :root.light .faq-q:hover{color:#7c5cff}
        .faq-arrow{font-size:12px;color:#9aa4ad;transition:transform .25s cubic-bezier(.4,0,.2,1);flex-shrink:0}
        .faq-item.open .faq-arrow{transform:rotate(180deg);color:#b8a8ff}
        .faq-a{max-height:0;overflow:hidden;transition:max-height .3s cubic-bezier(.4,0,.2,1),padding .3s ease}
        .faq-item.open .faq-a{max-height:200px;padding:0 16px 14px}
        .faq-a p{margin:0;font-size:13px;color:#9aa4ad;line-height:1.7}
        :root.light .faq-a p{color:#5a6c7d}
    </style>
</head>
<body>
    <div class="top-banner">
        <a class="logo" href="/"><span class="logo-text">InfoBait</span></a>
        <button class="settings-btn" onclick="toggleSettings()">⚙️</button>
    </div>
    <div class="settings-dropdown" id="settingsDropdown">
        <div class="settings-section">
            <h3>Theme</h3>
            <div class="theme-toggle-row">
                <span class="theme-toggle-label">Light / Dark</span>
                <label class="theme-switch" aria-label="Toggle light and dark mode">
                    <input type="checkbox" id="themeToggle" onchange="toggleTheme(this.checked)">
                    <span class="theme-slider"><span class="theme-moon">🌙</span><span class="theme-sun">☀️</span></span>
                </label>
            </div>
        </div>
        <div class="settings-section">
            <h3>Help</h3>
            <div class="faq-link" onclick="openFAQ()">Frequently Asked Questions</div>
        </div>
    </div>
    <div class="faq-overlay" id="faqOverlay" onclick="if(event.target===this)closeFAQ()">
        <div class="faq-modal">
            <div class="faq-header">
                <h2>FAQ</h2>
                <button class="faq-close" onclick="closeFAQ()">✕</button>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>What file types can I upload?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>InfoBait supports all common image formats including PNG, JPG, JPEG, GIF, BMP, and WebP. For best OCR results, use high-resolution screenshots (800×600 or higher) with clear, readable text.</p></div>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>How does the truthfulness rating work?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>Our AI analyzes the extracted text and rates its factual accuracy on a scale of 1–10. A score of 1 means highly inaccurate, while 10 means highly truthful. The color bar shifts from red → yellow → green to reflect the rating visually.</p></div>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>Is my uploaded data private and secure?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>Yes. Images are processed in-memory and never saved to disk. No uploaded files are stored on the server after analysis is complete. Text is sent to the Cohere AI API for analysis but is not retained by InfoBait.</p></div>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>Why is the extracted text inaccurate or garbled?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>OCR accuracy depends on image quality. Low-resolution images, unusual fonts, handwritten text, or heavy background noise can reduce accuracy. Try uploading a clearer, higher-resolution screenshot for better results.</p></div>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>What does the Listen button do?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>The Listen button uses your browser's built-in text-to-speech to read the extracted text or AI analysis aloud. Click it once to start, and click again to stop. It works on most modern browsers without any extra software.</p></div>
            </div>
        </div>
    </div>
    <div class="wrap">
        <div class="card">
            <h1 id="tw-title"></h1>
            <p class="lead" id="tw-lead"></p>

            <form id="uploadForm" action="/upload" method="post" enctype="multipart/form-data" onsubmit="handleSubmit(event)">
                <label class="file-input">
                    <input type="file" name="image" accept="image/*" onchange="handleFile(event)" required>
                    <span class="note" id="fname">Choose an image…</span>
                </label>
                <button class="btn" type="submit">Analyze</button>
            </form>

            <div class="meta">
                <div class="preview" id="preview">Preview</div>
                <div style="flex:1">
                    <div class="note">Recommended: 800×600 or higher for best OCR/analysis results.</div>
                </div>
            </div>

            <footer>Built for quick, minimal analysis</footer>
        </div>
    </div>

    <script>
        function handleFile(e){
            const file = e.target.files[0];
            const fname = document.getElementById('fname');
            const preview = document.getElementById('preview');
            if(!file){ fname.textContent = 'Choose an image…'; preview.innerHTML = 'Preview'; return }
            fname.textContent = file.name;
            const reader = new FileReader();
            reader.onload = function(ev){
                preview.innerHTML = '<img src="'+ev.target.result+'" alt="preview">';
            }
            reader.readAsDataURL(file);
        }
                function showLoader(){
                    const l = document.getElementById('loader');
                    const btn = document.querySelector('.btn');
                    if(btn){ btn.disabled = true; btn.dataset.origText = btn.textContent; btn.textContent = 'Analyzing…'; }
                    if(l){ l.style.display = 'flex'; }
                }

                async function handleSubmit(e){
                    e.preventDefault();
                    const form = document.getElementById('uploadForm');
                    showLoader();
                    // Small delay so loader is visible, then do a real form submit
                    // (normal navigation preserves browser APIs like speechSynthesis)
                    await new Promise(r => setTimeout(r, 800));
                    form.removeAttribute('onsubmit');
                    form.submit();
                    return false;
                }

        // Settings functionality
        let currentTheme = localStorage.getItem('theme') || 'dark';

        function toggleSettings(){
            const dropdown = document.getElementById('settingsDropdown');
            dropdown.classList.toggle('show');
        }

        function setTheme(theme){
            currentTheme = theme;
            localStorage.setItem('theme', theme);
            document.documentElement.className = theme === 'light' ? 'light' : '';
            const toggle = document.getElementById('themeToggle');
            if(toggle){
                toggle.checked = theme === 'light';
            }
        }

        function toggleTheme(isLight){
            setTheme(isLight ? 'light' : 'dark');
        }

        // Apply saved theme on load
        if(currentTheme === 'light'){
            document.documentElement.className = 'light';
        }
        
        window.addEventListener('DOMContentLoaded', function(){
            const toggle = document.getElementById('themeToggle');
            if(toggle){
                toggle.checked = currentTheme === 'light';
            }
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', function(e){
            const dropdown = document.getElementById('settingsDropdown');
            const btn = document.querySelector('.settings-btn');
            if(dropdown && !dropdown.contains(e.target) && !btn.contains(e.target)){
                dropdown.classList.remove('show');
            }
        });

        function openFAQ(){
            document.getElementById('faqOverlay').classList.add('show');
            document.getElementById('settingsDropdown').classList.remove('show');
        }
        function closeFAQ(){
            document.getElementById('faqOverlay').classList.remove('show');
        }
        function toggleFaq(el){
            const item = el.parentElement;
            item.classList.toggle('open');
        }
        document.addEventListener('keydown', function(e){
            if(e.key === 'Escape') closeFAQ();
        });

        // Typewriter effect
        function typeWriter(el, text, speed, cb){
            let i = 0;
            const cursor = document.createElement('span');
            cursor.className = 'typewriter-cursor';
            el.appendChild(cursor);
            function tick(){
                if(i < text.length){
                    el.insertBefore(document.createTextNode(text.charAt(i)), cursor);
                    i++;
                    setTimeout(tick, speed);
                } else if(cb){
                    cursor.remove();
                    cb();
                }
            }
            tick();
        }
        window.addEventListener('DOMContentLoaded', function(){
            const title = document.getElementById('tw-title');
            const lead = document.getElementById('tw-lead');
            if(title && lead){
                typeWriter(title, 'Screenshot Analyzer', 100, function(){
                    typeWriter(lead, 'Upload a screenshot and get a concise analysis. We respect your privacy \u2014 files are processed locally or on your configured AI endpoint.', 35, function(){
                        const c = lead.querySelector('.typewriter-cursor');
                        if(c) setTimeout(function(){ c.style.animation='none'; c.style.opacity='0'; c.style.transition='opacity .4s'; }, 1500);
                    });
                });
            }
        });
    </script>
        <div id="loader" style="display:none;position:fixed;inset:0;background:rgba(3,6,10,0.6);backdrop-filter:blur(4px);align-items:center;justify-content:center;z-index:60">
            <div style="width:80%;max-width:560px;padding:18px;background:linear-gradient(180deg,#0b0f12,#0d1319);border-radius:12px;border:1px solid rgba(255,255,255,0.04);display:flex;flex-direction:column;gap:12px;align-items:center">
                <div style="width:100%;height:10px;background:rgba(255,255,255,0.03);border-radius:8px;overflow:hidden;position:relative">
                    <div style="position:absolute;left:-40%;top:0;bottom:0;width:40%;background:linear-gradient(90deg,transparent,rgba(124,92,255,0.9),transparent);animation:loaderMove 1.2s linear infinite"></div>
                </div>
                <div style="color:#cfe6ff;font-size:14px">Analyzing image — this may take a moment</div>
            </div>
        </div>
        <style>
            @keyframes loaderMove { from { left:-40% } to { left:140% } }
        </style>
</body>
</html>
"""

RESULT_PAGE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Results — InfoBait</title>
    <style>
        :root{--bg:#0b0f12;--card:#0f1720;--muted:#9aa4ad;--accent:#7c5cff;--glass:rgba(255,255,255,0.03)}
        :root.light{--bg:#f5f7fa;--card:#ffffff;--muted:#5a6c7d;--accent:#7c5cff;--glass:rgba(0,0,0,0.03)}
        html,body{height:100%;margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial;font-size:16px}
        /* animated gradient background */
        body::before{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:
                radial-gradient(ellipse 80% 50% at 20% 80%, rgba(124,92,255,0.15), transparent),
                radial-gradient(ellipse 60% 40% at 80% 20%, rgba(59,130,246,0.12), transparent),
                radial-gradient(ellipse 50% 60% at 50% 50%, rgba(139,92,246,0.08), transparent),
                linear-gradient(140deg,#04060a 0%,#070d1e 20%,#0b0f1a 40%,#0a0e1d 60%,#070c18 80%,#04060a 100%);
            background-size:200% 200%;
            animation:bgShift 20s ease infinite;
        }
        body::after{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:
                radial-gradient(circle 320px at 15% 85%, rgba(124,92,255,0.1), transparent 70%),
                radial-gradient(circle 280px at 85% 15%, rgba(59,100,246,0.08), transparent 70%);
            animation:orbFloat 12s ease-in-out infinite alternate;
            pointer-events:none;
        }
        :root.light body::before{
            background:
                radial-gradient(ellipse 80% 50% at 20% 80%, rgba(124,92,255,0.06), transparent),
                radial-gradient(ellipse 60% 40% at 80% 20%, rgba(59,130,246,0.05), transparent),
                linear-gradient(140deg,#eef2f7 0%,#f0f4f8 25%,#f5f7fa 50%,#f0f4f8 75%,#eef2f7 100%);
            background-size:200% 200%;
        }
        :root.light body::after{
            background:
                radial-gradient(circle 320px at 15% 85%, rgba(124,92,255,0.04), transparent 70%),
                radial-gradient(circle 280px at 85% 15%, rgba(59,100,246,0.03), transparent 70%);
        }
        @keyframes bgShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
        @keyframes orbFloat{0%{transform:translate(0,0) scale(1)}100%{transform:translate(30px,-20px) scale(1.08)}}
        .wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:36px}

        /* Animations */
        @keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .card{width:100%;max-width:1100px;background:linear-gradient(180deg,var(--card),#0d1319);border-radius:14px;padding:28px;box-shadow:0 8px 36px rgba(2,6,23,0.6);color:#e6eef6;animation:fadeUp .42s ease-out both}
        :root.light .card{background:linear-gradient(180deg,var(--card),#fafbfc);box-shadow:0 8px 36px rgba(0,0,0,0.08);color:#1a2332}
        .row{display:flex;gap:20px;align-items:flex-start}
        .left{width:320px}
        .preview{width:100%;border-radius:10px;overflow:hidden;background:#091216;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.03);padding:12px;transition:transform .18s ease,box-shadow .18s ease}
        :root.light .preview{background:#f0f4f8;border:1px solid rgba(0,0,0,0.06)}
        .preview img{max-width:100%;height:auto;display:block;transition:transform .25s ease,filter .25s ease}
        .preview:hover{transform:translateY(-6px);box-shadow:0 18px 46px rgba(2,6,23,0.5)}
        .preview:hover img{transform:scale(1.03);filter:brightness(1.02)}
        .right{flex:1}
        h1{margin:0 0 8px;font-weight:600;font-size:20px}
        .note{color:var(--muted);font-size:14px;margin-bottom:10px}
        .panel{background:rgba(255,255,255,0.02);padding:14px;border-radius:10px;border:1px solid rgba(255,255,255,0.03);color:#dce9f5;font-size:14px}
        :root.light .panel{background:rgba(0,0,0,0.02);border:1px solid rgba(0,0,0,0.06);color:#2a3a4a}
        pre{white-space:pre-wrap;word-break:break-word;margin:0;font-family:inherit}
        a.btn{position:relative;display:inline-flex;align-items:center;justify-content:center;text-align:center;margin-top:14px;padding:10px 18px;border-radius:10px;background:linear-gradient(135deg,rgba(124,92,255,0.08),rgba(106,76,219,0.12));border:1px solid rgba(124,92,255,0.25);color:#b8a8ff;text-decoration:none;font-weight:500;transition:all .2s ease;box-shadow:0 2px 8px rgba(0,0,0,0.15)}
        a.btn:hover{transform:translateY(-2px);background:linear-gradient(135deg,rgba(124,92,255,0.15),rgba(106,76,219,0.2));border-color:rgba(124,92,255,0.4);box-shadow:0 4px 16px rgba(124,92,255,0.2);color:#d0c4ff}
        a.btn:active{transform:translateY(0px)}
        .settings-btn{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,rgba(124,92,255,0.1),rgba(106,76,219,0.15));border:1px solid rgba(124,92,255,0.3);color:#b8a8ff;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:20px;transition:all .2s ease}
        .settings-btn:hover{background:linear-gradient(135deg,rgba(124,92,255,0.18),rgba(106,76,219,0.25));border-color:rgba(124,92,255,0.5);transform:rotate(90deg) scale(1.05);box-shadow:0 4px 12px rgba(124,92,255,0.2)}
        .settings-dropdown{position:fixed;top:62px;right:24px;width:320px;background:linear-gradient(180deg,#0f1720,#0d1319);border-radius:12px;border:1px solid rgba(255,255,255,0.06);box-shadow:0 12px 48px rgba(2,6,23,0.8);display:none;z-index:99;overflow:hidden;animation:fadeUp .3s ease-out}
        .settings-dropdown.show{display:block}
        .settings-section{border-bottom:1px solid rgba(255,255,255,0.03);padding:16px}
        .settings-section:last-child{border-bottom:none}
        .settings-section h3{margin:0 0 10px;font-size:13px;font-weight:600;color:#b8a8ff;text-transform:uppercase;letter-spacing:0.5px}
        .theme-toggle-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:4px 0}
        .theme-toggle-label{color:#dce9f5;font-size:14px}
        .theme-switch{position:relative;display:inline-block;width:64px;height:34px}
        .theme-switch input{opacity:0;width:0;height:0}
        .theme-slider{position:absolute;inset:0;cursor:pointer;background:linear-gradient(135deg,rgba(124,92,255,0.25),rgba(106,76,219,0.3));border:1px solid rgba(124,92,255,0.35);border-radius:999px;transition:all .2s ease;display:flex;align-items:center;justify-content:space-between;padding:0 9px;font-size:13px}
        .theme-slider::before{content:"";position:absolute;height:26px;width:26px;left:3px;top:3px;background:#ffffff;border-radius:50%;box-shadow:0 3px 10px rgba(2,6,23,0.35);transition:transform .2s ease}
        .theme-switch input:checked + .theme-slider::before{transform:translateX(30px)}
        .theme-switch input:focus-visible + .theme-slider{outline:2px solid rgba(124,92,255,0.65);outline-offset:2px}
        .theme-sun,.theme-moon{position:relative;z-index:1;opacity:0.9}
        .theme-switch input:checked + .theme-slider .theme-sun{opacity:1}
        .theme-switch input:checked + .theme-slider .theme-moon{opacity:0.55}
        .theme-switch input:not(:checked) + .theme-slider .theme-moon{opacity:1}
        .theme-switch input:not(:checked) + .theme-slider .theme-sun{opacity:0.55}
        .help-text{color:var(--muted);font-size:13px;line-height:1.6}
        @keyframes ttsShimmer{0%{background-position:200% center}100%{background-position:-200% center}}
        @keyframes ttsPulse{0%,100%{box-shadow:0 0 8px rgba(124,92,255,0.15),0 0 0 rgba(124,92,255,0)}50%{box-shadow:0 0 16px rgba(124,92,255,0.3),0 4px 24px rgba(124,92,255,0.12)}}
        @keyframes ttsActivePulse{0%,100%{box-shadow:0 0 8px rgba(220,80,80,0.2),0 0 0 rgba(220,80,80,0)}50%{box-shadow:0 0 18px rgba(220,80,80,0.35),0 4px 24px rgba(220,80,80,0.15)}}
        .tts-btn{position:relative;padding:9px 20px;border-radius:12px;background:linear-gradient(135deg,#7c5cff,#6a4cdb,#8b6aff);background-size:200% 200%;border:1px solid rgba(124,92,255,0.45);color:#fff;cursor:pointer;font-size:13px;font-weight:600;transition:all .3s cubic-bezier(.4,0,.2,1);display:inline-flex;align-items:center;gap:8px;overflow:hidden;backdrop-filter:blur(8px);letter-spacing:0.4px;text-shadow:0 1px 3px rgba(0,0,0,0.2);animation:ttsShimmer 4s ease-in-out infinite}
        .tts-btn::before{content:"";position:absolute;top:0;left:-100%;width:100%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.18),transparent);transition:left .6s cubic-bezier(.4,0,.2,1)}
        .tts-btn::after{content:"";position:absolute;inset:0;border-radius:inherit;background:linear-gradient(135deg,rgba(255,255,255,0.12) 0%,transparent 50%);pointer-events:none}
        .tts-btn:hover{background:linear-gradient(135deg,#8b6aff,#7c5cff,#9b7aff);border-color:rgba(139,106,255,0.7);transform:translateY(-3px) scale(1.03);box-shadow:0 8px 28px rgba(124,92,255,0.35),0 0 20px rgba(124,92,255,0.15);color:#fff}
        .tts-btn:hover::before{left:100%}
        .tts-btn:active{transform:translateY(-1px) scale(0.98);box-shadow:0 2px 10px rgba(124,92,255,0.25);transition:all .1s ease}
        :root.light .tts-btn{background:linear-gradient(135deg,#7c5cff,#6a4cdb,#8b6aff);background-size:200% 200%;border-color:rgba(124,92,255,0.35);color:#fff;text-shadow:0 1px 2px rgba(0,0,0,0.15)}
        :root.light .tts-btn:hover{background:linear-gradient(135deg,#8b6aff,#7c5cff,#9b7aff);border-color:rgba(139,106,255,0.6);box-shadow:0 8px 28px rgba(124,92,255,0.25),0 0 16px rgba(124,92,255,0.1);color:#fff}
        .tts-btn.tts-active{background:linear-gradient(135deg,#dc4444,#c83030,#e85555);background-size:200% 200%;border-color:rgba(220,68,68,0.5);color:#fff;animation:ttsShimmer 3s ease-in-out infinite,ttsActivePulse 1.5s ease-in-out infinite}
        .tts-btn.tts-active:hover{background:linear-gradient(135deg,#e85555,#dc4444,#f06666);box-shadow:0 8px 28px rgba(220,68,68,0.35),0 0 20px rgba(220,68,68,0.15);color:#fff}
        :root.light .tts-btn.tts-active{background:linear-gradient(135deg,#dc4444,#c83030,#e85555);border-color:rgba(220,68,68,0.4);color:#fff}
        :root.light .tts-btn.tts-active:hover{box-shadow:0 8px 28px rgba(220,68,68,0.25)}
        @media (max-width:820px){.row{flex-direction:column}.left{width:100%}}
        .top-banner{position:fixed;top:0;left:0;right:0;height:56px;background:#000;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid rgba(255,255,255,0.06);box-shadow:0 2px 16px rgba(0,0,0,0.4)}
        :root.light .top-banner{background:#111;border-bottom:1px solid rgba(255,255,255,0.08)}
        .logo{text-decoration:none;transition:all .25s ease}
        .logo:hover{transform:translateY(-2px);filter:drop-shadow(0 4px 18px rgba(124,92,255,0.35))}
        .logo-text{font-size:26px;font-weight:800;letter-spacing:-0.5px;background:linear-gradient(135deg,#b8a8ff 0%,#7c5cff 50%,#6a4cdb 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
        :root.light .logo-text{background:linear-gradient(135deg,#7c5cff 0%,#6a4cdb 50%,#5a3bcc 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
        body{padding-top:56px}
        .faq-link{display:inline-flex;align-items:center;gap:6px;color:#b8a8ff;font-size:13px;cursor:pointer;padding:8px 14px;border-radius:10px;border:1px solid rgba(124,92,255,0.25);background:linear-gradient(135deg,rgba(124,92,255,0.06),rgba(106,76,219,0.1));transition:all .2s ease;font-weight:500;width:100%;justify-content:center}
        .faq-link:hover{background:linear-gradient(135deg,rgba(124,92,255,0.12),rgba(106,76,219,0.18));border-color:rgba(124,92,255,0.4);color:#d0c4ff;transform:translateY(-1px);box-shadow:0 4px 12px rgba(124,92,255,0.15)}
        .faq-overlay{display:none;position:fixed;inset:0;background:rgba(3,6,10,0.7);backdrop-filter:blur(6px);z-index:200;align-items:center;justify-content:center;padding:24px;animation:fadeUp .25s ease-out}
        .faq-overlay.show{display:flex}
        .faq-modal{width:100%;max-width:600px;max-height:80vh;overflow-y:auto;background:linear-gradient(180deg,#0f1720,#0d1319);border-radius:14px;border:1px solid rgba(255,255,255,0.06);box-shadow:0 24px 64px rgba(2,6,23,0.8);padding:28px;animation:fadeUp .3s ease-out}
        :root.light .faq-modal{background:linear-gradient(180deg,#ffffff,#fafbfc);border:1px solid rgba(0,0,0,0.08);box-shadow:0 24px 64px rgba(0,0,0,0.12)}
        .faq-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
        .faq-header h2{margin:0;font-size:20px;font-weight:600;color:#e6eef6}
        :root.light .faq-header h2{color:#1a2332}
        .faq-close{width:36px;height:36px;border-radius:10px;border:1px solid rgba(255,255,255,0.06);background:rgba(255,255,255,0.03);color:#9aa4ad;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;transition:all .2s ease}
        .faq-close:hover{background:rgba(220,60,60,0.12);border-color:rgba(220,60,60,0.3);color:#ff9a9a;transform:scale(1.05)}
        :root.light .faq-close{border-color:rgba(0,0,0,0.08);background:rgba(0,0,0,0.03);color:#5a6c7d}
        :root.light .faq-close:hover{background:rgba(220,60,60,0.08);color:#dc4444}
        .faq-item{border-radius:10px;border:1px solid rgba(255,255,255,0.04);background:rgba(255,255,255,0.02);margin-bottom:10px;overflow:hidden;transition:all .2s ease}
        :root.light .faq-item{border-color:rgba(0,0,0,0.06);background:rgba(0,0,0,0.02)}
        .faq-item:hover{border-color:rgba(124,92,255,0.2);background:rgba(124,92,255,0.03)}
        .faq-q{padding:14px 16px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:12px;font-weight:600;font-size:14px;color:#dce9f5;transition:color .2s ease;user-select:none}
        :root.light .faq-q{color:#2a3a4a}
        .faq-q:hover{color:#b8a8ff}
        :root.light .faq-q:hover{color:#7c5cff}
        .faq-arrow{font-size:12px;color:#9aa4ad;transition:transform .25s cubic-bezier(.4,0,.2,1);flex-shrink:0}
        .faq-item.open .faq-arrow{transform:rotate(180deg);color:#b8a8ff}
        .faq-a{max-height:0;overflow:hidden;transition:max-height .3s cubic-bezier(.4,0,.2,1),padding .3s ease}
        .faq-item.open .faq-a{max-height:200px;padding:0 16px 14px}
        .faq-a p{margin:0;font-size:13px;color:#9aa4ad;line-height:1.7}
        :root.light .faq-a p{color:#5a6c7d}
    </style>
</head>
<body>
    <div class="top-banner">
        <a class="logo" href="/"><span class="logo-text">InfoBait</span></a>
        <button class="settings-btn" onclick="toggleSettings()">⚙️</button>
    </div>
    <div class="settings-dropdown" id="settingsDropdown">
        <div class="settings-section">
            <h3>Theme</h3>
            <div class="theme-toggle-row">
                <span class="theme-toggle-label">Light / Dark</span>
                <label class="theme-switch" aria-label="Toggle light and dark mode">
                    <input type="checkbox" id="themeToggle" onchange="toggleTheme(this.checked)">
                    <span class="theme-slider"><span class="theme-moon">🌙</span><span class="theme-sun">☀️</span></span>
                </label>
            </div>
        </div>
        <div class="settings-section">
            <h3>Help</h3>
            <div class="faq-link" onclick="openFAQ()">Frequently Asked Questions</div>
        </div>
    </div>
    <div class="faq-overlay" id="faqOverlay" onclick="if(event.target===this)closeFAQ()">
        <div class="faq-modal">
            <div class="faq-header">
                <h2>FAQ</h2>
                <button class="faq-close" onclick="closeFAQ()">✕</button>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>What file types can I upload?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>InfoBait supports all common image formats including PNG, JPG, JPEG, GIF, BMP, and WebP. For best OCR results, use high-resolution screenshots (800×600 or higher) with clear, readable text.</p></div>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>How does the truthfulness rating work?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>Our AI analyzes the extracted text and rates its factual accuracy on a scale of 1–10. A score of 1 means highly inaccurate, while 10 means highly truthful. The color bar shifts from red → yellow → green to reflect the rating visually.</p></div>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>Is my uploaded data private and secure?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>Yes. Images are processed in-memory and never saved to disk. No uploaded files are stored on the server after analysis is complete. Text is sent to the Cohere AI API for analysis but is not retained by InfoBait.</p></div>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>Why is the extracted text inaccurate or garbled?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>OCR accuracy depends on image quality. Low-resolution images, unusual fonts, handwritten text, or heavy background noise can reduce accuracy. Try uploading a clearer, higher-resolution screenshot for better results.</p></div>
            </div>
            <div class="faq-item">
                <div class="faq-q" onclick="toggleFaq(this)"><span>What does the Listen button do?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>The Listen button uses your browser's built-in text-to-speech to read the extracted text or AI analysis aloud. Click it once to start, and click again to stop. It works on most modern browsers without any extra software.</p></div>
            </div>
        </div>
    </div>
    <div class="wrap">
        <div class="card">
            <h1>Analysis Result</h1>
            <div class="note">File: {{ filename }}</div>
            <div class="row">
                <div class="left">
                    <div class="preview">
                        <img src="data:{{ mime }};base64,{{ image_b64 }}" alt="uploaded image">
                    </div>
                </div>
                <div class="right">
                    <div class="panel">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                            <strong>Extracted Text</strong>
                            <button onclick="speakExtractedText()" class="tts-btn" id="ttsExtractedBtn">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                                <span>Listen</span>
                            </button>
                        </div>
                        <pre id="extractedTextContent">{{ extracted_text }}</pre>
                    </div>
                    <div style="height:12px"></div>
                    <div class="panel">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                            <strong>AI Analysis</strong>
                            <button onclick="speakAnalysis()" class="tts-btn" id="ttsAnalysisBtn">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                                <span>Listen</span>
                            </button>
                        </div>
                        <pre id="aiAnalysisText">{{ ai_output }}</pre>
                    </div>
                    <div style="height:12px"></div>
                    <div class="panel">
                        <strong>Truthfulness Rating</strong>
                        <div style="margin-top:8px">
                        {% if rating is not none %}
                            <div style="display:flex;align-items:center;gap:12px">
                                <div style="flex:1">
                                    <div style="position:relative;background:rgba(255,255,255,0.03);height:14px;border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,0.03)">
                                        <!-- ticks overlay: 10 equal segments -->
                                        <div style="position:absolute;inset:0;pointer-events:none;z-index:3;background-image:linear-gradient(to right,rgba(255,255,255,0.06) 1px, transparent 1px);background-size:10% 100%;background-repeat:repeat-x;opacity:0.9"></div>
                                        <div style="position:relative;z-index:2;height:100%;width:{{ rating_percent }}%;background:{{ bar_color }};transition:width:420ms ease"></div>
                                    </div>
                                    <div style="display:flex;justify-content:space-between;margin-top:6px;color:var(--muted);font-size:12px">
                                        <span>1</span>
                                        <span>5</span>
                                        <span>10</span>
                                    </div>
                                </div>
                                <div style="min-width:84px;text-align:center">
                                    <div style="font-weight:700;font-size:18px">{{ rating }}</div>
                                    <div style="color:var(--muted);font-size:12px">/ 10</div>
                                </div>
                            </div>
                        {% else %}
                            <div style="display:flex;align-items:center;gap:12px">
                                <div style="flex:1;display:flex;align-items:center;gap:12px">
                                    <div style="min-width:84px;height:38px;border-radius:8px;background:rgba(255,255,255,0.03);display:flex;align-items:center;justify-content:center;font-weight:700;color:var(--muted);font-size:16px">N/A</div>
                                    <div style="color:var(--muted);font-size:14px">Unable to provide an accuracy report. Please try again.</div>
                                </div>
                            </div>
                        {% endif %}
                        </div>
                    </div>
                    <a href="/" class="btn">Upload another</a>
                </div>
            </div>
        </div>
    </div>
    <script>
        let currentTheme = localStorage.getItem('theme') || 'dark';

        function toggleSettings(){
            const dropdown = document.getElementById('settingsDropdown');
            dropdown.classList.toggle('show');
        }

        function setTheme(theme){
            currentTheme = theme;
            localStorage.setItem('theme', theme);
            document.documentElement.className = theme === 'light' ? 'light' : '';
            const toggle = document.getElementById('themeToggle');
            if(toggle){
                toggle.checked = theme === 'light';
            }
        }

        function toggleTheme(isLight){
            setTheme(isLight ? 'light' : 'dark');
        }

        // Apply saved theme on load
        if(currentTheme === 'light'){
            document.documentElement.className = 'light';
        }
        
        window.addEventListener('DOMContentLoaded', function(){
            const toggle = document.getElementById('themeToggle');
            if(toggle){
                toggle.checked = currentTheme === 'light';
            }
        });

        document.addEventListener('click', function(e){
            const dropdown = document.getElementById('settingsDropdown');
            const btn = document.querySelector('.settings-btn');
            if(dropdown && !dropdown.contains(e.target) && !btn.contains(e.target)){
                dropdown.classList.remove('show');
            }
        });

        let isSpeaking = false;

        function speakText(rawText, btnEl){
            // If already speaking, stop and reset
            if(isSpeaking){
                window.speechSynthesis.cancel();
                isSpeaking = false;
                if(btnEl){
                    btnEl.querySelector('span').textContent = 'Listen';
                    btnEl.classList.remove('tts-active');
                }
                return;
            }

            const text = (rawText || '').trim();
            if(!text){
                alert('No text to read');
                return;
            }
            if(!window.speechSynthesis || !window.SpeechSynthesisUtterance){
                alert('Text-to-speech is not supported in this browser.');
                return;
            }
            window.speechSynthesis.cancel();

            function doSpeak(){
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'en-US';
                utterance.rate = 1;
                utterance.pitch = 1;
                utterance.volume = 1;
                const voices = window.speechSynthesis.getVoices();
                const enVoice = voices.find(v => v.lang && v.lang.startsWith('en'));
                if(enVoice) utterance.voice = enVoice;

                utterance.onstart = function(){
                    isSpeaking = true;
                    if(btnEl){
                        btnEl.querySelector('span').textContent = 'Stop';
                        btnEl.classList.add('tts-active');
                    }
                };
                utterance.onend = function(){
                    isSpeaking = false;
                    if(btnEl){
                        btnEl.querySelector('span').textContent = 'Listen';
                        btnEl.classList.remove('tts-active');
                    }
                };
                utterance.onerror = function(){
                    isSpeaking = false;
                    if(btnEl){
                        btnEl.querySelector('span').textContent = 'Listen';
                        btnEl.classList.remove('tts-active');
                    }
                };

                window.speechSynthesis.speak(utterance);
            }

            const voices = window.speechSynthesis.getVoices();
            if(voices.length > 0){
                doSpeak();
            } else {
                window.speechSynthesis.onvoiceschanged = function(){
                    doSpeak();
                };
            }
        }

        function speakExtractedText(){
            const btn = document.getElementById('ttsExtractedBtn');
            const textEl = document.getElementById('extractedTextContent');
            const text = textEl ? (textEl.textContent || textEl.innerText || '') : '';
            speakText(text, btn);
        }

        function speakAnalysis(){
            const btn = document.getElementById('ttsAnalysisBtn');
            const textEl = document.getElementById('aiAnalysisText');
            const text = textEl ? (textEl.textContent || textEl.innerText || '') : '';
            speakText(text, btn);
        }

        function openFAQ(){
            document.getElementById('faqOverlay').classList.add('show');
            document.getElementById('settingsDropdown').classList.remove('show');
        }
        function closeFAQ(){
            document.getElementById('faqOverlay').classList.remove('show');
        }
        function toggleFaq(el){
            const item = el.parentElement;
            item.classList.toggle('open');
        }
        document.addEventListener('keydown', function(e){
            if(e.key === 'Escape') closeFAQ();
        });
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML_PAGE)

@app.route("/upload", methods=["POST"])
def upload():
    if "image" not in request.files:
        return "No file uploaded", 400

    file = request.files["image"]
    if file.filename == "":
        return "No file selected", 400

    file_bytes = file.read()
    if not file_bytes:
        return "Uploaded file is empty", 400

    # ----------------------------
    # OCR Step (preprocess image for speed)
    # ----------------------------
    def preprocess_image(image_bytes, max_dim=MAX_IMAGE_DIM):
        img = Image.open(BytesIO(image_bytes))
        # Keep original color mode (do NOT convert to grayscale).
        # Convert palette images to RGB for compatibility, but otherwise keep color as-is.
        if img.mode == 'P':
            img = img.convert("RGB")
        # downscale large images to speed up OCR while preserving aspect ratio
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        return img

    img = preprocess_image(file_bytes)
    extracted_text = pytesseract.image_to_string(img, config=TESSERACT_CONFIG)
    
    # Clean up OCR text (spell-check and make coherent)
    extracted_text = clean_text(extracted_text)

    # ----------------------------
    # Cohere Chat API (latest)
    # ----------------------------
    try:
        prompt_text = (
            "You are a fact-check assistant.\n"
            "Instructions:\n"
            "1) On the FIRST line, output exactly one token: either an integer 1-10 (the truthfulness rating) or the token 'N/A' if you cannot provide a rating. Do NOT include any other text on this line.\n"
            "2) Starting from the SECOND line, provide a clear, concise analysis explaining whether the claim is accurate or not. Focus only on factual accuracy.\n"
            "3) Do NOT mention grammatical errors, punctuation, spelling, or style — only assess factual accuracy.\n"
            "4) Do NOT repeat the rating number in your explanation. Keep your analysis brief but informative (2-3 sentences).\n\n"
            f"Text to evaluate:\n{extracted_text}"
        )

        # Use configured model (env override allowed)
        response = co.chat(
            model=COHERE_MODEL,
            message=prompt_text,
            max_tokens=150
        )

        ai_output = response.text.strip()
    except Exception as e:
        ai_output = f"AI Error: {e}"

    # Try to extract a numeric rating (1-10) from the AI output
    def parse_rating(text: str):
        """Parse only a leading rating token at the start of the AI response.
        Accepts an integer 1-10 or 'N/A'. Returns int 1-10 or None for N/A/invalid.
        """
        if not text:
            return None
        first_line = text.strip().splitlines()[0].strip()
        if first_line.upper() == 'N/A':
            return None
        m = re.match(r'^(?:\s*)([1-9]|10)(?:\b)', first_line)
        if m:
            try:
                v = int(m.group(1))
                return max(1, min(10, v))
            except Exception:
                return None
        return None

    rating = parse_rating(ai_output)
    rating_percent = (rating * 10) if rating is not None else 0
    
    # Extract only the explanation (skip the rating line)
    ai_analysis_display = ai_output
    if ai_output and '\n' in ai_output:
        lines = ai_output.split('\n', 1)
        if len(lines) > 1:
            ai_analysis_display = lines[1].strip()
    elif ai_output:
        # If no newline, check if first word is just a rating
        first_word = ai_output.strip().split()[0] if ai_output.strip() else ''
        if first_word.upper() == 'N/A' or first_word.isdigit():
            ai_analysis_display = ' '.join(ai_output.strip().split()[1:])
    
    # Fallback if extraction resulted in empty text
    if not ai_analysis_display.strip():
        ai_analysis_display = ai_output
    # Compute a color that moves from red -> yellow -> green based on rating_percent
    def compute_bar_color(percent: int):
        try:
            p = int(percent)
        except Exception:
            return None
        if p <= 0:
            return None
        if p <= 50:
            # interpolate red (255,0,0) -> yellow (255,255,0)
            ratio = p / 50.0
            r = 255
            g = round(255 * ratio)
            b = 0
        else:
            # interpolate yellow (255,255,0) -> green (0,200,0)
            ratio = (p - 50) / 50.0
            r = round(255 * (1 - ratio))
            g = round(255 - 55 * ratio)
            b = 0
        return f"#{r:02x}{g:02x}{b:02x}"

    bar_color = compute_bar_color(rating_percent) or 'linear-gradient(90deg,var(--accent),#5a3bff)'
    # embed uploaded image as base64 for preview in result page
    try:
        image_b64 = base64.b64encode(file_bytes).decode("ascii")
    except Exception:
        image_b64 = ""
    mime = getattr(file, 'content_type', 'image/png') or 'image/png'

    return render_template_string(RESULT_PAGE, extracted_text=extracted_text, ai_output=ai_analysis_display, image_b64=image_b64, mime=mime, filename=file.filename, rating=rating, rating_percent=rating_percent, bar_color=bar_color)

if __name__ == "__main__":
    # Start on PORT (default 5002); if busy, pick the next available port.
    base_port = int(os.environ.get("PORT", "5002"))
    port = base_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                break
            port += 1
    if port != base_port:
        print(f"Port {base_port} is busy. Using {port} instead.")
    app.run(host="0.0.0.0", port=port, debug=True)
