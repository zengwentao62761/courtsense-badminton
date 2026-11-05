"""Nominal badminton diagram. Not surveyed line-edge calibration geometry."""

from html import escape


def nominal_court():
    segments = []

    def add(name, kind, start, end):
        segments.append(dict(id=name, kind=kind, start=start, end=end))

    add('near_baseline', 'boundary', [0, 0], [6.1, 0])
    add('far_baseline', 'boundary', [0, 13.4], [6.1, 13.4])
    add('left_doubles', 'boundary', [0, 0], [0, 13.4])
    add('right_doubles', 'boundary', [6.1, 0], [6.1, 13.4])
    for name, x in [('left', 0.46), ('right', 5.64)]:
        add(name + '_singles', 'singles_sideline', [x, 0], [x, 13.4])
    for name, y in [('near', 4.72), ('far', 8.68)]:
        add(name + '_short_service', 'short_service', [0, y], [6.1, y])
    for name, y in [('near', 0.76), ('far', 12.64)]:
        add(name + '_long_doubles', 'doubles_long_service', [0, y], [6.1, y])
    add('near_center', 'center_service', [3.05, 0], [3.05, 4.72])
    add('far_center', 'center_service', [3.05, 8.68], [3.05, 13.4])
    add('net', 'net_projection', [0, 6.7], [6.1, 6.7])
    return dict(
        schema_version='0.1', template_id='badminton-nominal-diagram-v1',
        evidence_type='nominal_geometry', usable_for_metric_calibration=False,
        width_m=6.1, length_m=13.4, segments=segments,
        convention='Top-view diagram: origin near-left, +x right, +y far; '
                   'nominal line positions only; painted edges/centers unresolved.',
        reference='BWF Laws 2023, Diagram A; not a current-rule certification',
    )


def render_svg(court):
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 660" '
        'role="img" aria-labelledby="title desc">',
        '<title id="title">CourtSense nominal court geometry</title>',
        '<desc id="desc">Geometric diagram only. No player measurements, '
        'camera calibration or shuttle trajectories.</desc>',
        '<rect width="1000" height="660" rx="20" fill="#102b30"/>',
        '<g font-family="sans-serif" fill="#eaf7f0">',
        '<text x="45" y="49" font-size="25">COURTSENSE / COURT GEOMETRY</text>',
        '<text x="45" y="78" font-size="13" fill="#a7d2c6">'
        'NOMINAL DIAGRAM - NOT A CALIBRATION</text>',
        '<rect x="95" y="140" width="804" height="366" fill="#20594e"/>',
    ]
    # Rotate the top-view coordinates for a landscape README illustration.
    for segment in court['segments']:
        x1, y1 = segment['start']
        x2, y2 = segment['end']
        net = segment['kind'] == 'net_projection'
        extra = ' stroke-dasharray="9 6"' if net else ''
        parts.append(
            f'<line id="{escape(segment["id"], quote=True)}" '
            f'x1="{95 + y1 * 60:.2f}" y1="{140 + x1 * 60:.2f}" '
            f'x2="{95 + y2 * 60:.2f}" y2="{140 + x2 * 60:.2f}" '
            f'stroke="{"#ffcb77" if net else "#effbf4"}" '
            f'stroke-width="{3 if net else 2}"{extra}/>'
        )
    parts.extend([
        '<text x="430" y="124" font-size="15">13.40 m nominal</text>',
        '<text x="95" y="538" font-size="14">Doubles width 6.10 m / singles width 5.18 m</text>',
        '<text x="95" y="565" font-size="14" fill="#ffcb77">Dashed amber: net ground projection</text>',
        '<text x="45" y="607" font-size="13" fill="#a7d2c6">'
        'No measured positions. No speed estimates. No automatic line matching.</text>',
        '<text x="45" y="630" font-size="12" fill="#a7d2c6">'
        'Line-edge conventions must be resolved before metric calibration.</text>',
        '</g></svg>',
    ])
    return '\n'.join(parts) + '\n'
