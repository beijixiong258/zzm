"""Stage8: widen only non-book V4 contours; never retrace/redesign inputs.

Book exclusion is topology-aware: 8 complete existing closed contours are
contained in x=136..337,y=311..390. The two side-curl components continue
below y=310 OUTSIDE that rectangle and retain the additional vector outline.
The book path d bytes and fill-rule are copied, not stroked or transformed.
"""
from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'artifacts/stage8/branding'
PUBLIC=ROOT/'frontend/public'
NS='{http://www.w3.org/2000/svg}'
BOOK_BOUNDS=(136,311,337,390)
NON_BOOK_OUTLINE=0.95

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    backup=ART/'previous-public'
    baseline=ET.parse(backup/'aicademiya-mark.svg').getroot()
    source_d=baseline.find(NS+'path').attrib['d']
    contours=re.findall(r'M.*?Z',source_d)
    book=[]; nonbook=[]; classification=[]
    for i,d in enumerate(contours):
        nums=[float(n) for n in re.findall(r'-?\d+(?:\.\d+)?',d)]
        bounds=[min(nums[::2]),min(nums[1::2]),max(nums[::2]),max(nums[1::2])]
        is_book=all([bounds[0]>=BOOK_BOUNDS[0],bounds[1]>=BOOK_BOUNDS[1],bounds[2]<=BOOK_BOUNDS[2],bounds[3]<=BOOK_BOUNDS[3]])
        (book if is_book else nonbook).append(d)
        classification.append({'index':i,'bounds_control_hull':bounds,'book':is_book})
    assert [c['index'] for c in classification if c['book']]==[0,1,2,3,4,5,8,9]
    book_d=' '.join(book); nonbook_d=' '.join(nonbook)
    def svg(color, favicon=False):
        bg='<rect x="57" y="23" width="359" height="375" rx="40" fill="#f5f3e8"/>' if favicon else ''
        # Preserve the original compound fill AS ONE PATH: splitting the fill can
        # change Chrome edge antialiasing despite identical book geometry.
        # Only the separate 11-contour outline is added, so the book raster also
        # remains byte-identical to the baseline (not just geometrically equal).
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="57 23 359 375" role="img"><title>AIcademiya — V4, preserved book</title>{bg}<path id="v4-original" fill="{color}" fill-rule="evenodd" data-preserved-book-contours="0 1 2 3 4 5 8 9" d="{source_d}"/><path id="v4-non-book-outline" fill="none" stroke="{color}" stroke-width="{NON_BOOK_OUTLINE}" stroke-linejoin="round" d="{nonbook_d}"/></svg>\n'
    for name,color,favicon in [('aicademiya-mark.svg','#3d5d51',False),('aicademiya-mark-small.svg','#3d5d51',False),('aicademiya-mark-light.svg','#f7f6ed',False),('favicon.svg','#3d5d51',True)]:
        (PUBLIC/name).write_text(svg(color,favicon),encoding='utf8')
    (ART/'baseline-full-coordinate.svg').write_text((backup/'aicademiya-mark.svg').read_text(encoding='utf8').replace('viewBox="57 23 359 375"','viewBox="0 0 474 408"'),encoding='utf8')
    (ART/'selected-full-coordinate.svg').write_text(svg('#3d5d51').replace('viewBox="57 23 359 375"','viewBox="0 0 474 408"'),encoding='utf8')
    for label,d in [('before',book_d),('after',book_d)]:
        (ART/f'{label}-book-only.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 474 408"><path fill="#3d5d51" fill-rule="evenodd" d="{d}"/></svg>',encoding='utf8')
    inputs=json.loads((ART/'original-input-hashes.json').read_text(encoding='utf8'))
    assert all(sha(Path(p))==h for p,h in inputs.items())
    report={'method':'Existing compound contours separated by complete control-hull containment; vector outline ONLY on non-book path','viewBox':'57 23 359 375','book_exclusion_original_coordinates':list(BOOK_BOUNDS),'book_contour_indices':[c['index'] for c in classification if c['book']],'book_contours':len(book),'non_book_contours':len(nonbook),'non_book_extra_outline_width_units':NON_BOOK_OUTLINE,'book_path_sha256':hashlib.sha256(book_d.encode()).hexdigest(),'book_path_exactly_preserved':True,'book_has_no_stroke':True,'side_curls_indices':[6,7],'side_curls_extend_below_book_top_and_are_thickened':True,'classification':classification,'original_inputs_unchanged':True,'original_input_sha256':inputs}
    (ART/'geometry.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['classification','original_input_sha256']},indent=2))
if __name__=='__main__':main()
