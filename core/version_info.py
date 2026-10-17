"""
Windows PE Version Info Generator for PyInstaller.
Embeds Company, Product, Description, and File Version metadata into the executable.
"""

import os


def generate_version_info_file(filepath: str, version_str: str, exe_name: str, description: str):
    """
    Generates a Windows PE VSVersionInfo file compatible with PyInstaller.
    """
    clean_ver = version_str.lstrip("v").strip()
    parts = []
    for x in clean_ver.split("."):
        try:
            parts.append(int(x))
        except ValueError:
            parts.append(0)
    while len(parts) < 4:
        parts.append(0)
    ver_tuple = tuple(parts[:4])
    ver_joined = ".".join(str(p) for p in parts[:4])

    content = f'''# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver_tuple},
    prodvers={ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904b0',
        [StringStruct('CompanyName', 'mazi0182'),
        StringStruct('FileDescription', '{description}'),
        StringStruct('FileVersion', '{ver_joined}'),
        StringStruct('InternalName', '{exe_name}'),
        StringStruct('LegalCopyright', 'Copyright (c) 2026 mazi0182. All rights reserved.'),
        StringStruct('OriginalFilename', '{exe_name}.exe'),
        StringStruct('ProductName', 'P2P Tunnel Client'),
        StringStruct('ProductVersion', '{clean_ver}')])
      ]), 
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'''
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
