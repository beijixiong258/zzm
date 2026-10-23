"""Stage9 real HTTP avatar/feedback checks; only explicitly isolated synthetic targets."""
from pathlib import Path
from io import BytesIO
from urllib.parse import urlsplit
import argparse, hashlib, json, os, sqlite3, traceback
import httpx
from PIL import Image, ImageDraw, PngImagePlugin


def picture(color, fmt='PNG'):
    image = Image.new('RGB', (512, 256), (240, 240, 240))
    ImageDraw.Draw(image).rectangle((128, 0, 383, 255), fill=color)
    out = BytesIO()
    if fmt == 'PNG':
        info = PngImagePlugin.PngInfo(); info.add_text('Synthetic private metadata', 'Must be stripped')
        image.save(out, format=fmt, pnginfo=info)
    else:
        image.save(out, format=fmt)
    return out.getvalue()


def records(db, excluded=('auth_sessions', 'account_avatars', 'feedback')):
    if not db:
        return None
    with sqlite3.connect(f'file:{Path(db).as_posix()}?mode=ro', uri=True) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name") if r[0] not in excluded]
        return {t: sorted(json.dumps([{'bytes_hex': v.hex()} if isinstance(v, bytes) else v for v in row], ensure_ascii=False) for row in conn.execute('SELECT * FROM "'+t+'"')) for t in tables}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--base-url', required=True); p.add_argument('--artifact-dir', required=True); p.add_argument('--confirm-test-data', action='store_true'); a = p.parse_args()
    assert a.confirm_test_data and urlsplit(a.base_url).port != 18773, 'Isolated target only'
    out = Path(a.artifact_dir); out.mkdir(parents=True, exist_ok=True)
    checks, events, failures, ids = [], [], [], {}
    db = os.environ.get('AICADEMIYA_QA_DB')
    clients = [httpx.Client(base_url=a.base_url, trust_env=False, timeout=40) for _ in range(5)]
    student, other, teacher, admin, anon = clients

    def call(client, method, url, body=None, expected=200, **kwargs):
        r = client.request(method, url, **({'json': body} if body is not None else {}), **kwargs)
        events.append({'method': method, 'path': url, 'status': r.status_code})
        allowed = (expected,) if isinstance(expected, int) else expected
        assert r.status_code in allowed, f'{method} {url}: expected {allowed}, got {r.status_code}'
        return r.json() if r.headers.get('content-type', '').startswith('application/json') else r

    def check(name, condition=True):
        assert condition, name
        checks.append(name)

    def upload(actor, data, filename='Synthetic.png', mime='image/png', expected=200):
        return call(actor, 'POST', '/api/auth/avatar', files={'file': (filename, data, mime)}, expected=expected)

    try:
        check('Explicit isolated demo-enabled application with declared QA API target', call(anon, 'GET', '/api/bootstrap')['demo_enabled'] and call(anon, 'GET', '/openapi.json')['info']['version'] == os.environ.get('AICADEMIYA_QA_TARGET_API','0.8.0'))
        for client, role, index in ((student, 'student', 1), (other, 'student', 2), (teacher, 'teacher', 1), (admin, 'admin', 1)):
            call(client, 'POST', '/api/auth/demo', {'role': role, 'student_index': index})
        original = records(db)
        check('Fresh accounts have no invented avatar', call(student, 'GET', '/api/auth/me')['user'].get('avatar_url') is None)
        first_bytes = picture((178, 46, 53)); second_bytes = picture((37, 88, 142))
        upload(anon, first_bytes, expected=401); call(anon, 'DELETE', '/api/auth/avatar', expected=401)
        first = upload(student, first_bytes)['user']; url = first['avatar_url']
        check('Upload targets authenticated caller and me readback matches', first['id'] == 'demo-student-1' and url == call(student, 'GET', '/api/auth/me')['user']['avatar_url'] and not call(other, 'GET', '/api/auth/me')['user'].get('avatar_url'))
        image_response = call(student, 'GET', url); image = Image.open(BytesIO(image_response.content))
        check('Stored avatar is normalized square PNG without original metadata', image_response.headers['content-type'].startswith('image/png') and image.size == (256, 256) and image.format == 'PNG' and not image.info and image.convert('RGB').getpixel((128,128)) == (178,46,53))
        check('Avatar response is private, nosniff, and content hash versioned', image_response.headers.get('x-content-type-options') == 'nosniff' and 'private' in image_response.headers.get('cache-control','') and bool(image_response.headers.get('etag')) and hashlib.sha256(image_response.content).hexdigest() in url)
        call(anon, 'GET', url, expected=401); check('Anonymous avatar reads are denied and signed-in profile display works', call(other, 'GET', url).content == image_response.content)
        for data, name, mime in [(b'<svg><script>alert(1)</script></svg>', 'Synthetic.svg', 'image/svg+xml'), (b'not a picture', 'Synthetic.png', 'image/png'), (b'GIF89a', 'Synthetic.gif', 'image/gif'), (b'X' * (5*1024*1024+1), 'Synthetic.png', 'image/png')]:
            upload(student, data, name, mime, expected=(413,415,422))
        huge = BytesIO(); Image.new('RGB',(4001,4000),'white').save(huge,format='PNG'); upload(student,huge.getvalue(),expected=(413,415,422))
        check('Invalid, unsupported, over-byte and over-pixel input preserves previous avatar', call(student,'GET','/api/auth/me')['user']['avatar_url']==url and call(student,'GET',url).content==image_response.content)
        replaced = upload(student, second_bytes)['user']['avatar_url']; call(student,'GET',url,expected=404)
        check('Replacement produces fresh URL/content and invalidates old revision', replaced!=url and Image.open(BytesIO(call(student,'GET',replaced).content)).convert('RGB').getpixel((128,128))==(37,88,142))
        call(student,'DELETE','/api/auth/avatar'); call(student,'DELETE','/api/auth/avatar'); call(student,'GET',replaced,expected=404)
        check('Remove is idempotent and restores initials metadata', call(student,'GET','/api/auth/me')['user']['avatar_url'] is None)
        final_avatar=upload(student,second_bytes)['user']['avatar_url']; ids.update(avatar_user='demo-student-1',avatar_url=final_avatar,avatar_sha256=hashlib.sha256(call(student,'GET',final_avatar).content).hexdigest())
        for actor in (teacher,admin):
            u=upload(actor,picture((34,117,65),'JPEG'),'Synthetic.jpg','image/jpeg')['user'];check('Own avatar upload also works for '+u['role'],call(actor,'GET',u['avatar_url']).status_code==200)
        payload={'request_id':'s9-core','category':'idea','subject':'  Synthetic interface suggestion  ','message':'  First line\n<script>window.syntheticUnsafe=true</script>\nSecond line  '}
        call(anon,'POST','/api/feedback',payload,401);call(anon,'GET','/api/feedback',expected=401)
        item=call(student,'POST','/api/feedback',payload);fid=item['id'];ids['feedback']=fid
        check('Feedback retains literal escaped-display text and trusted identity with initial status',item['subject']==payload['subject'].strip() and item['message']==payload['message'].strip() and item['status']=='new' and item['revision']==1 and item['reply']=='' and item['author']['id']=='demo-student-1')
        check('Independent exact and own-request readback matches submission',call(student,'GET','/api/feedback/'+fid)==item and call(student,'GET','/api/feedback/requests/s9-core')==item)
        again=call(student,'POST','/api/feedback',payload);call(student,'POST','/api/feedback',{**payload,'message':'Changed payload'},409)
        check('Same-id retry deduplicates; changed same-id input rejects',again['id']==fid and call(student,'GET','/api/feedback')['total']==1)
        other_item=call(other,'POST','/api/feedback',{**payload,'subject':'Other synthetic account'});check('Idempotency key is scoped to author',other_item['id']!=fid)
        call(other,'GET','/api/feedback/'+fid,expected=404);call(other,'GET','/api/feedback/requests/no-such-id',expected=404)
        for actor in (student,other,teacher):
            call(actor,'GET','/api/admin/feedback',expected=403);call(actor,'GET','/api/admin/feedback/'+fid,expected=403);call(actor,'PATCH','/api/admin/feedback/'+fid,{'status':'reviewed','reply':'Denied','expected_revision':1},403)
        check('Non-admin cannot access inbox/replies or another author detail',call(other,'GET','/api/feedback')['total']==1 and call(teacher,'GET','/api/feedback')['total']==0)
        before=call(student,'GET','/api/feedback')['total']
        for mutation in ({'subject':' '},{'subject':'X'*161},{'message':'X'*6001},{'message':' '},{'request_id':'bad key'},{'category':'other'},{'status':'reviewed'},{'author_id':'demo-admin'},{'reply':'Spoofed'}):
            call(student,'POST','/api/feedback',{**payload,**mutation},422)
        check('Feedback validation forbids oversized/blank/spoofed fields',call(student,'GET','/api/feedback')['total']==before)
        for i in range(6):
            call(student,'POST','/api/feedback',{'request_id':f's9-page-{i}','category':'bug' if i%2 else'general','subject':f'Synthetic page {i}','message':'Generated test feedback, not a real experience.'})
        p1=call(student,'GET','/api/feedback?offset=0&limit=3');p2=call(student,'GET','/api/feedback?offset=3&limit=3');p3=call(student,'GET','/api/feedback?offset=6&limit=3')
        check('Exact own pagination total with no duplicate/missing IDs',all(p['total']==7 for p in (p1,p2,p3)) and len({row['id'] for p in (p1,p2,p3)for row in p['items']})==7)
        filtered=call(student,'GET','/api/feedback?category=bug&status=new');check('Category/status filtering reports actual total',filtered['total']==3 and all(x['category']=='bug' and x['status']=='new' for x in filtered['items']))
        all_items=call(admin,'GET','/api/admin/feedback');check('Admin inbox includes all accounts while admin own list stays separate',all_items['total']==8 and call(admin,'GET','/api/feedback')['total']==0)
        reply='Synthetic administrator reply.\nThank you for the concrete example.'
        updated=call(admin,'PATCH','/api/admin/feedback/'+fid,{'status':'reviewed','reply':reply,'expected_revision':1})
        check('Human reply and reviewed status persist and reach only author/admin',updated['revision']==2 and updated['status']=='reviewed' and updated['reply']==reply and call(admin,'GET','/api/admin/feedback/'+fid)==updated and call(student,'GET','/api/feedback/'+fid)==updated)
        call(admin,'PATCH','/api/admin/feedback/'+fid,{'status':'new','reply':'Stale overwrite','expected_revision':1},409)
        call(admin,'PATCH','/api/admin/feedback/'+fid,{'status':'reviewed','reply':'Bad revision','expected_revision':True},422)
        check('Stale and malformed admin edits cannot overwrite saved reply',call(student,'GET','/api/feedback/'+fid)==updated)
        check('Filter total changes after actual review, not a fake success badge',call(admin,'GET','/api/admin/feedback?status=reviewed')['total']==1 and call(admin,'GET','/api/admin/feedback?status=new')['total']==7)
        ids.update(feedback_reviewed=fid,expected_reply=reply,expected_revision=2,feedback_total=8)
        if db:check('All original non-auth application tables remain unchanged',records(db)==original)
        else:checks.append('External HTTP-only run; independent remote database inventory required')
    except Exception as e:
        failures.append({'error':str(e),'traceback':traceback.format_exc()})
    finally:
        for c in clients:c.close()
        report={'status':'failed'if failures else'passed','checks':checks,'failures':failures,'ids':ids,'events':events,'real_http':True,'sqlite_inspected':bool(db),'synthetic_only':True,'real_model_or_search_calls':0}
        (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':report['status'],'checks':len(checks),'failures':failures,'result':str(out/'result.json')},ensure_ascii=False))
    return 1 if failures else 0


if __name__=='__main__':raise SystemExit(main())
