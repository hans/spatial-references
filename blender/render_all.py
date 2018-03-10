import sys
sys.path.append("/home/jon/anaconda3/lib/python3.6/site-packages")

from argparse import ArgumentParser
from collections import namedtuple
from itertools import permutations
import json
import math
import os
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm, trange

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector, Euler
from mathutils.noise import random


Box = namedtuple("Box", ["min_x", "min_y", "max_x", "max_y"])


FRAME_PROPERTY_VALUES = {
    0: None,
    1: "relative",
    2: "intrinsic",
    3: "functional"
}


def camera_view_bounds_2d(scene, cam_ob, me_ob):
    """
    Returns camera space bounding box of mesh object.
    From https://blender.stackexchange.com/a/7203

    Negative 'z' value means the point is behind the camera.

    Takes shift-x/y, lens angle and sensor size into account
    as well as perspective/ortho projections.

    :arg scene: Scene to use for frame size.
    :type scene: :class:`bpy.types.Scene`
    :arg obj: Camera object.
    :type obj: :class:`bpy.types.Object`
    :arg me: Untransformed Mesh.
    :type me: :class:`bpy.types.Mesh´
    :return: a Box object (call its to_tuple() method to get x, y, width and height)
    :rtype: :class:`Box`
    """

    mat = cam_ob.matrix_world.normalized().inverted()
    me = me_ob.to_mesh(scene, True, 'PREVIEW')
    me.transform(me_ob.matrix_world)
    me.transform(mat)

    camera = cam_ob.data
    frame = [-v for v in camera.view_frame(scene=scene)[:3]]
    camera_persp = camera.type != 'ORTHO'

    lx = []
    ly = []

    for v in me.vertices:
        co_local = v.co
        z = -co_local.z

        if camera_persp:
            if z == 0.0:
                lx.append(0.5)
                ly.append(0.5)
            # Does it make any sense to drop these?
            #if z <= 0.0:
            #    continue
            else:
                frame = [(v / (v.z / z)) for v in frame]

        min_x, max_x = frame[1].x, frame[2].x
        min_y, max_y = frame[0].y, frame[1].y

        x = (co_local.x - min_x) / (max_x - min_x)
        y = (co_local.y - min_y) / (max_y - min_y)

        lx.append(x)
        ly.append(y)

    min_x = clamp(min(lx), 0.0, 1.0)
    max_x = clamp(max(lx), 0.0, 1.0)
    min_y = clamp(min(ly), 0.0, 1.0)
    max_y = clamp(max(ly), 0.0, 1.0)

    bpy.data.meshes.remove(me)

    # TODO what are these?
    r = scene.render
    fac = r.resolution_percentage * 0.01
    dim_x = r.resolution_x * fac
    dim_y = r.resolution_y * fac

    return Box(min_x, min_y, max_x, max_y)


def clamp(x, minimum, maximum):
    return max(minimum, min(x, maximum))


def get_referents(data):
    """Get a list of objects labeled as potential referents in the current 3D scene."""
    fakes_group = data.groups.get("Fakes")

    return [obj for obj in data.groups["Referents"].objects
            if not obj.hide_render or fakes_group in obj.users_group]


def randomize_position(obj, guide):
    """
    Randomize the position of an object `obj` along some linear guide path `guide`.
    """
    guide_points = guide.data.splines.active.points
    p1, p2 = guide_points[0], guide_points[-1]

    # Convert to scene coordinates and remove 4th dimension (what is this?)
    p1 = Vector((guide.matrix_world * p1)[:3])
    p2 = Vector((guide.matrix_world * p2)[:3])

    t = random()
    obj.location = p1 + t * (p2 - p1)


def randomize_rotation(obj, bounds=(0, 2 * math.pi)):
    rot = obj.rotation_euler
    obj.rotation_euler = Euler((rot.x, rot.y, bounds[0] + random() * (bounds[1] - bounds[0])), "XYZ")


def render_images(context, data, scene_data, out_dir):
    scene = context.scene
    camera = scene.camera

    scene.render.image_settings.file_format = "PNG"

    for frame in trange(scene.frame_start, scene.frame_end + 1, desc="Rendering frames"):
        scene.frame_set(frame)
        frame_name = "%s-%02i" % (scene_data["scene_name"], frame)
        render_frame(context, data, get_referents(data), frame_name, scene_data, out_dir)


def render_frame(context, data, referents, frame_name, scene_data, out_dir):

    # Output Blender render.
    img_name = "%s.png" % frame_name
    img_path = str(out_dir / img_name)
    context.scene.render.filepath = img_path
    bpy.ops.render.render(write_still=True)

    img = Image.open(img_path).convert("RGBA")

    for i, ordered_referents in tqdm(enumerate(permutations(referents)), desc="Rendering permutations"):
        bboxes = [camera_view_bounds_2d(context.scene, context.scene.camera, obj)
                  for obj in ordered_referents]

        # Draw reference names on a new layer.
        layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(layer)
        width, height = img.size

        # # DEV: draw bounding boxes.
        # for bbox in bboxes:
        #     min_x, min_y, max_x, max_y = bbox
        #     draw.rectangle(((min_x * width, height - min_y * height),
        #                     (max_x * width, height - max_y * height)), outline="black")

        # Draw text labels.
        referents = {}
        font = ImageFont.truetype("arial", size=26)
        for j, (bbox, obj) in enumerate(zip(bboxes, ordered_referents)):
            min_x, min_y, max_x, max_y = bbox
            min_x *= width
            max_x *= width
            min_y = (1 - min_y) * height
            max_y = (1 - max_y) * height

            # Calculate text bbox and center.
            text_label = chr(65 + j)
            text_bbox = font.getmask(text_label).getbbox()

            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1] + 10

            textbox_x = min_x + (max_x - min_x) / 2 - text_width / 2
            textbox_y = min_y + (max_y - min_y) / 2 - text_height / 2

            draw.rectangle([(textbox_x, textbox_y), (textbox_x + text_width, textbox_y + text_height)],
                           fill=(0, 0, 0, 100))
            draw.text((textbox_x, textbox_y), text_label, fill="white",
                      font=font)

            try:
                obj_data = data.meshes[obj.name]
                reference_frame_id = obj_data.get("frame", 0)
            except KeyError:
                # not all referents have reference frame data
                reference_frame_id = 0

            reference_frame = FRAME_PROPERTY_VALUES[reference_frame_id]
            referents[text_label] = (obj.name, reference_frame)

        img_name_i = "%s.%02.i.png" % (frame_name, i)
        img_path_i = str(out_dir / img_name_i)

        combined = Image.alpha_composite(img, layer)
        combined.save(img_path_i, "PNG")

        # Save referent order in companion text file.
        info_file = str(out_dir / ("%s.%02i.json" % (frame_name, i)))
        info = {
            "scene": scene_data["scene_name"],
            "scene_data": scene_data,

            "frame": frame_name,
            "frame_path": img_name,
            "labeled_frame_path": img_name_i,
            "referents": referents
        }

        with open(info_file, "w") as info_f:
            json.dump(info, info_f)


def main(args):
    with open(args.scene_json, "r") as f:
        scene_data = json.load(f)

    scene_dir = Path(args.scene_json).parents[0]
    out_dir = Path(args.out_dir)

    # Change to the Blender file's directory before loading the scene.
    # Otherwise loading of external textures can break.
    #
    # This also allows the scene JSON files to use relative paths to
    # the Blender files.
    os.chdir(scene_dir)

    @persistent
    def load_handler(_):
        render_images(bpy.context, bpy.data, scene_data, out_dir)

    bpy.app.handlers.load_post.append(load_handler)

    bpy.ops.wm.open_mainfile(filepath=scene_data["scene_file"])


if __name__ == '__main__':
    try:
        argv = sys.argv[sys.argv.index("--") + 1:]
    except:
        argv = []

    p = ArgumentParser()

    p.add_argument("scene_json")
    p.add_argument("-o", "--out_dir", default=os.getcwd())

    main(p.parse_args(argv))
