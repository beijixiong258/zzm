"""Strict complete-PDF bundle boundary; no OCR is performed in this module."""
import hashlib
import json
import math
import re
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

MAX_PAGES = 1000
MAX_FULL_UPLOAD_BYTES = 64 * 1024 * 1024
FULL_FORMATS = ('pdf', 'pptx', 'ppt', 'docx', 'doc', 'xls', 'xlsx', 'txt', 'md', 'png', 'jpg', 'jpeg', 'webp')
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 4 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 36_000_000
MAX_BLOCKS = 200_000
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}


class BundleError(ValueError):
    """Messages are fixed public-safe descriptions, never worker stderr."""


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular_file(path):
    path = Path(path)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents) or not path.is_file():
        raise BundleError('Document source or asset is unavailable or unsafe')
    return path


def source_identity(path):
    import pymupdf
    path = regular_file(path)
    try:
        if path.stat().st_size > MAX_FULL_UPLOAD_BYTES:
            raise BundleError('Complete document upload exceeds the 64 MiB limit')
        suffix = path.suffix.lower().lstrip('.')
        if suffix not in FULL_FORMATS:
            raise BundleError('Unsupported complete document source format')
        if suffix in ('txt', 'md'):
            from tools.material_stage13.source_text import decode_text
            decode_text(path.read_bytes())
            return sha256_file(path), None
        if suffix in ('png', 'jpg', 'jpeg', 'webp'):
            expected = {'png':'PNG', 'jpg':'JPEG', 'jpeg':'JPEG', 'webp':'WEBP'}[suffix]
            with Image.open(path) as image:
                count = getattr(image, 'n_frames', 1)
                if (image.format != expected or not 1 <= count <= MAX_PAGES
                        or image.width < 1 or image.height < 1
                        or image.width * image.height > 16_000_000):
                    raise BundleError('A matching image with 1 to 1000 frames up to16million pixels is required')
                image.verify()
            # verify() alone does not decode pixels. Reopen and decode every
            # composited display canvas, including an APNG default/poster frame.
            # Keep this admission check independent of the worker's PDF adapter.
            with Image.open(path) as image:
                for index in range(count):
                    image.seek(index)
                    if (image.width < 1 or image.height < 1
                            or image.width * image.height > 16_000_000):
                        raise BundleError('Image frame exceeds the 16million pixel limit')
                    image.load()
                    duration = image.info.get('duration')
                    if duration is not None and (not isinstance(duration, (int, float))
                            or not math.isfinite(duration) or duration < 0):
                        raise BundleError('Image frame duration is invalid')
            return sha256_file(path), count
        if suffix == 'xlsx':
            from tools.material_stage16.workbook_inventory import read_workbook
            read_workbook(path)  # Complete stored-cell preflight, never calculation.
            return sha256_file(path), None  # Sheets are not rendered PDF pages.

        if suffix in ('pptx', 'docx'):
            from .extraction_limits import office_guard
            office_guard(path, max_expanded=100 * 1024 * 1024)
            with zipfile.ZipFile(path) as archive:
                member = 'ppt/presentation.xml' if suffix == 'pptx' else 'word/document.xml'
                if member not in archive.namelist():
                    raise BundleError('Office file does not match its declared format')
                count = None
                if suffix == 'pptx':
                    if archive.getinfo(member).file_size > 4 * 1024 * 1024:
                        raise BundleError('Presentation inventory exceeds the limit')
                    root = ET.fromstring(archive.read(member))
                    count = len(root.findall('{http://schemas.openxmlformats.org/presentationml/2006/main}sldIdLst/{http://schemas.openxmlformats.org/presentationml/2006/main}sldId'))
                    if not 1 <= count <= MAX_PAGES:
                        raise BundleError('Complete document processing supports 1 to 1000 pages/slides')
            return sha256_file(path), count
        if suffix in ('doc', 'ppt', 'xls'):
            with path.open('rb') as stream:
                if stream.read(8) != bytes.fromhex('d0cf11e0a1b11ae1'):
                    raise BundleError('A valid legacy Office container is required')
            return sha256_file(path), None
        with pymupdf.open(path) as document:
            if not document.is_pdf or document.is_encrypted:
                raise BundleError('A readable, unencrypted PDF is required')
            count = document.page_count
            if not 1 <= count <= MAX_PAGES:
                raise BundleError('Complete PDF processing supports 1 to 1000 pages')
        return sha256_file(path), count
    except BundleError:
        raise
    except Exception:
        raise BundleError('A readable, unencrypted document matching its format is required') from None


def relative_name(value):
    if not isinstance(value, str) or not value or len(value) > 240:
        raise BundleError('Unsafe document asset name')
    path = PurePosixPath(value)
    if (path.is_absolute() or value != path.as_posix() or '\\' in value or ':' in value
            or any(p in ('', '.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]+', p)
                   or p.endswith(('.', ' ')) or p.split('.')[0].upper() in
                   {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}
                   for p in value.split('/'))):
        raise BundleError('Unsafe document asset name')
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Parser(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=200)
    recipe: str = Field(min_length=1, max_length=2000)


class Review(StrictModel):
    by: str = Field(min_length=1, max_length=100)
    at: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)


class Block(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    type: Literal['text','heading','list','table','image','caption','header','footer','page_number','equation','other']
    bbox: list[float] = Field(min_length=4, max_length=4)
    text: str = Field(max_length=1_000_000)
    quality: Literal['extracted','needs_review','excluded','approved']
    issues: list[str] = Field(max_length=100)
    assets: list[str] = Field(max_length=100)
    parent_id: str | None
    text_format: Literal['plain', 'markdown'] = 'plain'
    visual_description: str | None = Field(default=None, max_length=2000)
    raw_text: str | None = Field(default=None, max_length=1_000_000)
    review: Review | None = None

    @field_validator('bbox')
    @classmethod
    def box(cls, value):
        if (not all(math.isfinite(v) and 0 <= v <= 1 for v in value)
                or value[0] > value[2] or value[1] > value[3]):
            raise ValueError('Invalid normalized box')
        return value

    @field_validator('issues')
    @classmethod
    def issue_strings(cls, value):
        if any(len(v) > 2000 for v in value):
            raise ValueError('Issue too long')
        return value


class Page(StrictModel):
    number: StrictInt = Field(ge=1, le=MAX_PAGES)
    printed_label: str | None = Field(max_length=200)
    rotation: Literal[0,90,180,270]
    image: str
    width: StrictInt = Field(ge=1, le=20000)
    height: StrictInt = Field(ge=1, le=20000)
    status: Literal['text','blank','needs_review','failed']
    issues: list[str] = Field(max_length=100)
    blocks: list[Block] = Field(max_length=10000)

    @field_validator('rotation', mode='before')
    @classmethod
    def integer_rotation(cls, value):
        if type(value) is not int:
            raise ValueError('Rotation must be an integer')
        return value

    @field_validator('issues')
    @classmethod
    def issue_strings(cls, value):
        return Block.issue_strings(value)


class Supplement(StrictModel):
    id: str = Field(pattern=r'^s[0-9]+$',min_length=2,max_length=100)
    kind: Literal['speaker_notes','comment','footnote','endnote','header','footer','diagram_text','alt_text']
    source_part: str = Field(min_length=1,max_length=240)
    source_node: str = Field(max_length=256)
    page_hint: StrictInt | None = Field(default=None,ge=1,le=MAX_PAGES)
    char_start: StrictInt = Field(ge=0)
    char_end: StrictInt = Field(ge=0)
    text: str = Field(max_length=12000)
    quality: Literal['extracted']
    visibility: Literal['teacher','student'] = 'teacher'
    derivation: Literal['original_office_xml','libreoffice_docx','libreoffice_pptx','libreoffice_xlsx']
    sharing_review: Review | None = None


class Manifest(StrictModel):
    schema_version: Literal[1]
    source_sha256: str = Field(pattern=r'^[0-9a-fA-F]{64}$')
    parser: Parser
    page_count: StrictInt = Field(ge=1, le=MAX_PAGES)
    complete: bool
    warnings: list[str] = Field(max_length=1000)
    pages: list[Page] = Field(min_length=1, max_length=MAX_PAGES)
    source_format: Literal['pdf','pptx','ppt','docx','doc','xls','xlsx','txt','md','png','jpg','jpeg','webp'] | None = None
    preview_pdf: str | None = Field(default=None, max_length=240)
    coverage: dict | None = None
    supplements: list[Supplement] | None = Field(default=None,max_length=10000)

    @field_validator('schema_version', mode='before')
    @classmethod
    def integer_schema(cls, value):
        if type(value) is not int:
            raise ValueError('Schema version must be an integer')
        return value

    @field_validator('warnings')
    @classmethod
    def warning_strings(cls, value):
        return Block.issue_strings(value)


def registered_assets(manifest):
    return {p['image'] for p in manifest['pages']} | {
        name for p in manifest['pages'] for b in p['blocks'] for name in b['assets']}


def validate_manifest(value, *, source_sha256=None, page_count=None, reviewed=False):
    try:
        normalized = Manifest.model_validate(value).model_dump(exclude_none=False)
        for key in ('source_format', 'preview_pdf', 'coverage', 'supplements'):
            if key not in value:
                normalized.pop(key, None)
        if normalized.get('preview_pdf'):
            if relative_name(normalized['preview_pdf']) != 'preview.pdf':
                raise BundleError('Rendered document must use its registered PDF view')
        if normalized.get('source_format') not in (None, 'pdf') and not normalized.get('preview_pdf'):
            raise BundleError('Non-PDF document requires a retained rendered PDF view')
        if not normalized['complete']:
            raise BundleError('Worker did not provide a complete document')
        if source_sha256 and normalized['source_sha256'].lower() != source_sha256:
            raise BundleError('Document source hash does not match the original')
        if page_count is not None and normalized['page_count'] != page_count:
            raise BundleError('Document page coverage does not match the original')
        if [p['number'] for p in normalized['pages']] != list(range(1, normalized['page_count'] + 1)):
            raise BundleError('Document page coverage does not match the original')
        supplement_ids=set()
        for item in normalized.get('supplements')or[]:
            relative_name(item['source_part'])
            if item['id']in supplement_ids or item['char_end']-item['char_start']!=len(item['text']):
                raise BundleError('Supplementary source identity or character coverage is invalid')
            supplement_ids.add(item['id'])
            if item['page_hint'] is not None and item['page_hint']>normalized['page_count']:
                raise BundleError('Supplementary source slide is outside the document')
            if not reviewed and (item['visibility']!='teacher' or item['sharing_review']is not None):
                raise BundleError('Worker cannot publish supplemental source text to students')
            if item['sharing_review']is None:item.pop('sharing_review')
        ids, parents, total = set(), [], 0
        for page in normalized['pages']:
            if page['width'] * page['height'] > MAX_IMAGE_PIXELS:
                raise BundleError('Document raster exceeds the pixel limit')
            if not relative_name(page['image']).startswith('pages/'):
                raise BundleError('Page raster must be registered under pages')
            for block in page['blocks']:
                total += 1
                if total > MAX_BLOCKS:
                    raise BundleError('Document exceeds the block limit')
                if not re.fullmatch(r'p'+str(page['number'])+r'-b[0-9]+(?:[-_][A-Za-z0-9_-]+)?', block['id']) or block['id'] in ids:
                    raise BundleError('Document block identities are invalid')
                ids.add(block['id'])
                if not reviewed and (block['quality'] == 'approved' or block['raw_text'] is not None or block['review'] is not None):
                    raise BundleError('Worker cannot approve or review source text')
                if block['parent_id']:
                    parents.append((block['id'], block['parent_id'], page['number']))
                for asset in block['assets']:
                    if not relative_name(asset).startswith('assets/'):
                        raise BundleError('Crop must be registered under assets')
                # Optional application review fields are absent in pristine parser output.
                if block['text_format'] == 'plain':
                    block.pop('text_format')
                if block['visual_description'] is None:
                    block.pop('visual_description')
                if block['raw_text'] is None:
                    block.pop('raw_text')
                if block['review'] is None:
                    block.pop('review')
        if any(parent not in ids or parent == child or not parent.startswith(f'p{number}-')
               for child, parent, number in parents):
            raise BundleError('Document parent block identities are invalid')
        parent_map = {child: parent for child, parent, _ in parents}
        for child in parent_map:
            seen = set()
            while child in parent_map:
                if child in seen:
                    raise BundleError('Document parent blocks contain a cycle')
                seen.add(child)
                child = parent_map[child]
        return normalized
    except BundleError:
        raise
    except Exception:
        raise BundleError('Worker document manifest is invalid') from None


def asset_file(root, name):
    name = relative_name(name)
    root = Path(root)
    path = root / name
    regular_file(path)
    if not path.resolve().is_relative_to(root.resolve()) or path.suffix.lower() not in IMAGE_SUFFIXES:
        raise BundleError('Document asset is unavailable or unsafe')
    return path


def rendered_pdf_file(root, manifest):
    import pymupdf
    name = manifest.get('preview_pdf')
    if name != 'preview.pdf':
        raise BundleError('No rendered PDF view is registered')
    path = regular_file(Path(root) / relative_name(name))
    if path.stat().st_size > MAX_FILE_BYTES:
        raise BundleError('Rendered PDF exceeds the size limit')
    try:
        with pymupdf.open(path) as pdf:
            if not pdf.is_pdf or pdf.is_encrypted or pdf.page_count != manifest['page_count']:
                raise BundleError('Rendered PDF does not match document coverage')
    except BundleError:
        raise
    except Exception:
        raise BundleError('Rendered PDF is invalid') from None
    return path


def validate_bundle(root, source_sha256, page_count):
    root = Path(root)
    manifest_path = regular_file(root / 'manifest.json')
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise BundleError('Document manifest exceeds the size limit')
    try:
        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError('Duplicate manifest key')
                value[key] = item
            return value
        value = json.loads(manifest_path.read_text(encoding='utf-8'),
                           object_pairs_hook=unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except Exception:
        raise BundleError('Worker document manifest is invalid') from None
    manifest = validate_manifest(value, source_sha256=source_sha256, page_count=page_count)
    if manifest.get('preview_pdf'):
        rendered_pdf_file(root, manifest)
    total, files = 0, 0
    for path in root.rglob('*'):
        relative_name(path.relative_to(root).as_posix())
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise BundleError('Document bundle contains unsafe files')
        if path.is_file():
            size = path.stat().st_size
            total += size
            files += 1
            if size > MAX_FILE_BYTES or total > MAX_BUNDLE_BYTES or files > 100000:
                raise BundleError('Document bundle exceeds the size limit')
        elif not path.is_dir():
            raise BundleError('Document bundle contains unsafe files')
    dimensions = {}
    for name in registered_assets(manifest):
        path = asset_file(root, name)
        try:
            with Image.open(path) as image:
                if image.format not in {'PNG','JPEG','WEBP'} or image.width * image.height > MAX_IMAGE_PIXELS or getattr(image, 'n_frames', 1) != 1:
                    raise BundleError('Document raster is invalid or exceeds the pixel limit')
                dimensions[name] = image.size
                image.verify()
        except BundleError:
            raise
        except Exception:
            raise BundleError('Document raster is invalid') from None
    if any(dimensions[p['image']] != (p['width'], p['height']) for p in manifest['pages']):
        raise BundleError('Document raster dimensions do not match the manifest')
    return manifest
