# Resume Studio notices

## Original templates

The 9 layout families in `apps/api/app/resume_studio_typst/base.typ`, their 18 Chinese/English catalog entries, and the fictitious gallery samples were created for AI Career OS. Catalog marker: `LicenseRef-AICareerOS-Original`, source version `1.0.0`. No third-party resume template source, images, icons, or fonts are included in these files. This marker documents provenance; it does not add a repository-wide public license.

## Typst runtime

The renderer calls the separately installed **Typst CLI 0.15.1**. The CLI binary is not committed or redistributed in this repository. The official Windows release archive used for development contained `LICENSE` (Apache License 2.0) and `NOTICE`; retain both when installing or redistributing that binary. Source: <https://github.com/typst/typst/releases/tag/v0.15.1>.

Set `TYPST_BIN` to the absolute executable path, or place `typst` on `PATH`. Check with `typst --version`. The renderer does not execute user-authored Typst code; it passes JSON text to fixed project-owned templates.

## Fonts

The templates request `Microsoft YaHei`, `Noto Sans CJK SC`, `Libertinus Sans`, and `Arial` as fallbacks. These are resolved from the host's font installation and are **not redistributed** in this repository or the generated preview assets. Microsoft YaHei and Arial are system fonts subject to their platform terms. Noto Sans CJK and Libertinus Sans can be installed from their respective upstream distributions under their own open font licenses; retain those notices if packaged. Record `typst fonts` in each release environment and verify Chinese and English glyph coverage before deployment.

## PDF inspection dependency

The existing API dependency `pymupdf==1.25.1` is used to verify page counts and extracted text. PyMuPDF is distributed under AGPL-3.0 or a commercial license; review the project's distribution model and license obligations before public deployment. It was already present in `apps/api/requirements.txt` before Resume Studio work.
