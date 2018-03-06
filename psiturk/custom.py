import itertools
import json
from pathlib2 import Path
import random

from flask import Blueprint, jsonify, send_file

from psiturk.psiturk_config import PsiturkConfig
from psiturk.user_utils import PsiTurkAuthorization


config = PsiturkConfig()
config.load_config()
myauth = PsiTurkAuthorization(config) # if you want to add a password protected route use this

# explore the Blueprint
custom_code = Blueprint("custom_code", __name__, template_folder="templates", static_folder="static")


RENDER_PATH = "../blender/out"


ENABLED_SCENES = [
    "mancar",
    "mantv",
    "manbus",
]


def sample_stimuli(n, stimuli_path=RENDER_PATH):
    all_scenes = set(ENABLED_SCENES)
    choices = {scene: set(Path(stimuli_path).glob("%s-*.json" % scene))
               for scene in all_scenes}

    ret = []
    last_scene = None
    for _ in range(n):
        # Choose any scene randomly, as long as it isn't the same as the
        # previous scene.
        scene = random.choice(list(all_scenes - set([last_scene])))
        last_scene = scene

        remaining_frames = choices[scene]
        json_path = random.choice(list(remaining_frames))
        remaining_frames.remove(json_path)

        with open(str(json_path), "r") as f:
            data = json.load(f)

        ret.append(data)

    return ret


@custom_code.route("/stimuli", methods=["GET"])
def get_stimuli():
    n_samples = 12

    ret = []
    for stim in sample_stimuli(n_samples):
        meta = stim["scene_data"]
        relation = random.choice(meta["relations"])

        prompt_type = random.choice(meta["prompts"].keys())
        prompt = meta["prompts"][prompt_type]
        prompt = prompt.format(relation=relation, ground=meta["ground"])

        ret.append({
            "scene": stim["scene"],
            "frame": stim["frame"],
            "referents": stim["referents"],

            "relation": relation,
            "prompt_type": prompt_type,
            "prompt": prompt,

            "frame_path": stim["frame_path"],
            "labeled_frame_path": stim["labeled_frame_path"],
        })

    return jsonify({"stimuli": ret})


@custom_code.route("/renders/<fname>")
def get_render(fname):
    return send_file(str(Path(RENDER_PATH) / fname), mimetype="image/png")
