import sys
from pathlib import Path

CODE_PATH = Path('./codes/')
sys.path.append(str(CODE_PATH))

from flask import Flask, request, jsonify, render_template
import base64, io, uuid, os
from PIL import Image
import torch, yaml, json

from model.pipeline import Pipeline
from clip.model import CLIP
from clip.clip import _transform, tokenize

cfg_path = 'configs/config.yaml'
config = yaml.safe_load(open(cfg_path))
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

with open(config["model_config"]) as f:
    info = json.load(f)

model = CLIP(**info)
checkpoint = torch.load(config["model_ckpt"], map_location=device, weights_only=False)
state = checkpoint.get("state_dict", checkpoint)
state = {k.replace("module.", "", 1): v for k, v in state.items()}
model.load_state_dict(state, strict=False)
model.to(device)

transform = _transform(model.visual.input_resolution, is_train=False)
pipeline = Pipeline(config, model, transform, tokenize, device)

# DB indexing
img_dir = config["encoding"]["image_dir"]
img_paths = sorted(str(p) for p in Path(img_dir).glob("*") if p.suffix.lower() in [".jpg", ".png"])
pipeline.index_database(img_paths)

app = Flask(__name__, static_folder='static', template_folder='templates')
UPLOAD_DIR = Path('uploads')
UPLOAD_DIR.mkdir(exist_ok=True)

# intro page
@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/infer', methods=['POST'])
def infer():
    data = request.get_json()
    sketch_b64 = data['sketch'].split(',')[1]
    caption = data.get('caption', '')
    print("caption from client:", caption)

    im = Image.open(io.BytesIO(base64.b64decode(sketch_b64))).convert('RGB')
    tmp_name = UPLOAD_DIR / f"{uuid.uuid4().hex}.png"
    im.save(tmp_name)

    result_paths = pipeline.run_retrieval(str(tmp_name), caption)

    result_b64_list = []
    for p in result_paths:
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
            result_b64_list.append("data:image/jpeg;base64," + b64)

    tmp_name.unlink(missing_ok=True)
    return jsonify({"results": result_b64_list})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)
