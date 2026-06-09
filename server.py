import os
import re
import base64
import mimetypes
import tempfile
import subprocess
from flask import Flask, request, Response, jsonify

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    return 'ok', 200


@app.route('/convert', methods=['POST'])
def convert():
    pdf_data = request.data
    if not pdf_data:
        return jsonify({'error': 'No PDF data in request body'}), 400

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, 'input.pdf')
        output_dir = os.path.join(tmpdir, 'output')
        os.makedirs(output_dir)

        with open(input_path, 'wb') as f:
            f.write(pdf_data)

        result = subprocess.run(
            ['opendataloader-pdf', input_path, '-o', output_dir, '--format', 'markdown'],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            return jsonify({'error': result.stderr or 'Conversion failed'}), 500

        files = os.listdir(output_dir)
        md_file = next((f for f in files if f.endswith('.md')), None)
        if not md_file:
            return jsonify({'error': 'opendataloader-pdf produced no .md file'}), 500

        with open(os.path.join(output_dir, md_file), encoding='utf-8') as f:
            content = f.read()

        content = _embed_images(content, output_dir)

    return Response(content, mimetype='text/markdown')


def _embed_images(markdown: str, output_dir: str) -> str:
    def replacer(match):
        alt = match.group(1)
        img_path = match.group(2).strip('<>')  # opendataloader wraps paths in angle brackets
        # Skip already-embedded data URIs and remote URLs
        if img_path.startswith('data:') or img_path.startswith('http'):
            return match.group(0)
        full_path = os.path.join(output_dir, img_path)
        if not os.path.exists(full_path):
            return match.group(0)
        mime, _ = mimetypes.guess_type(full_path)
        mime = mime or 'image/jpeg'
        with open(full_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        return f'![{alt}](data:{mime};base64,{b64})'

    return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replacer, markdown)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port)
