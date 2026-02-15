#Flask File

from flask import Flask, request, render_template_string
import os
from PIL import Image
import pytesseract
import cohere
import base64
import platform
import re

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

# ----------------------------
# Upload folder
# ----------------------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Performance tunables
# Maximum image dimension (pixels). Images larger than this will be downscaled before OCR.
MAX_IMAGE_DIM = int(os.environ.get("MAX_IMAGE_DIM", "1200"))
# Tesseract config for faster OCR (OEM 1 = LSTM engine, PSM 3 = Fully automatic page segmentation)
TESSERACT_CONFIG = os.environ.get("TESSERACT_CONFIG", "--oem 1 --psm 3")

# ----------------------------
# HTML page
# ----------------------------
HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Upload — Peacebait</title>
    <style>
        :root{--bg:#0b0f12;--card:#0f1720;--muted:#9aa4ad;--accent:#7c5cff;--glass:rgba(255,255,255,0.03)}
        html,body{height:100%;margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial;font-size:16px}
        /* animated gradient background */
        body::before{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:linear-gradient(120deg,#06080a 0%,#071026 25%,#0b0f12 50%,#071026 75%,#05060a 100%);
            background-size:200% 200%;filter:blur(18px) saturate(1.05);
            animation:bgShift 18s linear infinite;
            opacity:0.98;
        }
        @keyframes bgShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
        .wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:36px}

        /* Animations */
        @keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(124,92,255,0.35); } 70% { box-shadow: 0 0 0 10px rgba(124,92,255,0); } 100% { box-shadow: 0 0 0 0 rgba(124,92,255,0); } }

        .card{width:100%;max-width:820px;background:linear-gradient(180deg,var(--card),#0d1319);border-radius:14px;padding:32px;box-shadow:0 8px 36px rgba(2,6,23,0.6);color:#e6eef6;animation:fadeUp .42s ease-out both}
        h1{margin:0 0 12px;font-weight:600;font-size:22px}
        p.lead{margin:0 0 18px;color:var(--muted);font-size:14px}
        form{display:flex;gap:12px;align-items:center}
        .file-input{flex:1;display:flex;align-items:center;gap:12px;padding:12px 14px;background:var(--glass);border-radius:12px;border:1px solid rgba(255,255,255,0.04);transition:box-shadow .18s ease,transform .12s ease}
        .file-input input[type=file]{background:transparent;color:inherit}
        .file-input:hover{box-shadow:0 6px 20px rgba(2,6,23,0.6);transform:translateY(-2px)}
        .btn{background:var(--accent);border:none;color:white;padding:12px 16px;border-radius:12px;font-weight:600;cursor:pointer;transition:transform .12s ease,box-shadow .12s ease}
        .btn:hover{transform:translateY(-3px);box-shadow:0 10px 30px rgba(124,92,255,0.12)}
        .btn:active{transform:translateY(-1px)}
        .meta{margin-top:18px;display:flex;gap:16px;align-items:center}
        .preview{width:160px;height:120px;border-radius:10px;overflow:hidden;background:#091216;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.03);transition:transform .18s ease,box-shadow .18s ease}
        .preview img{max-width:100%;max-height:100%;display:block;transition:transform .25s ease,filter .25s ease}
        .preview:hover{transform:translateY(-6px);box-shadow:0 18px 46px rgba(2,6,23,0.5)}
        .preview:hover img{transform:scale(1.04);filter:brightness(1.03)}
        .note{color:var(--muted);font-size:13px}
        footer{margin-top:18px;color:var(--muted);font-size:12px;text-align:right}
        @media (max-width:520px){.card{padding:18px}.meta{flex-direction:column;align-items:flex-start}.preview{width:100%;height:auto}}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            <h1>InfoBait — Screenshot Analyzer</h1>
            <p class="lead">Upload a screenshot and get a concise analysis. We respect your privacy — files are processed locally or on your configured AI endpoint.</p>

            <form action="/upload" method="post" enctype="multipart/form-data" onsubmit="handleSubmit(event)">
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
                    const form = e.target;
                    showLoader();
                    const start = Date.now();
                    try{
                        const data = new FormData(form);
                        const res = await fetch(form.action, { method: 'POST', body: data });
                        const text = await res.text();
                        const elapsed = Date.now() - start;
                        const min = 3000; // ensure loader visible at least 3 seconds
                        if(elapsed < min){
                            await new Promise(r => setTimeout(r, min - elapsed));
                        }
                        // Replace current document with response HTML
                        document.open();
                        document.write(text);
                        document.close();
                    }catch(err){
                        // On error, hide loader and re-enable button
                        const l = document.getElementById('loader');
                        if(l){ l.style.display = 'none'; }
                        const btn = document.querySelector('.btn');
                        if(btn){ btn.disabled = false; btn.textContent = btn.dataset.origText || 'Analyze'; }
                        alert('Upload failed: ' + err);
                    }
                    return false;
                }
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
    <title>Results — Peacebait</title>
    <style>
        :root{--bg:#0b0f12;--card:#0f1720;--muted:#9aa4ad;--accent:#7c5cff;--glass:rgba(255,255,255,0.03)}
        html,body{height:100%;margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial;font-size:16px}
        /* animated gradient background */
        body::before{
            content:"";
            position:fixed;inset:0;z-index:-1;
            background:linear-gradient(120deg,#05060a 0%,#071026 30%,#0b0f12 60%,#071026 90%);
            background-size:200% 200%;filter:blur(20px) saturate(1.05);
            animation:bgShift 18s linear infinite;
            opacity:0.98;
        }
        @keyframes bgShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
        .wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:36px}

        /* Animations */
        @keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .card{width:100%;max-width:1100px;background:linear-gradient(180deg,var(--card),#0d1319);border-radius:14px;padding:28px;box-shadow:0 8px 36px rgba(2,6,23,0.6);color:#e6eef6;animation:fadeUp .42s ease-out both}
        .row{display:flex;gap:20px;align-items:flex-start}
        .left{width:320px}
        .preview{width:100%;border-radius:10px;overflow:hidden;background:#091216;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.03);padding:12px;transition:transform .18s ease,box-shadow .18s ease}
        .preview img{max-width:100%;height:auto;display:block;transition:transform .25s ease,filter .25s ease}
        .preview:hover{transform:translateY(-6px);box-shadow:0 18px 46px rgba(2,6,23,0.5)}
        .preview:hover img{transform:scale(1.03);filter:brightness(1.02)}
        .right{flex:1}
        h1{margin:0 0 8px;font-weight:600;font-size:20px}
        .note{color:var(--muted);font-size:14px;margin-bottom:10px}
        .panel{background:rgba(255,255,255,0.02);padding:14px;border-radius:10px;border:1px solid rgba(255,255,255,0.03);color:#dce9f5;font-size:14px}
        pre{white-space:pre-wrap;word-break:break-word;margin:0;font-family:inherit}
        a.btn{display:inline-block;margin-top:14px;padding:8px 12px;border-radius:8px;background:transparent;border:1px solid rgba(255,255,255,0.04);color:var(--muted);text-decoration:none}
        @media (max-width:820px){.row{flex-direction:column}.left{width:100%}}
    </style>
</head>
<body>
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
                        <strong>Extracted Text</strong>
                        <pre>{{ extracted_text }}</pre>
                    </div>
                    <div style="height:12px"></div>
                    <div class="panel">
                        <strong>AI Analysis</strong>
                        <pre>{{ ai_output }}</pre>
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

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    # ----------------------------
    # OCR Step (preprocess image for speed)
    # ----------------------------
    def preprocess_image(path, max_dim=MAX_IMAGE_DIM):
        img = Image.open(path)
        # Keep original color mode (do NOT convert to grayscale).
        # Convert palette images to RGB for compatibility, but otherwise keep color as-is.
        if img.mode == 'P':
            img = img.convert("RGB")
        # downscale large images to speed up OCR while preserving aspect ratio
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        return img

    img = preprocess_image(filepath)
    extracted_text = pytesseract.image_to_string(img, config=TESSERACT_CONFIG)

    # ----------------------------
    # Cohere Chat API (latest)
    # ----------------------------
    try:
        prompt_text = (
            "You are a fact-check assistant.\n"
            "Instructions:\n"
            "1) On the FIRST line, output exactly one token: either an integer 1-10 (the truthfulness rating) or the token 'N/A' if you cannot provide a rating. Do NOT include any other text on this line.\n"
            "2) On the SECOND line, provide a single, short factual sentence (one line) explaining concisely why the claim is accurate or not.\n"
            "3) Do NOT mention grammatical errors, punctuation, spelling, or style — only assess factual accuracy.\n"
            "4) Keep the explanation strictly factual and brief (one sentence).\n\n"
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
        with open(filepath, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception:
        image_b64 = ""
    mime = getattr(file, 'content_type', 'image/png') or 'image/png'

    return render_template_string(RESULT_PAGE, extracted_text=extracted_text, ai_output=ai_output, image_b64=image_b64, mime=mime, filename=file.filename, rating=rating, rating_percent=rating_percent, bar_color=bar_color)

if __name__ == "__main__":
    # Run on port 5001 to avoid conflicts
    app.run(host="0.0.0.0", port=5001, debug=True)
