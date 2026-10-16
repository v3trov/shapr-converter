# SHAPR Converter — Shapr3D to STL, STEP, OBJ, 3MF, GLB and PLY

[Русский](README.ru.md) · **English** · [Download for Windows](https://github.com/v3trov/shapr-converter/releases/latest) · [Author's blog: v3trov.pro](https://v3trov.pro/)

[![Latest release](https://img.shields.io/github/v/release/v3trov/shapr-converter?include_prereleases)](https://github.com/v3trov/shapr-converter/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Windows x64](https://img.shields.io/badge/Windows-x64-0078D4)](https://github.com/v3trov/shapr-converter/releases)

**An offline Windows tool for converting supported Shapr3D `.shapr` projects to common CAD and 3D mesh formats.** The packaged application runs without Shapr3D, an installed Python runtime, a CAD subscription, or an internet connection.

**Experimental compatibility: 11 of 18 author-owned projects converted successfully in the initial test set.** Seven projects still encounter unsupported geometry or fail validation. This is a working recovery tool with documented limits, not a universal SHAPR reader.

## Download and convert a SHAPR file

1. Download `ShaprConverter-v0.1.0-Windows-x64.zip` from [Releases](https://github.com/v3trov/shapr-converter/releases).
2. Extract the complete archive. Keep the `_internal` directory beside `ShaprConverter.exe`.
3. Run `ShaprConverter.exe`, choose a `.shapr` file, an output filename, and a format.
4. Click **Конвертировать** (Convert). The initial GUI is in Russian; the command-line options are listed below.

The converter reads the source file without modifying it. It refuses to overwrite an existing output. A JSON report records the exported body revisions, units, mesh settings, omitted mesh bodies, and output SHA-256.

## Export formats

| Output | Geometry and units | Use |
| --- | --- | --- |
| STL | Triangle mesh, millimetres | Slicers and 3D printing workflows |
| OBJ | Triangle mesh, millimetres | Blender and other 3D applications |
| 3MF | Triangle mesh, explicit millimetre units | Slicers; separate exported bodies |
| GLB / glTF 2.0 | Triangle mesh, metres | Viewers and web-based 3D tools |
| PLY | Binary triangle mesh, millimetres | Mesh processing |
| STEP | Supported exact CAD geometry | Further work in CAD software |

For STEP, a project containing imported mesh geometry requires the explicit **Только точные тела** (Exact bodies only) option. That option excludes mesh bodies and records the omission; it does not turn a mesh into an exact CAD solid. Sheets can also be present in the saved geometry.

The default tessellation deflection is **0.02 mm**. This is a meshing setting, not a certified end-to-end accuracy guarantee. Imported meshes retain their source detail. Repeated boundary vertices are joined on a 0.000001 mm grid; triangles collapsed by that operation are removed and counted in the report.

## Why I made this

Shapr3D is genuinely convenient to model in. I enjoyed using it and made a lot of projects with it. But its subscription costs more than I can justify for my own use, and I am not willing to keep paying for it.

A friend had helped me get temporary access to a subscription. Before that access ended, I saved my projects as native `.shapr` files to preserve their geometry and project data rather than settling for a low-detail mesh export. My plan was simple: keep my own work, and convert it to accessible formats later if an opportunity came along.

As AI coding tools improved, I wondered whether this could become a small practical experiment: could I make a useful converter in about an hour of vibe coding? The result is this project. It reads supported saved geometry, converts it, and has already helped me recover usable models from my `.shapr` archive. The initial reproducible result is 11 successful conversions out of 18 tested projects; the remaining cases are still work to do.

I strongly disagree with Shapr3D's approach to export after a subscription ends. In my view, people should retain a straightforward way to export their own designs at full quality into common formats, without renewing a subscription just to retrieve their work in a usable form. I criticize that product decision precisely because the modeling experience itself is so good.

For accuracy: [Shapr3D Basic does officially allow low-resolution STL and 3MF export](https://support.shapr3d.com/hc/en-us/articles/7872024839452-Shapr3D-Basic). My objection is to the limits on high-quality and neutral CAD export, not a claim that every export option disappears.

## What is preserved, and what is not

The converter exports **active saved bodies, including hidden bodies**, using the positions stored in their geometry. It checks each saved partition's revision against the latest applicable history operation and excludes bodies consumed or deleted by operations.

It does not export sketches, the editable feature history, drawings, materials, colors, or a reconstructed Shapr3D project tree. Separate or overlapping bodies are not automatically fused. A source sheet or open mesh is not automatically repaired into a printable solid.

If any required body in the selected scope cannot be converted, the application reports an error rather than presenting an incomplete project as a successful conversion. Keep the original `.shapr` files.

## Compatibility and validation

The first test set contained 18 real projects belonging to the author. Eleven exported to 3MF, including two `.shapr` containers of approximately 489 MB. One supported project was also exported to STL, OBJ, PLY, GLB, and STEP; STEP used exact bodies only.

Checks included:

- Independent mesh reimport, triangle counts, finite coordinates, and bounding boxes with unit conversion.
- STEP reimport, OpenCascade geometry validity, and preservation of face and solid counts.
- Refusal to export an intentionally mismatched saved revision.
- Preservation of an existing output file.
- GUI initialization and execution of the packaged EXE with external Python removed from `PATH`.

Known failures involve swept surfaces, some surface-parameter curve variants, invalid reconstructed parametric faces, or UV trims that disagree with source points. New Shapr3D versions and untested modeling features may require more work. Private source models are not included in this repository or its releases.

See [architecture and validation notes](docs/ARCHITECTURE.md) for the implementation boundaries.

## Command line

```powershell
ShaprConverter.exe model.shapr -o model.stl -f stl
ShaprConverter.exe model.shapr -o model.3mf -f 3mf --tolerance 0.02
ShaprConverter.exe model.shapr -o model.step -f step --solids-only
```

Exit code `0` means success; `1` means failure. The Windows GUI build does not print console diagnostics. On success, the output and its `.json` report are created.

To get console messages when running from source:

```powershell
python ShaprConverter.py model.shapr -o model.obj -f obj
```

## Run from source or build the Windows application

Use Python **3.12 x64** with Tk support. The released dependencies are pinned in `requirements.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ShaprConverter.py
```

Run `BUILD.ps1` to create `dist/ShaprConverter/ShaprConverter.exe`. Dependency installation needs internet access; conversion itself is local. The tested desktop target is Windows x64; other platforms are not validated.

## Frequently asked questions

### Can I convert SHAPR to STL without Shapr3D installed?

Yes, for models supported by this converter. Use the Windows release and select STL. Check the compatibility limits above.

### Does SHAPR to STEP preserve editable geometry?

For supported exact bodies it exports CAD geometry, not a triangle mesh disguised as STEP. It does not preserve Shapr3D's parametric feature history. Imported meshes are excluded only when explicitly requested.

### Are my models uploaded to an online conversion service?

No. The application reads and converts files locally. It has no conversion service, account login, or telemetry integration.

### Will every SHAPR project work?

No. The initial verified result is 11 out of 18 projects. If your model fails, [open an issue](https://github.com/v3trov/shapr-converter/issues) with the error, application version, and Shapr3D version if known. Only attach a model you are willing to make public.

## Author and contributions

Created by **v3trov**. Author's blog: **[v3trov.pro](https://v3trov.pro/)**.

Bug reports, reproducible examples, and geometry support improvements are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

The application code is available under the [MIT License](LICENSE). Third-party components retain their own licenses; see [THIRD_PARTY.txt](THIRD_PARTY.txt) and `licenses/`. The reader and CAD conversion depend on **parasolid-kit**, **OpenCascade / OCP**, and the base schema distributed with **ps-parser**; the project builds on that work.

This is an independent project and is not affiliated with Shapr3D or Siemens.
