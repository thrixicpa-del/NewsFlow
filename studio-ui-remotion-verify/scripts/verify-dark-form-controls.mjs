import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const styles = readFileSync(resolve(root, 'src/ui/styles.css'), 'utf8');
const required = '.youtube-source-sample textarea{display:block;width:100%;min-height:84px;padding:12px;border:1px solid #253a53;border-radius:9px;background:#081522;color:#cbd8e8;resize:vertical;outline:none}';

if (!styles.includes(required)) {
  console.error('Dark form-control contract failed: channel-reference rules textarea is missing the NewsFlow dark theme.');
  process.exit(1);
}

console.log('Dark form-control contract passed: channel-reference rules textarea uses the NewsFlow dark theme.');
