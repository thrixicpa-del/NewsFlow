"""Native regression: actual NSIS plugin must restore every architecture payload."""
import hashlib
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'studio-ui-remotion-verify'


@unittest.skipUnless(os.name == 'nt', 'Windows NSIS integration')
class WindowsPortableArchiveTests(unittest.TestCase):
    def test_nsis_restores_arm64_and_x64_files_with_packaging_filter(self):
        self.assertEqual(os.environ.get('NEWSFLOW_TEST_MODE'), '1', 'Use run_isolated.py')
        cache = Path(os.environ['NEWSFLOW_PRODUCTION_LOCALAPPDATA']) / 'electron-builder/Cache'
        archive_tool = next(cache.glob('7zip@*/**/bin/7za.exe'))
        compiler = next(p for p in cache.glob('nsis-*/**/makensis.exe') if p.parent.name == 'Bin')
        plugin = next(cache.glob('nsis-resources-*/**/plugins/x86-unicode/nsis7z.dll'))
        package = json.loads((APP/'package.json').read_text())
        resource = next(item for item in package['build']['extraResources'] if item['to']=='core-bin')
        library = (APP/resource['from']/'_internal/tkinterdnd2/tkdnd').resolve()
        inputs = ['win-arm64/libtkdnd2.10.2.dll', 'linux-arm64/libtkdnd2.10.2.so',
                  'osx-arm64/libtkdnd2.10.2.dylib', 'win-x64/libtkdnd2.10.2.dll']
        code = "import { windowsPackagingEnvironment } from './scripts/windows-packaging-env.mjs'; console.log(JSON.stringify(windowsPackagingEnvironment({})));"
        environment = json.loads(subprocess.check_output(['node','--input-type=module','-e',code],cwd=APP,text=True))
        with TemporaryDirectory(prefix='nsis-filter-',dir=os.environ['NEWSFLOW_TEST_ROOT']) as temporary:
            work = Path(temporary)
            source, output = work/'input', work/'output'
            source.mkdir()
            output.mkdir()
            for relative in inputs:
                target = source/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(library/relative,target)
            archive = work/'payload.7z'
            args = [str(archive_tool),'a','-t7z','-mx=9','-mtc=off','-mtm=off','-mta=off']
            if environment.get('ELECTRON_BUILDER_7Z_FILTER'):
                args += ['-mf='+environment['ELECTRON_BUILDER_7Z_FILTER']]
            subprocess.run([*args,str(archive),'.'],cwd=source,check=True,capture_output=True,timeout=20)
            helper = work/'extract.exe'
            script = work/'extract.nsi'
            script.write_text(f'''Unicode true
SilentInstall silent
RequestExecutionLevel user
OutFile "{helper}"
!addplugindir /x86-unicode "{plugin.parent}"
Section
InitPluginsDir
SetOutPath "{output}"
File /oname=payload.7z "{archive}"
Nsis7z::Extract "{output / 'payload.7z'}"
Delete "{output / 'payload.7z'}"
SectionEnd
''',encoding='utf-8')
            subprocess.run([str(compiler),'/V2',str(script)],check=True,capture_output=True,timeout=20)
            subprocess.run([str(helper)],check=True,capture_output=True,timeout=20,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            restored = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(restored,set(inputs),'NSIS silently omitted an unsupported 7z architecture filter')
            for relative in inputs:
                self.assertEqual(hashlib.sha256((source/relative).read_bytes()).hexdigest(),
                                 hashlib.sha256((output/relative).read_bytes()).hexdigest(),relative)
