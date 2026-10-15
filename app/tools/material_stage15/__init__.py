"""Local, source-grounded schema-1 multimodal page adapter; no inference."""
from .adapter import CropPolicy, adapt_page, plan_page, verify_readback, write_image_bundle

__all__ = ['CropPolicy', 'adapt_page', 'plan_page', 'verify_readback', 'write_image_bundle']
