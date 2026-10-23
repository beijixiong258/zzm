"""Real image admission/HTTP/bundle checks; synthetic only, no inference."""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import pytest
from PIL import Image
import pymupdf
from fastapi.testclient import TestClient
from backend.aicademiya.document_bundle import BundleError, source_identity, validate_bundle
from backend.aicademiya.main import create_app
from backend.tests.conftest import catalog, expect, no_live_search_environment
from backend.tests.test_stage12_document_api import wait_job, endpoint


def image_bytes(kind='png', poster=False, count=3):
    frames = [Image.new('RGBA', (36, 24), (i * 45 % 255, 30, 220, 80 + i % 150)) for i in range(count)]
    stream = io.BytesIO()
    options = {'save_all':True, 'append_images':frames[1:], 'duration':[80, 120, 200][:count], 'loop':2}
    if count > 3:options['duration']=20
    if kind=='webp':options.update(lossless=True)
    else:
        options.update(default_image=poster)
        if poster:options['duration']=[80,120]
        else:options.update(disposal=[0,1,2][:count] if count <= 3 else 0,blend=[0,1,1][:count] if count <= 3 else 0)
    frames[0].save(stream,format='WEBP' if kind=='webp' else 'PNG',**options)
    return stream.getvalue()


def corrupt_late_png(data):
    # Keep valid lengths/CRCs but break the LAST zlib payload. First-frame
    # header/verify-only admission would succeed; pixel decoding must reject it.
    chunks=[];pos=8
    while pos<len(data):
        size=struct.unpack_from('>I',data,pos)[0]
        chunks.append((data[pos+4:pos+8],data[pos+8:pos+8+size]))
        pos+=size+12
    last=max(i for i,(kind,_) in enumerate(chunks) if kind==b'fdAT')
    chunks[last]=(b'fdAT',chunks[last][1][:4]+b'NOT_A_ZLIB_FRAME')
    return data[:8]+b''.join(struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)) for kind,body in chunks)


@pytest.mark.parametrize('kind,poster',[('png',False),('png',True),('webp',False)],ids=['apng','apng-poster','webp'])
def test_every_frame_decoded_count_source_duration_alpha_identity(tmp_path,kind,poster):
    source=tmp_path/('source.'+kind);original=image_bytes(kind,poster);source.write_bytes(original)
    digest,count=source_identity(source)
    assert digest==hashlib.sha256(original).hexdigest() and count==3
    assert source.read_bytes()==original
    from tools.material_stage13.simple_material import image_pdf
    info=image_pdf(source,tmp_path/'preview.pdf',kind)
    assert info['frames']==count and info['all_frames_retained']
    assert info['default_image']==poster
    assert [f['duration_ms'] for f in info['frame_map']]==([None,80,120] if poster else [80,120,200])
    with Image.open(source) as im:
        for row in info['frame_map']:
            im.seek(row['frame_index']);im.load()
            with Image.open(tmp_path/row['decoded_rgba_asset']) as retained:
                assert retained.mode=='RGBA' and retained.tobytes()==im.convert('RGBA').tobytes()
            assert row['original_source_sha256']==digest
    with pymupdf.open(tmp_path/'preview.pdf') as pdf:assert pdf.page_count==count


def corrupt_late_webp(data):
    data=bytearray(data);pos=12;frames=[]
    while pos<len(data):
        size=struct.unpack_from('<I',data,pos+4)[0]
        if data[pos:pos+4]==b'ANMF':frames.append((pos,size))
        pos+=8+size+(size%2)
    pos,size=frames[-1];payload=pos+8+16
    assert data[payload:payload+4]==b'VP8L'
    # Preserve RIFF/ANMF/VP8L headers and the lossless dimensions, corrupt only
    # final-frame entropy. WebP opens and frame0 decodes successfully.
    start=payload+8+5;end=pos+8+size;data[start:end]=b'\xff'*(end-start)
    return bytes(data)


def test_webp_late_entropy_corruption_cannot_pass_first_frame_admission(tmp_path):
    source=tmp_path/'bad.webp';source.write_bytes(corrupt_late_webp(image_bytes('webp')))
    with Image.open(source) as image:
        assert image.n_frames==3
        image.load()
    with pytest.raises(BundleError):source_identity(source)


def test_decode_not_only_verify_rejects_crc_valid_late_frame(tmp_path):
    source=tmp_path/'bad.png';source.write_bytes(corrupt_late_png(image_bytes()))
    with Image.open(source) as image:image.verify()  # CRC-only is not enough.
    with Image.open(source) as image:image.load()  # First frame alone is valid.
    with pytest.raises(BundleError):source_identity(source)


@pytest.mark.parametrize('count',[1000,1001])
def test_actual_frame_count_boundary(tmp_path,count):
    frames=[Image.new('RGB',(2,2),(i%256,i//256,0)) for i in range(count)]
    source=tmp_path/'many.png';frames[0].save(source,save_all=True,append_images=frames[1:],duration=20)
    if count==1000:assert source_identity(source)[1]==1000
    else:
        with pytest.raises(BundleError,match='1000'):source_identity(source)


def test_pixel_limit_checked_before_decoder(tmp_path,monkeypatch):
    stream=io.BytesIO();Image.new('RGB',(1,1)).save(stream,format='PNG');data=bytearray(stream.getvalue())
    struct.pack_into('>II',data,16,4001,4000);struct.pack_into('>I',data,29,zlib.crc32(bytes(data[12:29])))
    source=tmp_path/'huge.png';source.write_bytes(data)
    from PIL.PngImagePlugin import PngImageFile
    monkeypatch.setattr(PngImageFile,'load',lambda _:pytest.fail('oversized header decoded'))
    with pytest.raises(BundleError,match='16million'):source_identity(source)


def test_input_byte_limit(tmp_path):
    source=tmp_path/'large.png'
    with source.open('wb') as f:f.truncate(64*1024*1024+1)
    with pytest.raises(BundleError,match='64 MiB'):source_identity(source)


@pytest.mark.parametrize('fmt,suffix',[('PNG','jpg'),('WEBP','png'),('JPEG','webp')])
def test_suffix_mismatch(tmp_path,fmt,suffix):
    source=tmp_path/('wrong.'+suffix);Image.new('RGB',(16,16)).save(source,format=fmt)
    with pytest.raises(BundleError):source_identity(source)


def test_jpeg_pixels_must_decode_and_exif_remains_original(tmp_path):
    source=tmp_path/'exif.jpg';im=Image.new('RGB',(80,40),'blue');exif=im.getexif();exif[274]=6;im.save(source,exif=exif)
    original=source.read_bytes();assert source_identity(source)==(hashlib.sha256(original).hexdigest(),1)
    from tools.material_stage13.simple_material import image_pdf
    info=image_pdf(source,tmp_path/'preview.pdf','jpg')
    assert info['exif_orientation']==6 and (info['normalized_width'],info['normalized_height'])==(40,80)
    source.write_bytes(original[:-20])
    with pytest.raises(BundleError):source_identity(source)


def frame_bundle(source,root):
    # The actual CPU frame adapter emits original-bound frame metadata/PDF;
    # blocks remain empty and explicitly need review (no fake recognition).
    from tools.material_stage13.simple_material import image_pdf
    root=Path(root);(root/'pages').mkdir(parents=True)
    digest,count=source_identity(source);info=image_pdf(source,root/'preview.pdf',source.suffix[1:])
    pages=[]
    with pymupdf.open(root/'preview.pdf') as doc:
        for n in range(count):
            pix=doc[n].get_pixmap(alpha=False);name=f'pages/p{n+1}.png';pix.save(root/name)
            pages.append({'number':n+1,'printed_label':None,'rotation':0,'image':name,'width':pix.width,'height':pix.height,
                          'status':'needs_review','issues':['synthetic_cpu_frame_no_recognition'],'blocks':[]})
    value={'schema_version':1,'source_sha256':digest,'source_format':source.suffix[1:],'preview_pdf':'preview.pdf',
           'parser':{'name':'SYNTHETIC-frame-test','version':'1','recipe':'actual CPU frame derivation; no OCR'},
           'page_count':count,'complete':True,'warnings':[],'pages':pages,'coverage':{'original_image':info}}
    (root/'manifest.json').write_text(json.dumps(value),encoding='utf-8')
    return value


@pytest.mark.parametrize('kind,poster',[('png',False),('png',True),('webp',False)],ids=['apng','poster','webp'])
def test_http_upload_commit_full_count_last_page_and_original(tmp_path,catalog,monkeypatch,kind,poster):
    monkeypatch.setenv('AICADEMIYA_DOCUMENT_FORMATS','png,webp');monkeypatch.setenv('AICADEMIYA_AI_MODE','demo')
    app=create_app(data_dir=tmp_path/'data',catalog_path=catalog,demo_enabled=True,frontend_dir=tmp_path/'dist',
                   document_processor=lambda source,root,cancel:frame_bundle(source,root))
    original=image_bytes(kind,poster)
    with TestClient(app) as client:
        expect(client.post('/api/auth/demo',json={'role':'teacher'}))
        material=expect(client.post('/api/sessions/s4/materials',data={'processing':'full_document'},
            files={'file':('synthetic.'+kind,original,'application/octet-stream')}))
        mid=material['id'];job=wait_job(client,mid)
        assert job['status']=='completed' and job['page_count']==job['processed_pages']==3
        doc=expect(client.get(endpoint(mid)))['document'];rid=doc['revision_id']
        assert doc['page_count']==3
        last=expect(client.get(endpoint(mid)+'/pages/3',params={'revision_id':rid}));assert last['number']==3
        assert client.get(material['download_url']).content==original
        pdf=client.get(endpoint(mid)+'/pdf',params={'revision_id':rid});assert pdf.status_code==200
        with pymupdf.open(stream=pdf.content,filetype='pdf') as p:assert p.page_count==3


def test_http_corrupt_late_frame_never_enqueued(tmp_path,catalog,monkeypatch):
    monkeypatch.setenv('AICADEMIYA_DOCUMENT_FORMATS','png')
    calls=[]
    app=create_app(data_dir=tmp_path/'data',catalog_path=catalog,demo_enabled=True,frontend_dir=tmp_path/'dist',
                   document_processor=lambda *args:calls.append(args))
    with TestClient(app) as client:
        expect(client.post('/api/auth/demo',json={'role':'teacher'}))
        response=client.post('/api/sessions/s4/materials',data={'processing':'full_document'},
            files={'file':('corrupt.png',corrupt_late_png(image_bytes()),'image/png')})
        assert response.status_code==422 and not calls


def test_bundle_cannot_omit_late_frames(tmp_path):
    source=tmp_path/'source.png';source.write_bytes(image_bytes(poster=True))
    root=tmp_path/'bundle';manifest=frame_bundle(source,root);digest,count=source_identity(source)
    assert validate_bundle(root,digest,count)['page_count']==3
    manifest['pages']=manifest['pages'][:1];manifest['page_count']=1
    (root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(BundleError,match='coverage'):validate_bundle(root,digest,count)
