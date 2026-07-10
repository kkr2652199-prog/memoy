# -*- coding: utf-8 -*-
from pathlib import Path
p = Path(r"d:\MONEY\My_Library\app\static\index.html")
t = p.read_text(encoding="utf-8")
old = """          <aside id=\"graphDetailPanel\" class=\"graph-detail-panel\" aria-hidden=\"true\">\n            <div class=\"graph-detail-panel-inner\">\n              <div class=\"gdp-head\">\n                <h3 class=\"gdp-title\" id=\"graphDetailTitle\">\uc0c1\uc138</h3>\n                <button type=\"button\" class=\"gdp-close\" id=\"graphDetailPanelClose\" aria-label=\"\ub2eb\uae30\">&times;</button>\n              </div>\n              <div class=\"gdp-body\" id=\"graphDetailBody\"></div>\n            </div>\n          </aside>"""
new = """          <aside id=\"graphDetailPanel\" class=\"graph-detail-panel\" aria-hidden=\"true\">\n            <button type=\"button\" class=\"gdp-close\" id=\"graphDetailPanelClose\" aria-label=\"\ub2eb\uae30\">&times;</button>\n            <div class=\"graph-detail-panel-inner\">\n              <div class=\"gdp-body\" id=\"graphDetailBody\"></div>\n            </div>\n          </aside>"""
if old not in t:
    raise SystemExit("block not found")
p.write_text(t.replace(old, new, 1), encoding="utf-8")
print("index ok")
