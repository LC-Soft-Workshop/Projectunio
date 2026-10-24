"""Shared export formats; mappings use normalized coordinates at every size."""
RESOLUTIONS={
    '720p — 1280 × 720':(1280,720),
    'Full HD — 1920 × 1080':(1920,1080),
    '4K UHD — 3840 × 2160':(3840,2160),
}


def valid_resolution(value):
    return isinstance(value,(list,tuple)) and len(value)==2 and all(type(v)==int for v in value) and tuple(value) in RESOLUTIONS.values()
