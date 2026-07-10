# -*- coding: utf-8 -*-
from pathlib import Path
p = Path(r"d:\MONEY\My_Library\app\static\css\style.css")
t = p.read_text(encoding="utf-8")
start = t.index("/* 오버레이: ���버스 ��을 줄이지 않음")
end = t.index(".graph-shared-topic-tooltip {")
new_block = r"""/* 오버��버스 ��을 줄이지 않음 (그래프 SVG clientWidth 유지) */
.graph-detail-panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  width: 340px;
  box-sizing: border-box;
  padding: 20px;
  padding-top: 48px;
  overflow-y: auto;
  overflow-x: hidden;
  background: #161b22;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.35);
  transform: translateX(100%);
  opacity: 0;
  pointer-events: none;
  transition: transform 200ms ease, opacity 200ms ease;
}

#libraryGraphView.graph-detail-open .graph-detail-panel {
  transform: translateX(0);
  opacity: 1;
  pointer-events: auto;
}

.graph-detail-panel-inner {
  min-height: 0;
}

.gdp-close {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #8b949e;
  font-size: 1.35rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gdp-close:hover {
  color: #ffffff;
}

.gdp-body {
  padding: 0;
  font-size: 13px;
  color: #c9d1d9;
  line-height: 1.6;
}

.gdp-panel-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: #e6edf3;
  line-height: 1.35;
  word-break: break-word;
  padding-right: 28px;
}

.gdp-panel-date {
  font-size: 11px;
  color: #8b949e;
  margin-bottom: 16px;
  line-height: 1.4;
}

.gdp-rule {
  border: none;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  margin: 0;
}

.gdp-subhead {
  font-size: 12px;
  color: #8b949e;
  margin-top: 12px;
  margin-bottom: 8px;
  font-weight: 600;
}

.gdp-prose {
  font-size: 13px;
  color: #c9d1d9;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.gdp-prose--empty {
  color: #8b949e;
}

.gdp-section {
  margin-bottom: 14px;
}

.gdp-section h4 {
  margin: 0 0 6px;
  font-size: 0.78rem;
  color: var(--accent);
  font-weight: 600;
}

.gdp-meta {
  font-size: 11px;
  color: #8b949e;
  margin: 0 0 8px;
  line-height: 1.5;
}

.gdp-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 10px;
}

.gdp-tag {
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 11px;
  color: #c9d1d9;
}

.gdp-wiki-snippet {
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(0, 0, 0, 0.2);
  padding: 8px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: #c9d1d9;
  line-height: 1.6;
}

.gdp-linked-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.gdp-linked-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
  color: #e6edf3;
}

.gdp-linked-item:last-child {
  border-bottom: none;
}

.gdp-linked-item:hover .gdp-linked-title {
  color: #58a6ff;
}

.gdp-linked-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.gdp-linked-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  line-height: 1.4;
}

.gdp-neighbor-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.gdp-neighbor-list li {
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
  color: var(--text-primary);
}

.gdp-neighbor-list li:hover {
  color: var(--accent);
}

"""
t2 = t[:start] + new_block + t[end:]
p.write_text(t2, encoding="utf-8")
print("css ok")
