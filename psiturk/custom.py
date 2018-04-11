from collections import defaultdict
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


def load_scenes(scenes):
    ret = defaultdict(dict)
    for scene in scenes:
        if isinstance(scene, tuple):
            base = Path(RENDER_PATH) / scene[0]
            scene_name = scene[1]
        else:
            scene_name = scene

        for path in base.glob("%s.*.json" % scene_name):
            with path.open("r") as frame_f:
                data = json.load(frame_f)
                ret[(scene_name, data["frame"])] = data

    return dict(ret)


PART1_SCENE_DATA = load_scenes([("1", "mancar")])
PART2_SCENE_DATA = load_scenes([("2", "mancar")])

# Maximum number of requests to display to a particular user from each part.
PART1_MAX_REQUESTS = 3
PART2_MAX_REQUESTS = 3


def prepare_frame_json(frame, relation, prompt_type):
    meta = frame["scene_data"]
    prompt = meta["prompts"][prompt_type]
    prompt = prompt.format(relation=relation, ground=meta["ground"])

    return {
        "scene": frame["scene"],
        "frame": frame["frame"],
        "referents": frame["referents"],

        "relation": relation,
        "prompt_type": prompt_type,
        "prompt": prompt,

        "frame_path": frame["frame_path"],
        "labeled_frame_path": frame["labeled_frame_path"],
        "arrow_frame_path": frame["arrow_frame_path"],
    }


@custom_code.route("/stimuli", methods=["GET"])
def get_stimuli():
    filler_idxs = random.sample(list(range(n_samples)), FILLER_PROPORTION * n_samples)

    ret = []

    part1_frames = random.sample(PART1_SCENE_DATA.keys(), PART1_MAX_REQUESTS)
    for frame_key in part1_frames:
        frame = PART1_SCENE_DATA[frame_key]

        relation = "in front of" if random.random() < 0.75 else "near"
        prompt_type = "confirm"

        ret.append(prepare_frame_json(frame, relation, prompt_type))


    part2_frames = random.sample(PART2_SCENE_DATA.keys(), PART2_MAX_REQUESTS)
    for frame_key in part2_frames:
        frame = PART2_SCENE_DATA[frame_key]

        relation = "near"
        prompt_type = "count"

        ret.append(prepare_frame_json(frame, relation, prompt_type))

    random.shuffle(ret)

    return jsonify({"stimuli": ret})


@custom_code.route("/renders/<fname>")
def get_render(fname):
    return send_file(str(Path(RENDER_PATH) / fname), mimetype="image/png")
