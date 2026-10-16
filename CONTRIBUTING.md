# Contributing / Как помочь проекту

Geometry support and reproducible bug reports are the most useful contributions.
Include the converter version, the original Shapr3D version if known, the exact
error, and whether the failure happens with exact bodies only.

Only attach a `.shapr` file if you own it or have permission to publish it.
A minimal model that reproduces the problem is preferable to a private project.
Do not include credentials, account data, or unrelated files.

For geometry changes, describe what changed and validate exported geometry by
reimporting it. Compare units, bounds, face/body or triangle counts, validity,
and relevant edge cases. A parser returning without an exception does not by
itself establish correct final-state geometry.

The Windows build is described in `BUILD.ps1`. The public CI builds and imports
the application; it does not run the author's private model corpus.

---

Больше всего помогут поддержка новых типов геометрии и воспроизводимые ошибки.
Укажите версию конвертера, известную версию Shapr3D, точный текст ошибки и
результат с опцией «Только точные тела».

Прикладывайте только файлы, которые вправе публиковать. Лучше подготовить
небольшую модель, воспроизводящую проблему. Для исправлений геометрии нужна
проверка повторным импортом: единицы, размеры, состав тел, поверхности или
треугольники и корректность результата.

CI собирает приложение и проверяет импорт модулей. Личный набор моделей автора
не включён в репозиторий и не запускается в публичном CI.
