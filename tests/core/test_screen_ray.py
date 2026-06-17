"""Screen-pixel → world-ray unprojection (#25), headless `core`.

QML hands the bridge a screen click ``(px, py)`` plus the camera; the bridge needs
a world-space ray to feed :func:`pick_face`. :func:`screen_ray` is that pinhole
unprojection — it lives in ``core`` (ADR-0004: all geometry maths stays in the test
seam), so a known camera resolves a known ray with no Qt and no 3D scene.
"""

from __future__ import annotations

import numpy as np
import trimesh

from polycut.core.picking import pick_face, screen_ray


def test_centre_pixel_shoots_along_the_camera_forward():
    """The pixel at the exact centre of the viewport unprojects to a ray that starts
    at the camera and points straight down its forward axis — no tilt."""
    origin, direction = screen_ray(
        cam_pos=[0.0, 0.0, 5.0],
        forward=[0.0, 0.0, -1.0],
        up=[0.0, 1.0, 0.0],
        fov_y=60.0,
        px=49.5,  # centre of a 100-px axis: (49.5 + 0.5) / 100 = 0.5
        py=49.5,
        width=100,
        height=100,
    )

    assert np.allclose(origin, [0.0, 0.0, 5.0])  # ray starts at the camera
    assert np.allclose(direction, [0.0, 0.0, -1.0])  # straight along forward, normalised


def test_off_centre_pixels_tilt_the_ray_by_fov_and_aspect():
    """A pixel off the centre tilts the ray: the right edge swings it toward +x, the
    top edge toward +y (py grows downward, so the small py is the top), and a wider
    viewport swings the same right-edge pixel further — aspect is respected."""
    cam = dict(cam_pos=[0.0, 0.0, 0.0], forward=[0.0, 0.0, -1.0], up=[0.0, 1.0, 0.0], fov_y=90.0)

    _, right = screen_ray(**cam, px=99.5, py=49.5, width=100, height=100)  # right edge, square
    assert right[0] > 0 and np.isclose(right[1], 0.0)
    assert np.allclose(right, np.array([1.0, 0.0, -1.0]) / np.sqrt(2))  # tan(45°)=1 → 45° swing

    _, top = screen_ray(**cam, px=49.5, py=-0.5, width=100, height=100)  # top edge
    assert top[1] > 0 and np.isclose(top[0], 0.0)

    _, wide = screen_ray(**cam, px=199.5, py=49.5, width=200, height=100)  # right edge, 2:1
    assert wide[0] > right[0]  # the wider frustum tilts the same edge pixel further in x


def _big_diagonal_quad():
    """A large z=0 quad split along the y=x diagonal: face 0 is the lower-right half
    (y<x), face 1 the upper-left (y>x). Big enough that any modest screen tilt lands
    on it, so the click→face mapping is unambiguous."""
    verts = np.array([[-10, -10, 0], [10, -10, 0], [10, 10, 0], [-10, 10, 0]], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def test_a_screen_click_resolves_to_the_face_under_the_cursor():
    """End-to-end: unproject a click with a known top-down camera, feed the ray to
    pick_face, and land on the face beneath that pixel. A lower-right click hits the
    lower-right triangle; an upper-left click hits the other one."""
    mesh = _big_diagonal_quad()
    cam = dict(cam_pos=[0.0, 0.0, 5.0], forward=[0.0, 0.0, -1.0], up=[0.0, 1.0, 0.0], fov_y=60.0)

    o, d = screen_ray(**cam, px=70, py=70, width=100, height=100)  # lower-right of centre
    assert pick_face(mesh, o, d) == 0  # tilts to +x,-y → the y<x triangle

    o, d = screen_ray(**cam, px=30, py=30, width=100, height=100)  # upper-left of centre
    assert pick_face(mesh, o, d) == 1  # tilts to -x,+y → the y>x triangle
