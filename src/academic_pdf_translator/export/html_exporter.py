"""Self-contained escaped HTML; credentials and provider URLs are never embedded."""

from html import escape
from pathlib import Path
from urllib.parse import urlencode

from academic_pdf_translator.pir.models import Block, Document
from academic_pdf_translator.pir.serializer import atomic_write

CSS = """
:root{color-scheme:light;--ink:#203a47;--muted:#617580;--paper:#f3f5f1;--line:#d9e1df}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.75 system-ui,'Microsoft YaHei',sans-serif}
main{max-width:1160px;margin:0 auto;padding:42px 28px}header{border-bottom:2px solid #326a62;padding-bottom:28px}
.eyebrow{font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#326a62}h1{font:600 34px/1.3 Georgia,serif;margin:12px 0}
.meta,.label{color:var(--muted);font-size:13px}.summary{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}.summary span{background:white;padding:8px 16px;border:1px solid var(--line);border-radius:8px}
.page{margin-top:34px}.page h2{font-size:18px;border-bottom:1px solid var(--line);padding-bottom:8px}
article{background:white;border:1px solid var(--line);border-radius:10px;margin:16px 0;padding:20px 24px;break-inside:avoid}
.bar{display:flex;justify-content:space-between;gap:12px;align-items:center;font-size:12px}.badge{border-radius:20px;padding:3px 10px;background:#edf1f2;color:#566872}
.ok{background:#e5f3eb;color:#24644b}.risk{background:#fff0dc;color:#885b16}.columns{display:grid;grid-template-columns:1fr 1fr;gap:32px;margin-top:18px}
.text{white-space:pre-wrap;overflow-wrap:anywhere}.source{font-family:Georgia,'Times New Roman',serif}.label{margin-bottom:6px;font-size:11px;letter-spacing:1px}
a{color:#21695e}details{margin-top:16px;border-top:1px solid var(--line);padding-top:10px}summary{cursor:pointer}ul{padding-left:22px}.notice{padding:12px 16px;background:#fff3e1;border-radius:6px;margin:12px 0}
.explain{display:inline-block;margin-top:12px;font-size:13px}.role{border-left:3px solid #7ba299;padding-left:14px}footer{margin-top:36px;color:var(--muted);font-size:12px}
@media(max-width:740px){main{padding:22px 14px}.columns{grid-template-columns:1fr;gap:18px}article{padding:16px}h1{font-size:27px}.bar{align-items:flex-start}}
@media print{body{background:white}main{padding:0}.explain{display:none}}
"""


def badge(block: Block) -> tuple[str, str]:
    if block.translation_status == "demo":
        return "risk", "DEMO · 未翻译"
    if block.translation_status == "retained":
        return "", "保留原文 · 未校验"
    if block.translation_status == "pending":
        return "", "尚未翻译"
    if block.check and block.check.passed and block.confidence >= 0.7 and not block.warnings:
        return "ok", "✓ verified · 规则通过"
    return "risk", "⚠ translation risk"


def render_html(document: Document) -> str:
    """Render document text as data, never executable markup."""
    verified = sum(badge(b)[0] == "ok" for b in document.blocks)
    stats = document.processing
    chunks = [
        f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(document.title)} · AcademicPDFTranslator</title><style>{CSS}</style></head><body><main><header><div class="eyebrow">AcademicPDFTranslator / v0.2-dev</div><h1>{escape(document.title)}</h1><div class="meta">{escape(document.filename)} · {escape(document.target_language)} · {escape(document.model or "native parser")} · {escape(document.status)}</div><div class="summary"><span>{len(document.pages)} 页</span><span>{len(document.blocks)} 文本块</span><span>{verified} 规则通过</span><span>API {stats.provider_calls} / 缓存 {stats.cache_hits} / 续传 {stats.resumed_blocks}</span></div><div class="meta">verified 仅表示确定性学术标记检查通过，不代表语义准确。低置信度版面需要人工复核。</div></header>'
    ]
    for warning in document.warnings:
        chunks.append(f'<div class="notice">{escape(warning)}</div>')
    for page in document.pages:
        chunks.append(
            f'<section class="page"><h2>Page {page.page} <span class="meta">{escape(page.layout)}</span></h2>'
        )
        for warning in page.warnings:
            chunks.append(f'<div class="notice">{escape(warning)}</div>')
        for block in page.blocks:
            style, status = badge(block)
            chunks.append(
                f'<article id="{escape(block.block_id, quote=True)}"><div class="bar"><span>{escape(block.block_id)} · {escape(block.block_type)} · {escape(block.section)} · {escape(block.translation_origin)}</span><span class="badge {style}">{escape(status)}</span></div><div class="columns"><div><div class="label">ORIGINAL</div><div class="text source">{escape(block.text)}</div></div><div><div class="label">TRANSLATION</div><div class="text">{escape(block.translation or "尚未翻译")}</div></div></div>'
            )
            warnings = list(block.warnings)
            if block.check:
                warnings.extend(
                    f"{e.type}: {e.message or e.source + ' → ' + e.translation}"
                    for e in block.check.errors
                )
            if warnings:
                chunks.append(
                    "<details><summary>检查详情 / Warnings</summary><ul>"
                    + "".join(f"<li>{escape(w)}</li>" for w in warnings)
                    + "</ul></details>"
                )
            if block.explanation:
                exp = block.explanation
                chunks.append(
                    f'<details open><summary>PaperExplain</summary><p class="text">{escape(exp.plain_explanation)}</p><p class="role text">{escape(exp.role_in_paper)}</p><ul>'
                )
                chunks.extend(
                    f"<li><b>{escape(t.term)}</b> — {escape(t.explanation)}</li>"
                    for t in exp.key_terms
                )
                chunks.append(f'</ul><p class="meta">{escape(exp.warning)}</p></details>')
            else:
                query = urlencode({"document": document.document_id, "block": block.block_id})
                chunks.append(
                    f'<a class="explain" href="http://localhost:8501/?{escape(query, quote=True)}" target="_blank" rel="noopener noreferrer">Explain ↗</a>'
                )
            chunks.append("</article>")
        chunks.append("</section>")
    chunks.append(
        "<footer>Explain 需要本地 Web UI：运行 python app.py，再打开链接。若使用自定义输出目录，请在 UI 导入 document.json。离线 HTML 不直接调用 API。© AcademicPDFTranslator · AGPL-3.0-or-later</footer></main></body></html>"
    )
    return "\n".join(chunks)


def export_html(document: Document, path: str | Path) -> Path:
    path = Path(path)
    atomic_write(path, render_html(document))
    return path
