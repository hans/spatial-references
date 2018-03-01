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
    ret = jsonify({"stimuli": sample_stimuli(10)})
    print(ret)
    return ret


@custom_code.route("/renders/<fname>")
def get_render(fname):
    return send_file(str(Path(RENDER_PATH) / fname), mimetype="image/png")
