# PyInstaller spec for ADI-2 Commander, run by tools/build.py. One folder, dist/Commander, not one file: the Qt
# libraries stay files of their own, which a user may replace (LGPL).

import os
import sys

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

ROOT = os.path.dirname(SPECPATH)
sys.path.insert(0, ROOT)
from commander import __version__                         # noqa: E402

NAME = "ADI-2 Commander"
NUMBERS = tuple(int(n) for n in __version__.split("-")[0].split(".")) + (0,)       # 0.1.0-rc.1 -> (0, 1, 0, 0)

# pyqtgraph imports QtOpenGL, QtSvg and QtTest itself; these come only with plugins Commander has no use for:
# the virtual keyboard (with Qml and Quick), PDF images, TLS, network information and touch over the network (TUIO),
# software OpenGL.
DROP = {"opengl32sw.dll", "qtvirtualkeyboardplugin.dll", "qpdf.dll", "qcertonlybackend.dll", "qopensslbackend.dll",
        "qschannelbackend.dll", "qnetworklistmanager.dll", "qtuiotouchplugin.dll", "Qt6VirtualKeyboard.dll",
        "Qt6Pdf.dll", "Qt6Qml.dll",
        "Qt6QmlMeta.dll", "Qt6QmlModels.dll", "Qt6QmlWorkerScript.dll", "Qt6Quick.dll", "Qt6Network.dll",
        "libcrypto-3-x64.dll", "libssl-3-x64.dll"}

a = Analysis([os.path.join(ROOT, "Commander.pyw")],
             pathex=[ROOT],
             datas=[(os.path.join(ROOT, "commander", "ui", "icon.ico"), "commander/ui"),
                    (os.path.join(ROOT, "commander", "ui", "icon-simulated.ico"), "commander/ui"),
                    (os.path.join(ROOT, "commander", "device", "demo"), "commander/device/demo")],
             excludes=["PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "pyqtgraph.opengl",
                       "pyqtgraph.examples", "pyqtgraph.jupyter", "tkinter"])
a.binaries = [b for b in a.binaries if os.path.basename(b[0]) not in DROP]
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").startswith("PySide6/translations/")]

version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS),
    kids=[StringFileInfo([StringTable("040904B0", [StringStruct("CompanyName", "Alexander van den Bosch"),
                                                   StringStruct("FileDescription", NAME),
                                                   StringStruct("FileVersion", __version__),
                                                   StringStruct("InternalName", "Commander"),
                                                   StringStruct("LegalCopyright",
                                                                "Copyright (C) 2026 Alexander van den Bosch"),
                                                   StringStruct("OriginalFilename", "Commander.exe"),
                                                   StringStruct("ProductName", NAME),
                                                   StringStruct("ProductVersion", __version__)])]),
          VarFileInfo([VarStruct("Translation", [0x0409, 1200])])])

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Commander", console=False, upx=False,
          icon=os.path.join(ROOT, "commander", "ui", "icon.ico"), version=version)
coll = COLLECT(exe, a.binaries, a.datas, name="Commander", upx=False)
