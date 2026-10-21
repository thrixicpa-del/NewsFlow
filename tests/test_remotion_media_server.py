"""Real loopback requests stay within the current disposable media manifest."""
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "studio-ui-remotion-verify/remotion/local-media-server.mjs"


@unittest.skipUnless(shutil.which("node"), "Node runtime unavailable")
class RemotionMediaServerTests(unittest.TestCase):
    def run_case(self, body):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1", "use tests/run_isolated.py")
        script = f"""
import assert from 'node:assert/strict';
import {{ mkdtemp, writeFile, rm, symlink }} from 'node:fs/promises';
import {{ join }} from 'node:path';
import {{ createLocalMediaServer }} from {json.dumps(MODULE.as_uri())};
const root = await mkdtemp(join(process.env.NEWSFLOW_TEST_ROOT, 'remotion-server-'));
const media = join(root, 'selected.mp4');
const outside = join(root, 'private-test.txt');
await writeFile(media, '0123456789');
await writeFile(outside, 'disposable secret fixture');
const server = await createLocalMediaServer([media]);
await new Promise((resolve, reject) => {{
  server.once('error', reject);
  server.listen(0, '127.0.0.1', resolve);
}});
const url = (file) => `http://127.0.0.1:${{server.address().port}}/media?src=${{Buffer.from(file).toString('base64url')}}`;
try {{
{body}
}} finally {{
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
  await rm(root, {{ recursive: true, force: true }});
}}
"""
        result = subprocess.run([shutil.which("node"), "--input-type=module", "-e", script],
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-4000:])
        if "SYMLINK_FIXTURE_UNAVAILABLE" in result.stdout:
            self.skipTest("Windows account cannot create the disposable symlink fixture")

    def test_serves_only_selected_file_and_normalized_selected_alias(self):
        self.run_case("""
for (const file of [media, join(root, 'unused') + '/../selected.mp4']) {
  const response = await fetch(url(file));
  assert.equal(response.status, 200);
  assert.equal(await response.text(), '0123456789');
}
""")

    def test_rejects_unselected_file_and_normalized_escape(self):
        self.run_case("""
for (const file of [outside, join(root, 'unused') + '/../private-test.txt']) {
  const response = await fetch(url(file));
  assert.equal(response.status, 404);
  assert.equal(await response.text(), '');
}
""")

    def test_permits_selected_byte_range_without_exposing_other_files(self):
        self.run_case("""
const response = await fetch(url(media), { headers: { Range: 'bytes=2-5' } });
assert.equal(response.status, 206);
assert.equal(response.headers.get('content-range'), 'bytes 2-5/10');
assert.equal(await response.text(), '2345');
const outsideResponse = await fetch(url(outside), { headers: { Range: 'bytes=0-3' } });
assert.equal(outsideResponse.status, 404);
assert.equal(await outsideResponse.text(), '');
""")

    def test_serves_single_first_byte(self):
        self.run_case("""
const response = await fetch(url(media), { headers: { Range: 'bytes=0-0' } });
assert.equal(response.status, 206);
assert.equal(response.headers.get('content-range'), 'bytes 0-0/10');
assert.equal(response.headers.get('content-length'), '1');
assert.equal(await response.text(), '0');
""")

    def test_serves_suffix_ranges_from_the_end(self):
        self.run_case("""
for (const [range, contentRange, body] of [
  ['bytes=-3', 'bytes 7-9/10', '789'],
  ['bytes=-20', 'bytes 0-9/10', '0123456789'],
]) {
  const response = await fetch(url(media), { headers: { Range: range } });
  assert.equal(response.status, 206);
  assert.equal(response.headers.get('content-range'), contentRange);
  assert.equal(await response.text(), body);
}
""")

    def test_serves_open_ended_range(self):
        self.run_case("""
const response = await fetch(url(media), { headers: { Range: 'bytes=7-' } });
assert.equal(response.status, 206);
assert.equal(response.headers.get('content-range'), 'bytes 7-9/10');
assert.equal(await response.text(), '789');
""")

    def test_rejects_unsatisfiable_ranges_without_streaming_other_bytes(self):
        self.run_case("""
for (const range of ['bytes=10-20', 'bytes=10-', 'bytes=-0']) {
  const response = await fetch(url(media), { headers: { Range: range } });
  assert.equal(response.status, 416);
  assert.equal(response.headers.get('content-range'), 'bytes */10');
  assert.equal(await response.text(), '');
}
await writeFile(media, '');
const response = await fetch(url(media), { headers: { Range: 'bytes=0-' } });
assert.equal(response.status, 416);
assert.equal(response.headers.get('content-range'), 'bytes */0');
assert.equal(await response.text(), '');
""")

    def test_replaced_selected_symlink_cannot_redirect_to_an_unselected_file(self):
        self.run_case("""
await rm(media);
let linked = false;
try {
  await symlink(outside, media, 'file');
  linked = true;
} catch (error) {
  if (process.platform !== 'win32' || error.code !== 'EPERM') throw error;
  console.log('SYMLINK_FIXTURE_UNAVAILABLE');
}
if (linked) {
  const response = await fetch(url(media));
  assert.equal(response.status, 404);
  assert.equal(await response.text(), '');
}
""")

    def test_unpacked_renderer_keeps_its_helper_available(self):
        package = json.loads((ROOT / "studio-ui-remotion-verify/package.json").read_text(encoding="utf-8"))
        self.assertIn("remotion/local-media-server.mjs", package["build"]["asarUnpack"])
        runner = (ROOT / "studio-ui-remotion-verify/remotion/render.mjs").read_text(encoding="utf-8")
        self.assertIn("createLocalMediaServer([", runner)
        self.assertIn("sequence.src", runner)
        self.assertIn("project.voiceover?.src", runner)


if __name__ == "__main__":
    unittest.main()
