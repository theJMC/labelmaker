#!/usr/bin/env python3
"""
app.py — quick webserver for generate_labels.py

Upload a spreadsheet (.xlsx or .csv), pick a label preset, and download
the generated A4 label sheet as a PDF.

Run:
    pip install flask
    python app.py

Then open http://localhost:5000 in a browser.
"""

import io
import os
import tempfile

from flask import Flask, request, render_template_string, send_file, flash, redirect, url_for

from generate_labels import (
    read_spreadsheet,
    generate_pdf,
    PRESETS,
    DEFAULT_COLS,
    DEFAULT_ROWS,
)

app = Flask(__name__)
app.secret_key = "dev"  # only needed for flash messages; fine for local/dev use

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Label PDF Generator</title>
  <style>
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 560px; margin: 60px auto; color: #222; }
    h1 { font-size: 1.4rem; }
    form { border: 1px solid #ddd; border-radius: 8px; padding: 24px; margin-top: 24px; }
    label { display: block; margin-top: 16px; margin-bottom: 4px; font-weight: 600; font-size: 0.9rem; }
    select, input[type=file], input[type=number] { width: 100%; padding: 8px; box-sizing: border-box; font-size: 0.95rem; }
    .row { display: flex; gap: 16px; }
    .row > div { flex: 1; }
    button { margin-top: 24px; padding: 10px 20px; font-size: 1rem; background: #1a73e8; color: white; border: none; border-radius: 6px; cursor: pointer; }
    button:hover { background: #1558b0; }
    .flash { background: #fdecea; color: #d93025; padding: 10px 14px; border-radius: 6px; margin-top: 16px; }
    .hint { color: #666; font-size: 0.85rem; margin-top: 4px; }
  </style>
</head>
<body>
  <h1>Name Label PDF Generator</h1>
  <p>Upload a spreadsheet with columns <code>name</code>, <code>group</code>, <code>position 1</code>, <code>position 2</code>.</p>

  {% with messages = get_flashed_messages() %}
    {% if messages %}
      {% for m in messages %}<div class="flash">{{ m }}</div>{% endfor %}
    {% endif %}
  {% endwith %}

  <form action="/generate" method="post" enctype="multipart/form-data">
    <label for="file">Spreadsheet (.xlsx or .csv)</label>
    <input type="file" id="file" name="file" accept=".xlsx,.xls,.csv" required>

    <label for="preset">Label sheet</label>
    <select id="preset" name="preset" onchange="toggleCustom()">
      {% for key in presets %}
        <option value="{{ key }}">{{ key }}</option>
      {% endfor %}
      <option value="__custom__">Custom grid...</option>
    </select>

    <div id="custom-fields" style="display:none;">
      <div class="row">
        <div>
          <label for="cols">Columns</label>
          <input type="number" id="cols" name="cols" min="1" value="{{ default_cols }}">
        </div>
        <div>
          <label for="rows">Rows</label>
          <input type="number" id="rows" name="rows" min="1" value="{{ default_rows }}">
        </div>
      </div>
      <p class="hint">Custom grid divides the A4 page evenly (no exact label dimensions).</p>
    </div>

    <button type="submit">Generate PDF</button>
  </form>

  <script>
    function toggleCustom() {
      var v = document.getElementById('preset').value;
      document.getElementById('custom-fields').style.display = (v === '__custom__') ? 'block' : 'none';
    }
  </script>
</body>
</html>
"""


def allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template_string(
        PAGE_TEMPLATE,
        presets=sorted(PRESETS.keys()),
        default_cols=DEFAULT_COLS,
        default_rows=DEFAULT_ROWS,
    )


@app.route("/generate", methods=["POST"])
def generate():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Please choose a spreadsheet file to upload.")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("Unsupported file type. Please upload a .xlsx or .csv file.")
        return redirect(url_for("index"))

    # Save the upload to a temp file so pandas can read it by path/extension.
    suffix = os.path.splitext(file.filename)[1].lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        try:
            records = read_spreadsheet(tmp_path)
        except Exception as e:
            flash(f"Couldn't read spreadsheet: {e}")
            return redirect(url_for("index"))

        if not records:
            flash("No rows found in that spreadsheet.")
            return redirect(url_for("index"))

        preset_key = request.form.get("preset")
        if preset_key and preset_key != "__custom__" and preset_key in PRESETS:
            p = PRESETS[preset_key]
            cols, rows = p["cols"], p["rows"]
            label_w, label_h = p["label_w"], p["label_h"]
        else:
            cols = int(request.form.get("cols") or DEFAULT_COLS)
            rows = int(request.form.get("rows") or DEFAULT_ROWS)
            label_w = label_h = None

        pdf_buffer = io.BytesIO()
        # generate_pdf writes to a path; use a second temp file for the output.
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as out_tmp:
            out_path = out_tmp.name

        generate_pdf(records, out_path, cols=cols, rows=rows, label_w=label_w, label_h=label_h)

        with open(out_path, "rb") as f:
            pdf_buffer.write(f.read())
        pdf_buffer.seek(0)
        os.remove(out_path)

        download_name = os.path.splitext(os.path.basename(file.filename))[0] + "_labels.pdf"
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_name,
        )
    finally:
        os.remove(tmp_path)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)