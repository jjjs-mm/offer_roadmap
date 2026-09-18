# AGENTS.md

## Cursor Cloud specific instructions

This repository is **documentation-only**. It contains Markdown files (a
Chinese-language job-hunting roadmap and knowledge base) plus a `LICENSE`. There
is intentionally **no application code, no dependency manifest, no build system,
and no test framework**. The `scripts/` and `projects/` directories currently
hold only `README.md` design docs describing work that has not been written yet.

Implications for future agents:

- **Dependencies / update script:** nothing to install. There is no
  `package.json`, `requirements.txt`, lockfile, or similar. The startup update
  script is intentionally a no-op.
- **Lint:** no linter is configured. If you want to sanity-check Markdown, you
  can optionally run `npx markdownlint-cli2 "**/*.md"` (requires network the
  first time); it is not part of the repo and not required for changes.
- **Tests:** there are no automated tests to run.
- **Build / run (preview):** the "product" is the rendered documentation. To
  preview it, serve the repo root and open it in a browser:
  `python3 -m http.server 8080` (Python stdlib, already available). Raw Markdown
  is then served at `http://localhost:8080/<path>.md`. For a rendered view with
  the **Mermaid** diagrams (the docs use ```` ```mermaid ```` code fences, e.g.
  the flowchart in `README.md` and the architecture diagram in
  `projects/README.md`), use any Markdown renderer with Mermaid support — GitHub
  renders these natively, or point a local Markdown viewer (marked.js +
  mermaid.js, docsify, grip, etc.) at the folder.
- **Content language:** documents are primarily in Chinese; `README.md` is the
  entry point and links to everything else.
