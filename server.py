import os
import re
import base64
import mimetypes
import tempfile
import subprocess

import requests
from docling_core.types.doc.document import DoclingDocument
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

HYBRID_URL = 'http://localhost:5003'

# Magic bytes for image formats docling accepts (RIFF covers WebP)
_IMAGE_MAGIC = (b'\x89PNG', b'\xff\xd8\xff', b'GIF8', b'BM',
                b'II*\x00', b'MM\x00*', b'RIFF')


@app.route('/health', methods=['GET'])
def health():
    return 'ok', 200


@app.route('/convert', methods=['POST'])
def convert():
    data = request.data
    if not data:
        return jsonify({'error': 'No file data in request body'}), 400

    content_type = (request.content_type or '').split(';')[0].strip().lower()
    if content_type.startswith('image/') or data.startswith(_IMAGE_MAGIC):
        return _convert_image(data, content_type)
    return _convert_pdf(data)


def _convert_image(data, content_type):
    # The opendataloader-pdf CLI is PDF-only; images go straight to the
    # docling hybrid backend, which OCRs them and returns a DoclingDocument.
    ext = (mimetypes.guess_extension(content_type)
           if content_type.startswith('image/') else None) or '.jpg'
    try:
        resp = requests.post(
            f'{HYBRID_URL}/v1/convert/file',
            files={'files': (f'input{ext}', data,
                             content_type if content_type.startswith('image/')
                             else 'application/octet-stream')},
            timeout=300,
        )
    except requests.RequestException as e:
        return jsonify({'error': f'hybrid backend unreachable: {e}'}), 502

    if resp.status_code != 200:
        app.logger.error('hybrid backend failed: %s', resp.text[:1000])
        return jsonify({'error': resp.text[:1000] or 'Image conversion failed'}), 500

    doc = DoclingDocument.model_validate(resp.json()['document']['json_content'])
    content = doc.export_to_markdown()
    if not content.strip():
        return jsonify({'error': 'No text recognized in image'}), 422

    return Response(content, mimetype='text/markdown')


def _convert_pdf(pdf_data):
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, 'input.pdf')
        output_dir = os.path.join(tmpdir, 'output')
        os.makedirs(output_dir)

        with open(input_path, 'wb') as f:
            f.write(pdf_data)

        result = subprocess.run(
            ['opendataloader-pdf', input_path, '-o', output_dir, '--format', 'markdown',
             '--hybrid', 'docling-fast', '--hybrid-mode', 'full',
             '--hybrid-url', 'http://localhost:5003', '--hybrid-fallback'],
            capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            detail = (result.stderr or '') + (result.stdout or '')
            app.logger.error('opendataloader-pdf failed: %s', detail)
            return jsonify({'error': detail or 'Conversion failed'}), 500

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
