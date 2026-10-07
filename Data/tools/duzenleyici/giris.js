// Konsol's text editor (DD-249): CodeMirror 6 as one IIFE bundle, console/duzenleyici.js, built by
// derle.mjs. konsol.js loads it on first use and talks to window.KonsolEditor only.
import { EditorState } from "@codemirror/state";
import {
  EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection,
  highlightSpecialChars, rectangularSelection, dropCursor,
} from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { syntaxHighlighting, bracketMatching, foldGutter, foldKeymap, indentOnInput, StreamLanguage } from "@codemirror/language";
import { classHighlighter } from "@lezer/highlight";
import { search, searchKeymap, highlightSelectionMatches } from "@codemirror/search";
import { StyleModule } from "style-mod";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { python } from "@codemirror/lang-python";
import { css } from "@codemirror/lang-css";
import { html } from "@codemirror/lang-html";
import { xml } from "@codemirror/lang-xml";
import { yaml } from "@codemirror/lang-yaml";
import { markdown } from "@codemirror/lang-markdown";
import { shell } from "@codemirror/legacy-modes/mode/shell";
import { nginx } from "@codemirror/legacy-modes/mode/nginx";
import { toml } from "@codemirror/legacy-modes/mode/toml";
import { properties } from "@codemirror/legacy-modes/mode/properties";
import { dockerFile } from "@codemirror/legacy-modes/mode/dockerfile";
import { diff } from "@codemirror/legacy-modes/mode/diff";

// Konsol's CSP (style-src 'self') refuses the <style> element style-mod adds to a document. The same
// rules go into one constructed sheet instead, in style-mod's own module order (later modules win).
const sheet = new CSSStyleSheet(), mounted = [];
StyleModule.mount = (root, modules) => {
  let index = 0;
  for (const mod of [].concat(modules).flat(Infinity)) {
    if (!mod) continue;
    let found = mounted.indexOf(mod);
    if (found > -1 && found < index) { mounted.splice(found, 1); index--; found = -1; }
    if (found === -1) mounted.splice(index++, 0, mod); else index = found + 1;
  }
  sheet.replaceSync(mounted.map((m) => m.getRules()).join("\n"));
  const doc = root.ownerDocument || root;
  if (!doc.adoptedStyleSheets.includes(sheet)) doc.adoptedStyleSheets = [...doc.adoptedStyleSheets, sheet];
};

// Operator-facing strings are Turkish.
const PHRASES = {
  "Find": "Bul", "Replace": "Değiştir", "next": "sonraki", "previous": "önceki", "all": "tümü",
  "match case": "büyük/küçük harf", "regexp": "düzenli ifade", "by word": "tam sözcük",
  "replace": "değiştir", "replace all": "tümünü değiştir", "close": "kapat", "current match": "geçerli eşleşme",
  "on line": "satırda", "replaced $ matches": "$ eşleşme değiştirildi", "replaced match on line $": "$. satırdaki eşleşme değiştirildi",
  "Go to line": "Satıra git", "go": "git", "Control character": "Denetim karakteri", "Selection deleted": "Seçim silindi",
  "folded code": "katlanmış bölüm", "unfold": "aç", "to": "–", "Fold line": "Satırı katla", "Unfold line": "Satırı aç",
  "Folded lines": "Satırlar katlandı", "Unfolded lines": "Satırlar açıldı",
};

const legacy = (mode) => () => StreamLanguage.define(mode);
const KINDS = {
  yaml: ["YAML", yaml], json: ["JSON", json], js: ["JavaScript", javascript], ts: ["TypeScript", () => javascript({ typescript: true })],
  py: ["Python", python], css: ["CSS", css], html: ["HTML", html], xml: ["XML", xml], md: ["Markdown", markdown],
  sh: ["Kabuk", legacy(shell)], ini: ["INI", legacy(properties)], toml: ["TOML", legacy(toml)], nginx: ["nginx", legacy(nginx)],
  docker: ["Dockerfile", legacy(dockerFile)], diff: ["Fark", legacy(diff)], conf: ["Yapılandırma", legacy(shell)], text: ["Düz metin", null],
};
const BY_EXT = {
  yaml: "yaml", yml: "yaml", json: "json", js: "js", mjs: "js", cjs: "js", ts: "ts", py: "py", css: "css", html: "html", htm: "html",
  xml: "xml", svg: "xml", md: "md", sh: "sh", bash: "sh", zsh: "sh", ini: "ini", env: "ini", properties: "ini", service: "ini",
  timer: "ini", socket: "ini", mount: "ini", path: "ini", target: "ini", network: "ini", netdev: "ini", link: "ini", container: "ini",
  toml: "toml", diff: "diff", patch: "diff", conf: "conf", cfg: "conf", cnf: "conf", rules: "conf", caddy: "conf",
};
// A name without an extension (sshd_config, hosts, fstab, Caddyfile) is read as configuration:
// # comments, strings and numbers are coloured.
function kindOf(name) {
  const lower = name.toLowerCase(), dot = lower.lastIndexOf(".");
  if (lower === "dockerfile" || lower.startsWith("dockerfile.")) return "docker";
  if (/(^|\.)nginx\.conf$/.test(lower) || lower.startsWith("nginx")) return "nginx";
  if (dot <= 0) return lower.startsWith(".") && !lower.slice(1).includes(".") ? "sh" : "conf";
  return BY_EXT[lower.slice(dot + 1)] || "text";
}

window.KonsolEditor = {
  language(name) { return KINDS[kindOf(name)][0]; },
  // doc: the text (lines joined with "\n"); onChange(dirty), onCursor(line, column), onSave().
  create(parent, { doc, name, label, onChange, onCursor, onSave }) {
    const [, lang] = KINDS[kindOf(name)];
    let saved = null;
    const view = new EditorView({
      parent,
      state: EditorState.create({
        doc,
        extensions: [
          EditorState.phrases.of(PHRASES),
          lineNumbers(), highlightActiveLineGutter(), highlightSpecialChars(), history(), foldGutter(), drawSelection(), dropCursor(),
          EditorState.allowMultipleSelections.of(true), rectangularSelection(), indentOnInput(), syntaxHighlighting(classHighlighter),
          bracketMatching(), highlightActiveLine(), highlightSelectionMatches(), search({ top: true }),
          keymap.of([{ key: "Mod-s", preventDefault: true, run: () => { if (onSave) onSave(); return true; } },
            ...defaultKeymap, ...searchKeymap, ...historyKeymap, ...foldKeymap, indentWithTab]),
          EditorView.contentAttributes.of({ "aria-label": label || name, spellcheck: "false", autocorrect: "off", autocapitalize: "off" }),
          lang ? lang() : [],
          EditorView.updateListener.of((u) => {
            if (u.docChanged && onChange) onChange(!u.state.doc.eq(saved));
            if ((u.selectionSet || u.docChanged) && onCursor) {
              const head = u.state.selection.main.head, line = u.state.doc.lineAt(head);
              onCursor(line.number, head - line.from + 1);
            }
          }),
        ],
      }),
    });
    saved = view.state.doc;
    return {
      view,
      text: () => view.state.doc.toString(),
      dirty: () => !view.state.doc.eq(saved),
      // After a save: the current text is the new clean state.
      markSaved() { saved = view.state.doc; if (onChange) onChange(false); },
      focus: () => view.focus(),
      destroy: () => view.destroy(),
    };
  },
};
