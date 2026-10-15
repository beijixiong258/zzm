import { renderToStaticMarkup } from "react-dom/server";
import { describe, it, expect } from "vitest";
import DocumentBlockContent, { sourceTableParts } from "../src/DocumentBlockContent";
describe("source table display, not interpretation or approval", () => {
  it("renders supported rows/cells and retains raw transcription", () => {
    const text='Table 5.1\n<table><tr><th>Advantages</th><th>Disadvantages</th></tr><tr><td><ul><li>First</li><li>Second</li></ul></td><td>Source text</td></tr></table>';
    const html=renderToStaticMarkup(<DocumentBlockContent text={text}/>);
    expect(html).toContain('<table><tbody><tr><th>Advantages</th>');expect(html).toContain('<li>Second</li>');expect(html).toContain('Raw transcription');expect(html).toContain('&lt;table&gt;');
  });
  it("preserves merged-cell relationships without executing HTML",()=>{
    const html=renderToStaticMarkup(<DocumentBlockContent text={'<table><tr><td rowspan="2">Method</td><td colspan="3">Trait</td></tr><tr><td>Grammar &amp; syntax</td></tr></table>'}/>);
    expect(html).toMatch(/row[Ss]pan="2"/);expect(html).toMatch(/col[Ss]pan="3"/);expect(html).toContain('Grammar &amp; syntax');
  });
  it.each(['<table onclick="alert(1)"><tr><td>x</td></tr></table>','<table><tr><td><img src="https://example.invalid/pixel"></td></tr></table>','<table><tr><td><script>alert(1)</script></td></tr></table>'])("keeps unsupported markup literal: %s",text=>{
    expect(sourceTableParts(text)).toBeNull();const html=renderToStaticMarkup(<DocumentBlockContent text={text}/>);expect(html).toContain('<pre');expect(html).not.toContain('<img');expect(html).not.toContain('<script');expect(html).not.toContain('<table');
  });
  it("does not repair malformed row structure or unmatched brackets",()=>{
    expect(sourceTableParts('<table><td>unmatched</td></table>')).toBeNull();expect(sourceTableParts('<table><tr><td>x</table>')).toBeNull();
  });
});
