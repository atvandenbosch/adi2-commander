"""Build the installer, dist\\ADI-2-Commander-<version>-setup.exe.

    .venv\\Scripts\\python.exe -m pip install -r requirements-build.txt
    .venv\\Scripts\\python.exe tools\\build.py

Needs Inno Setup 6 as well (https://jrsoftware.org/isinfo.php). PyInstaller makes the program folder
dist\\Commander (installer\\Commander.spec); the licenses of Commander and of what it bundles go into it; the wizard's
images are drawn into build\\wizard; Inno Setup packs that folder (installer\\Commander.iss), per user and without
administrator rights, with two Start menu shortcuts: the device and the simulator.
"""

import importlib.metadata
import os
import shutil
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from commander import __version__                           # noqa: E402
from commander.app import APP_ID, SIMULATED_APP_ID          # noqa: E402
from commander.device import DEVICE, MODEL                  # noqa: E402
from make_icon import draw                                  # noqa: E402  (beside this script)

DIST = os.path.join(ROOT, "dist")
FOLDER = os.path.join(DIST, "Commander")
INSTALLER = os.path.join(ROOT, "installer")
WIZARD = os.path.join(ROOT, "build", "wizard")
# The wizard's image areas at 100, 125, 150 and 200 % (Inno Setup's WizardImageFile and WizardSmallImageFile): the
# app's icon on the first and last page, and in the upper right corner of the others
LARGE = [(202, 386), (269, 515), (336, 643), (430, 824)]
SMALL = [58, 77, 97, 124]

DESCRIPTION = "Control the %s from your computer: input, EQ, presets and output settings" % DEVICE
SIMULATED_DESCRIPTION = ("ADI-2 Commander with a simulated %s: work out EQ settings, fit filter files, "
                         "see the curves" % MODEL)

NOTICE = """\
ADI-2 Commander {version} is free software under the GNU General Public License, version 3 or later (LICENSE.txt).
It includes the following software, each under its own license, in this folder:

Python {python}
    PSF License, with the libraries of its Windows build (Python.txt)
    https://www.python.org/downloads/source/

Qt {qt}, PySide6 and Shiboken6 {pyside}
    GNU Lesser General Public License, version 3 (LGPL-3.0.txt, which adds to the GPL in ..\\LICENSE.txt)
    https://download.qt.io/official_releases/qt/
    https://download.qt.io/official_releases/QtForPython/
    The Qt libraries are the Qt6*.dll files in ..\\_internal\\PySide6; they may be replaced by other builds of
    the same version.

NumPy {numpy}
    BSD-3-Clause, with the libraries it bundles (numpy)
    https://numpy.org

pyqtgraph {pyqtgraph}
    MIT License (pyqtgraph.txt)
    https://www.pyqtgraph.org
"""


def license_files(dist):
    """The license files a distribution ships, as (path relative to its licenses folder, absolute path)."""
    return [(os.path.join(*f.parts[2:]), str(f.locate())) for f in importlib.metadata.distribution(dist).files
            if f.parts[0].endswith(".dist-info") and f.parts[1] == "licenses"]


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def licenses():
    """LICENSE.txt and licenses\\ in the program folder."""
    from PySide6.QtCore import qVersion
    copy(os.path.join(ROOT, "LICENSE"), os.path.join(FOLDER, "LICENSE.txt"))
    out = os.path.join(FOLDER, "licenses")
    copy(os.path.join(sys.base_prefix, "LICENSE.txt"), os.path.join(out, "Python.txt"))
    copy(os.path.join(INSTALLER, "LGPL-3.0.txt"), os.path.join(out, "LGPL-3.0.txt"))
    for name, path in license_files("numpy"):
        copy(path, os.path.join(out, "numpy", name))
    [(_, path)] = license_files("pyqtgraph")
    copy(path, os.path.join(out, "pyqtgraph.txt"))
    v = importlib.metadata.version
    with open(os.path.join(out, "README.txt"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(NOTICE.format(version=__version__, python=sys.version.split()[0], qt=qVersion(),
                              pyside=v("PySide6"), numpy=v("numpy"), pyqtgraph=v("pyqtgraph")))


def wizard_images():
    """build\\wizard\\large-*.png and small-*.png: the icon, transparent around it; on the large ones half the width
    wide, a third of the way down."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])   # noqa: F841
    os.makedirs(WIZARD, exist_ok=True)
    for w, h in LARGE:
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        icon = draw(w // 2)
        p = QPainter(img)
        p.drawImage((w - icon.width()) // 2, h // 3 - icon.height() // 2, icon)
        p.end()
        img.save(os.path.join(WIZARD, "large-%d.png" % w))
    for size in SMALL:
        draw(size).save(os.path.join(WIZARD, "small-%d.png" % size))


def iscc():
    """Inno Setup's compiler: installed per user, for all users, or on the PATH."""
    places = [os.path.join(os.environ.get(var, ""), *sub, "Inno Setup 6", "ISCC.exe")
              for var, sub in (("LOCALAPPDATA", ["Programs"]), ("ProgramFiles(x86)", []), ("ProgramFiles", []))]
    for path in places + [shutil.which("ISCC")]:
        if path and os.path.exists(path):
            return path
    raise SystemExit("Inno Setup 6 not found (ISCC.exe)")


def main():
    compiler = iscc()
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", DIST,
                    "--workpath", os.path.join(ROOT, "build"), os.path.join(INSTALLER, "Commander.spec")],
                   cwd=ROOT, check=True)
    licenses()
    wizard_images()
    numeric = __version__.split("-")[0]
    subprocess.run([compiler, "/Qp", "/O" + DIST, "/DVersion=" + __version__, "/DNumericVersion=" + numeric,
                    "/DFolder=" + FOLDER, "/DWizard=" + WIZARD,
                    "/DAppId=" + APP_ID, "/DSimulatedAppId=" + SIMULATED_APP_ID,
                    "/DDescription=" + DESCRIPTION, "/DSimulatedDescription=" + SIMULATED_DESCRIPTION,
                    os.path.join(INSTALLER, "Commander.iss")], check=True)
    print("installer:", os.path.join(DIST, "ADI-2-Commander-%s-setup.exe" % __version__))


if __name__ == "__main__":
    main()
