#Flask File

from flask import Flask, request, render_template_string
import os

app = Flask(__name__)

# Create uploads folder if it doesn't exist
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Simple HTML page
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

    # Save file
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    return f"""
    <h3>Upload Successful!</h3>
    <p>File saved as: {file.filename}</p>
    <a href="/">Upload another file</a>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

