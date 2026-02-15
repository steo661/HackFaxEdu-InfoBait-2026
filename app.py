#Flask File

from flask import Flask, request, render_template_string
import os
from PIL import Image
import pytesseract
import cohere
import base64
import platform

app = Flask(__name__)

# ----------------------------
# Cohere setup
# ----------------------------
COHERE_API_KEY = "F2ahifI4wPh18RvXrbQnEd17WlL8avVAJfl3HQ2d"  # Replace with your key
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
        html,body{height:100%;margin:0;background:linear-gradient(180deg,#060809 0%,var(--bg) 100%);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial;font-size:16px}
        .wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:36px}
        .card{width:100%;max-width:820px;background:linear-gradient(180deg,var(--card),#0d1319);border-radius:14px;padding:32px;box-shadow:0 8px 36px rgba(2,6,23,0.6);color:#e6eef6}
        h1{margin:0 0 12px;font-weight:600;font-size:22px}
        p.lead{margin:0 0 18px;color:var(--muted);font-size:14px}
        form{display:flex;gap:12px;align-items:center}
        .file-input{flex:1;display:flex;align-items:center;gap:12px;padding:12px 14px;background:var(--glass);border-radius:12px;border:1px solid rgba(255,255,255,0.04)}
        .file-input input[type=file]{background:transparent;color:inherit}
        .btn{background:var(--accent);border:none;color:white;padding:12px 16px;border-radius:12px;font-weight:600;cursor:pointer}
        .meta{margin-top:18px;display:flex;gap:16px;align-items:center}
        .preview{width:160px;height:120px;border-radius:10px;overflow:hidden;background:#091216;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.03)}
        .preview img{max-width:100%;max-height:100%;display:block}
        .note{color:var(--muted);font-size:13px}
        footer{margin-top:18px;color:var(--muted);font-size:12px;text-align:right}
        @media (max-width:520px){.card{padding:18px}.meta{flex-direction:column;align-items:flex-start}.preview{width:100%;height:auto}}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            <h1>Peacebait — Screenshot Analyzer</h1>
            <p class="lead">Upload a screenshot and get a concise analysis. We respect your privacy — files are processed locally or on your configured AI endpoint.</p>

            <form action="/upload" method="post" enctype="multipart/form-data">
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
    </script>
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
        html,body{height:100%;margin:0;background:linear-gradient(180deg,#060809 0%,var(--bg) 100%);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial;font-size:16px}
        .wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:36px}
        .card{width:100%;max-width:1100px;background:linear-gradient(180deg,var(--card),#0d1319);border-radius:14px;padding:28px;box-shadow:0 8px 36px rgba(2,6,23,0.6);color:#e6eef6}
        .row{display:flex;gap:20px;align-items:flex-start}
        .left{width:320px}
        .preview{width:100%;border-radius:10px;overflow:hidden;background:#091216;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.03);padding:12px}
        .preview img{max-width:100%;height:auto;display:block}
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
    # OCR Step
    # ----------------------------
    extracted_text = pytesseract.image_to_string(Image.open(filepath))

    # ----------------------------
    # Cohere Chat API (latest)
    # ----------------------------
    try:
        prompt_text = (
            "You are a helpful assistant that only provides factual information(you will not mention any grammatical errors). "
            "Do NOT hallucinate or make up content. "
            f"Analyze the following text and provide a TRUTHFUL rating from 1 to 10:\n\n{extracted_text}"
        )

        response = co.chat(
            model="command-r-08-2024",
            message=prompt_text,
            max_tokens=150
        )

        ai_output = response.text.strip()
    except Exception as e:
        ai_output = f"AI Error: {e}"
    # embed uploaded image as base64 for preview in result page
    try:
        with open(filepath, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception:
        image_b64 = ""
    mime = getattr(file, 'content_type', 'image/png') or 'image/png'

    return render_template_string(RESULT_PAGE, extracted_text=extracted_text, ai_output=ai_output, image_b64=image_b64, mime=mime, filename=file.filename)

if __name__ == "__main__":
    # Run on port 5001 to avoid conflicts
    app.run(host="0.0.0.0", port=5001, debug=True)
