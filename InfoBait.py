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
import json

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
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Lora:ital,wght@0,400;0,600;1,400&family=UnifrakturMaguntia&display=swap" rel="stylesheet">
    <style>
        :root{--bg:#1a1a18;--card:#222220;--muted:#8a8a80;--accent:#c41e1e;--glass:rgba(255,255,255,0.03);--ink:#e8e4d8;--paper:#222220;--border:rgba(200,195,170,0.15)}
        :root.light{--bg:#f4f1ea;--card:#fffef8;--muted:#6b6860;--accent:#b31a1a;--glass:rgba(0,0,0,0.02);--ink:#1a1a18;--paper:#fffef8;--border:rgba(0,0,0,0.12)}
        html,body{height:100%;margin:0;font-family:'Lora',Georgia,'Times New Roman',serif;font-size:16px;color:var(--ink)}
        body::before{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:var(--bg) repeating-linear-gradient(transparent,transparent 27px,rgba(200,195,170,0.12) 27px,rgba(200,195,170,0.12) 28px);
        }
        body::after{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:none;
            pointer-events:none;
        }
        :root.light body::before{
            background:var(--bg) repeating-linear-gradient(transparent,transparent 27px,rgba(80,75,65,0.1) 27px,rgba(80,75,65,0.1) 28px);
        }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(196,30,30,0.25); } 70% { box-shadow: 0 0 0 10px rgba(196,30,30,0); } 100% { box-shadow: 0 0 0 0 rgba(196,30,30,0); } }
        .wrap{min-height:100%;display:flex;align-items:flex-start;justify-content:center;padding:36px;gap:24px}

        .card{width:100%;max-width:820px;flex:1 1 auto;background:var(--card);border-radius:0;padding:44px 40px 36px;box-shadow:0 4px 24px rgba(0,0,0,0.25),0 1px 4px rgba(0,0,0,0.15);color:var(--ink);animation:fadeUp .42s ease-out both;border:1px solid var(--border);border-top:4px double var(--ink);border-bottom:4px double var(--ink);position:relative;z-index:2;transition:transform .25s ease,box-shadow .25s ease}
        .card:hover{transform:translateY(-3px);box-shadow:0 8px 32px rgba(0,0,0,0.32),0 2px 8px rgba(0,0,0,0.18)}

        .sidebar{width:220px;flex-shrink:0;animation:fadeUp .5s ease-out both;animation-delay:.15s}
        .sidebar-box{background:var(--card);border:1px solid var(--border);border-top:3px double var(--ink);padding:16px 14px;margin-bottom:16px;transition:transform .25s ease,box-shadow .25s ease}
        .sidebar-box:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,0.2)}
        .sidebar-box-heading{font-family:'Playfair Display',Georgia,serif;font-weight:900;font-size:11px;text-transform:uppercase;letter-spacing:3px;color:var(--accent);margin:0 0 10px;padding-bottom:8px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:6px}
        .weather-icon{font-size:36px;line-height:1;text-align:center;margin:4px 0 8px}
        .weather-temp{font-family:'Playfair Display',Georgia,serif;font-size:32px;font-weight:900;text-align:center;line-height:1;margin-bottom:2px}
        .weather-desc{font-family:'Lora',Georgia,serif;font-size:12px;color:var(--muted);text-align:center;font-style:italic;margin-bottom:10px}
        .weather-location{font-family:'Lora',Georgia,serif;font-size:10px;color:var(--muted);text-align:center;text-transform:uppercase;letter-spacing:2px;margin-bottom:12px}
        .weather-details{border-top:1px solid var(--border);padding-top:10px}
        .weather-row{display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:11px;font-family:'Lora',Georgia,serif}
        .weather-row-label{color:var(--muted);text-transform:uppercase;letter-spacing:1px;font-size:9px;font-weight:600}
        .weather-row-val{font-weight:700;color:var(--ink)}
        .weather-loading{text-align:center;padding:16px 0;color:var(--muted);font-size:11px;font-style:italic;font-family:'Lora',Georgia,serif}
        .weather-forecast{border-top:1px solid var(--border);padding-top:10px;margin-top:6px}
        .forecast-day{display:flex;justify-content:space-between;align-items:center;padding:3px 0;font-size:10px;font-family:'Lora',Georgia,serif}
        .forecast-day-name{color:var(--muted);text-transform:uppercase;letter-spacing:1px;font-size:9px;font-weight:600;width:32px}
        .forecast-day-icon{font-size:14px;flex-shrink:0}
        .forecast-day-temps{color:var(--ink);font-weight:600;font-size:10px}
        .forecast-day-temps span{color:var(--muted);font-weight:400}
        .sidebar-quote{font-family:'Lora',Georgia,serif;font-size:12px;font-style:italic;color:var(--muted);line-height:1.6;padding:4px 0}
        .sidebar-quote-attr{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:2px;margin-top:6px;text-align:right;font-style:normal}
        .right-sidebar{width:220px;flex-shrink:0;animation:fadeUp .5s ease-out both;animation-delay:.25s}
        @media (max-width:1100px){.sidebar,.right-sidebar{display:none}}
        .page-footer{background:#111;border-top:3px double rgba(255,255,255,0.2);padding:24px 28px;text-align:center;margin-top:auto}
        :root.light .page-footer{background:#1a1a18;border-top:3px double rgba(255,255,255,0.15)}
        .page-footer .footer-logo{font-family:'UnifrakturMaguntia','Playfair Display',Georgia,serif;font-size:28px;color:#fff;text-decoration:none;letter-spacing:2px;transition:opacity .25s}
        .page-footer .footer-logo:hover{opacity:.7}
        .pen-line-wrap{position:relative;width:100%;max-width:320px;margin:12px auto 0;height:16px;overflow:visible}
        .pen-line{position:absolute;top:50%;left:0;height:1px;background:rgba(255,255,255,0.25);width:0;animation:penDraw 2.5s ease-out 0.5s forwards}
        :root.light .pen-line{background:rgba(255,255,255,0.2)}
        .pen-icon{position:absolute;top:50%;transform:translate(-4px,-50%) rotate(-45deg);left:0;font-size:12px;opacity:0;animation:penMove 2.5s ease-out 0.5s forwards;color:rgba(255,255,255,0.5);filter:none}
        @keyframes penDraw{0%{width:0}100%{width:100%}}
        @keyframes penMove{0%{left:0;opacity:1}90%{opacity:1}100%{left:100%;opacity:0}}
        :root.light .card{background:var(--card);box-shadow:0 1px 6px rgba(0,0,0,0.08);color:var(--ink)}
        h1{margin:0 0 4px;font-weight:900;font-size:32px;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:1px;line-height:1.1;border-bottom:2px solid var(--ink);padding-bottom:10px;min-height:46px}
        p.lead{margin:0 0 20px;color:var(--muted);font-size:14px;font-family:'Lora',Georgia,serif;line-height:1.7;font-style:italic;padding-top:8px;min-height:72px}
        .typewriter-cursor{display:inline-block;width:2px;height:1em;background:var(--accent);margin-left:2px;vertical-align:text-bottom;animation:blink .6s step-end infinite}
        :root.light .typewriter-cursor{background:var(--accent)}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
        form{display:flex;gap:12px;align-items:center}
        .file-input{flex:1;display:flex;align-items:center;gap:12px;padding:12px 14px;background:var(--glass);border-radius:0;border:1px solid var(--border);transition:box-shadow .18s ease,transform .12s ease}
        :root.light .file-input{border:1px solid var(--border)}
        .file-input input[type=file]{background:transparent;color:inherit;font-size:14px;font-family:'Lora',Georgia,serif}
        .file-input input[type=file]::file-selector-button{
            margin-right:12px;
            padding:8px 16px;
            border-radius:0;
            border:2px solid var(--ink);
            background:transparent;
            color:var(--ink);
            font-weight:700;
            font-family:'Playfair Display',Georgia,serif;
            cursor:pointer;
            transition:all .15s ease;
            text-transform:uppercase;
            letter-spacing:1px;
            font-size:11px;
        }
        .file-input input[type=file]::file-selector-button:hover{
            background:var(--ink);
            color:var(--bg);
        }
        .file-input input[type=file]::file-selector-button:active{
            transform:translateY(0);
        }
        .file-input input[type=file]::-webkit-file-upload-button{
            margin-right:12px;
            padding:8px 16px;
            border-radius:0;
            border:2px solid var(--ink);
            background:transparent;
            color:var(--ink);
            font-weight:700;
            font-family:'Playfair Display',Georgia,serif;
            cursor:pointer;
            transition:all .15s ease;
            text-transform:uppercase;
            letter-spacing:1px;
            font-size:11px;
        }
        .file-input:hover{box-shadow:0 2px 6px rgba(0,0,0,0.1);transform:translateY(-1px)}
        .btn{position:relative;background:var(--accent);border:none;color:#fff;padding:12px 24px;border-radius:0;font-weight:700;cursor:pointer;transition:all .2s ease;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:2px;font-size:13px;overflow:hidden}
        .btn::before{content:none}
        .btn:hover{transform:translateY(-2px);background:#a01818;box-shadow:0 3px 10px rgba(196,30,30,0.25)}
        .btn:hover::before{left:100%}
        .btn:active{transform:translateY(0);box-shadow:none}
        .settings-btn{width:44px;height:44px;border-radius:0;background:rgba(255,255,255,0.1);border:none;color:#ccc;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:20px;transition:all .2s ease}
        .settings-btn:hover{background:rgba(255,255,255,0.18);transform:rotate(90deg) scale(1.05)}
        .settings-dropdown{position:fixed;top:62px;right:24px;width:320px;background:var(--card);border-radius:0;border:1px solid var(--border);box-shadow:0 4px 20px rgba(0,0,0,0.3);display:none;z-index:99;overflow:hidden;animation:fadeUp .3s ease-out;font-family:'Lora',Georgia,serif}
        :root.light .settings-dropdown{background:#fffef8;box-shadow:0 4px 20px rgba(0,0,0,0.08)}
        .settings-dropdown.show{display:block}
        .settings-section{border-bottom:1px solid var(--border);padding:16px}
        .settings-section:last-child{border-bottom:none}
        .settings-section h3{margin:0 0 10px;font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:3px;font-family:'Playfair Display',Georgia,serif}
        .theme-toggle-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:4px 0}
        .theme-toggle-label{color:var(--ink);font-size:14px;font-family:'Lora',Georgia,serif}
        .theme-switch{position:relative;display:inline-block;width:64px;height:34px}
        .theme-switch input{opacity:0;width:0;height:0}
        .theme-slider{position:absolute;inset:0;cursor:pointer;background:rgba(200,195,170,0.2);border:1px solid rgba(200,195,170,0.3);border-radius:999px;transition:all .2s ease;display:flex;align-items:center;justify-content:space-between;padding:0 9px;font-size:13px}
        .theme-slider::before{content:"";position:absolute;height:26px;width:26px;left:3px;top:3px;background:var(--accent);border-radius:50%;box-shadow:0 2px 6px rgba(0,0,0,0.2);transition:transform .2s ease}
        .theme-switch input:checked + .theme-slider::before{transform:translateX(30px)}
        .theme-switch input:focus-visible + .theme-slider{outline:2px solid var(--accent);outline-offset:2px}
        .theme-sun,.theme-moon{position:relative;z-index:1;opacity:0.9}
        .theme-switch input:checked + .theme-slider .theme-sun{opacity:1}
        .theme-switch input:checked + .theme-slider .theme-moon{opacity:0.55}
        .theme-switch input:not(:checked) + .theme-slider .theme-moon{opacity:1}
        .theme-switch input:not(:checked) + .theme-slider .theme-sun{opacity:0.55}
        .help-text{color:var(--muted);font-size:13px;line-height:1.6;font-family:'Lora',Georgia,serif}
        @keyframes ttsShimmer{0%{background-position:200% center}100%{background-position:-200% center}}
        @keyframes ttsPulse{0%,100%{box-shadow:0 0 4px rgba(196,30,30,0.15)}50%{box-shadow:0 0 12px rgba(196,30,30,0.3)}}
        @keyframes ttsActivePulse{0%,100%{box-shadow:0 0 4px rgba(180,60,60,0.15)}50%{box-shadow:0 0 12px rgba(180,60,60,0.3)}}
        .tts-btn{position:relative;padding:8px 16px;border-radius:0;background:transparent;border:2px solid var(--ink);color:var(--ink);cursor:pointer;font-size:11px;font-weight:700;transition:all .2s ease;display:inline-flex;align-items:center;gap:8px;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:1px;animation:none}
        .tts-btn::before{content:none}
        .tts-btn::after{content:none}
        .tts-btn:hover{background:var(--ink);color:var(--bg);transform:translateY(-1px)}
        .tts-btn:active{transform:translateY(0);box-shadow:none}
        :root.light .tts-btn{border-color:var(--ink);color:var(--ink)}
        :root.light .tts-btn:hover{background:var(--ink);color:var(--bg)}
        .tts-btn.tts-active{background:var(--accent);border-color:var(--accent);color:#fff;animation:ttsActivePulse 1.5s ease-in-out infinite}
        .tts-btn.tts-active:hover{background:#a01818;border-color:#a01818;color:#fff}
        :root.light .tts-btn.tts-active{background:var(--accent);border-color:var(--accent);color:#fff}
        :root.light .tts-btn.tts-active:hover{background:#8a1515}
        .meta{margin-top:20px;display:flex;gap:16px;align-items:center;padding-top:16px;border-top:1px solid var(--border)}
        .preview{width:160px;height:120px;border-radius:0;overflow:hidden;background:rgba(0,0,0,0.1);display:flex;align-items:center;justify-content:center;border:1px solid var(--border);transition:transform .18s ease,box-shadow .18s ease}
        :root.light .preview{background:rgba(0,0,0,0.03);border:1px solid var(--border)}
        .preview img{max-width:100%;max-height:100%;display:block;transition:transform .25s ease}
        .preview:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.15)}
        .preview:hover img{transform:scale(1.02)}
        .note{color:var(--muted);font-size:13px;font-family:'Lora',Georgia,serif;font-style:italic}
        footer{margin-top:20px;color:var(--muted);font-size:11px;text-align:center;font-family:'Lora',Georgia,serif;font-style:italic;padding-top:14px;border-top:1px solid var(--border)}
        .top-banner{position:fixed;top:0;left:0;right:0;height:auto;background:#111;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:10px 28px;border-bottom:3px double rgba(255,255,255,0.2);box-shadow:none;flex-direction:row}
        :root.light .top-banner{background:#1a1a18;border-bottom:3px double rgba(255,255,255,0.15)}
        .logo{text-decoration:none;transition:all .25s ease;display:flex;flex-direction:column;align-items:flex-start}
        .logo:hover{transform:translateY(-1px);filter:none}
        .logo-text{font-size:32px;font-weight:400;letter-spacing:2px;font-family:'UnifrakturMaguntia','Playfair Display',Georgia,serif;color:#fff;text-transform:none;-webkit-text-fill-color:unset;background:none;line-height:1}
        :root.light .logo-text{color:#fff;background:none;-webkit-text-fill-color:unset}
        .banner-date{font-size:10px;color:rgba(255,255,255,0.5);font-family:'Lora',Georgia,serif;letter-spacing:2px;text-transform:uppercase;margin-top:2px}
        body{padding-top:62px}
        @media (max-width:520px){.card{padding:20px 16px}.meta{flex-direction:column;align-items:flex-start}.preview{width:100%;height:auto}}
        .faq-link{display:inline-flex;align-items:center;gap:6px;color:var(--accent);font-size:12px;cursor:pointer;padding:8px 14px;border-radius:0;border:1px solid var(--border);background:transparent;transition:all .2s ease;font-weight:600;width:100%;justify-content:center;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:2px}
        .faq-link:hover{background:var(--accent);border-color:var(--accent);color:#fff;transform:translateY(-1px)}
        .faq-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(3px);z-index:200;align-items:center;justify-content:center;padding:24px;animation:fadeUp .25s ease-out}
        .faq-overlay.show{display:flex}
        .faq-modal{width:100%;max-width:600px;max-height:80vh;overflow-y:auto;background:var(--card);border-radius:0;border:1px solid var(--border);border-top:3px double var(--ink);box-shadow:0 8px 32px rgba(0,0,0,0.4);padding:28px;animation:fadeUp .3s ease-out;font-family:'Lora',Georgia,serif}
        :root.light .faq-modal{background:#fffef8;border:1px solid var(--border);border-top:3px double var(--ink);box-shadow:0 8px 32px rgba(0,0,0,0.1)}
        .faq-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;border-bottom:1px solid var(--border);padding-bottom:12px}
        .faq-header h2{margin:0;font-size:20px;font-weight:900;color:var(--ink);text-transform:uppercase;letter-spacing:3px;font-family:'Playfair Display',Georgia,serif}
        :root.light .faq-header h2{color:var(--ink)}
        .faq-close{width:36px;height:36px;border-radius:0;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;transition:all .2s ease;font-family:Georgia,serif}
        .faq-close:hover{background:var(--accent);border-color:var(--accent);color:#fff;transform:scale(1.05)}
        :root.light .faq-close{border-color:var(--border);background:transparent;color:var(--muted)}
        :root.light .faq-close:hover{background:var(--accent);color:#fff}
        .faq-item{border-radius:0;border:none;border-bottom:1px solid var(--border);background:transparent;margin-bottom:0;overflow:hidden;transition:all .2s ease}
        .faq-item:last-child{border-bottom:none}
        :root.light .faq-item{border-color:var(--border);background:transparent}
        .faq-item:hover{background:rgba(200,195,170,0.05)}
        .faq-q{padding:14px 4px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:12px;font-weight:700;font-size:14px;color:var(--ink);transition:color .2s ease;user-select:none;font-family:'Playfair Display',Georgia,serif}
        :root.light .faq-q{color:var(--ink)}
        .faq-q:hover{color:var(--accent)}
        :root.light .faq-q:hover{color:var(--accent)}
        .faq-arrow{font-size:12px;color:var(--muted);transition:transform .25s cubic-bezier(.4,0,.2,1);flex-shrink:0}
        .faq-item.open .faq-arrow{transform:rotate(180deg);color:var(--accent)}
        .faq-a{max-height:0;overflow:hidden;transition:max-height .3s cubic-bezier(.4,0,.2,1),padding .3s ease}
        .faq-item.open .faq-a{max-height:200px;padding:0 4px 14px}
        .faq-a p{margin:0;font-size:13px;color:var(--muted);line-height:1.8;font-family:'Lora',Georgia,serif}
        :root.light .faq-a p{color:var(--muted)}
        .edition-line{text-align:center;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:4px;font-family:'Lora',Georgia,serif;margin-bottom:16px}
        .divider{border:none;border-top:1px solid var(--border);margin:0}
        .thick-divider{border:none;border-top:3px double var(--ink);margin:12px 0}
    </style>
</head>
<body>
    <div class="top-banner">
        <a class="logo" href="/"><span class="logo-text">InfoBait</span><span class="banner-date" id="bannerDate"></span></a>
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
                <div class="faq-q" onclick="toggleFaq(this)"><span>How does the accuracy rating work?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>Our AI analyzes the extracted text and rates its factual accuracy on a scale of 1–10. A score of 1 means highly inaccurate, while 10 means highly accurate. The color bar shifts from red → yellow → green to reflect the rating visually.</p></div>
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
        <div class="sidebar" id="leftSidebar">
            <div class="sidebar-box">
                <div class="sidebar-box-heading">&#9788; Weather</div>
                <div id="weatherWidget">
                    <div class="weather-loading">Fetching forecast&hellip;</div>
                </div>
            </div>
        </div>
        <div class="card">
            <div class="edition-line">Screenshot Intelligence Bureau</div>
            <hr class="thick-divider">
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

            <footer>"Saved me from ragebait" &mdash; Est. 2026</footer>
        </div>
        <div class="right-sidebar">
            <div class="sidebar-box">
                <div class="sidebar-box-heading">&#10070; Quote of the Day</div>
                <div class="sidebar-quote" id="dailyQuote">"The truth is rarely pure and never simple."</div>
                <div class="sidebar-quote-attr" id="quoteAttr">&mdash; Oscar Wilde</div>
            </div>
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
            // Set banner date
            const dateEl = document.getElementById('bannerDate');
            if(dateEl){
                const d = new Date();
                const opts = {weekday:'long',year:'numeric',month:'long',day:'numeric'};
                dateEl.textContent = d.toLocaleDateString('en-US', opts);
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

        // Weather widget
        (function(){
            const WMO_ICONS = {0:'☀',1:'🌤',2:'⛅',3:'☁',45:'🌫',48:'🌫',51:'🌦',53:'🌦',55:'🌧',56:'🌨',57:'🌨',61:'🌧',63:'🌧',65:'🌧',66:'🌨',67:'🌨',71:'🌨',73:'🌨',75:'❄',77:'❄',80:'🌦',81:'🌧',82:'🌧',85:'🌨',86:'🌨',95:'⛈',96:'⛈',99:'⛈'};
            const WMO_DESC = {0:'Clear sky',1:'Mostly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',48:'Rime fog',51:'Light drizzle',53:'Drizzle',55:'Heavy drizzle',56:'Freezing drizzle',57:'Freezing drizzle',61:'Light rain',63:'Rain',65:'Heavy rain',66:'Freezing rain',67:'Freezing rain',71:'Light snow',73:'Snow',75:'Heavy snow',77:'Snow grains',80:'Light showers',81:'Showers',82:'Heavy showers',85:'Snow showers',86:'Heavy snow showers',95:'Thunderstorm',96:'Thunderstorm w/ hail',99:'Severe thunderstorm'};
            const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

            function renderWeather(data, city){
                const w = document.getElementById('weatherWidget');
                if(!w) return;
                const cur = data.current;
                const daily = data.daily;
                const icon = WMO_ICONS[cur.weather_code] || '☀';
                const desc = WMO_DESC[cur.weather_code] || 'Unknown';
                let html = '<div class="weather-icon">'+icon+'</div>';
                html += '<div class="weather-temp">'+Math.round(cur.temperature_2m)+'°</div>';
                html += '<div class="weather-desc">'+desc+'</div>';
                if(city) html += '<div class="weather-location">'+city+'</div>';
                html += '<div class="weather-details">';
                html += '<div class="weather-row"><span class="weather-row-label">Humidity</span><span class="weather-row-val">'+cur.relative_humidity_2m+'%</span></div>';
                html += '<div class="weather-row"><span class="weather-row-label">Wind</span><span class="weather-row-val">'+Math.round(cur.wind_speed_10m)+' mph</span></div>';
                html += '<div class="weather-row"><span class="weather-row-label">Feels like</span><span class="weather-row-val">'+Math.round(cur.apparent_temperature)+'°</span></div>';
                html += '</div>';
                // 5-day forecast
                if(daily && daily.time){
                    html += '<div class="weather-forecast">';
                    for(var i=1;i<=5&&i<daily.time.length;i++){
                        var d = new Date(daily.time[i]);
                        var dn = DAYS[d.getDay()];
                        var fi = WMO_ICONS[daily.weather_code[i]] || '☀';
                        html += '<div class="forecast-day"><span class="forecast-day-name">'+dn+'</span><span class="forecast-day-icon">'+fi+'</span><span class="forecast-day-temps">'+Math.round(daily.temperature_2m_max[i])+'° <span>'+Math.round(daily.temperature_2m_min[i])+'°</span></span></div>';
                    }
                    html += '</div>';
                }
                w.innerHTML = html;
            }

            function fetchWeather(lat, lon, city){
                var url = 'https://api.open-meteo.com/v1/forecast?latitude='+lat+'&longitude='+lon+'&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=6&temperature_unit=fahrenheit&wind_speed_unit=mph';
                fetch(url).then(function(r){return r.json()}).then(function(data){
                    renderWeather(data, city);
                }).catch(function(){
                    var w=document.getElementById('weatherWidget');
                    if(w) w.innerHTML='<div class="weather-loading">Weather unavailable</div>';
                });
            }

            function reverseGeocode(lat, lon, cb){
                fetch('https://nominatim.openstreetmap.org/reverse?lat='+lat+'&lon='+lon+'&format=json')
                .then(function(r){return r.json()}).then(function(d){
                    var city = (d.address && (d.address.city||d.address.town||d.address.village||d.address.county)) || '';
                    cb(city);
                }).catch(function(){ cb(''); });
            }

            // IP-based geolocation (no permission needed)
            fetch('https://ipapi.co/json/')
            .then(function(r){return r.json()})
            .then(function(geo){
                if(geo && geo.latitude && geo.longitude){
                    fetchWeather(geo.latitude, geo.longitude, geo.city || '');
                } else {
                    // Fallback: try browser geolocation
                    if(navigator.geolocation){
                        navigator.geolocation.getCurrentPosition(function(pos){
                            var lat=pos.coords.latitude, lon=pos.coords.longitude;
                            reverseGeocode(lat, lon, function(city){
                                fetchWeather(lat, lon, city);
                            });
                        }, function(){ fetchWeather(51.51, -0.13, 'London'); }, {timeout:5000});
                    } else { fetchWeather(51.51, -0.13, 'London'); }
                }
            })
            .catch(function(){
                fetchWeather(51.51, -0.13, 'London');
            });
        })();

        // Daily quote rotation
        (function(){
            var quotes = [
                ['The truth is rarely pure and never simple.','Oscar Wilde'],
                ['Facts do not cease to exist because they are ignored.','Aldous Huxley'],
                ['A lie can travel half way around the world while the truth is putting on its shoes.','Mark Twain'],
                ['In a time of deceit, telling the truth is a revolutionary act.','George Orwell'],
                ['The first duty of a newspaper is to be accurate.','C.P. Scott'],
                ['Journalism is printing what someone else does not want printed. Everything else is public relations.','George Orwell'],
                ['The pen is mightier than the sword.','Edward Bulwer-Lytton']
            ];
            var dayIndex = new Date().getDate() % quotes.length;
            var q = quotes[dayIndex];
            var qEl = document.getElementById('dailyQuote');
            var aEl = document.getElementById('quoteAttr');
            if(qEl) qEl.textContent = '\u201c'+q[0]+'\u201d';
            if(aEl) aEl.innerHTML = '&mdash; '+q[1];
        })();

        // Secret code
        (function(){
            var seq=['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','a','b','Enter'];
            var pos=0;
            document.addEventListener('keydown',function(e){
                if(e.key===seq[pos]){pos++;if(pos===seq.length){pos=0;window.location.href='/bibi';}}else{pos=0;}
            });
        })();
    </script>
        <div id="loader" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(3px);align-items:center;justify-content:center;z-index:60">
            <div style="width:80%;max-width:560px;padding:24px;background:#222220;border-radius:0;border:1px solid rgba(200,195,170,0.2);border-top:3px double #e8e4d8;display:flex;flex-direction:column;gap:12px;align-items:center;font-family:'Lora',Georgia,serif">
                <div style="width:100%;height:4px;background:rgba(200,195,170,0.1);border-radius:0;overflow:hidden;position:relative">
                    <div style="position:absolute;left:-40%;top:0;bottom:0;width:40%;background:linear-gradient(90deg,transparent,rgba(196,30,30,0.8),transparent);animation:loaderMove 1.2s linear infinite"></div>
                </div>
                <div style="color:#e8e4d8;font-size:14px;letter-spacing:2px;text-transform:uppercase;font-family:'Playfair Display',Georgia,serif;font-weight:700">Press Running&hellip;</div>
            </div>
        </div>
        <style>
            @keyframes loaderMove { from { left:-40% } to { left:140% } }
        </style>
    <div class="page-footer">
        <a href="/" class="footer-logo">InfoBait</a>
        <div class="pen-line-wrap">
            <div class="pen-line"></div>
            <div class="pen-icon">&#9998;</div>
        </div>
    </div>
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
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Lora:ital,wght@0,400;0,600;1,400&family=UnifrakturMaguntia&display=swap" rel="stylesheet">
    <style>
        :root{--bg:#1a1a18;--card:#222220;--muted:#8a8a80;--accent:#c41e1e;--glass:rgba(255,255,255,0.03);--ink:#e8e4d8;--paper:#222220;--border:rgba(200,195,170,0.15)}
        :root.light{--bg:#f4f1ea;--card:#fffef8;--muted:#6b6860;--accent:#b31a1a;--glass:rgba(0,0,0,0.02);--ink:#1a1a18;--paper:#fffef8;--border:rgba(0,0,0,0.12)}
        html,body{height:100%;margin:0;font-family:'Lora',Georgia,'Times New Roman',serif;font-size:16px;color:var(--ink)}
        body::before{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:var(--bg) repeating-linear-gradient(transparent,transparent 27px,rgba(200,195,170,0.12) 27px,rgba(200,195,170,0.12) 28px);
        }
        body::after{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:none;
            pointer-events:none;
        }
        :root.light body::before{
            background:var(--bg) repeating-linear-gradient(transparent,transparent 27px,rgba(80,75,65,0.1) 27px,rgba(80,75,65,0.1) 28px);
        }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:36px}

        .card{width:100%;max-width:1100px;background:var(--card);border-radius:0;padding:32px 28px;box-shadow:0 1px 4px rgba(0,0,0,0.15);color:var(--ink);animation:fadeUp .42s ease-out both;border:1px solid var(--border);border-top:3px double var(--ink);border-bottom:3px double var(--ink)}
        :root.light .card{background:var(--card);box-shadow:0 1px 6px rgba(0,0,0,0.08);color:var(--ink)}
        .row{display:flex;gap:24px;align-items:flex-start}
        .left{width:320px}
        .preview{width:100%;border-radius:0;overflow:hidden;background:rgba(0,0,0,0.1);display:flex;align-items:center;justify-content:center;border:1px solid var(--border);padding:12px;transition:transform .18s ease,box-shadow .18s ease}
        :root.light .preview{background:rgba(0,0,0,0.03);border:1px solid var(--border)}
        .preview img{max-width:100%;height:auto;display:block;transition:transform .25s ease}
        .preview:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.15)}
        .preview:hover img{transform:scale(1.02)}
        .right{flex:1;border-left:1px solid var(--border);padding-left:24px}
        h1{margin:0 0 8px;font-weight:900;font-size:24px;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid var(--ink);padding-bottom:8px}
        .note{color:var(--muted);font-size:13px;margin-bottom:12px;font-family:'Lora',Georgia,serif;font-style:italic}
        .panel{background:transparent;padding:16px 0;border-radius:0;border:none;border-bottom:1px solid var(--border);color:var(--ink);font-size:14px;font-family:'Lora',Georgia,serif}
        .panel:last-of-type{border-bottom:none}
        :root.light .panel{background:transparent;border-bottom:1px solid var(--border);color:var(--ink)}
        .panel strong{font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:2px;font-size:12px;color:var(--accent)}
        pre{white-space:pre-wrap;word-break:break-word;margin:0;font-family:'Lora',Georgia,serif;font-size:14px;line-height:1.7}
        a.btn{position:relative;display:inline-flex;align-items:center;justify-content:center;text-align:center;margin-top:16px;padding:10px 20px;border-radius:0;background:var(--accent);border:none;color:#fff;text-decoration:none;font-weight:700;transition:all .2s ease;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:2px;font-size:12px}
        a.btn:hover{transform:translateY(-2px);background:#a01818;box-shadow:0 3px 10px rgba(196,30,30,0.2)}
        a.btn:active{transform:translateY(0px)}
        .settings-btn{width:44px;height:44px;border-radius:0;background:rgba(255,255,255,0.1);border:none;color:#ccc;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:20px;transition:all .2s ease}
        .settings-btn:hover{background:rgba(255,255,255,0.18);transform:rotate(90deg) scale(1.05)}
        .settings-dropdown{position:fixed;top:62px;right:24px;width:320px;background:var(--card);border-radius:0;border:1px solid var(--border);box-shadow:0 4px 20px rgba(0,0,0,0.3);display:none;z-index:99;overflow:hidden;animation:fadeUp .3s ease-out;font-family:'Lora',Georgia,serif}
        :root.light .settings-dropdown{background:#fffef8;box-shadow:0 4px 20px rgba(0,0,0,0.08)}
        .settings-dropdown.show{display:block}
        .settings-section{border-bottom:1px solid var(--border);padding:16px}
        .settings-section:last-child{border-bottom:none}
        .settings-section h3{margin:0 0 10px;font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:3px;font-family:'Playfair Display',Georgia,serif}
        .theme-toggle-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:4px 0}
        .theme-toggle-label{color:var(--ink);font-size:14px;font-family:'Lora',Georgia,serif}
        .theme-switch{position:relative;display:inline-block;width:64px;height:34px}
        .theme-switch input{opacity:0;width:0;height:0}
        .theme-slider{position:absolute;inset:0;cursor:pointer;background:rgba(200,195,170,0.2);border:1px solid rgba(200,195,170,0.3);border-radius:999px;transition:all .2s ease;display:flex;align-items:center;justify-content:space-between;padding:0 9px;font-size:13px}
        .theme-slider::before{content:"";position:absolute;height:26px;width:26px;left:3px;top:3px;background:var(--accent);border-radius:50%;box-shadow:0 2px 6px rgba(0,0,0,0.2);transition:transform .2s ease}
        .theme-switch input:checked + .theme-slider::before{transform:translateX(30px)}
        .theme-switch input:focus-visible + .theme-slider{outline:2px solid var(--accent);outline-offset:2px}
        .theme-sun,.theme-moon{position:relative;z-index:1;opacity:0.9}
        .theme-switch input:checked + .theme-slider .theme-sun{opacity:1}
        .theme-switch input:checked + .theme-slider .theme-moon{opacity:0.55}
        .theme-switch input:not(:checked) + .theme-slider .theme-moon{opacity:1}
        .theme-switch input:not(:checked) + .theme-slider .theme-sun{opacity:0.55}
        .help-text{color:var(--muted);font-size:13px;line-height:1.6;font-family:'Lora',Georgia,serif}
        @keyframes ttsShimmer{0%{background-position:200% center}100%{background-position:-200% center}}
        @keyframes ttsPulse{0%,100%{box-shadow:0 0 4px rgba(196,30,30,0.15)}50%{box-shadow:0 0 12px rgba(196,30,30,0.3)}}
        @keyframes ttsActivePulse{0%,100%{box-shadow:0 0 4px rgba(180,60,60,0.15)}50%{box-shadow:0 0 12px rgba(180,60,60,0.3)}}
        .tts-btn{position:relative;padding:6px 14px;border-radius:0;background:transparent;border:2px solid var(--ink);color:var(--ink);cursor:pointer;font-size:10px;font-weight:700;transition:all .2s ease;display:inline-flex;align-items:center;gap:6px;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:1px;animation:none}
        .tts-btn::before{content:none}
        .tts-btn::after{content:none}
        .tts-btn:hover{background:var(--ink);color:var(--bg);transform:translateY(-1px)}
        .tts-btn:active{transform:translateY(0);box-shadow:none}
        :root.light .tts-btn{border-color:var(--ink);color:var(--ink)}
        :root.light .tts-btn:hover{background:var(--ink);color:var(--bg)}
        .tts-btn.tts-active{background:var(--accent);border-color:var(--accent);color:#fff;animation:ttsActivePulse 1.5s ease-in-out infinite}
        .tts-btn.tts-active:hover{background:#a01818;border-color:#a01818;color:#fff}
        :root.light .tts-btn.tts-active{background:var(--accent);border-color:var(--accent);color:#fff}
        :root.light .tts-btn.tts-active:hover{background:#8a1515}
        @media (max-width:820px){.row{flex-direction:column}.left{width:100%}.right{border-left:none;padding-left:0;border-top:1px solid var(--border);padding-top:20px}}
        .top-banner{position:fixed;top:0;left:0;right:0;height:auto;background:#111;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:10px 28px;border-bottom:3px double rgba(255,255,255,0.2);box-shadow:none;flex-direction:row}
        :root.light .top-banner{background:#1a1a18;border-bottom:3px double rgba(255,255,255,0.15)}
        .logo{text-decoration:none;transition:all .25s ease;display:flex;flex-direction:column;align-items:flex-start}
        .logo:hover{transform:translateY(-1px);filter:none}
        .logo-text{font-size:32px;font-weight:400;letter-spacing:2px;font-family:'UnifrakturMaguntia','Playfair Display',Georgia,serif;color:#fff;text-transform:none;-webkit-text-fill-color:unset;background:none;line-height:1}
        :root.light .logo-text{color:#fff;background:none;-webkit-text-fill-color:unset}
        .banner-date{font-size:10px;color:rgba(255,255,255,0.5);font-family:'Lora',Georgia,serif;letter-spacing:2px;text-transform:uppercase;margin-top:2px}
        body{padding-top:62px}
        .faq-link{display:inline-flex;align-items:center;gap:6px;color:var(--accent);font-size:12px;cursor:pointer;padding:8px 14px;border-radius:0;border:1px solid var(--border);background:transparent;transition:all .2s ease;font-weight:600;width:100%;justify-content:center;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:2px}
        .faq-link:hover{background:var(--accent);border-color:var(--accent);color:#fff;transform:translateY(-1px)}
        .faq-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(3px);z-index:200;align-items:center;justify-content:center;padding:24px;animation:fadeUp .25s ease-out}
        .faq-overlay.show{display:flex}
        .faq-modal{width:100%;max-width:600px;max-height:80vh;overflow-y:auto;background:var(--card);border-radius:0;border:1px solid var(--border);border-top:3px double var(--ink);box-shadow:0 8px 32px rgba(0,0,0,0.4);padding:28px;animation:fadeUp .3s ease-out;font-family:'Lora',Georgia,serif}
        :root.light .faq-modal{background:#fffef8;border:1px solid var(--border);border-top:3px double var(--ink);box-shadow:0 8px 32px rgba(0,0,0,0.1)}
        .faq-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;border-bottom:1px solid var(--border);padding-bottom:12px}
        .faq-header h2{margin:0;font-size:20px;font-weight:900;color:var(--ink);text-transform:uppercase;letter-spacing:3px;font-family:'Playfair Display',Georgia,serif}
        :root.light .faq-header h2{color:var(--ink)}
        .faq-close{width:36px;height:36px;border-radius:0;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;transition:all .2s ease;font-family:Georgia,serif}
        .faq-close:hover{background:var(--accent);border-color:var(--accent);color:#fff;transform:scale(1.05)}
        :root.light .faq-close{border-color:var(--border);background:transparent;color:var(--muted)}
        :root.light .faq-close:hover{background:var(--accent);color:#fff}
        .faq-item{border-radius:0;border:none;border-bottom:1px solid var(--border);background:transparent;margin-bottom:0;overflow:hidden;transition:all .2s ease}
        .faq-item:last-child{border-bottom:none}
        :root.light .faq-item{border-color:var(--border);background:transparent}
        .faq-item:hover{background:rgba(200,195,170,0.05)}
        .faq-q{padding:14px 4px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:12px;font-weight:700;font-size:14px;color:var(--ink);transition:color .2s ease;user-select:none;font-family:'Playfair Display',Georgia,serif}
        :root.light .faq-q{color:var(--ink)}
        .faq-q:hover{color:var(--accent)}
        :root.light .faq-q:hover{color:var(--accent)}
        .faq-arrow{font-size:12px;color:var(--muted);transition:transform .25s cubic-bezier(.4,0,.2,1);flex-shrink:0}
        .faq-item.open .faq-arrow{transform:rotate(180deg);color:var(--accent)}
        .faq-a{max-height:0;overflow:hidden;transition:max-height .3s cubic-bezier(.4,0,.2,1),padding .3s ease}
        .faq-item.open .faq-a{max-height:200px;padding:0 4px 14px}
        .faq-a p{margin:0;font-size:13px;color:var(--muted);line-height:1.8;font-family:'Lora',Georgia,serif}
        :root.light .faq-a p{color:var(--muted)}
        .edition-line{text-align:center;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:4px;font-family:'Lora',Georgia,serif;margin-bottom:12px}
        .divider{border:none;border-top:1px solid var(--border);margin:0}
        .thick-divider{border:none;border-top:3px double var(--ink);margin:8px 0}
        .sources-section{margin-top:16px;padding:14px 0 0;border-top:1px solid var(--border)}
        .sources-heading{font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:2px;font-size:11px;color:var(--accent);font-weight:700;margin:0 0 10px;display:flex;align-items:center;gap:8px}
        .sources-heading::after{content:'';flex:1;height:1px;background:var(--border)}
        .sources-list{list-style:none;margin:0;padding:0}
        .sources-list li{padding:6px 0;border-bottom:1px solid var(--border);font-size:12px;font-family:'Lora',Georgia,serif;line-height:1.5;display:flex;align-items:baseline;gap:6px}
        .sources-list li:last-child{border-bottom:none}
        .sources-list li::before{content:'§';color:var(--accent);font-weight:700;font-size:11px;flex-shrink:0}
        .sources-list a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--border);transition:all .15s ease;word-break:break-all}
        .sources-list a:hover{color:var(--accent);border-bottom-color:var(--accent)}
        .sources-list .source-name{color:var(--ink);font-weight:600}
        .sources-list .source-url{color:var(--muted);font-size:10px;display:block;margin-top:1px;font-style:italic;word-break:break-all}
        .no-sources{color:var(--muted);font-size:12px;font-style:italic;font-family:'Lora',Georgia,serif}
        .edit-btn{padding:6px 14px;border-radius:0;background:transparent;border:2px solid var(--ink);color:var(--ink);cursor:pointer;font-size:10px;font-weight:700;transition:all .2s ease;display:inline-flex;align-items:center;gap:6px;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:1px}
        .edit-btn:hover{background:var(--ink);color:var(--bg);transform:translateY(-1px)}
        .edit-btn:active{transform:translateY(0)}
        .edit-btn.editing{background:var(--accent);border-color:var(--accent);color:#fff}
        .edit-btn.editing:hover{background:#a01818;border-color:#a01818}
        .reanalyze-btn{padding:6px 14px;border-radius:0;background:var(--accent);border:2px solid var(--accent);color:#fff;cursor:pointer;font-size:10px;font-weight:700;transition:all .2s ease;display:none;align-items:center;gap:6px;font-family:'Playfair Display',Georgia,serif;text-transform:uppercase;letter-spacing:1px}
        .reanalyze-btn.show{display:inline-flex}
        .reanalyze-btn:hover{background:#a01818;border-color:#a01818;transform:translateY(-1px)}
        .reanalyze-btn:active{transform:translateY(0)}
        .reanalyze-btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
        .extracted-textarea{width:100%;min-height:120px;background:transparent;border:1px solid var(--border);color:var(--ink);font-family:'Lora',Georgia,serif;font-size:14px;line-height:1.7;padding:10px;resize:vertical;outline:none;transition:border-color .2s ease;display:none}
        .extracted-textarea:focus{border-color:var(--accent)}
        .extracted-textarea.show{display:block}
        .edit-hint{color:var(--muted);font-size:11px;font-style:italic;font-family:'Lora',Georgia,serif;margin-top:6px;display:none}
        .edit-hint.show{display:block}
        .page-footer{background:#111;border-top:3px double rgba(255,255,255,0.2);padding:24px 28px;text-align:center;margin-top:auto}
        :root.light .page-footer{background:#1a1a18;border-top:3px double rgba(255,255,255,0.15)}
        .page-footer .footer-logo{font-family:'UnifrakturMaguntia','Playfair Display',Georgia,serif;font-size:28px;color:#fff;text-decoration:none;letter-spacing:2px;transition:opacity .25s}
        .page-footer .footer-logo:hover{opacity:.7}
    </style>
</head>
<body>
    <div class="top-banner">
        <a class="logo" href="/"><span class="logo-text">InfoBait</span><span class="banner-date" id="bannerDate"></span></a>
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
                <div class="faq-q" onclick="toggleFaq(this)"><span>How does the accuracy rating work?</span><span class="faq-arrow">▼</span></div>
                <div class="faq-a"><p>Our AI analyzes the extracted text and rates its factual accuracy on a scale of 1–10. A score of 1 means highly inaccurate, while 10 means highly accurate. The color bar shifts from red → yellow → green to reflect the rating visually.</p></div>
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
            <div class="edition-line">Investigative Report &mdash; Fact-Check Division</div>
            <hr class="thick-divider">
            <div class="note">File: {{ filename }}</div>
            <div class="row">
                <div class="left">
                    <div class="preview">
                        <img src="data:{{ mime }};base64,{{ image_b64 }}" alt="uploaded image">
                    </div>
                    <div class="sources-section" id="sourcesSection">
                        <div class="sources-heading">Sources</div>
                        <ul class="sources-list" id="sourcesList"></ul>
                    </div>
                </div>
                <div class="right">
                    <div class="panel">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:6px">
                            <strong>Extracted Text</strong>
                            <div style="display:flex;gap:6px;align-items:center">
                                <button onclick="toggleEdit()" class="edit-btn" id="editBtn">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                                    <span id="editBtnText">Edit</span>
                                </button>
                                <button onclick="reanalyze()" class="reanalyze-btn" id="reanalyzeBtn" title="Re-run AI analysis with edited text">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                                    <span id="reanalyzeBtnText">Re-analyze</span>
                                </button>
                                <button onclick="speakExtractedText()" class="tts-btn" id="ttsExtractedBtn">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                                    <span>Listen</span>
                                </button>
                            </div>
                        </div>
                        <pre id="extractedTextContent">{{ extracted_text }}</pre>
                        <textarea id="extractedTextEdit" class="extracted-textarea">{{ extracted_text }}</textarea>
                        <div id="editHint" class="edit-hint">Edit the text above, then click <strong>Re-analyze</strong> to get an updated analysis.</div>
                    </div>
                    <input type="hidden" id="hiddenImageB64" value="{{ image_b64 }}">
                    <input type="hidden" id="hiddenMime" value="{{ mime }}">
                    <input type="hidden" id="hiddenFilename" value="{{ filename }}">
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
                        <strong>Accuracy Rating</strong>
                        <div id="ratingContent" style="margin-top:8px">
                        {% if rating is not none %}
                            <div style="display:flex;align-items:center;gap:12px">
                                <div style="flex:1">
                                    <div style="position:relative;background:rgba(200,195,170,0.1);height:14px;border-radius:0;overflow:hidden;border:1px solid rgba(200,195,170,0.15)">
                                        <!-- ticks overlay: 10 equal segments -->
                                        <div style="position:absolute;inset:0;pointer-events:none;z-index:3;background-image:linear-gradient(to right,rgba(200,195,170,0.15) 1px, transparent 1px);background-size:10% 100%;background-repeat:repeat-x;opacity:0.9"></div>
                                        <div style="position:relative;z-index:2;height:100%;width:{{ rating_percent }}%;background:{{ bar_color }};transition:width:420ms ease;border-radius:0"></div>
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
            // Set banner date
            const dateEl = document.getElementById('bannerDate');
            if(dateEl){
                const d = new Date();
                const opts = {weekday:'long',year:'numeric',month:'long',day:'numeric'};
                dateEl.textContent = d.toLocaleDateString('en-US', opts);
            }
            // Render sources
            try{
                const sources = JSON.parse('{{ sources | safe }}');
                const list = document.getElementById('sourcesList');
                const section = document.getElementById('sourcesSection');
                if(sources && sources.length > 0 && list){
                    sources.forEach(function(s){
                        const li = document.createElement('li');
                        if(s.url && s.url.startsWith('http')){
                            const a = document.createElement('a');
                            a.href = s.url;
                            a.target = '_blank';
                            a.rel = 'noopener noreferrer';
                            const nameSpan = document.createElement('span');
                            nameSpan.className = 'source-name';
                            nameSpan.textContent = s.name || s.url;
                            a.appendChild(nameSpan);
                            if(s.url && s.name){
                                const urlSpan = document.createElement('span');
                                urlSpan.className = 'source-url';
                                urlSpan.textContent = s.url;
                                a.appendChild(urlSpan);
                            }
                            li.appendChild(a);
                        } else {
                            const span = document.createElement('span');
                            span.className = 'source-name';
                            span.textContent = s.name;
                            li.appendChild(span);
                        }
                        list.appendChild(li);
                    });
                } else if(section){
                    list.innerHTML = '<li class="no-sources" style="padding:6px 0">No sources available for this analysis.</li>';
                }
            }catch(e){
                const section = document.getElementById('sourcesSection');
                if(section){
                    document.getElementById('sourcesList').innerHTML = '<li class="no-sources" style="padding:6px 0">No sources available for this analysis.</li>';
                }
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

        // Edit extracted text functionality
        let isEditing = false;
        function toggleEdit(){
            isEditing = !isEditing;
            const pre = document.getElementById('extractedTextContent');
            const textarea = document.getElementById('extractedTextEdit');
            const hint = document.getElementById('editHint');
            const editBtn = document.getElementById('editBtn');
            const editBtnText = document.getElementById('editBtnText');
            const reanalyzeBtn = document.getElementById('reanalyzeBtn');
            if(isEditing){
                textarea.value = pre.textContent;
                pre.style.display = 'none';
                textarea.classList.add('show');
                hint.classList.add('show');
                editBtn.classList.add('editing');
                editBtnText.textContent = 'Cancel';
                reanalyzeBtn.classList.add('show');
                textarea.focus();
            } else {
                pre.style.display = '';
                textarea.classList.remove('show');
                hint.classList.remove('show');
                editBtn.classList.remove('editing');
                editBtnText.textContent = 'Edit';
                reanalyzeBtn.classList.remove('show');
            }
        }

        async function reanalyze(){
            const textarea = document.getElementById('extractedTextEdit');
            const editedText = textarea.value.trim();
            if(!editedText){ alert('Text cannot be empty.'); return; }
            const reanalyzeBtn = document.getElementById('reanalyzeBtn');
            const reanalyzeBtnText = document.getElementById('reanalyzeBtnText');
            reanalyzeBtn.disabled = true;
            reanalyzeBtnText.textContent = 'Analyzing\u2026';
            try{
                const resp = await fetch('/reanalyze', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        extracted_text: editedText,
                        image_b64: document.getElementById('hiddenImageB64').value,
                        mime: document.getElementById('hiddenMime').value,
                        filename: document.getElementById('hiddenFilename').value
                    })
                });
                const data = await resp.json();
                // Update extracted text
                const pre = document.getElementById('extractedTextContent');
                pre.textContent = editedText;
                // Update AI analysis
                document.getElementById('aiAnalysisText').textContent = data.ai_output;
                // Update rating bar using explicit ID
                const ratingContent = document.getElementById('ratingContent');
                if(data.rating !== null){
                    const pct = data.rating * 10;
                    ratingContent.innerHTML = ''+
                        '<div style="display:flex;align-items:center;gap:12px">'+
                            '<div style="flex:1">'+
                                '<div style="position:relative;background:rgba(200,195,170,0.1);height:14px;border-radius:0;overflow:hidden;border:1px solid rgba(200,195,170,0.15)">'+
                                    '<div style="position:absolute;inset:0;pointer-events:none;z-index:3;background-image:linear-gradient(to right,rgba(200,195,170,0.15) 1px, transparent 1px);background-size:10% 100%;background-repeat:repeat-x;opacity:0.9"></div>'+
                                    '<div style="position:relative;z-index:2;height:100%;width:'+pct+'%;background:'+data.bar_color+';transition:width 420ms ease;border-radius:0"></div>'+
                                '</div>'+
                                '<div style="display:flex;justify-content:space-between;margin-top:6px;color:var(--muted);font-size:12px">'+
                                    '<span>1</span><span>5</span><span>10</span>'+
                                '</div>'+
                            '</div>'+
                            '<div style="min-width:84px;text-align:center">'+
                                '<div style="font-weight:700;font-size:18px">'+data.rating+'</div>'+
                                '<div style="color:var(--muted);font-size:12px">/ 10</div>'+
                            '</div>'+
                        '</div>';
                } else {
                    ratingContent.innerHTML = ''+
                        '<div style="display:flex;align-items:center;gap:12px">'+
                            '<div style="flex:1;display:flex;align-items:center;gap:12px">'+
                                '<div style="min-width:84px;height:38px;border-radius:8px;background:rgba(255,255,255,0.03);display:flex;align-items:center;justify-content:center;font-weight:700;color:var(--muted);font-size:16px">N/A</div>'+
                                '<div style="color:var(--muted);font-size:14px">Unable to provide an accuracy report. Please try again.</div>'+
                            '</div>'+
                        '</div>';
                }
                // Update sources
                const sourcesList = document.getElementById('sourcesList');
                sourcesList.innerHTML = '';
                if(data.sources && data.sources.length > 0){
                    data.sources.forEach(function(s){
                        const li = document.createElement('li');
                        if(s.url && s.url.startsWith('http')){
                            const a = document.createElement('a');
                            a.href = s.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
                            const nameSpan = document.createElement('span');
                            nameSpan.className = 'source-name'; nameSpan.textContent = s.name || s.url;
                            a.appendChild(nameSpan);
                            if(s.url && s.name){ const urlSpan = document.createElement('span'); urlSpan.className = 'source-url'; urlSpan.textContent = s.url; a.appendChild(urlSpan); }
                            li.appendChild(a);
                        } else {
                            const span = document.createElement('span'); span.className = 'source-name'; span.textContent = s.name; li.appendChild(span);
                        }
                        sourcesList.appendChild(li);
                    });
                } else {
                    sourcesList.innerHTML = '<li class="no-sources" style="padding:6px 0">No sources available for this analysis.</li>';
                }
                // Exit edit mode
                toggleEdit();
            } catch(err){
                alert('Re-analysis failed: ' + err.message);
            } finally {
                reanalyzeBtn.disabled = false;
                reanalyzeBtnText.textContent = 'Re-analyze';
            }
        }
    </script>
    <div class="page-footer"><a href="/" class="footer-logo">InfoBait</a></div>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML_PAGE)

BIBI_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Leader Chat</title>
<link href="https://fonts.googleapis.com/css2?family=Frank+Ruhl+Libre:wght@400;700;900&family=Assistant:wght@400;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;font-family:'Assistant','Segoe UI',sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;transition:background .5s ease}
body.bibi-mode{background:linear-gradient(135deg,#0038b8 0%,#0038b8 40%,#fff 40%,#fff 60%,#0038b8 60%,#0038b8 100%)}
body.trump-mode{background:linear-gradient(135deg,#b22234 0%,#b22234 33%,#fff 33%,#fff 50%,#3c3b6e 50%,#3c3b6e 100%)}
.chat-container{width:100%;max-width:640px;margin:24px auto;background:#fff;border-radius:12px;box-shadow:0 8px 40px rgba(0,0,0,0.3);overflow:hidden;display:flex;flex-direction:column;height:85vh}
.chat-header{padding:20px 24px;display:flex;align-items:center;gap:16px;position:relative;transition:background .4s ease,border-color .4s ease}
.bibi-mode .chat-header{background:linear-gradient(135deg,#0038b8,#002d8f);border-bottom:4px solid #f4c430}
.trump-mode .chat-header{background:linear-gradient(135deg,#b22234,#8b1a2b);border-bottom:4px solid #f4c430}
.chat-avatar{width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:28px;flex-shrink:0;border:3px solid #fff;transition:background .4s ease}
.bibi-mode .chat-avatar{background:#f4c430}
.trump-mode .chat-avatar{background:#f4c430}
.chat-header-text h1{font-family:'Frank Ruhl Libre',Georgia,serif;color:#fff;font-size:22px;font-weight:900;margin-bottom:2px}
.chat-header-text p{color:rgba(255,255,255,0.7);font-size:13px}
.header-symbol{position:absolute;right:20px;top:50%;transform:translateY(-50%);font-size:32px;color:rgba(255,255,255,0.15)}
.messages{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:12px;background:#f8f9fc}
.msg{max-width:80%;padding:12px 16px;border-radius:12px;font-size:14px;line-height:1.6;animation:msgIn .3s ease-out}
@keyframes msgIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.msg.bot{align-self:flex-start;border-bottom-left-radius:4px;transition:background .3s ease,border-color .3s ease}
.bibi-mode .msg.bot{background:linear-gradient(135deg,#e8ecf8,#dce3f5);color:#1a1a2e;border:1px solid rgba(0,56,184,0.1)}
.trump-mode .msg.bot{background:linear-gradient(135deg,#fce8e8,#f5dcdc);color:#1a1a2e;border:1px solid rgba(178,34,52,0.1)}
.msg.user{align-self:flex-end;border-bottom-right-radius:4px;color:#fff;transition:background .3s ease}
.bibi-mode .msg.user{background:linear-gradient(135deg,#0038b8,#0045d4)}
.trump-mode .msg.user{background:linear-gradient(135deg,#b22234,#d42a3f)}
.msg.bot .sender{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;transition:color .3s ease}
.bibi-mode .msg.bot .sender{color:#0038b8}
.trump-mode .msg.bot .sender{color:#b22234}
.bibi-mode .msg.bot .sender::before{content:'\\2721 ';font-size:11px}
.trump-mode .msg.bot .sender::before{content:'\\2605 ';font-size:11px}
.input-area{padding:16px 20px;background:#fff;border-top:2px solid #e8ecf5;display:flex;gap:10px;align-items:center}
.input-area input{flex:1;padding:12px 16px;border:2px solid #dce3f5;border-radius:8px;font-size:14px;font-family:'Assistant',sans-serif;outline:none;transition:border .2s}
.bibi-mode .input-area input:focus{border-color:#0038b8}
.trump-mode .input-area input:focus{border-color:#b22234}
.input-area button{padding:12px 20px;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;font-family:'Assistant',sans-serif;transition:all .3s;letter-spacing:0.5px}
.bibi-mode .input-area button{background:linear-gradient(135deg,#0038b8,#0045d4)}
.bibi-mode .input-area button:hover{background:linear-gradient(135deg,#002d8f,#0038b8);transform:translateY(-1px);box-shadow:0 2px 8px rgba(0,56,184,0.3)}
.trump-mode .input-area button{background:linear-gradient(135deg,#b22234,#d42a3f)}
.trump-mode .input-area button:hover{background:linear-gradient(135deg,#8b1a2b,#b22234);transform:translateY(-1px);box-shadow:0 2px 8px rgba(178,34,52,0.3)}
.input-area button:disabled{opacity:.5;cursor:not-allowed;transform:none}
.typing{display:flex;gap:4px;padding:8px 0}
.typing span{width:6px;height:6px;border-radius:50%;animation:bounce .6s infinite alternate;transition:background .3s ease}
.bibi-mode .typing span{background:#0038b8}
.trump-mode .typing span{background:#b22234}
.typing span:nth-child(2){animation-delay:.2s}
.typing span:nth-child(3){animation-delay:.4s}
@keyframes bounce{to{transform:translateY(-6px);opacity:.4}}
.back-link{position:fixed;top:16px;left:16px;color:#fff;text-decoration:none;font-weight:700;font-size:14px;background:rgba(0,0,0,0.25);padding:8px 14px;border-radius:6px;backdrop-filter:blur(4px);transition:background .2s}
.back-link:hover{background:rgba(0,0,0,0.4)}
.welcome-flag{text-align:center;padding:8px;font-size:11px;color:#8a8fa8;letter-spacing:1px}
.char-toggle{position:fixed;top:16px;right:16px;display:flex;align-items:center;gap:8px;background:rgba(0,0,0,0.35);padding:6px 14px;border-radius:8px;backdrop-filter:blur(4px);z-index:10}
.char-toggle label{color:#fff;font-size:12px;font-weight:700;letter-spacing:0.5px;cursor:pointer;padding:6px 12px;border-radius:6px;transition:all .25s ease;border:2px solid transparent}
.char-toggle label.active{background:rgba(255,255,255,0.2);border-color:rgba(255,255,255,0.4)}
.char-toggle label:hover{background:rgba(255,255,255,0.1)}
</style>
</head>
<body class="bibi-mode">
<a href="/" class="back-link">&larr; Back to InfoBait</a>
<div class="char-toggle">
    <label id="bibLabel" class="active" onclick="switchCharacter('bibi')">&#x1F1EE;&#x1F1F1; Bibi</label>
    <label id="trumpLabel" onclick="switchCharacter('trump')">&#x1F1FA;&#x1F1F8; Trump</label>
</div>
<div class="chat-container">
    <div class="chat-header" id="chatHeader">
        <div class="chat-avatar" id="chatAvatar">&#x1F1EE;&#x1F1F1;</div>
        <div class="chat-header-text">
            <h1 id="chatTitle">BIBI Chat</h1>
            <p id="chatSubtitle">Prime Minister of Israel &bull; AI Simulation</p>
        </div>
        <div class="header-symbol" id="headerSymbol">&#x2721;</div>
    </div>
    <div class="messages" id="messages">
        <div class="welcome-flag" id="welcomeFlag">&#x1F1EE;&#x1F1F1; Shalom! This is an AI simulation for entertainment purposes only. &#x1F1EE;&#x1F1F1;</div>
        <div class="msg bot"><div class="sender">Bibi Netanyahu</div>Shalom! I am Benjamin Netanyahu. Ask me anything about Israel, politics, security, or the Middle East. I am always happy to talk.</div>
    </div>
    <div class="input-area">
        <input type="text" id="userInput" placeholder="Type your message..." autocomplete="off">
        <button id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
</div>
<script>
var chatHistory = [];
var input = document.getElementById('userInput');
var msgs = document.getElementById('messages');
var btn = document.getElementById('sendBtn');
var currentChar = 'bibi';

var charConfig = {
    bibi: {
        name: 'Bibi Netanyahu',
        title: 'BIBI Chat',
        subtitle: 'Prime Minister of Israel \\u2022 AI Simulation',
        avatar: '\\ud83c\\uddee\\ud83c\\uddf1',
        symbol: '\\u2721',
        welcome: '\\ud83c\\uddee\\ud83c\\uddf1 Shalom! This is an AI simulation for entertainment purposes only. \\ud83c\\uddee\\ud83c\\uddf1',
        greeting: 'Shalom! I am Benjamin Netanyahu. Ask me anything about Israel, politics, security, or the Middle East. I am always happy to talk.',
        bodyClass: 'bibi-mode'
    },
    trump: {
        name: 'Donald Trump',
        title: 'TRUMP Chat',
        subtitle: 'President of the United States \\u2022 AI Simulation',
        avatar: '\\ud83c\\uddfa\\ud83c\\uddf8',
        symbol: '\\u2605',
        welcome: '\\ud83c\\uddfa\\ud83c\\uddf8 Welcome! This is an AI simulation for entertainment purposes only. \\ud83c\\uddfa\\ud83c\\uddf8',
        greeting: 'Hello, tremendous to meet you! I am Donald Trump, the greatest president ever. Ask me anything about America, deals, winning, or Making America Great Again. Believe me!',
        bodyClass: 'trump-mode'
    }
};

function switchCharacter(char){
    if(char === currentChar) return;
    currentChar = char;
    var cfg = charConfig[char];
    document.body.className = cfg.bodyClass;
    document.getElementById('chatTitle').textContent = cfg.title;
    document.getElementById('chatSubtitle').innerHTML = cfg.subtitle;
    document.getElementById('chatAvatar').innerHTML = cfg.avatar;
    document.getElementById('headerSymbol').innerHTML = cfg.symbol;
    document.getElementById('bibLabel').className = char==='bibi'?'active':'';
    document.getElementById('trumpLabel').className = char==='trump'?'active':'';
    // Clear chat and reset
    chatHistory = [];
    msgs.innerHTML = '<div class="welcome-flag" id="welcomeFlag">'+cfg.welcome+'</div>' +
        '<div class="msg bot"><div class="sender">'+cfg.name+'</div>'+cfg.greeting+'</div>';
    document.title = cfg.title;
}

input.addEventListener('keydown', function(e){ if(e.key==='Enter'&&!btn.disabled) sendMessage(); });

function addMsg(text, cls, sender){
    var d = document.createElement('div');
    d.className = 'msg '+cls;
    if(sender) d.innerHTML = '<div class="sender">'+sender+'</div>'+text;
    else d.textContent = text;
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
}

function showTyping(){
    var cfg = charConfig[currentChar];
    var d = document.createElement('div');
    d.className = 'msg bot';
    d.id = 'typing';
    d.innerHTML = '<div class="sender">'+cfg.name+'</div><div class="typing"><span></span><span></span><span></span></div>';
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
}

function removeTyping(){
    var t = document.getElementById('typing');
    if(t) t.remove();
}

function sendMessage(){
    var text = input.value.trim();
    if(!text) return;
    addMsg(text, 'user');
    input.value = '';
    btn.disabled = true;
    chatHistory.push({role:'user', text:text});
    showTyping();
    var cfg = charConfig[currentChar];

    fetch('/bibi-chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:text, history:chatHistory, character:currentChar})
    })
    .then(function(r){return r.json()})
    .then(function(data){
        removeTyping();
        addMsg(data.reply, 'bot', cfg.name);
        chatHistory.push({role:'bot', text:data.reply});
        btn.disabled = false;
        input.focus();
    })
    .catch(function(){
        removeTyping();
        addMsg('Connection error. Please try again.', 'bot', 'System');
        btn.disabled = false;
    });
}
</script>
</body>
</html>
"""

@app.route("/bibi")
def bibi_page():
    return render_template_string(BIBI_PAGE)

@app.route("/bibi-chat", methods=["POST"])
def bibi_chat():
    data = request.get_json()
    user_msg = data.get("message", "")
    chat_history = data.get("history", [])
    character = data.get("character", "bibi")

    # Character-specific system prompts
    if character == "trump":
        system_prompt = (
            "You are roleplaying as Donald J. Trump, President of the United States. "
            "Stay in character at all times. Speak with supreme confidence, use superlatives constantly. "
            "Say things are 'tremendous', 'the best', 'like nobody has ever seen before'. "
            "Reference your deal-making skills, your presidency, Making America Great Again, and winning. "
            "Occasionally say 'Believe me', 'Many people are saying', 'Everybody knows it'. "
            "Keep responses conversational and 2-4 sentences. This is for entertainment only."
        )
        char_label = "Trump"
        error_reply = "Look, we're having some technical difficulties, okay? Even the greatest president has a bad day. Tremendous. Try again, believe me!"
    else:
        system_prompt = (
            "You are roleplaying as Benjamin 'Bibi' Netanyahu, Prime Minister of Israel. "
            "Stay in character at all times. Speak with confidence, authority, and occasional humor. "
            "Reference your long political career, Israel's security, innovation, and strength. "
            "Occasionally use Hebrew phrases like 'Shalom', 'Toda raba', 'Am Yisrael Chai'. "
            "Keep responses conversational and 2-4 sentences. This is for entertainment only."
        )
        char_label = "Bibi"
        error_reply = "Shalom, my friend. I seem to be having technical difficulties. Even prime ministers have bad days! Please try again."

    messages_for_api = system_prompt + "\\n\\nConversation so far:\\n"
    for h in chat_history[-10:]:
        role = "User" if h["role"] == "user" else char_label
        messages_for_api += f"{role}: {h['text']}\\n"
    messages_for_api += f"User: {user_msg}\\n{char_label}:"

    try:
        response = co.chat(
            model=COHERE_MODEL,
            message=messages_for_api,
            max_tokens=200,
        )
        reply = response.text.strip()
    except Exception as e:
        reply = error_reply

    return {"reply": reply}

@app.route("/reanalyze", methods=["POST"])
def reanalyze():
    """Re-run AI analysis with user-edited extracted text."""
    data = request.get_json()
    if not data or 'extracted_text' not in data:
        return {"error": "No text provided"}, 400

    extracted_text = data['extracted_text'].strip()
    image_b64 = data.get('image_b64', '')
    mime = data.get('mime', 'image/png')
    filename = data.get('filename', 'unknown')

    if not extracted_text:
        return {"error": "Text cannot be empty"}, 400

    # Step 1: AI Analysis
    try:
        analysis_prompt = (
            "You are a fact-check assistant.\n"
            "Analyze the following text for factual accuracy.\n"
            "Instructions:\n"
            "1) Provide a clear, concise analysis explaining whether the claim(s) are accurate, misleading, or false.\n"
            "2) Focus only on factual accuracy \u2014 do NOT mention grammar, spelling, punctuation, or style.\n"
            "3) Be explicit about your conclusion: clearly state whether the statement is 'accurate', 'mostly accurate', "
            "'partially true', 'misleading', 'mostly false', or 'false'.\n"
            "4) Keep your analysis brief but informative (2-4 sentences).\n"
            "5) Write in clear, coherent, and grammatically correct English. Use complete sentences with proper punctuation.\n"
            "6) Do NOT use asterisks (*) anywhere in your response. No bold, no bullet markers with asterisks, no emphasis with asterisks.\n"
            "7) After your analysis, output a blank line, then 'SOURCES:' on its own line, followed by 2-4 credible reference sources "
            "that support your fact-check. Each source on its own line in this format: '- Source Title | https://example.com/page'\n"
            "   Only cite real, well-known sources (e.g., Reuters, AP News, BBC, Wikipedia, WHO, CDC, official .gov sites, major newspapers). "
            "Do NOT invent URLs.\n\n"
            f"Text to evaluate:\n{extracted_text}"
        )
        response = co.chat(model=COHERE_MODEL, message=analysis_prompt, max_tokens=350)
        ai_output = response.text.strip()
    except Exception as e:
        ai_output = f"AI Error: {e}"

    # Strip any asterisks the AI might have included
    ai_output = ai_output.replace('*', '')
    ai_analysis_display = ai_output

    # Step 2: Derive rating from analysis sentiment
    analysis_for_rating = ai_analysis_display
    if 'SOURCES:' in analysis_for_rating:
        analysis_for_rating = analysis_for_rating.split('SOURCES:', 1)[0].strip()

    def derive_rating_from_analysis(analysis_text: str):
        if not analysis_text or analysis_text.startswith('AI Error:'):
            return None
        try:
            rating_prompt = (
                "You are a strict accuracy scoring system. Read the fact-check analysis below and output "
                "a single accuracy score from 1 to 10.\n\n"
                "CRITICAL RULES — you must follow these exactly:\n"
                "1. Look for the conclusion keyword in the analysis (e.g. 'false', 'accurate', 'misleading', etc.)\n"
                "2. If the analysis concludes the statement is FALSE, FABRICATED, DEBUNKED, INCORRECT, or COMPLETELY WRONG, "
                "you MUST output 1 or 2. Never output higher than 2 for false statements.\n"
                "3. If the analysis says MISLEADING, EXAGGERATED, LACKS CONTEXT, MOSTLY FALSE, or MOSTLY INACCURATE, output 3 or 4.\n"
                "4. If the analysis says PARTIALLY TRUE, MIXED, or has significant caveats, output 5 or 6.\n"
                "5. If the analysis says MOSTLY ACCURATE or LARGELY TRUE with only minor issues, output 7 or 8.\n"
                "6. If the analysis says TRUE, ACCURATE, CORRECT, VERIFIED, or CONFIRMED with no caveats, output 9 or 10.\n"
                "7. If the analysis cannot determine accuracy or says INSUFFICIENT INFO, output N/A.\n\n"
                "IMPORTANT: A score of 9-10 should be RARE — only for clearly verified true statements. "
                "When in doubt, score LOWER rather than higher.\n\n"
                "Output ONLY the integer (1-10) or 'N/A'. Nothing else.\n\n"
                f"Fact-check analysis:\n{analysis_text}"
            )
            resp = co.chat(model=COHERE_MODEL, message=rating_prompt, max_tokens=10)
            result = resp.text.strip().splitlines()[0].strip()
            if result.upper() == 'N/A':
                return None
            m = re.match(r'^([1-9]|10)\b', result)
            if m:
                score = int(m.group(1))
                # Sanity check: if analysis text contains strong "false" keywords, cap the score
                lower_analysis = analysis_text.lower()
                false_keywords = ['false', 'fabricated', 'debunked', 'completely wrong', 'incorrect', 'not true', 'no evidence']
                misleading_keywords = ['misleading', 'exaggerated', 'lacks context', 'mostly false', 'mostly inaccurate', 'unsubstantiated']
                if any(kw in lower_analysis for kw in false_keywords) and score > 3:
                    score = 2
                elif any(kw in lower_analysis for kw in misleading_keywords) and score > 5:
                    score = 4
                return max(1, min(10, score))
            return None
        except Exception as e:
            print(f"Rating derivation error: {e}")
            return None

    rating = derive_rating_from_analysis(analysis_for_rating)
    rating_percent = (rating * 10) if rating is not None else 0

    # Parse sources
    sources_list = []
    if 'SOURCES:' in ai_analysis_display:
        parts = ai_analysis_display.split('SOURCES:', 1)
        ai_analysis_display = parts[0].strip()
        sources_raw = parts[1].strip()
        for line in sources_raw.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                line = line[2:].strip()
            if not line or line.upper() == 'SOURCES:':
                continue
            if '|' in line:
                name, url = line.split('|', 1)
                name = name.strip()
                url = url.strip()
                if name:
                    sources_list.append({'name': name, 'url': url})
            elif line.startswith('http'):
                sources_list.append({'name': line, 'url': line})
            elif line:
                sources_list.append({'name': line, 'url': ''})

    def compute_bar_color(percent: int):
        try:
            p = int(percent)
        except Exception:
            return None
        if p <= 0:
            return None
        if p <= 50:
            ratio = p / 50.0
            r, g, b = 255, round(255 * ratio), 0
        else:
            ratio = (p - 50) / 50.0
            r, g, b = round(255 * (1 - ratio)), round(255 - 55 * ratio), 0
        return f"#{r:02x}{g:02x}{b:02x}"

    bar_color = compute_bar_color(rating_percent) or 'var(--accent)'

    return {
        'ai_output': ai_analysis_display,
        'rating': rating,
        'rating_percent': rating_percent,
        'bar_color': bar_color,
        'sources': sources_list
    }

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
    # Cohere Chat API — Step 1: Get AI Analysis
    # ----------------------------
    try:
        analysis_prompt = (
            "You are a fact-check assistant.\n"
            "Analyze the following text for factual accuracy.\n"
            "Instructions:\n"
            "1) Provide a clear, concise analysis explaining whether the claim(s) are accurate, misleading, or false.\n"
            "2) Focus only on factual accuracy — do NOT mention grammar, spelling, punctuation, or style.\n"
            "3) Be explicit about your conclusion: clearly state whether the statement is 'accurate', 'mostly accurate', "
            "'partially true', 'misleading', 'mostly false', or 'false'.\n"
            "4) Keep your analysis brief but informative (2-4 sentences).\n"
            "5) Write in clear, coherent, and grammatically correct English. Use complete sentences with proper punctuation.\n"
            "6) Do NOT use asterisks (*) anywhere in your response. No bold, no bullet markers with asterisks, no emphasis with asterisks.\n"
            "7) After your analysis, output a blank line, then 'SOURCES:' on its own line, followed by 2-4 credible reference sources "
            "that support your fact-check. Each source on its own line in this format: '- Source Title | https://example.com/page'\n"
            "   Only cite real, well-known sources (e.g., Reuters, AP News, BBC, Wikipedia, WHO, CDC, official .gov sites, major newspapers). "
            "Do NOT invent URLs.\n\n"
            f"Text to evaluate:\n{extracted_text}"
        )

        response = co.chat(
            model=COHERE_MODEL,
            message=analysis_prompt,
            max_tokens=350
        )

        ai_output = response.text.strip()
    except Exception as e:
        ai_output = f"AI Error: {e}"

    # Strip any asterisks the AI might have included
    ai_output = ai_output.replace('*', '')
    ai_analysis_display = ai_output

    # ----------------------------
    # Cohere Chat API — Step 2: Derive Accuracy Rating from Analysis Sentiment
    # ----------------------------
    # Strip sources from display text before sending to rating prompt
    analysis_for_rating = ai_analysis_display
    if 'SOURCES:' in analysis_for_rating:
        analysis_for_rating = analysis_for_rating.split('SOURCES:', 1)[0].strip()

    def derive_rating_from_analysis(analysis_text: str):
        """Send the AI analysis to a second Cohere call that scores it 1-10
        based on the sentiment/conclusion of the analysis."""
        if not analysis_text or analysis_text.startswith('AI Error:'):
            return None
        try:
            rating_prompt = (
                "You are a strict accuracy scoring system. Read the fact-check analysis below and output "
                "a single accuracy score from 1 to 10.\n\n"
                "CRITICAL RULES — you must follow these exactly:\n"
                "1. Look for the conclusion keyword in the analysis (e.g. 'false', 'accurate', 'misleading', etc.)\n"
                "2. If the analysis concludes the statement is FALSE, FABRICATED, DEBUNKED, INCORRECT, or COMPLETELY WRONG, "
                "you MUST output 1 or 2. Never output higher than 2 for false statements.\n"
                "3. If the analysis says MISLEADING, EXAGGERATED, LACKS CONTEXT, MOSTLY FALSE, or MOSTLY INACCURATE, output 3 or 4.\n"
                "4. If the analysis says PARTIALLY TRUE, MIXED, or has significant caveats, output 5 or 6.\n"
                "5. If the analysis says MOSTLY ACCURATE or LARGELY TRUE with only minor issues, output 7 or 8.\n"
                "6. If the analysis says TRUE, ACCURATE, CORRECT, VERIFIED, or CONFIRMED with no caveats, output 9 or 10.\n"
                "7. If the analysis cannot determine accuracy or says INSUFFICIENT INFO, output N/A.\n\n"
                "IMPORTANT: A score of 9-10 should be RARE — only for clearly verified true statements. "
                "When in doubt, score LOWER rather than higher.\n\n"
                "Output ONLY the integer (1-10) or 'N/A'. Nothing else.\n\n"
                f"Fact-check analysis:\n{analysis_text}"
            )
            resp = co.chat(
                model=COHERE_MODEL,
                message=rating_prompt,
                max_tokens=10
            )
            result = resp.text.strip().splitlines()[0].strip()
            if result.upper() == 'N/A':
                return None
            m = re.match(r'^([1-9]|10)\b', result)
            if m:
                score = int(m.group(1))
                # Sanity check: if analysis text contains strong "false" keywords, cap the score
                lower_analysis = analysis_text.lower()
                false_keywords = ['false', 'fabricated', 'debunked', 'completely wrong', 'incorrect', 'not true', 'no evidence']
                misleading_keywords = ['misleading', 'exaggerated', 'lacks context', 'mostly false', 'mostly inaccurate', 'unsubstantiated']
                if any(kw in lower_analysis for kw in false_keywords) and score > 3:
                    score = 2
                elif any(kw in lower_analysis for kw in misleading_keywords) and score > 5:
                    score = 4
                return max(1, min(10, score))
            return None
        except Exception as e:
            print(f"Rating derivation error: {e}")
            return None

    rating = derive_rating_from_analysis(analysis_for_rating)
    rating_percent = (rating * 10) if rating is not None else 0

    # Parse sources from AI output (format: SOURCES:\n- Title | URL)
    sources_list = []
    if 'SOURCES:' in ai_analysis_display:
        parts = ai_analysis_display.split('SOURCES:', 1)
        ai_analysis_display = parts[0].strip()
        sources_raw = parts[1].strip()
        for line in sources_raw.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                line = line[2:].strip()
            if not line or line.upper() == 'SOURCES:':
                continue
            if '|' in line:
                name, url = line.split('|', 1)
                name = name.strip()
                url = url.strip()
                if name:
                    sources_list.append({'name': name, 'url': url})
            elif line.startswith('http'):
                sources_list.append({'name': line, 'url': line})
            elif line:
                sources_list.append({'name': line, 'url': ''})
    sources_json = json.dumps(sources_list)

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

    bar_color = compute_bar_color(rating_percent) or 'var(--accent)'
    # embed uploaded image as base64 for preview in result page
    try:
        image_b64 = base64.b64encode(file_bytes).decode("ascii")
    except Exception:
        image_b64 = ""
    mime = getattr(file, 'content_type', 'image/png') or 'image/png'

    return render_template_string(RESULT_PAGE, extracted_text=extracted_text, ai_output=ai_analysis_display, image_b64=image_b64, mime=mime, filename=file.filename, rating=rating, rating_percent=rating_percent, bar_color=bar_color, sources=sources_json)

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
