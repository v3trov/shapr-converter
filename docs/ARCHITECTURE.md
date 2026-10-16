# SHAPR reading and conversion / Чтение и преобразование SHAPR

## Container and saved state

The supported `.shapr` files are ZIP containers holding a `workspace` SQLite
database. The application copies that entry into a temporary directory and
opens SQLite read-only with `query_only` enabled. It never extracts arbitrary
archive paths into the source directory.

The reader handles the two observed history-call payload layouts and the
`BodyRevisionPartitions` / chunked `BodyRevisionBlocks` storage variants.
History order is taken from the history root. The latest applicable saved call
determines which partitions remain active. Deleted or consumed bodies are
excluded. Each included partition's `WORLD.current_id` must match the saved
call's revision; a mismatch fails the conversion.

This is a container-specific state-selection implementation tested on the
author's corpus. It is not a general interpreter of arbitrary Parasolid delta
streams and does not claim to reconstruct editable Shapr3D history. The delta
data are not exported or blindly appended to a partition.

## Geometry

`parasolid-kit` parses the binary transmit data using the explicit 13006 base
schema distributed with `ps-parser`. Merely replacing a version number does
not make an unsupported schema safe; the original stream keys are retained.

Supported exact B-Reps are converted by the library's general parametric
OpenCascade builder, including vertex-trimmed analytic circles. The application
selects that builder while retaining the library's boundary, face, and shape
checks. Conversion validation uses a 0.0001 mm absolute and 1e-7 relative
tolerance. Those thresholds are not a certificate of continuous global error.

Imported meshes are read from supported `PSM_MESH`, vector-comb, and integer-comb
records. One-based triangle indices, orientation, affine mesh transforms, and
stored world-space bounds are checked. Multi-body mesh partitions and unsupported
encodings fail explicitly. Mesh patches belonging to the single body are joined.

Model-space lengths are converted from metres to millimetres. GLB positions are
written in metres as required by glTF. The other mesh outputs use millimetres.

Exact bodies are tessellated with a default 0.02 mm linear deflection and 0.15 rad
angular setting. Duplicate boundary vertices are joined on a 0.000001 mm grid,
retaining the first coordinate. Any triangle collapsed by joining is removed and
counted in the report. No automatic Boolean fusion of overlapping bodies occurs.

## Export validation

The writer checks non-empty geometry, finite mesh coordinates, and non-collapsed
triangle indices. STEP is read back with OpenCascade and checked for validity,
face counts, and solid counts before the output is published. Existing outputs
are rejected. A failed final file copy or report write removes only files created
by that invocation.

The initial manual validation also used independent Trimesh reimport to check
mesh triangle counts and bounding boxes, with GLB unit conversion. Source sheets
can remain open, and conversion success does not imply a model is a single closed
solid suitable for printing. The shipped application does not require Trimesh.

## Reproducibility

- Python 3.12.4 x64 and Windows 10 x64 were used for the initial build.
- `parasolid-kit` 0.3.7; OCP / OpenCascade 7.9.3.1.1; msgpack 1.2.3.
- Base schema provenance: `khoanguyen-3fc/ps-parser`, commit
  `887f7b3be1e500d79583c133129b5d845cc1498c`, `assets/sch_13006.s_t`.
- The 18 source projects are private. Eleven converted in the initial tests;
  the other seven failed on the unsupported geometry described in the README.
- This repository's build workflow checks packaging and imports, not private
  corpus compatibility. Downloadable binaries are provided in GitHub Releases.

## Кратко по-русски

Конвертер читает SQLite из контейнера `.shapr`, определяет активные секции по
порядку истории и сверяет сохранённую версию каждой секции с последней операцией.
Это позволяет исключить поглощённые детали и не выдать старую версию тела за
текущую. Общего интерпретатора произвольных потоков изменений Parasolid здесь нет.

Точные тела преобразуются через parasolid-kit и OpenCascade с проверками границ
и поверхностей. Поддержанные импортированные сетки читаются отдельно, с проверкой
индексов, ориентации, преобразования и сохранённых границ. Исходные координаты
переводятся из метров в миллиметры; GLB записывается в метрах.

Успех означает экспорт выбранного поддерживаемого состава геометрии. Он не
означает восстановление истории Shapr3D, автоматическое исправление исходной
модели или обязательную пригодность каждого тела к 3D-печати.
