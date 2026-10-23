"""Generate offline review from actual Chrome captures (not synthetic images)."""
from pathlib import Path
import base64
import difflib
import hashlib
import html
import json

root = Path(__file__).resolve().parents[1]
out = root / "artifacts/stage9/branding"
metrics = json.loads((out / "browser-metrics.json").read_text(encoding="utf-8"))
units = json.loads((out / "unit-results.json").read_text(encoding="utf-8"))
assert metrics["status"] == "passed" and not metrics["componentsOnly"]
assert len(metrics["reports"]) == 22
assert units["success"] and units["numPassedTests"] == 15 and units["numPendingTests"] == 0
assert not metrics["errors"] and not metrics["unexpectedRequests"]

# Preserve an exact minimal diff for the parent (not a Git workspace).
diff = []
for name in ("brand.css", "Login.tsx", "styles.css", "ui.tsx"):
    before = (out / "baseline" / name).read_text(encoding="utf-8").splitlines(keepends=True)
    after = (root / "frontend/src" / name).read_text(encoding="utf-8").splitlines(keepends=True)
    diff.extend(difflib.unified_diff(before, after, fromfile=f"baseline/{name}", tofile=f"frontend/src/{name}"))
(out / "source-diff.patch").write_text("".join(diff), encoding="utf-8")
manifest = json.loads((out / "baseline-manifest.json").read_text(encoding="utf-8"))
assets = {name: hashlib.sha256((root / "frontend/public" / name).read_bytes()).hexdigest() == value for name, value in manifest["publicAssets"].items()}
assert len(assets) == 8 and all(assets.values())
build = json.loads((out / "fixture-build.json").read_text(encoding="utf-8"))
build_source_match = {}
for record in build["records"]:
    for source, digest in record["sources"].items():
        build_source_match[source] = hashlib.sha256((root / "frontend" / source).read_bytes()).hexdigest() == digest
for source in ("src/brand.css", "src/Login.tsx", "src/ui.tsx", "src/styles.css"):
    assert build_source_match[source], f"Owned source changed after tested build: {source}"

embedded = []
def image(file: str, label: str) -> str:
    data = (out / file).read_bytes()
    embedded.append(file)
    url = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    return f'<figure><button class="shot" aria-label="放大：{html.escape(label)}"><img src="{url}" alt="{html.escape(label)}" loading="lazy"></button><figcaption>{html.escape(label)} · 点击按原始像素查看</figcaption></figure>'

def pair(view: str, label: str, suffix: str = "") -> str:
    return '<h3>' + label + '</h3><div class="pair">' + image(f"login-standard-{view}{suffix}.png", "浅色预览 · " + label) + image(f"login-panel-{view}{suffix}.png", "深色 panel 对照 · " + label) + '</div>'

sections = pair("desktop", "完整 Login · 1440 × 1000")
sections += pair("mobile", "完整 Login · 390 × 844")
sections += pair("wide", "完整 Login · 3771 × 1974")
sections += pair("wide", "3771 宽屏的实际 Login 卡片裁切（不是另一张小窗口截图）", "-card")
sections += '<h2 id="sidebar">已实现的横向 Sidebar</h2><div class="pair">'
sections += image("app-student-desktop.png", "实际 App · synthetic student · 1440 × 1000")
sections += image("app-student-mobile.png", "实际 App · synthetic student mobile drawer · 390 × 844")
sections += '</div><details><summary>教师中间断点及 standard Sidebar 对照</summary><div class="pair">'
sections += image("app-teacher-boundary.png", "实际 App · synthetic teacher · 821 × 900")
sections += image("sidebar-standard-desktop.png", "独立 horizontal standard brand fixture · 1440 × 1000")
sections += '</div></details>'
light = html.escape((out / "preview.html").read_text(encoding="utf-8"), quote=True)
panel = html.escape((out / "login-panel-preview.html").read_text(encoding="utf-8"), quote=True)
rows = []
for r in metrics["reports"]:
    if r["mode"] == "Login preview" and r["appearance"] == "standard":
        v = r["viewport"]
        rows.append(f'<tr><td>{v["width"]} × {v["height"]}</td><td>{r["brand"]["width"]:.2f} × {r["brand"]["height"]:.2f}</td><td>{r["mark"]["width"]:.0f} × {r["mark"]["height"]:.2f}</td><td>{r["name"]["fontSize"]}</td><td>{r["tagline"]["fontSize"]}</td></tr>')
review = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stage9 · Login / Sidebar 离线评审</title>
<style>
:root{font-family:"Segoe UI","Microsoft YaHei",sans-serif;color:#23352e;background:#f6f7f3;line-height:1.6}*{box-sizing:border-box}body{margin:0}main{max-width:1600px;margin:auto;padding:28px}h1{font-size:30px}h2{margin-top:40px}.notice{padding:18px 22px;border:1px solid #dce4df;background:#edf3ee;border-radius:12px}a{color:#1f5d50}nav{display:flex;flex-wrap:wrap;gap:18px;margin:20px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:22px}figure{margin:0 0 24px;min-width:0}.shot{padding:0;border:1px solid #dce4df;border-radius:12px;overflow:hidden;width:100%;background:white;cursor:zoom-in}.shot img{display:block;width:100%;height:auto}figcaption{font-size:13px;margin-top:8px}summary{cursor:pointer;padding:14px 0;font-weight:600}iframe{width:100%;height:900px;border:1px solid #dce4df;border-radius:12px;background:white}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;border:1px solid #dce4df;text-align:left}.table-scroll{overflow-x:auto}dialog{width:94vw;height:94vh;max-width:none;max-height:none;border:1px solid #87978d;border-radius:12px;padding:12px;background:#fff}dialog::backdrop{background:#23352eaa}.toolbar{display:flex;gap:16px;align-items:center;padding-bottom:10px}.toolbar button{padding:8px 14px;cursor:pointer;border:1px solid #87978d;border-radius:6px;background:#edf3ee}.zoom{height:calc(100% - 50px);overflow:auto}.zoom img{display:block;width:auto;max-width:none}.zoom.fit img{max-width:100%;height:auto}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #947128;outline-offset:3px}@media(max-width:820px){main{padding:18px}.pair{grid-template-columns:1fr}h1{font-size:24px}}
</style></head><body><main><h1>Stage9 · Login / Sidebar 离线评审</h1>
<div class="notice"><strong>浅底绿线 Login 仅供预览，生产默认仍为深色 panel，待 friend Z 决定。</strong><br>Sidebar 已改为左 logo、右名称 + tagline；保留绿色品牌面板。以下均为真实 Chrome 截图，不是绘制的 mockup。预览输入与认证按钮禁用；未输入密码，也未进行真实登录、模型或搜索调用。</div>
<nav><a href="#login">完整 Login 对照</a><a href="#sidebar">横向 Sidebar</a><a href="#live">自包含可渲染预览</a><a href="preview.html" target="_blank">单独打开浅色预览</a><a href="login-panel-preview.html" target="_blank">单独打开 panel 对照</a></nav>
<h2 id="login">浅色 standard / 深色 panel · 同尺寸完整 Login</h2>'''
review += sections
review += '<h2 id="live">自包含可渲染预览</h2><p>CSS、JS 与原 V4 SVG 均内嵌。此评审 HTML 可独立复制，仍能展开下列两种预览；宽度跟随各自 iframe，截图部分才是已标注的实际 viewport。</p><details id="live-previews"><summary>展开实际浅色 / panel Login（仅展示，不提供认证）</summary><div class="pair"><section><h3>浅色 standard</h3><iframe title="Safe light Login preview" sandbox="allow-scripts" srcdoc="' + light + '"></iframe></section><section><h3>深色 panel</h3><iframe title="Safe panel Login preview" sandbox="allow-scripts" srcdoc="' + panel + '"></iframe></section></div></details>'
review += '<h2>实际 CSS 尺寸</h2><div class="table-scroll"><table><thead><tr><th>Viewport</th><th>品牌组</th><th>V4 图标</th><th>名称字号</th><th>Tagline</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
review += f'<p>Chrome {metrics["browser"]} · {len(metrics["reports"])} 条最终 measured view records · {units["numPassedTests"]}/{units["numTotalTests"]} 本 lane 单元/保留回归通过 · 0 page errors · 0 auth writes。实际 App 身份由隔离 fixture 的 synthetic GET responses 提供；不是后端认证或部署验收。</p>'
review += '''</main><dialog id="viewer"><div class="toolbar"><button id="close">关闭</button><button id="fit">适应窗口 / 1:1 原像素</button><span id="caption"></span></div><div class="zoom"><img alt=""></div></dialog><script>
const dialog=document.getElementById('viewer'),zoom=dialog.querySelector('.zoom'),large=zoom.querySelector('img');document.querySelectorAll('.shot').forEach(button=>button.addEventListener('click',()=>{const image=button.querySelector('img');large.src=image.src;large.alt=image.alt;document.getElementById('caption').textContent=image.alt;zoom.classList.remove('fit');dialog.showModal()}));document.getElementById('close').onclick=()=>dialog.close();document.getElementById('fit').onclick=()=>zoom.classList.toggle('fit');
</script></body></html>'''
(out / "review.html").write_text(review, encoding="utf-8")
summary = {"status":"generated", "embeddedScreenshots":embedded,"embeddedScreenshotCount":len(embedded),"standaloneReview":str(out / "review.html"),"standaloneLightPreview":str(out / "preview.html"),"standalonePanelPreview":str(out / "login-panel-preview.html"),"measuredViews":len(metrics["reports"]),"unitTests":units["numTotalTests"],"unchangedV4PublicAssets":assets,"buildSourcesStillMatch":build_source_match}
(out / "review-generation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k:v for k,v in summary.items() if k not in ("embeddedScreenshots","buildSourcesStillMatch","unchangedV4PublicAssets")}, ensure_ascii=False, indent=2))
