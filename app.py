#Flask File

from flask import Flask, request, render_template_string
import os
from PIL import Image
import pytesseract
import cohere

app = Flask(__name__)

# ----------------------------
# Cohere setup
# ----------------------------
COHERE_API_KEY = "F2ahifI4wPh18RvXrbQnEd17WlL8avVAJfl3HQ2d"  # Replace with your key
co = cohere.Client(COHERE_API_KEY)

# ----------------------------
# Tesseract setup (Mac)
# ----------------------------
pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"

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
<html>
<head>
    <title>Peacebait Upload</title>
</head>
<body>
    <h2>Peacebait Screenshot Upload</h2>

    <form action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="image" required>
        <button type="submit">Upload</button>
    </form>
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
            "You are a helpful assistant that only provides factual information. "
            "Do NOT hallucinate or make up content. "
            f"Analyze the following text and provide a concise summary or highlight key points:\n\n{extracted_text}"
        )

        response = co.chat(
            model="command-r-08-2024",
            message=prompt_text,
            max_tokens=150
        )

        ai_output = response.text.strip()
    except Exception as e:
        ai_output = f"AI Error: {e}"

    return f"""
    <h3>Upload Successful!</h3>
    <p><strong>Extracted Text:</strong></p>
    <pre>{extracted_text}</pre>
    <p><strong>AI Analysis:</strong></p>
    <pre>{ai_output}</pre>
    <br>
    <a href="/">Upload another file</a>
    """

if __name__ == "__main__":
    # Run on port 5001 to avoid conflicts
    app.run(host="0.0.0.0", port=5001, debug=True)
