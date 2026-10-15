"""Synthetic OOXML field classification; real converted PPT replay is separate."""
from xml.etree import ElementTree as ET
import pytest
from backend.aicademiya.document_supplements import generated_note_shape, paragraphs, A


def shape(content):
    return ET.fromstring('<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:txBody><a:p>'+content+'</a:p></p:txBody></p:sp>')


@pytest.mark.parametrize('body,skip',[
 ('<a:fld type="slidenum"><a:t>&lt;number&gt;</a:t></a:fld>',True),
 ('<a:r><a:t>\t\t</a:t></a:r><a:fld type="slidenum"><a:t>2</a:t></a:fld>',True),
 ('<a:r><a:t>&lt;number&gt;</a:t></a:r>',False),
 ('<a:r><a:t>Teacher-authored note: </a:t></a:r><a:fld type="slidenum"><a:t>2</a:t></a:fld>',False),
 ('<a:fld type="custom"><a:t>Keep this authored variable</a:t></a:fld>',False),
 ('<a:fld type="slidenum"><a:t>1</a:t></a:fld><a:fld type="custom"><a:t>Keep</a:t></a:fld>',False),
])
def test_only_generated_slidenum_shapes_are_excluded(body,skip):
    value=shape(body);before=ET.tostring(value);text=paragraphs(value,A)
    assert generated_note_shape(value)is skip
    assert ET.tostring(value)==before and paragraphs(value,A)==text
