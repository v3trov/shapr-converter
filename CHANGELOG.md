# Changelog / История версий

## 0.1.0 — 2026-10-16

First experimental release of SHAPR Converter.

- Offline Windows x64 GUI and command-line entry point.
- SHAPR export to STL, OBJ, 3MF, GLB, PLY, and supported exact STEP geometry.
- Two observed container layouts, revision matching, consumed-body exclusion,
  mesh transforms, and joins between repeated face-boundary vertices.
- Refusal to overwrite existing outputs or report incomplete selected projects
  as successful conversions.
- Initial test set: 11/18 projects converted; seven geometry failures documented.
- English and Russian documentation; author: [v3trov.pro](https://v3trov.pro/).

Первая экспериментальная версия: автономная Windows-сборка, шесть выходных
форматов, сверка состояний тел и отчёты о конвертации. Проверенный результат —
11 успешных преобразований из 18 проектов. Ограничения указаны в README.
