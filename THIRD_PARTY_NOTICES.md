# Source and third-party notices

## Authorized predecessor code reuse

On 2026-11-05 the user authorized migrating the relevant pose foundation into
CourtSense. The source is the user's predecessor badminton embodied-intelligence
project at commit `4cd869c7a4576b5c2f4e3c05de55165eebe32952`. Only the three files listed below were copied,
byte-for-byte, including their original docstrings and comments.

The predecessor has no project-wide LICENSE. Its `THIRD_PARTY_LICENSE` contains
Apache License 2.0 for the bundled official inference code; it does **not** grant
Apache 2.0 terms to every file in that repository. This migration relies on the
user's express reuse authorization for their own code, and makes no claim of a
blanket predecessor license. CourtSense does not redistribute the official
inference implementation, model weights, board server, or private material.

| Source at commit above | Destination | Source and destination SHA256 |
| --- | --- | --- |
| `platforms/rdk_x5/board/pose_observation.py` | `courtsense/pose/pose_observation.py` | `2e84fcf75af06a9f73896727901c70cff47a0f5e537bfde5f211d54cee8336de` |
| `platforms/rdk_x5/board/pose_skeleton.py` | `courtsense/pose/pose_skeleton.py` | `c7cd6b7c977b0cab86958531b4f6a174aad62b1163c49a39f3f7f52b20b84efb` |
| `platforms/rdk_x5/board/camera_orientation.py` | `courtsense/pose/camera_orientation.py` | `80ba44c463ffe838524b99ffdbbfce1046695a753c72bbb40ce91fee728c1899` |

## File-by-file origin and dependency notes

- `pose_observation.py`: predecessor project utility for exporting raw-logit
  COCO17 observations and projected elbow/knee angles. No third-party copyright
  or license header appears in the source. Only the Python standard library is
  imported. COCO17 names and angle triples describe the data convention.
- `pose_skeleton.py`: predecessor project utility described in its historical
  runtime notes as custom skeleton lines. Its docstring references the X5
  official sample's raw-logit contract, not a bundled inference implementation.
  The COCO17 topology is preserved. `draw_skeleton` lazily imports OpenCV; the
  numeric `skeleton_segments` function uses only the standard library. OpenCV is
  an external optional dependency, not copied code.
- `camera_orientation.py`: predecessor project utility for a fixed inverted
  MIPI mount. No third-party copyright or license header appears in this file.
  It lazily uses OpenCV rotation. Its mount-specific 180-degree rotation and
  image-space identifier must not be applied to unrelated video cameras.
- `courtsense/pose/__init__.py`, `courtsense/sources/rdk.py`, and the associated
  migration tests and documentation: new CourtSense integration code, not copied
  from the predecessor server. The RDK reader uses Python's standard library.

The referenced official example is
[D-Robotics X5 pose sample](https://github.com/D-Robotics/x5-hobot-sp-samples/tree/main/debian/app/pydev_demo/04_pose_sample/01_ultralytics_yolo11_pose).
It is provenance context, not a redistributed dependency in this migration.
No third-party license text is represented as covering the migrated utilities.
Additional model/runtime dependency terms must be checked separately before
redistribution or use beyond the authorized scope.

## Optional video inference

The video adapter imports Ultralytics and OpenCV at runtime; it does not vendor
their source or weights. Ultralytics distributes its software/models under its
AGPL-3.0 or enterprise terms; review https://www.ultralytics.com/license before
deployment or redistribution. Official model download provenance and the exact
validation SHA256 are recorded in docs/validation-video-2026-11-05.md.

OpenCV, NumPy and PyTorch have their own distribution notices. Installing a
runtime dependency does not relicense it under this repository. No project-wide
license has yet been selected for CourtSense, and no bundled rights to private
training videos, official BPU model binaries or the Fine-Badminton broadcasts
are granted. The public video validation record contains aggregate measurements
and provenance only, not the source video, extracted images or model weights.
