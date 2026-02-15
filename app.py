#Flask File

from flask import Flask, request, render_template_string
import os
from PIL import Image
import pytesseract

# Tell pytesseract where the Tesseract engine is
pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"

app = Flask(__name__)

# Folder to store uploaded images
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# HTML upload page
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

    # Save the uploaded file
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    # Extract text using OCR
    extracted_text = pytesseract.image_to_string(Image.open(filepath))

    return f"""
    <h3>Upload Successful!</h3>
    <p><strong>Extracted Text:</strong></p>
    <pre>{extracted_text}</pre>
    <br>
    <a href="/">Upload another file</a>
    """

if __name__ == "__main__":
    # Run on port 5001 to avoid conflicts
    app.run(host="0.0.0.0", port=5001, debug=True)
