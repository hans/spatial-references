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


MALE_NAMES = ["Oliver", "Harry", "Jack", "Noah", "George", "Charlie",
              "Jacob", "Fred", "Oscar", "Leo", "Thomas"]


def sample_stimuli(n, stimuli_path=RENDER_PATH):
    choices = list(Path(stimuli_path).glob("*.json"))

    ret = []
    for json_path in random.sample(choices, min(n, len(choices))):
        with open(str(json_path), "r") as f:
            data = json.load(f)

        ret.append(data)

    return ret


@custom_code.route("/stimuli", methods=["GET"])
def get_stimuli():
    n_samples = 10
    male_names = random.sample(MALE_NAMES, n_samples)

    ret = []
    for stim, male_name in zip(sample_stimuli(n_samples), male_names):
        meta = stim["scene_data"]
        relation = random.choice(meta["relations"])

        prompt_type = random.choice(meta["prompts"].keys())
        prompt = meta["prompts"][prompt_type]
        prompt = prompt.format(relation=relation, ground=meta["ground"],
                               name=random.choice(MALE_NAMES))

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
