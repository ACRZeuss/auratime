"""
AuraTime Brand Logo & Multi-Resolution Icon Generator.
Uses analytical Signed Distance Fields (SDF) with sub-pixel smoothstep anti-aliasing
to generate crisp RGBA PNGs (256x256, 64x64, 36x36, 32x32, 16x16) and a multi-resolution
Windows .ico file with zero third-party dependencies.
"""

from __future__ import annotations

import math
from pathlib import Path
import struct
import zlib


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else (hi if x > hi else x)


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 0.0 if x < edge0 else 1.0
    t = _clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_color(
    c1: tuple[float, float, float],
    c2: tuple[float, float, float],
    t: float,
) -> tuple[float, float, float]:
    t = _clamp(t)
    return (
        _lerp(c1[0], c2[0], t),
        _lerp(c1[1], c2[1], t),
        _lerp(c1[2], c2[2], t),
    )


def _blend_rgba(
    bg: tuple[float, float, float, float],
    fg_rgb: tuple[float, float, float],
    fg_a: float,
) -> tuple[float, float, float, float]:
    """Alpha-over compositing in straight alpha [0..1]."""
    fg_a = _clamp(fg_a)
    if fg_a <= 0.0:
        return bg
    inv_a = 1.0 - fg_a
    out_a = fg_a + bg[3] * inv_a
    if out_a <= 1e-6:
        return (0.0, 0.0, 0.0, 0.0)
    r = (fg_rgb[0] * fg_a + bg[0] * bg[3] * inv_a) / out_a
    g = (fg_rgb[1] * fg_a + bg[1] * bg[3] * inv_a) / out_a
    b = (fg_rgb[2] * fg_a + bg[2] * bg[3] * inv_a) / out_a
    return (r, g, b, out_a)


def _sd_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Signed distance from point (px, py) to line segment (ax, ay)-(bx, by)."""
    pax, pay = px - ax, py - ay
    bax, bay = bx - ax, by - ay
    denom = bax * bax + bay * bay
    h = _clamp((pax * bax + pay * bay) / denom) if denom > 1e-9 else 0.0
    dx = pax - bax * h
    dy = pay - bay * h
    return math.hypot(dx, dy)


def _sd_triangle(
    px: float,
    py: float,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    """Signed distance to a 2D triangle (negative inside, positive outside)."""
    e0x, e0y = x1 - x0, y1 - y0
    e1x, e1y = x2 - x1, y2 - y1
    e2x, e2y = x0 - x2, y0 - y2

    v0x, v0y = px - x0, py - y0
    v1x, v1y = px - x1, py - y1
    v2x, v2y = px - x2, py - y2

    pq0 = _sd_segment(px, py, x0, y0, x1, y1)
    pq1 = _sd_segment(px, py, x1, y1, x2, y2)
    pq2 = _sd_segment(px, py, x2, y2, x0, y0)
    d = min(pq0, pq1, pq2)

    # Winding check for inside/outside sign
    s = e0x * (y2 - y0) - e0y * (x2 - x0)
    sign_w = 1.0 if s >= 0 else -1.0
    c0 = sign_w * (v0x * e0y - v0y * e0x)
    c1 = sign_w * (v1x * e1y - v1y * e1x)
    c2 = sign_w * (v2x * e2y - v2y * e2x)
    if c0 <= 0.0 and c1 <= 0.0 and c2 <= 0.0:
        return -d
    return d


def render_auratime_rgba(size: int) -> bytes:
    """
    Render the AuraTime logo at (size x size) returning raw RGBA bytes (top-to-bottom).
    Design:
    - Ubuntu Yaru squircle badge (vibrant Sunset Orange #FF6B35/#E95420 -> Aubergine Violet #77216F/#3B1045)
    - Luminous inner aura glow + glass border highlight
    - 275-degree Time Progress Ring with glowing active endpoint dot
    - Sleek geometric Aura Hourglass with glowing golden sand core in the center
    """
    buf = bytearray(size * size * 4)
    aa = 2.2 / float(size)  # Sub-pixel anti-aliasing width in normalized [-1, 1] coords

    # Brand palette in normalized RGB [0..1]
    c_orange_bright = (1.00, 0.44, 0.20)   # #FF7033
    c_ubuntu_orange = (0.914, 0.329, 0.125)  # #E95420
    c_magenta = (0.68, 0.16, 0.48)         # #AD297A
    c_aubergine = (0.26, 0.07, 0.33)       # #421254
    c_gold = (1.00, 0.78, 0.28)            # #FFC747 (glowing sand / active pulse)
    c_cyan_glow = (0.45, 0.95, 0.78)       # #73F2C7 (wellbeing accent)
    c_white = (1.0, 1.0, 1.0)
    c_shadow = (0.10, 0.02, 0.14)

    # Progress arc angles (in degrees, 0 = top / 12 o'clock, clockwise)
    arc_start_deg = -140.0
    arc_end_deg = 135.0
    ring_r = 0.60

    # End cap position for active progress dot (at arc_end_deg)
    end_rad = math.radians(arc_end_deg - 90.0)
    dot_x = ring_r * math.cos(end_rad)
    dot_y = ring_r * math.sin(end_rad)

    for py in range(size):
        ny = ((py + 0.5) / float(size)) * 2.0 - 1.0
        for px in range(size):
            nx = ((px + 0.5) / float(size)) * 2.0 - 1.0

            # 1. Squircle signed distance: (|x/r|^4.2 + |y/r|^4.2)^(1/4.2) - 1
            sq_r = 0.90
            ax = abs(nx) / sq_r
            ay = abs(ny) / sq_r
            sq_norm = (ax ** 4.2 + ay ** 4.2) ** (1.0 / 4.2)
            sd_squircle = (sq_norm - 1.0) * sq_r

            bg_alpha = 1.0 - _smoothstep(-aa, aa, sd_squircle)
            if bg_alpha <= 0.0:
                continue

            # Diagonal gradient t in [0..1] from top-left (-1,-1) to bottom-right (+1,+1)
            diag_t = _clamp((nx * 0.55 + ny * 0.75 + 1.1) / 2.2)
            if diag_t < 0.42:
                base_rgb = _lerp_color(c_orange_bright, c_ubuntu_orange, diag_t / 0.42)
            elif diag_t < 0.75:
                base_rgb = _lerp_color(c_ubuntu_orange, c_magenta, (diag_t - 0.42) / 0.33)
            else:
                base_rgb = _lerp_color(c_magenta, c_aubergine, (diag_t - 0.75) / 0.25)

            # Warm central radial aura glow
            center_dist = math.hypot(nx, ny)
            aura = math.exp(-center_dist * center_dist * 2.4) * 0.25
            base_rgb = _lerp_color(base_rgb, c_orange_bright, aura)

            rgba: tuple[float, float, float, float] = (
                base_rgb[0],
                base_rgb[1],
                base_rgb[2],
                bg_alpha,
            )

            # Inner glass border highlight along the squircle rim
            rim_dist = abs(sd_squircle + 0.025)
            rim_alpha = (1.0 - _smoothstep(0.0, 0.025 + aa, rim_dist)) * bg_alpha
            rim_light = _clamp(0.45 - (nx + ny) * 0.22, 0.08, 0.55)
            rgba = _blend_rgba(rgba, c_white, rim_alpha * rim_light)

            # 2. Outer Time Ring & Progress Arc
            ring_thick = 0.068 if size >= 32 else 0.085
            sd_ring = abs(center_dist - ring_r) - ring_thick * 0.5

            # Background track of the ring (full 360 circle, soft translucent white)
            track_a = (1.0 - _smoothstep(-aa, aa, sd_ring)) * 0.22 * bg_alpha
            rgba = _blend_rgba(rgba, c_white, track_a)

            # Active progress arc (-140 deg to +135 deg clockwise from 12 o'clock)
            angle_deg = math.degrees(math.atan2(ny, nx)) + 90.0
            if angle_deg > 180.0:
                angle_deg -= 360.0

            # Subtle shadow under arc (with rounded caps)
            sh_ny = ny - 0.03
            sh_dist = math.hypot(nx, sh_ny)
            sd_ring_sh = abs(sh_dist - ring_r) - ring_thick * 0.55
            sh_angle = math.degrees(math.atan2(sh_ny, nx)) + 90.0
            if sh_angle > 180.0:
                sh_angle -= 360.0
            s_rad = math.radians(arc_start_deg - 90.0)
            sx, sy = ring_r * math.cos(s_rad), ring_r * math.sin(s_rad)
            if arc_start_deg <= sh_angle <= arc_end_deg:
                sd_arc_shadow = sd_ring_sh
            else:
                d_sh_start = math.hypot(nx - sx, sh_ny - sy) - ring_thick * 0.55
                d_sh_end = math.hypot(nx - dot_x, sh_ny - dot_y) - ring_thick * 0.55
                sd_arc_shadow = min(d_sh_start, d_sh_end)

            rgba = _blend_rgba(
                rgba,
                c_shadow,
                (1.0 - _smoothstep(-aa * 2, aa * 3, sd_arc_shadow)) * 0.28 * bg_alpha,
            )

            # Distance to active arc with rounded caps
            if arc_start_deg <= angle_deg <= arc_end_deg:
                sd_arc = sd_ring
            else:
                d_start = math.hypot(nx - sx, ny - sy) - ring_thick * 0.5
                d_end = math.hypot(nx - dot_x, ny - dot_y) - ring_thick * 0.5
                sd_arc = min(d_start, d_end)

            arc_a = (1.0 - _smoothstep(-aa, aa, sd_arc)) * bg_alpha
            if arc_a > 0.0:
                arc_prog = _clamp((angle_deg - arc_start_deg) / (arc_end_deg - arc_start_deg))
                arc_color = _lerp_color(c_white, c_gold, arc_prog * 0.35)
                rgba = _blend_rgba(rgba, arc_color, arc_a * 0.96)

            # Glowing endpoint indicator dot on the progress ring
            d_dot = math.hypot(nx - dot_x, ny - dot_y)
            dot_glow = math.exp(-d_dot * d_dot / 0.012) * 0.45 * bg_alpha
            rgba = _blend_rgba(rgba, c_gold, dot_glow)
            dot_core_a = (1.0 - _smoothstep(0.085 - aa, 0.085 + aa, d_dot)) * bg_alpha
            rgba = _blend_rgba(rgba, c_white, dot_core_a)
            dot_inner_a = (1.0 - _smoothstep(0.048 - aa, 0.048 + aa, d_dot)) * bg_alpha
            rgba = _blend_rgba(rgba, c_cyan_glow, dot_inner_a)

            # 3. Central Stylized Hourglass Emblem ("Aura Hourglass")
            # Top & bottom horizontal bars, diagonal glass frame, and glowing golden sand
            hw = 0.24   # Half-width of hourglass top/bottom
            hh = 0.31   # Half-height of hourglass
            frame_t = 0.038 if size >= 32 else 0.048

            # Shadow offset for 3D depth
            sy_off = ny - 0.028
            sd_top_bar = _sd_segment(nx, ny, -hw, -hh, hw, -hh) - frame_t
            sd_bot_bar = _sd_segment(nx, ny, -hw, hh, hw, hh) - frame_t
            sd_diag1 = _sd_segment(nx, ny, -hw * 0.88, -hh, hw * 0.88, hh) - frame_t * 0.88
            sd_diag2 = _sd_segment(nx, ny, hw * 0.88, -hh, -hw * 0.88, hh) - frame_t * 0.88
            sd_hourglass_frame = min(sd_top_bar, sd_bot_bar, sd_diag1, sd_diag2)

            # Drop shadow under hourglass
            sd_sh_top = _sd_segment(nx, sy_off, -hw, -hh, hw, -hh) - frame_t
            sd_sh_bot = _sd_segment(nx, sy_off, -hw, hh, hw, hh) - frame_t
            sd_sh_d1 = _sd_segment(nx, sy_off, -hw * 0.88, -hh, hw * 0.88, hh) - frame_t * 0.88
            sd_sh_d2 = _sd_segment(nx, sy_off, hw * 0.88, -hh, -hw * 0.88, hh) - frame_t * 0.88
            sd_hg_shadow = min(sd_sh_top, sd_sh_bot, sd_sh_d1, sd_sh_d2)
            sh_a = (1.0 - _smoothstep(-aa * 1.5, aa * 2.5, sd_hg_shadow)) * 0.35 * bg_alpha
            rgba = _blend_rgba(rgba, c_shadow, sh_a)

            # Golden sand inside upper & lower chambers + falling sand stream
            sd_upper_sand = _sd_triangle(nx, ny, -0.11, -0.14, 0.11, -0.14, 0.0, -0.02) - 0.012
            sd_lower_sand = _sd_triangle(nx, ny, -0.15, 0.24, 0.15, 0.24, 0.0, 0.07) - 0.015
            sd_stream = _sd_segment(nx, ny, 0.0, -0.03, 0.0, 0.20) - 0.018
            sd_sand = min(sd_upper_sand, sd_lower_sand, sd_stream)
            sand_a = (1.0 - _smoothstep(-aa, aa, sd_sand)) * bg_alpha
            if sand_a > 0.0:
                rgba = _blend_rgba(rgba, c_gold, sand_a * 0.95)

            # White hourglass frame
            hg_a = (1.0 - _smoothstep(-aa, aa, sd_hourglass_frame)) * bg_alpha
            if hg_a > 0.0:
                rgba = _blend_rgba(rgba, c_white, hg_a)

            # Write pixel to buffer
            idx = (py * size + px) * 4
            buf[idx] = int(round(_clamp(rgba[0]) * 255))
            buf[idx + 1] = int(round(_clamp(rgba[1]) * 255))
            buf[idx + 2] = int(round(_clamp(rgba[2]) * 255))
            buf[idx + 3] = int(round(_clamp(rgba[3]) * 255))

    return bytes(buf)


def encode_png_rgba(width: int, height: int, rgba_bytes: bytes) -> bytes:
    """Encode raw top-to-bottom RGBA bytes into a standard PNG image using built-in zlib."""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    # Filter type 0 (None) prepended to each scanline
    stride = width * 4
    raw_rows = bytearray((stride + 1) * height)
    for y in range(height):
        dst_off = y * (stride + 1)
        src_off = y * stride
        raw_rows[dst_off] = 0
        raw_rows[dst_off + 1 : dst_off + 1 + stride] = rgba_bytes[src_off : src_off + stride]

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA (color type 6)
    idat = zlib.compress(bytes(raw_rows), level=9)

    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


def _rgba_to_dib_frame(size: int, rgba_bytes: bytes) -> bytes:
    """Convert top-to-bottom RGBA bytes to bottom-up BGRA DIB frame for Windows ICO."""
    bgra_bottom_up = bytearray(size * size * 4)
    stride = size * 4
    for y in range(size):
        src_row = (size - 1 - y) * stride
        dst_row = y * stride
        for x in range(size):
            r = rgba_bytes[src_row + x * 4]
            g = rgba_bytes[src_row + x * 4 + 1]
            b = rgba_bytes[src_row + x * 4 + 2]
            a = rgba_bytes[src_row + x * 4 + 3]
            bgra_bottom_up[dst_row + x * 4] = b
            bgra_bottom_up[dst_row + x * 4 + 1] = g
            bgra_bottom_up[dst_row + x * 4 + 2] = r
            bgra_bottom_up[dst_row + x * 4 + 3] = a

    and_row_bytes = ((size + 31) // 32) * 4
    and_mask = bytes(and_row_bytes * size)

    bmp_header = struct.pack(
        "<IIIHHIIIIII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        len(bgra_bottom_up) + len(and_mask),
        0,
        0,
        0,
        0,
    )
    return bmp_header + bytes(bgra_bottom_up) + and_mask


def ensure_brand_assets(assets_dir: Path) -> dict[str, Path]:
    """
    Generate all AuraTime brand assets in assets_dir:
    - auratime.ico (Multi-resolution Windows icon: 16, 32, 48, 64, 256)
    - auratime_256.png (High-resolution logo)
    - auratime_64.png (Medium badge)
    - auratime_36.png (HeaderBar UI logo)
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    ico_path = assets_dir / "auratime.ico"
    png_256 = assets_dir / "auratime_256.png"
    png_64 = assets_dir / "auratime_64.png"
    png_36 = assets_dir / "auratime_36.png"

    if (
        ico_path.exists()
        and png_256.exists()
        and png_64.exists()
        and png_36.exists()
        and ico_path.stat().st_size > 5000
    ):
        return {
            "ico": ico_path,
            "png_256": png_256,
            "png_64": png_64,
            "png_36": png_36,
        }

    # Render required resolutions
    sizes_needed = [16, 32, 36, 48, 64, 256]
    rendered_rgba: dict[int, bytes] = {}
    rendered_png: dict[int, bytes] = {}
    for sz in sizes_needed:
        rgba = render_auratime_rgba(sz)
        rendered_rgba[sz] = rgba
        rendered_png[sz] = encode_png_rgba(sz, sz, rgba)

    png_256.write_bytes(rendered_png[256])
    png_64.write_bytes(rendered_png[64])
    png_36.write_bytes(rendered_png[36])

    # Build multi-resolution .ico (16, 32, 48, 64 as DIB frames + 256 as PNG frame)
    ico_sizes = [16, 32, 48, 64, 256]
    frames: list[tuple[int, bytes]] = []
    for sz in ico_sizes:
        if sz == 256:
            frames.append((sz, rendered_png[256]))
        else:
            frames.append((sz, _rgba_to_dib_frame(sz, rendered_rgba[sz])))

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    dir_entries = bytearray()
    payload = bytearray()

    for sz, data in frames:
        b_width = 0 if sz >= 256 else sz
        b_height = 0 if sz >= 256 else sz
        dir_entries += struct.pack(
            "<BBBBHHII",
            b_width,
            b_height,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        payload += data
        offset += len(data)

    ico_path.write_bytes(header + bytes(dir_entries) + bytes(payload))

    return {
        "ico": ico_path,
        "png_256": png_256,
        "png_64": png_64,
        "png_36": png_36,
    }
