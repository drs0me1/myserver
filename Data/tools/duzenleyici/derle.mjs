// Builds ../../console/duzenleyici.js from giris.js (DD-249): npm ci && npm run derle
// The banner names every bundled package with its version and copyright line; a package that is
// not MIT licensed stops the build. tests/common.bats checks the banner against package.json.
import { build } from "esbuild";
import { readFileSync, writeFileSync } from "node:fs";

const result = await build({
  entryPoints: ["giris.js"], bundle: true, minify: true, format: "iife", charset: "utf8",
  legalComments: "none", metafile: true, write: false, logLevel: "warning",
});
const packages = new Map();
for (const input of Object.keys(result.metafile.inputs)) {
  const m = /node_modules\/((?:@[^/]+\/)?[^/]+)\//.exec(input);
  if (!m || packages.has(m[1])) continue;
  const dir = `node_modules/${m[1]}`, pkg = JSON.parse(readFileSync(`${dir}/package.json`, "utf8"));
  if (pkg.license !== "MIT") throw new Error(`${pkg.name}: lisans MIT değil (${pkg.license})`);
  let text = "";
  for (const f of ["LICENSE", "LICENSE.md", "LICENSE.txt"]) {
    try { text = readFileSync(`${dir}/${f}`, "utf8"); break; } catch { /* sıradaki ad */ }
  }
  const copyright = (/^Copyright .*$/m.exec(text) || ["Copyright (C) its authors"])[0].trim();
  packages.set(m[1], `${pkg.name} ${pkg.version} — ${copyright}`);
}
const banner = `/*! Konsol text editor (DD-249): CodeMirror 6 bundled from Data/tools/duzenleyici (npm ci && npm run derle).
 * Bundled packages, all under the MIT license:
${[...packages.values()].sort().map((p) => ` *   ${p}`).join("\n")}
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
 * associated documentation files (the "Software"), to deal in the Software without restriction,
 * including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
 * subject to the following conditions: The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS",
 * WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
 * OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
 * CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 * OTHER DEALINGS IN THE SOFTWARE.
 */
`;
const out = new URL("../../console/duzenleyici.js", import.meta.url);
writeFileSync(out, banner + result.outputFiles[0].text);
console.log(`${out.pathname}: ${packages.size} paket, ${(result.outputFiles[0].contents.length / 1024).toFixed(0)} KB`);
