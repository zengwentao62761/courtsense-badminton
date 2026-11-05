# Pose foundation migration and read-only RDK adapter

Date: 2026-11-05. Scope: P0.1 desktop implementation and simulated validation.
Source commit and per-file SHA256 are recorded in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). The three source utilities
were migrated byte-for-byte under the user's explicit reuse authorization;
the source project's Apache third-party text is not its project-wide license.
No board service, model, private report, credentials or capture implementation
was imported. This change neither deploys nor modifies the predecessor service.

## Preserved pose contract

`courtsense.pose.pose_observation.make_observation` accepts raw keypoint logits,
not probabilities, and returns COCO17 pixel measurements and 2D projected angles.
The logit threshold corresponds to probability 0.4. Finite out-of-image points
remain in the export but carry `valid: false`, `reason: out_of_frame`; they must
not be used as measurements. Nonfinite coordinates become null. Frame ID is
assigned by callers. Detection order is not tracking identity.

Ultralytics video probabilities must be clipped and converted to logits before
calling this function. Conversely the RDK `/observations` JSON already contains
probabilities; the reader validates [0, 1] and never applies sigmoid again.
Neither path produces court coordinates, true 3D angles or action scores.
`draw_skeleton` optionally requires OpenCV; the math/segment APIs do not.
`camera_orientation` preserves a mount-specific utility and is not automatically
invoked by the reader or video pipeline.

## RDK reader

```python
from courtsense.sources.rdk import RDKSource, RDKSourceError
source = RDKSource()  # http://localhost:8080, timeout=3
sample = source.read()  # {'observation': original_dict, 'jpeg': bytes}
```

Only GET `/observations` and GET `/frame.jpg` are issued. The origin and timeout
are validated. Three attempts maximum share a checked deadline; each network
operation receives the remaining socket timeout. The standard-library resolver
and socket scheduling are not a hard real-time deadline guarantee. JSON is
limited to 2 MiB, JPEG to 16 MiB, image dimensions to 16384 per axis and people
to 256. `ready: false`, missing identity, invalid timestamps, malformed points,
valid points outside bounds, nonfinite values and invalid probabilities fail.
Invalid flagged points are preserved consistently with the original exporter.
Failures raise `RDKSourceError`; there is no synthetic-data fallback.

Observation frame_id, image_space_id and service_instance_id must match the
JPEG headers exactly. Header coordinate width/height must match the observation.
The existing service uses smaller preview JPEGs while points remain in full
resolution coordinates: JPEG SOF dimensions must match preview_width/height
when present, otherwise width/height. The adapter checks JPEG SOI/EOI, segment
boundaries, supported SOF and scan header; it does not entropy-decode pixels.
JPEG decompression errors can still be detected by a downstream decoder.

Separate GETs can race with ongoing inference, even on a healthy device. The
source has no historical-frame endpoint. Retries obtain a new pair and refuse
to mix frames, coordinate spaces or service restarts. A sufficiently busy
service can therefore produce a visible offline/error state. Repeated matching
frames are returned as-is; downstream monitoring must deduplicate by service,
image-space and frame identity. Board host receive/process clocks are not
camera exposure timestamps and must not be subtracted from desktop monotonic
time.

## Validation and remaining limits

Tests were written first and initially failed because the modules did not
exist; then the migration/adapter passed. A later regression test exposed the
preview/full-resolution distinction before the adapter was updated. The focused
suite covers raw logits, threshold/boundary/NaN invalidity, a known 90-degree
angle, skeleton filtering, exact header pairing, restart/coordinate mismatch,
retries, readiness, timeouts, invalid input/probability, empty/truncated JPEG,
preview sizing and a real local HTTP fixture that races the first frame.

Run `python -m unittest discover -s tests -p "test_pose.py" -v` and
`python -m unittest discover -s tests -p "test_rdk.py" -v` (12 tests combined).
The HTTP server is a local test fixture, not RDK hardware. Actual live service
reachability, throughput and target-board acceptance remain unverified in this
migration. No MIPI acquisition, RDK libraries or new model is introduced.
