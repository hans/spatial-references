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

FILLER_PROPORTION = 2 / 7


def load_scenes(scenes):
    ret = defaultdict(dict)
    for scene in scenes:
        for path in Path(RENDER_PATH).glob("%s.*.json" % scene):
            with path.open("r") as frame_f:
                data = json.load(frame_f)
                ret[scene][data["frame"]] = data

    return dict(ret)


def get_humans(frame_data):
    return [ref for ref in frame_data["referents"].values() if ref["reference_frame"] is not None]


def sample_stimuli(n, scene_data):
    choices = {scene: set(frames.keys()) for scene, frames in SCENE_DATA.items()}

    ret = []
    last_scene = None
    for _ in range(n):
        frame_data = None
        while frame_data is None:
            scene = random.choice(choices.keys())
            remaining_frames = choices[scene]
            frame_name = random.choice(list(remaining_frames))
            frame_data_tmp = SCENE_DATA[scene][frame_name]

            # Bias samples to favor scenes with two people.
            if len(get_humans(frame_data_tmp)) < 2 and random.random() < 0.75:
                continue
            frame_data = frame_data_tmp

        ret.append(frame_data)
        remaining_frames.remove(frame_name)

    return ret


SCENE_DATA = load_scenes(["mancar"])


@custom_code.route("/stimuli", methods=["GET"])
def get_stimuli():
    n_samples = 15

    filler_idxs = random.sample(list(range(n_samples)), FILLER_PROPORTION * n_samples)

    ret = []
    for i, stim in enumerate(sample_stimuli(n_samples, SCENE_DATA)):
        is_filler = i in filler_idxs
        meta = stim["scene_data"]

        relation, prompt_type = None, None
        if is_filler:
            relation = "near"
            if len(get_humans(meta)) == 1:
                prompt_type = random.choice(["pick", "count"])
            else:
                prompt_type = "count"
        else:
            # Rejection-sample a non-filler.
            while relation is None or (relation == "near" and prompt_type == "count"):
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
