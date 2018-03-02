from argparse import ArgumentParser
from collections import namedtuple
from itertools import permutations
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector


Box = namedtuple("Box", ["min_x", "min_y", "max_x", "max_y"])


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
    """Get a list of objects labeled as potential referents in the 3D scene."""
    # return [obj for obj in objects if obj.name.startswith(prefix)]
    return data.groups["Referents"].objects


def render_images(context, data, scene_data):
    scene = context.scene
    camera = scene.camera

    scene.render.image_settings.file_format = "PNG"

    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        frame_name = "%s-%02i" % (scene_data["scene_name"], frame)
        render_frame(context, data, get_referents(data), frame_name, scene_data)


def render_frame(context, data, referents, frame_name, scene_data):

    # Output Blender render.
    img_path = "%s.png" % frame_name
    context.scene.render.filepath = img_path
    bpy.ops.render.render(write_still=True)

    for i, ordered_referents in enumerate(permutations(referents)):
        bboxes = [camera_view_bounds_2d(context.scene, context.scene.camera, obj)
                  for obj in ordered_referents]

        # Now open with PIL and draw on bboxes.
        img = Image.open(img_path)
        draw = ImageDraw.Draw(img)
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

            text_label = chr(65 + j)
            mid_x = min_x + (max_x - min_x) / 2
            mid_y = min_y + (max_y - min_y) / 2

            draw.text((mid_x * width - 7, height - mid_y * height - 10), text_label, fill="black",
                    font=font)

            referents[text_label] = obj.name

        img_path_i = "%s.%02i.png" % (frame_name, i)
        img.save(img_path_i, "PNG")
        print(img_path_i)

        # Save referent order in companion text file.
        info_file = "%s.%02i.json" % (frame_name, i)
        info = {
            "scene": scene_data["scene_name"],
            "frame": frame_name,
            "image_path": img_path,
            "referents": referents
        }

        with open(info_file, "w") as info_f:
            json.dump(info, info_f)


def main(args):
    with open(args.scene_json, "r") as f:
        scene_data = json.load(f)

    scene_path = Path(args.scene_json).parents[0] / scene_data["scene_file"]

    @persistent
    def load_handler(_):
        render_images(bpy.context, bpy.data, scene_data)

    bpy.app.handlers.load_post.append(load_handler)

    bpy.ops.wm.open_mainfile(filepath=str(scene_path))


if __name__ == '__main__':
    try:
        argv = sys.argv[sys.argv.index("--") + 1:]
    except:
        argv = []

    p = ArgumentParser()

    p.add_argument("scene_json")

    main(p.parse_args(argv))
