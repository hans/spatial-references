import sys
sys.path.append("/home/jon/anaconda3/lib/python3.6/site-packages")

from argparse import ArgumentParser
from collections import namedtuple, defaultdict
import itertools
import json
import math
import os
from pathlib import Path
import random
import sys

from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm, trange

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector, Euler


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
    """Get a list of objects labeled as potential referents in the current 3D scene."""
    fakes_group = data.groups.get("Fakes")

    return [obj for obj in data.groups["Referents"].objects
            if not obj.hide_render or fakes_group in obj.users_group]


def get_people(data):
    """Get a list of objects labeled as people in the current 3D scene."""
    return data.groups["People"].objects


def get_guides(data):
    """Get a list of objects labeled as frame guides in the current 3D scene."""
    return data.groups["Frames"].objects


def get_guide_type(guide):
    """Get the reference frame type corresponding to a particular guide."""
    # Maintained by naming convention in the Blender files. Sub-optimal.
    try:
        return guide.name[guide.name.rindex(".") + 1:]
    except:
        return None


def randomize_position(obj, guide):
    """
    Randomize the position of an object `obj` along some linear guide path `guide`.
    """
    guide_points = guide.data.splines.active.points
    p1, p2 = guide_points[0].co, guide_points[-1].co

    # Convert to scene coordinates and remove 4th dimension (what is this?)
    p1 = Vector((guide.matrix_world * p1)[:3])
    p2 = Vector((guide.matrix_world * p2)[:3])

    t = random.random()
    target_point = p1 + t * (p2 - p1)

    # update X and Y coordinates.
    obj.location[0] = target_point[0]
    obj.location[1] = target_point[1]

    return t


def randomize_rotation(obj, bounds=(-math.pi, math.pi)):
    rot = obj.rotation_euler

    dz = bounds[0] + random.random() * (bounds[1] - bounds[0])
    z = rot.z + dz % (2 * math.pi)
    obj.rotation_euler = Euler((rot.x, rot.y, z), "XYZ")

    return dz


def prepare_scene(data, people_setting):
    """
    Move people referents to random positions in the given reference frames.

    `people_setting` is of the form `[(person, guide_path), (person2, guide_path), ...]`
    """
    manipulations = defaultdict(dict)
    for person, guide in people_setting.items():
        m_pos = randomize_position(person, guide)

        rotation_bounds = (-math.pi, math.pi)
        if get_guide_type(guide) == "functional":
            # Functional frames are very angle-dependent -- we don't expect
            # them to hold for > 90 deg rotations. They probably won't hold for
            # even > 45 deg rotations -- but we should check :)
            rotation_bounds = (-math.pi / 4, math.pi / 4)
        m_rot = randomize_rotation(person, bounds=rotation_bounds)

        manipulations[person]["location"] = m_pos
        manipulations[person]["rotation"] = m_rot

        person.hide_render = False

    for person in set(get_people(data)) - set(people_setting.keys()):
        person.hide_render = True

    return dict(manipulations)


def render_images(context, data, scene_data, out_dir, samples_per_setting=5):
    scene = context.scene
    camera = scene.camera

    scene.render.image_settings.file_format = "PNG"

    people = get_people(data)
    frame_guides = get_guides(data)

    i = 0
    for n_people in range(1, len(people) + 1):
        for people_set in itertools.combinations(people, n_people):
            for frames_ordered in itertools.permutations(frame_guides, n_people):
                for _ in range(samples_per_setting):
                    people_setting = dict(zip(people_set, frames_ordered))

                    frame_name = "%s.%02i" % (scene_data["scene_name"], i)
                    render_frame(scene, data, frame_name, people_setting, scene_data, out_dir)

                    i += 1


def render_frame(scene, data, frame_name, people_setting, scene_data, out_dir):
    manipulations = prepare_scene(data, people_setting)

    referents = get_referents(data)
    random.shuffle(referents)

    # Output Blender render without labels.
    img_name = "%s.png" % frame_name
    img_path = str(out_dir / img_name)
    scene.render.filepath = img_path
    bpy.ops.render.render(write_still=True)

    img = Image.open(img_path).convert("RGBA")

    # Prepare a new layer which will contain reference labels.
    layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(layer)
    width, height = img.size

    # Get 2D bounding boxes in image of each referent.
    bboxes = [camera_view_bounds_2d(scene, scene.camera, obj)
              for obj in referents]

    # # DEV: draw bounding boxes.
    # for bbox in bboxes:
    #     min_x, min_y, max_x, max_y = bbox
    #     draw.rectangle(((min_x * width, height - min_y * height),
    #                     (max_x * width, height - max_y * height)), outline="black")

    # Draw text labels.
    referent_data = {}
    font = ImageFont.truetype("arial", size=26)
    for j, (bbox, obj) in enumerate(zip(bboxes, referents)):
        min_x, min_y, max_x, max_y = bbox
        min_x *= width
        max_x *= width
        min_y = (1 - min_y) * height
        max_y = (1 - max_y) * height

        # Shift up labels by default.
        min_y -= 40
        max_y -= 40

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

        reference_frame = None
        if obj in people_setting:
            reference_frame = get_guide_type(people_setting[obj])

        referent_data[text_label] = {
            "name": obj.name,
            "reference_frame": reference_frame,
            "manipulations": manipulations.get(obj, {})
        }

    labeled_img_name = "%s.labeled.png" % frame_name
    labeled_img_path = str(out_dir / labeled_img_name)

    combined = Image.alpha_composite(img, layer)
    combined.save(labeled_img_path, "PNG")

    # Save referent order in companion text file.
    info_file = str(out_dir / ("%s.json" % frame_name))
    info = {
        "scene": scene_data["scene_name"],
        "scene_data": scene_data,

        "frame": frame_name,
        "frame_path": img_name,
        "labeled_frame_path": labeled_img_name,
        "referents": referent_data
    }

    with open(info_file, "w") as info_f:
        json.dump(info, info_f)


def main(args):
    with open(args.scene_json, "r") as f:
        scene_data = json.load(f)

    scene_dir = Path(args.scene_json).parents[0].absolute()
    out_dir = Path(args.out_dir).absolute()

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

    p.add_argument("scene_json", nargs="?", default=None)
    p.add_argument("-o", "--out_dir", default=os.getcwd())

    args = p.parse_args(argv)
    if not args or not args.scene_json:
        print("---------- NOT RUNNING: No scene.json argument provided")
    else:
        main(args)
