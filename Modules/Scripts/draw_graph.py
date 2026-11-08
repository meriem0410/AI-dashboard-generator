"""
Modules/Scripts/draw_graph.py

Draws the panel graph (the Query Generation Agent) for the report.

    python Modules/Scripts/draw_graph.py

Writes to docs/figures/:
    panel_graph.mmd   the Mermaid text (always)
    panel_graph.md    the same inside a fenced block, previews in VS Code / GitHub
    panel_graph.png   a picture, if the Mermaid web renderer can be reached

If the picture fails, open https://mermaid.live , paste the content of
panel_graph.mmd and export PNG or SVG from there.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")

from Modules.graph_panel import build_panel_graph

out_dir = ROOT / "docs" / "figures"
out_dir.mkdir(parents=True, exist_ok=True)

drawable = build_panel_graph(None).get_graph()    # no database needed to draw
mermaid = drawable.draw_mermaid()

(out_dir / "panel_graph.mmd").write_text(mermaid, encoding="utf-8")
(out_dir / "panel_graph.md").write_text("```mermaid\n" + mermaid + "\n```\n", encoding="utf-8")
print("written:", out_dir / "panel_graph.mmd")
print("written:", out_dir / "panel_graph.md")

try:
    png = drawable.draw_mermaid_png()
    (out_dir / "panel_graph.png").write_bytes(png)
    print("written:", out_dir / "panel_graph.png")
except Exception as e:
    print("\nCould not make the PNG automatically:", str(e)[:150])
    print("Open https://mermaid.live , paste panel_graph.mmd, export PNG or SVG.")
