from uv import find_uv_bin

a = Analysis(
    ["launch.py"],
    binaries=[(find_uv_bin(), ".")],   # ship uv next to the app's code
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="mpf-manager", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="mpf-manager")
app = BUNDLE(coll, name="MPF Manager.app", bundle_identifier="com.techwitchastra.mpfmanager")  # macOS only