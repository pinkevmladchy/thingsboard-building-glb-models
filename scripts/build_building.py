#!/usr/bin/env python3
"""Build a GLB of a multi-storey building for the ThingsBoard 3D Model Viewer widget.

Pure Python (no numpy / trimesh). One mesh per floor, named Floor.001 .. Floor.NNN
(ground floor = Floor.001), so a Floor asset binds to its mesh through the `meshId`
attribute and the widget's mesh type `Floor`.

Design contract (same as silo-glb-builder):
  - +Y is up, the footprint lies on the XZ plane, centred on the origin, ground at y = 0.
  - Geometry is the source of truth: identity node transforms, no extras.
  - Every independently coloured part is its own named mesh with its own material.

Usage:
  python build_building.py --shape rect --width 36 --depth 24 --floors 4 --output building.glb
  python build_building.py --shape L --width 36 --depth 28 --wing 12 --floors 6 --output l.glb
  python build_building.py --shape U --width 42 --depth 28 --wing 12 --floors 3 --output u.glb
  python build_building.py --footprint '[[0,0],[30,0],[30,20],[0,20]]' --floors 5 --output custom.glb
"""
import argparse
import json
import math
import struct

# ---------------------------------------------------------------- footprints (metres)


def footprint(shape, width, depth, wing):
    """Polygon (x, z) points, counter-clockwise seen from above, origin at a corner."""
    if shape == 'rect':
        return [[0, 0], [width, 0], [width, depth], [0, depth]]
    if shape == 'L':     # L / Г: long wing along the back, short wing on the left
        return [[0, 0], [wing, 0], [wing, depth - wing], [width, depth - wing], [width, depth], [0, depth]]
    if shape == 'U':     # U / П: courtyard open to the front (z = 0)
        return [[0, 0], [wing, 0], [wing, depth - wing], [width - wing, depth - wing], [width - wing, 0],
                [width, 0], [width, depth], [0, depth]]
    raise ValueError('shape must be rect, L or U (or pass --footprint)')


def signed_area(poly):
    return sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
               for i in range(len(poly))) / 2


def offset_polygon(poly, d):
    """Offset a simple polygon outward by d (miter joins)."""
    ccw = signed_area(poly) > 0
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        def normal(a, b):
            ex, ez = b[0] - a[0], b[1] - a[1]
            length = math.hypot(ex, ez)
            # outward normal for a CCW polygon (x right, z down in plan) is (ez, -ex)
            nx, nz = (ez / length, -ex / length) if ccw else (-ez / length, ex / length)
            return nx, nz
        n1, n2 = normal(p0, p1), normal(p1, p2)
        bx, bz = n1[0] + n2[0], n1[1] + n2[1]
        bl = math.hypot(bx, bz) or 1
        bx, bz = bx / bl, bz / bl
        cos_half = bx * n1[0] + bz * n1[1]
        k = d / max(cos_half, 0.2)
        out.append([p1[0] + bx * k, p1[1] + bz * k])
    return out


def triangulate(poly):
    """Ear clipping for a simple polygon. Returns index triples, CCW order."""
    idx = list(range(len(poly)))
    if signed_area(poly) < 0:
        idx.reverse()
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if cross(a, b, c) <= 1e-9:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
    tris.append(tuple(idx))
    return tris

# ---------------------------------------------------------------- mesh building (flat shaded)


class Mesh:
    def __init__(self):
        self.pos, self.nrm, self.idx = [], [], []

    def tri(self, a, b, c):
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
        base = len(self.pos)
        for p in (a, b, c):
            self.pos.append(p)
            self.nrm.append((nx / ln, ny / ln, nz / ln))
        self.idx += [base, base + 1, base + 2]

    def quad(self, a, b, c, d):
        self.tri(a, b, c)
        self.tri(a, c, d)


def prism(mesh, poly, y0, y1):
    """Extrude a footprint polygon (x, z) between y0 and y1; outward-facing triangles."""
    pts = poly if signed_area(poly) > 0 else list(reversed(poly))
    # walls: polygon is CCW in (x, z) math sense, which is clockwise seen from +Y; wind accordingly
    for i in range(len(pts)):
        (x0, z0), (x1, z1) = pts[i], pts[(i + 1) % len(pts)]
        mesh.quad((x0, y0, z0), (x0, y1, z0), (x1, y1, z1), (x1, y0, z1))
    for a, b, c in triangulate(pts):
        pa, pb, pc = pts[a], pts[b], pts[c]
        mesh.tri((pa[0], y1, pa[1]), (pc[0], y1, pc[1]), (pb[0], y1, pb[1]))   # top faces +Y
        mesh.tri((pa[0], y0, pa[1]), (pb[0], y0, pb[1]), (pc[0], y0, pc[1]))   # bottom faces -Y


def box(mesh, cx, cy, cz, sx, sy, sz, rot):
    """Axis box rotated around Y by rot (radians), centred at (cx, cy, cz)."""
    c, s = math.cos(rot), math.sin(rot)
    def p(dx, dy, dz):
        return (cx + dx * c + dz * s, cy + dy, cz - dx * s + dz * c)
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    v = [p(-hx, -hy, -hz), p(hx, -hy, -hz), p(hx, hy, -hz), p(-hx, hy, -hz),
         p(-hx, -hy, hz), p(hx, -hy, hz), p(hx, hy, hz), p(-hx, hy, hz)]
    for f in ((4, 5, 6, 7), (1, 0, 3, 2), (0, 4, 7, 3), (5, 1, 2, 6), (3, 7, 6, 2), (0, 1, 5, 4)):
        mesh.quad(*(v[i] for i in f))

# ---------------------------------------------------------------- scene


def build(poly_m, floors, floor_h, slab, window_w, window_h, window_gap, scale):
    cx = (max(p[0] for p in poly_m) + min(p[0] for p in poly_m)) / 2
    cz = (max(p[1] for p in poly_m) + min(p[1] for p in poly_m)) / 2
    poly = [[(x - cx) * scale, (z - cz) * scale] for x, z in poly_m]
    fh, sl = floor_h * scale, slab * scale
    meshes = []    # (name, Mesh, rgba, roughness, metallic)

    slabs = Mesh()
    slab_poly = offset_polygon(poly, 0.15 * scale)
    for i in range(floors):
        body = Mesh()
        prism(body, poly, i * fh + sl, (i + 1) * fh)
        meshes.append(('Floor.%03d' % (i + 1), body, [0.80, 0.82, 0.85, 1], 0.8, 0.0))
        prism(slabs, slab_poly, i * fh, i * fh + sl)
    roof_y = floors * fh
    prism(slabs, offset_polygon(poly, 0.3 * scale), roof_y, roof_y + 1.5 * sl)
    meshes.append(('Slabs', slabs, [0.94, 0.95, 0.96, 1], 0.9, 0.0))

    # windows along every wall, every floor
    glass, frames = Mesh(), Mesh()
    ccw = signed_area(poly) > 0
    ww, wh, gap = window_w * scale, window_h * scale, window_gap * scale
    for k in range(len(poly)):
        (x0, z0), (x1, z1) = poly[k], poly[(k + 1) % len(poly)]
        ex, ez = x1 - x0, z1 - z0
        length = math.hypot(ex, ez)
        n = int((length - 0.8 * scale) // gap)
        if n < 1:
            continue
        nx, nz = (ez / length, -ex / length) if ccw else (-ez / length, ex / length)
        rot = math.atan2(nx, nz)          # local +Z faces outward
        for i in range(floors):
            yc = i * fh + sl + (fh - sl) * 0.52
            for j in range(n):
                t = (j + 0.5) / n
                px, pz = x0 + ex * t, z0 + ez * t
                box(frames, px + nx * 0.02 * scale, yc, pz + nz * 0.02 * scale, ww + 0.16 * scale, wh + 0.16 * scale, 0.06 * scale, rot)
                box(glass, px + nx * 0.06 * scale, yc, pz + nz * 0.06 * scale, ww, wh, 0.04 * scale, rot)
    meshes.append(('Window_Frames', frames, [0.97, 0.97, 0.98, 1], 0.6, 0.0))
    meshes.append(('Windows', glass, [0.16, 0.24, 0.34, 1], 0.15, 0.4))

    # rooftop plant
    plant = Mesh()
    box(plant, poly[0][0] * 0.4, roof_y + 1.5 * sl + 0.9 * scale, poly[0][1] * 0.3, 5 * scale, 1.8 * scale, 3.5 * scale, 0)
    meshes.append(('Roof_Plant', plant, [0.70, 0.74, 0.79, 1], 0.7, 0.2))
    return meshes


def write_glb(meshes, path):
    bin_chunks, buffer_views, accessors, gl_meshes, nodes, materials = [], [], [], [], [], []
    offset = 0

    def add_view(data, target):
        nonlocal offset
        pad = (-len(data)) % 4
        bin_chunks.append(data + b'\x00' * pad)
        buffer_views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data), 'target': target})
        offset += len(data) + pad
        return len(buffer_views) - 1

    for salt, (name, m, rgba, rough, metal) in enumerate(meshes):
        pos = struct.pack('<%df' % (len(m.pos) * 3), *[c for p in m.pos for c in p])
        nrm = struct.pack('<%df' % (len(m.nrm) * 3), *[c for p in m.nrm for c in p])
        idx = struct.pack('<%dI' % len(m.idx), *m.idx)
        vp, vn, vi = add_view(pos, 34962), add_view(nrm, 34962), add_view(idx, 34963)
        mins = [min(p[i] for p in m.pos) for i in range(3)]
        maxs = [max(p[i] for p in m.pos) for i in range(3)]
        accessors += [
            {'bufferView': vp, 'componentType': 5126, 'count': len(m.pos), 'type': 'VEC3', 'min': mins, 'max': maxs},
            {'bufferView': vn, 'componentType': 5126, 'count': len(m.nrm), 'type': 'VEC3'},
            {'bufferView': vi, 'componentType': 5125, 'count': len(m.idx), 'type': 'SCALAR'},
        ]
        a = len(accessors) - 3
        # unique material per mesh (salted roughness) so viewers never merge them
        materials.append({'name': name + '_Mat', 'pbrMetallicRoughness': {
            'baseColorFactor': rgba, 'metallicFactor': metal, 'roughnessFactor': min(1.0, rough + salt * 1e-4)}})
        gl_meshes.append({'name': name, 'primitives': [{'attributes': {'POSITION': a, 'NORMAL': a + 1}, 'indices': a + 2, 'material': salt}]})
        nodes.append({'name': name, 'mesh': salt})

    binary = b''.join(bin_chunks)
    gltf = {'asset': {'version': '2.0', 'generator': 'building-glb-builder'}, 'scene': 0,
            'scenes': [{'name': 'Building', 'nodes': list(range(len(nodes)))}], 'nodes': nodes, 'meshes': gl_meshes,
            'materials': materials, 'accessors': accessors, 'bufferViews': buffer_views,
            'buffers': [{'byteLength': len(binary)}]}
    js = json.dumps(gltf, separators=(',', ':')).encode()
    js += b' ' * ((-len(js)) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total))
        f.write(struct.pack('<II', len(js), 0x4E4F534A) + js)
        f.write(struct.pack('<II', len(binary), 0x004E4942) + binary)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--shape', choices=['rect', 'L', 'U'], default='rect')
    ap.add_argument('--width', type=float, default=36, help='overall width, m (x)')
    ap.add_argument('--depth', type=float, default=24, help='overall depth, m (z)')
    ap.add_argument('--wing', type=float, default=12, help='wing width for L / U, m')
    ap.add_argument('--footprint', help='custom polygon JSON [[x,z],...] in metres; overrides --shape')
    ap.add_argument('--floors', type=int, default=4)
    ap.add_argument('--floor-height', type=float, default=3.6, help='m, slab included')
    ap.add_argument('--slab', type=float, default=0.3, help='slab thickness, m')
    ap.add_argument('--window-width', type=float, default=1.6)
    ap.add_argument('--window-height', type=float, default=1.9)
    ap.add_argument('--window-spacing', type=float, default=3.0, help='centre-to-centre, m')
    ap.add_argument('--scale', type=float, default=0.1, help='model units per metre (0.1 = 1 unit per 10 m)')
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    if a.shape in ('L', 'U') and not a.footprint:
        if a.wing * (2 if a.shape == 'U' else 1) >= a.width or a.wing >= a.depth:
            ap.error('wings do not fit: check --wing against --width/--depth')
    poly = json.loads(a.footprint) if a.footprint else footprint(a.shape, a.width, a.depth, a.wing)
    meshes = build(poly, a.floors, a.floor_height, a.slab, a.window_width, a.window_height, a.window_spacing, a.scale)
    write_glb(meshes, a.output)
    print('Wrote %s: %s' % (a.output, ', '.join(m[0] for m in meshes)))


if __name__ == '__main__':
    main()
