"""Local Shapr3D container reader and validated CAD/mesh export."""
from __future__ import annotations

import gc
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import tempfile
import zipfile
from array import array
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

import msgpack
from parasolid_kit import DirectorySchemaProvider, map_brep, parse_xb
from parasolid_kit.interop.occt import ValidationTolerances, to_occt
import parasolid_kit.interop.occt.conversion as _conversion

# The general builder also supports analytic vertex-trimmed circles. Retain
# the library's source-boundary, per-face and complete-shape validation.
_conversion._uses_parametric_topology = lambda model: True

RESOURCE_DIR = Path(__file__).resolve().parent
FORMATS = ('stl', 'obj', '3mf', 'glb', 'ply', 'step')


class ConversionError(Exception):
    pass


@dataclass
class Mesh:
    name: str
    vertices: list = field(default_factory=list)
    triangles: list = field(default_factory=list)
    removed_degenerate_triangles: int = 0


def _active_parts(c):
    roots = c.execute('SELECT Properties FROM HistoryTreeNodes WHERE HistoryTreeNodeType=0').fetchall()
    if len(roots) != 1:
        raise ConversionError('Неизвестная структура истории: ожидается один корень.')
    root = msgpack.unpackb(roots[0][0])
    order = root[-1]
    if not isinstance(order, list) or not all(isinstance(x, int) for x in order):
        raise ConversionError('Неизвестный порядок операций проекта.')
    rank = {v: i for i, v in enumerate(order)}
    rows = [(msgpack.unpackb(k), msgpack.unpackb(d)) for k, d in c.execute('SELECT CallKey,CallData FROM PersistedCalls')]
    rows = [r for r in rows if r[0][0] in rank]
    rows.sort(key=lambda r: (rank[r[0][0]], r[0][1]))
    last = {}
    for key, value in rows:
        if not value[2][0]:
            continue
        payload = value[2][1]
        if len(value) > 3:
            for pid, entry in payload[1]:
                if entry[0]:
                    last[pid] = entry[1][1]
        else:
            parts = payload[0]
            for effect in payload[2]:
                last[parts[effect[0]][0]] = effect[2]
    result = {pid: state[1] for pid, state in last.items() if state[0]}
    if not result:
        raise ConversionError('В проекте не найдены активные сохранённые тела.')
    return result


def _block(c, pid):
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'BodyRevisionPartitions' in tables:
        cols = {r[1] for r in c.execute('PRAGMA table_info(BodyRevisionPartitions)')}
        if 'Phase' not in cols:
            row = c.execute('SELECT Block FROM BodyRevisionPartitions WHERE PartitionID=?', (pid,)).fetchone()
            if not row:
                raise ConversionError(f'Нет данных тела {pid}.')
            return row[0]
        rows = c.execute('SELECT Block,Phase,IsDeleted FROM BodyRevisionPartitions WHERE PartitionID=?', (pid,)).fetchall()
        if len(rows) != 1 or rows[0][2]:
            raise ConversionError(f'Неоднозначное состояние тела {pid}.')
        return rows[0][0]
    if 'BodyRevisionBlocks' not in tables:
        raise ConversionError('Эта версия контейнера SHAPR пока не поддерживается.')
    rows = c.execute('SELECT ChunkIndex,Block,Phase,IsDeleted FROM BodyRevisionBlocks WHERE PartitionID=? ORDER BY ChunkIndex,Phase', (pid,)).fetchall()
    if not rows or any(r[2] != 2 or r[3] for r in rows):
        raise ConversionError(f'Тело {pid}: незавершённое сохранение или неизвестная фаза.')
    if [r[0] for r in rows] != list(range(len(rows))):
        raise ConversionError(f'Тело {pid}: нарушен порядок блоков.')
    return b''.join(r[1] for r in rows)


def _fields(node):
    return {f.definition.name: [v.value for v in f.values] for f in node.fields}


def _source_meshes(doc, pid):
    nodes = {n.index: n for n in doc.nodes}

    def comb(index, kind):
        n = nodes[index]
        f = _fields(n)
        expected = 'VECTOR_COMB' if kind == 'vector' else 'INTEGER_COMB'
        if n.definition.name != expected or f['encoding'] != [1]:
            raise ConversionError(f'Тело {pid}: неизвестное кодирование сетки.')
        values = []
        for tooth in f['teeth']:
            if tooth:
                values.extend(_fields(nodes[tooth])['values'])
        count = f['n_vectors' if kind == 'vector' else 'n_integers'][0]
        needed = count * 3 if kind == 'vector' else count
        if len(values) < needed:
            raise ConversionError('Неполные данные сетки.')
        return values[:needed]

    result = []
    for n in doc.nodes:
        if n.definition.name != 'MESH':
            continue
        f = _fields(n)
        index = f.get('psm_imesh', [0])[0]
        if not index or nodes[index].definition.name != 'PSM_MESH':
            raise ConversionError(f'Тело {pid}: неизвестный тип сетки.')
        mesh = _fields(nodes[index])
        xyz = comb(mesh['position_pool'][0], 'vector')
        indices = comb(mesh['position_indices'][0], 'integer')
        if len(indices) % 3:
            raise ConversionError('Сетка содержит неполные треугольники.')
        vertices = [tuple(v * 1000.0 for v in xyz[i:i+3]) for i in range(0, len(xyz), 3)]
        if f.get('transform', [0])[0]:
            transform = _fields(nodes[f['transform'][0]])
            perspective = transform['perspective_vector'][0]
            if any(v is not None and v != 0 for v in perspective):
                raise ConversionError(f'Тело {pid}: перспективное преобразование сетки не поддерживается.')
            matrix = transform['rotation_matrix']; scale = transform['scale'][0]
            translation = transform['translation_vector'][0]
            vertices = [tuple(scale*sum(matrix[i*3+j]*p[j] for j in range(3)) + translation[i]*1000 for i in range(3)) for p in vertices]
        # Stored world-space bounds independently detect a wrong transform.
        bounds = f.get('mesh_box', [None])[0]
        if bounds and all(v is not None for v in bounds):
            actual = [v for i in range(3) for v in (min(p[i] for p in vertices), max(p[i] for p in vertices))]
            if max(abs(a-b*1000) for a,b in zip(actual,bounds)) > 0.01:
                raise ConversionError(f'Тело {pid}: границы сетки не совпали с сохранённой геометрией.')
        if any(not isinstance(i, int) or i < 1 or i > len(vertices) for i in indices):
            raise ConversionError('Индексы сетки выходят за границы массива.')
        triangles = [tuple(v-1 for v in indices[i:i+3]) for i in range(0, len(indices), 3)]
        if f['sense'][0] == 45:
            triangles = [(a, c, b) for a, b, c in triangles]
        elif f['sense'][0] != 43:
            raise ConversionError('Неизвестная ориентация сетки.')
        result.append(Mesh(f'body_{pid}_mesh_{n.index}', vertices, triangles))
    if not result:
        raise ConversionError('Не удалось прочитать сеточную геометрию.')
    bodies = [n for n in doc.nodes if n.definition.name == 'BODY']
    if len(bodies) != 1:
        raise ConversionError('Несколько тел в одной сеточной секции пока не поддерживаются.')
    combined = _merged(result); combined.name = f'body_{pid}_mesh'
    return [_weld(combined)]


def _tessellate(shape, name, tolerance):
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    mesher = BRepMesh_IncrementalMesh(shape, tolerance, False, 0.15, True)
    if not mesher.IsDone():
        raise ConversionError('OpenCascade не смог построить сетку.')
    result = Mesh(name)
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None or tri.NbTriangles() == 0:
            raise ConversionError('Одна из поверхностей не преобразована в треугольники.')
        offset = len(result.vertices)
        for i in range(1, tri.NbNodes() + 1):
            p = tri.Node(i).Transformed(loc.Transformation())
            result.vertices.append((p.X(), p.Y(), p.Z()))
        reverse = face.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            if reverse:
                b, c = c, b
            result.triangles.append((offset+a-1, offset+b-1, offset+c-1))
        explorer.Next()
    return _weld(result)


def _weld(mesh):
    # Join repeated face-boundary vertices at a 0.000001 mm grid. Preserve
    # the first source coordinate, rather than snapping the geometry to a grid.
    lookup = {}; remap = []; vertices = []
    for point in mesh.vertices:
        key = tuple(round(v * 1_000_000) for v in point)
        index = lookup.get(key)
        if index is None:
            index = len(vertices); lookup[key] = index; vertices.append(point)
        remap.append(index)
    triangles = [tuple(remap[i] for i in t) for t in mesh.triangles]
    kept = [t for t in triangles if len(set(t)) == 3]
    return Mesh(mesh.name, vertices, kept, mesh.removed_degenerate_triangles + len(triangles)-len(kept))


def _validate_mesh(mesh):
    if not mesh.vertices or not mesh.triangles:
        raise ConversionError('Получилась пустая сетка.')
    if any(not all(math.isfinite(v) for v in p) for p in mesh.vertices):
        raise ConversionError('В сетке обнаружены некорректные координаты.')
    if any(len(set(t)) != 3 for t in mesh.triangles):
        raise ConversionError('В сетке обнаружены вырожденные треугольники.')


def _merged(meshes):
    result = Mesh('model')
    for mesh in meshes:
        off = len(result.vertices)
        result.vertices.extend(mesh.vertices)
        result.triangles.extend((a+off, b+off, c+off) for a, b, c in mesh.triangles)
    return result


def _write_mesh(path, meshes, fmt):
    if fmt == 'obj':
        with path.open('w', encoding='utf8', newline='\n') as f:
            f.write('# Coordinates in millimetres\n')
            offset = 1
            for mesh in meshes:
                f.write(f'o {mesh.name}\n')
                for p in mesh.vertices:
                    f.write('v %.12g %.12g %.12g\n' % p)
                for a, b, c in mesh.triangles:
                    f.write(f'f {a+offset} {b+offset} {c+offset}\n')
                offset += len(mesh.vertices)
        return
    mesh = _merged(meshes)
    if fmt == 'stl':
        with path.open('wb') as f:
            f.write(b'SHAPR converter; millimetres'.ljust(80, b'\0'))
            f.write(struct.pack('<I', len(mesh.triangles)))
            for t in mesh.triangles:
                a, b, c = [mesh.vertices[i] for i in t]
                u = [b[i]-a[i] for i in range(3)]; v = [c[i]-a[i] for i in range(3)]
                normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                length = math.sqrt(sum(x*x for x in normal))
                normal = tuple(x/length for x in normal) if length else (0., 0., 0.)
                f.write(struct.pack('<12fH', *normal, *a, *b, *c, 0))
    elif fmt == 'ply':
        with path.open('wb') as f:
            f.write(('ply\nformat binary_little_endian 1.0\ncomment units millimetres\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nelement face %d\nproperty list uchar uint vertex_indices\nend_header\n' % (len(mesh.vertices), len(mesh.triangles))).encode())
            for p in mesh.vertices:f.write(struct.pack('<3f', *p))
            for t in mesh.triangles:f.write(struct.pack('<B3I', 3, *t))
    elif fmt == '3mf':
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
            z.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
            with z.open('3D/3dmodel.model', 'w') as f:
                def w(s):f.write(s.encode('utf8'))
                w('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="ru-RU" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>')
                for i, m in enumerate(meshes, 1):
                    w(f'<object id="{i}" type="model" name="{escape(m.name)}"><mesh><vertices>')
                    for x, y, zz in m.vertices:w(f'<vertex x="{x:.12g}" y="{y:.12g}" z="{zz:.12g}"/>')
                    w('</vertices><triangles>')
                    for a, b, c in m.triangles:w(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>')
                    w('</triangles></mesh></object>')
                w('</resources><build>')
                for i in range(1, len(meshes)+1):w(f'<item objectid="{i}"/>')
                w('</build></model>')
    elif fmt == 'glb':
        # glTF uses metres. Other mesh formats emitted here use millimetres.
        pos = b''.join(struct.pack('<3f', *(x/1000.0 for x in p)) for p in mesh.vertices)
        idx = b''.join(struct.pack('<3I', *t) for t in mesh.triangles)
        mins = [min(p[i] for p in mesh.vertices)/1000 for i in range(3)]
        maxs = [max(p[i] for p in mesh.vertices)/1000 for i in range(3)]
        doc = {'asset': {'version': '2.0', 'generator': 'SHAPR Converter'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}], 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]}], 'buffers': [{'byteLength': len(pos)+len(idx)}], 'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(pos), 'target': 34962}, {'buffer': 0, 'byteOffset': len(pos), 'byteLength': len(idx), 'target': 34963}], 'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': len(mesh.vertices), 'type': 'VEC3', 'min': mins, 'max': maxs}, {'bufferView': 1, 'componentType': 5125, 'count': len(mesh.triangles)*3, 'type': 'SCALAR'}]}
        js = json.dumps(doc, separators=(',', ':')).encode(); js += b' ' * (-len(js) % 4)
        binary = pos+idx; binary += b'\0' * (-len(binary) % 4)
        with path.open('wb') as f:
            f.write(struct.pack('<4sII', b'glTF', 2, 12+8+len(js)+8+len(binary)))
            f.write(struct.pack('<I4s', len(js), b'JSON')); f.write(js)
            f.write(struct.pack('<I4s', len(binary), b'BIN\0')); f.write(binary)
    else:
        raise ConversionError(f'Неизвестный формат {fmt}.')


def _write_step(path, shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from OCP.STEPControl import STEPControl_Writer, STEPControl_Reader, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    compound = TopoDS_Compound(); builder = BRep_Builder(); builder.MakeCompound(compound)
    for shape in shapes:builder.Add(compound, shape)
    writer = STEPControl_Writer()
    if writer.Transfer(compound, STEPControl_AsIs) != IFSelect_RetDone or writer.Write(str(path)) != IFSelect_RetDone:
        raise ConversionError('Не удалось записать STEP.')
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone or not reader.TransferRoots():
        raise ConversionError('Не удалось повторно прочитать STEP.')
    restored = reader.OneShape()
    if not BRepCheck_Analyzer(restored).IsValid():
        raise ConversionError('Повторная проверка STEP обнаружила некорректную геометрию.')
    for kind in (TopAbs_FACE, TopAbs_SOLID):
        counts = []
        for shape in (compound, restored):
            indexed = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(shape, kind, indexed); counts.append(indexed.Extent())
        if counts[0] != counts[1]:
            raise ConversionError('STEP потерял поверхности или тела при повторном чтении.')


def convert(source, destination, fmt='stl', tolerance=0.02, solids_only=False, progress=lambda s: None):
    source = Path(source).resolve(); destination = Path(destination).resolve()
    fmt = fmt.lower()
    if fmt not in FORMATS or not 0.001 <= tolerance <= 1.0:
        raise ConversionError('Неизвестный формат или недопустимая точность.')
    if destination.exists() or Path(str(destination)+'.json').exists():
        raise ConversionError('Результат уже существует. Выберите другое имя.')
    if not destination.parent.is_dir():
        raise ConversionError('Папка результата не существует.')
    meshes = []; shapes = []; parts = []; omitted = []; failures = []
    with tempfile.TemporaryDirectory(prefix='shapr-') as temp:
        db = Path(temp)/'workspace'
        progress('Чтение проекта')
        with zipfile.ZipFile(source) as archive:
            info = archive.getinfo('workspace')
            if info.file_size > 3 * 1024**3:
                raise ConversionError('База проекта превышает 3 ГБ.')
            with archive.open(info) as src, db.open('wb') as dst:shutil.copyfileobj(src, dst, 1024**2)
        c = sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True)
        c.execute('PRAGMA query_only=ON')
        try:
            active = _active_parts(c)
            provider = DirectorySchemaProvider(RESOURCE_DIR/'schema')
            for i, (pid, mark) in enumerate(active.items(), 1):
                progress(f'Тело {i}/{len(active)} — {pid}')
                try:
                    data = _block(c, pid)
                    if solids_only and b'psm_imesh' in data[:262144] and b'position_pool' in data[:262144]:
                        omitted.append(pid); continue
                    doc = parse_xb(data, schema_provider=provider)
                    del data
                    world = next(n for n in doc.nodes if n.node_type == 101)
                    actual_mark = _fields(world)['current_id'][0]
                    if mark != actual_mark:
                        raise ConversionError(f'Сохранённая версия {actual_mark} не совпала с последней операцией {mark}.')
                    has_mesh = any(n.definition.name == 'MESH' for n in doc.nodes)
                    if has_mesh:
                        if solids_only:
                            omitted.append(pid); continue
                        if fmt == 'step':
                            raise ConversionError('В проекте есть сеточное тело. Для STEP включите «Только точные тела» либо выберите STL/OBJ/3MF/GLB/PLY.')
                        meshes.extend(_source_meshes(doc, pid))
                    else:
                        brep = map_brep(doc)
                        result = to_occt(brep, source_unit='m', target_unit='mm', validation=ValidationTolerances(linear_absolute=1e-4, relative=1e-7))
                        if fmt == 'step':shapes.append(result.shape)
                        else:meshes.append(_tessellate(result.shape, f'body_{pid}', tolerance))
                    parts.append({'partition': pid, 'revision': mark, 'kind': 'mesh' if has_mesh else 'brep', 'body_types': [_fields(n).get('body_type', []) for n in doc.nodes if n.definition.name=='BODY']})
                    del doc
                    gc.collect()
                except Exception as exc:
                    failures.append(f'Тело {pid}: {exc}')
            if failures:
                raise ConversionError('Не удалось преобразовать весь выбранный состав проекта:\n'+'\n'.join(failures))
        finally:
            c.close()
        if not parts:
            raise ConversionError('Нет геометрии для выбранного режима.')
        for mesh in meshes:_validate_mesh(mesh)
        progress('Запись и проверка результата')
        staged = Path(temp)/('model.'+fmt)
        if fmt == 'step':_write_step(staged, shapes)
        else:_write_mesh(staged, meshes, fmt)
        if staged.stat().st_size == 0:
            raise ConversionError('Получился пустой файл.')
        all_vertices = [p for mesh in meshes for p in mesh.vertices]
        report = {'source': source.name, 'format': fmt, 'coordinates': 'm' if fmt=='glb' else 'mm', 'tessellation_deflection_mm': tolerance, 'scope': 'active_saved_bodies_including_hidden', 'solids_only': solids_only, 'omitted_mesh_partitions': omitted, 'parts': parts, 'triangles': sum(len(m.triangles) for m in meshes), 'bounding_box_mm': [[min(p[i] for p in all_vertices) for i in range(3)], [max(p[i] for p in all_vertices) for i in range(3)]] if all_vertices else None, 'notes': ['История, эскизы, чертежи, материалы и цвета не экспортируются.', 'Сохранённые активные тела включают скрытые тела; положение берётся из сохранённой геометрии.']}
        report['mesh_weld_grid_mm'] = 0.000001
        report['removed_degenerate_triangles'] = sum(m.removed_degenerate_triangles for m in meshes)
        # Exclusive creation: never replace any pre-existing user file.
        with staged.open('rb') as f:
            report['output_sha256'] = hashlib.file_digest(f, 'sha256').hexdigest()
        created = []
        try:
            with destination.open('xb') as dst, staged.open('rb') as src:
                created.append(destination); shutil.copyfileobj(src, dst)
            sidecar = Path(str(destination)+'.json')
            with sidecar.open('x', encoding='utf8') as f:
                created.append(sidecar); json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        return report
