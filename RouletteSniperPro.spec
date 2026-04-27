# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import copy_metadata

datas = [('D:\\GITHUBB\\bot_stake\\bot_ruleta\\icon.ico', '.'), ('D:\\GITHUBB\\bot_stake\\bot_ruleta\\dashboard\\static', 'dashboard/static'), ('D:\\GITHUBB\\bot_stake\\venv\\Lib\\site-packages\\customtkinter', 'customtkinter')]
binaries = []
hiddenimports = ['undetected_chromedriver', 'selenium', 'PIL', 'urllib', 'tkinter', 'waitress']
datas += collect_data_files('selenium')
datas += collect_data_files('customtkinter')
datas += copy_metadata('selenium')
datas += copy_metadata('undetected-chromedriver')
hiddenimports += collect_submodules('customtkinter')
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('selenium')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('undetected_chromedriver')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['D:\\GITHUBB\\bot_stake\\bot_ruleta\\gui_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'IPython'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RouletteSniperPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:\\GITHUBB\\bot_stake\\bot_ruleta\\icon.ico'],
)
