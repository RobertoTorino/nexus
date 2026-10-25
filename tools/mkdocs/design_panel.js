// SPDX-License-Identifier: GPL-3.0-or-later
// The design panel (tools/mkdocs/design_panel.py puts it on every page while `mkdocs serve` runs): every CSS variable
// this wiki's own stylesheets define, with a colour picker, a slider or a text field each. The groups and labels are
// the stylesheet's own comments. A change shows at once and goes to the server, which every open page asks once a
// second, so all devices show the same mock.
(() => {
  "use strict";
  const config = window.__designPanel;
  const endpoint = new URL(config.endpoint, location.href).href;
  const STORE = "design-panel:" + endpoint;
  const FONTS = ["Inter", "Roboto", "Noto Sans", "Open Sans", "system-ui", "Segoe UI", "Helvetica", "Arial",
                 "JetBrains Mono", "Fira Code", "monospace", "sans-serif", "serif"];
  let mock = {version: 0, values: {}};        // "selector|--name" -> value
  let shared = false, synced = false, editedAt = 0, sendTimer = 0;

  const read = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
  const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private window */ } };

  // The rules at the top level of a stylesheet's text: the comment just before each, its selector, and its body with
  // the comments blanked out (same length, so positions in it are positions in the text).
  function topRules(text) {
    const code = text.replace(/\/\*[\s\S]*?\*\//g, c => " ".repeat(c.length));
    const comments = [...text.matchAll(/\/\*([\s\S]*?)\*\//g)].map(m => ({end: m.index + m[0].length, text: m[1]}));
    const rules = [];
    let depth = 0, start = 0, open = 0;
    for (let i = 0; i < code.length; i++) {
      if (code[i] === "{" && depth++ === 0) open = i;
      else if (code[i] === "}" && --depth === 0) {
        const before = comments.filter(c => c.end > start && c.end <= open).pop();
        rules.push({title: before ? before.text.replace(/\s+/g, " ").trim() : "",
                    selector: code.slice(start, open).replace(/\s+/g, " ").trim(),
                    bodyStart: open + 1, body: code.slice(open + 1, i)});
        start = i + 1;
      }
    }
    return {rules, text};
  }

  // The variables: each rule of this wiki's own stylesheets (extra_css) that defines one, in the order of the file,
  // and the theme's fonts. A variable's label is the comment after it on its line; uses lists the rules that read it.
  async function variables() {
    const own = sheet => sheet.href && config.sheets.some(s => new URL(sheet.href).pathname.endsWith("/" + s));
    const groups = [], found = new Map(), uses = new Map();
    for (const sheet of [...document.styleSheets].filter(own)) {
      let parsed;
      try { parsed = topRules(await (await fetch(sheet.href, {cache: "no-store"})).text()); } catch { continue; }
      for (const rule of parsed.rules) {
        for (const m of rule.body.matchAll(/var\((--[\w-]+)/g)) {
          if (!uses.has(m[1])) uses.set(m[1], new Set());
          uses.get(m[1]).add(rule.selector.startsWith("@") ? rule.selector + " …" : rule.selector);
        }
        if (rule.selector.startsWith("@")) continue;
        const group = {title: rule.title, selector: rule.selector, keys: []};
        for (const m of rule.body.matchAll(/(--[\w-]+)\s*:([^;]*);?/g)) {
          const end = rule.bodyStart + m.index + m[0].length;
          const eol = parsed.text.indexOf("\n", end);
          const label = (parsed.text.slice(end, eol < 0 ? undefined : eol).match(/^\s*\/\*(.*?)\*\//) || [])[1];
          const key = rule.selector + "|" + m[1];
          for (const g of groups) g.keys = g.keys.filter(k => k !== key);      // a later stylesheet wins
          found.set(key, {selector: rule.selector, name: m[1], value: m[2].trim(), label: label ? label.trim() : ""});
          group.keys.push(key);
        }
        if (group.keys.length) groups.push(group);
      }
    }
    const root = getComputedStyle(document.documentElement);
    const fonts = {title: "Fonts: the theme's, from mkdocs.yml", selector: ":root", keys: []};
    for (const [name, label] of [["--md-text-font", "Text"], ["--md-code-font", "Code"]]) {
      const value = root.getPropertyValue(name).trim();
      if (value && !found.has(":root|" + name)) {
        found.set(":root|" + name, {selector: ":root", name, value, label});
        fonts.keys.push(":root|" + name);
      }
    }
    groups.push(fonts);
    for (const variable of found.values()) variable.uses = [...(uses.get(variable.name) || [])];
    return {groups: groups.filter(g => g.keys.length), found};
  }

  // A variable's value as the page has it now, var() resolved (Material's variables are set on <body>).
  const current = name => getComputedStyle(document.body).getPropertyValue(name).trim();

  const isColour = v => /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(v);
  const isLength = v => /^-?\d*\.?\d+(px|rem|em)$/.test(v);
  const isFont = name => /font/.test(name);
  const hex6 = v => v.length === 4 ? "#" + [...v.slice(1)].map(c => c + c).join("") : v.slice(0, 7);

  // The mock as CSS: each changed variable under the selector that defines it.
  function css(values) {
    const rules = new Map();
    for (const [key, value] of Object.entries(values)) {
      const [selector, name] = key.split("|");
      if (!rules.has(selector)) rules.set(selector, []);
      rules.get(selector).push(`  ${name}: ${value};`);
    }
    return [...rules].map(([selector, lines]) => `${selector} {\n${lines.join("\n")}\n}`).join("\n\n");
  }

  const style = document.createElement("style");
  style.id = "design-panel-mock";
  function apply() {
    style.textContent = css(mock.values);
    document.head.appendChild(style);           // last in <head>, so it wins over the stylesheets
    output.value = css(mock.values) || "/* No changes yet. */";
    for (const row of rows.values()) row.sync();
  }

  function send() {
    write(STORE, mock);
    clearTimeout(sendTimer);
    sendTimer = setTimeout(() => {
      fetch(endpoint, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(mock)})
        .then(r => r.ok && setShared(true)).catch(() => setShared(false));
    }, 250);
  }

  function change(key, value, original) {
    if (value === original || value === "") delete mock.values[key]; else mock.values[key] = value;
    mock.version = Date.now();
    editedAt = Date.now();
    apply();
    send();
  }

  function poll() {
    fetch(endpoint, {cache: "no-store"}).then(r => r.ok ? r.json() : Promise.reject())
      .then(remote => {
        setShared(true);
        // The server's mock wins once it answers (the browser's copy only bridges the moment before), then a newer one.
        if ((!synced || remote.version > mock.version) && Date.now() - editedAt > 1500) {
          synced = true;
          mock = {version: remote.version, values: remote.values || {}};
          write(STORE, mock);
          apply();
        }
      }).catch(() => setShared(false));
  }

  // The panel, in colours of its own, so it stays readable whatever the mock does to the page.
  const panel = document.createElement("aside");
  panel.className = "dp";
  panel.innerHTML = `
    <button class="dp-toggle" type="button" title="Design panel">Design</button>
    <div class="dp-body" hidden>
      <div class="dp-head"><strong>Design</strong><span class="dp-status"></span></div>
      <div class="dp-site"></div>
      <div class="dp-rows"></div>
      <div class="dp-actions">
        <button type="button" data-action="copy">Copy CSS</button>
        <button type="button" data-action="screens" title="This page at the sizes of PC, laptop and handheld screens">Screens</button>
        <button type="button" data-action="reset">Reset all</button>
      </div>
      <textarea class="dp-output" readonly rows="6" aria-label="The changed variables as CSS"></textarea>
    </div>`;
  const body = panel.querySelector(".dp-body");
  const status = panel.querySelector(".dp-status");
  const output = panel.querySelector(".dp-output");
  const list = panel.querySelector(".dp-rows");
  const rows = new Map();

  function setShared(on) {
    shared = on;
    status.textContent = on ? "shared with every device" : "this device only";
    status.title = on ? "Every page open on this server shows these changes."
                      : "The server is not reachable: the changes stay in this browser.";
  }

  function row(key, variable, group) {
    const el = document.createElement("label");
    el.className = "dp-row";
    const name = document.createElement("span");
    name.className = "dp-name";
    name.textContent = variable.label || variable.name;
    if (variable.label) {
      const code = document.createElement("code");
      code.textContent = variable.name;
      name.append(code);
    }
    name.title = `${variable.selector} { ${variable.name}: ${variable.value} }\n` +
      (variable.uses.length ? `Used by: ${variable.uses.join("; ")}` : "Not used by any rule");
    const text = document.createElement("input");
    text.type = "text";
    text.spellcheck = false;
    let picker = null, slider = null;
    if (isColour(variable.value) || isColour(current(variable.name))) {      // var(--x) of a colour too
      picker = document.createElement("input");
      picker.type = "color";
      picker.addEventListener("input", () => {
        const value = mock.values[key] ?? variable.value;
        const now = isColour(value) ? value : current(variable.name);
        const alpha = now.length === 9 ? now.slice(7) : "";              // the picker has no alpha: keep it
        change(key, picker.value + alpha, variable.value);
      });
    } else if (isLength(variable.value)) {
      const unit = variable.value.match(/(px|rem|em)$/)[1];
      slider = document.createElement("input");
      slider.type = "range";
      slider.min = 0;
      slider.max = unit === "px" ? 48 : 4;
      slider.step = unit === "px" ? 1 : 0.05;
      slider.addEventListener("input", () => change(key, slider.value + unit, variable.value));
    } else if (isFont(variable.name)) {
      text.setAttribute("list", "dp-fonts");
    }
    text.addEventListener("change", () => change(key, text.value.trim(), variable.value));
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "dp-reset";
    reset.textContent = "↺";
    reset.title = "Back to " + variable.value;
    reset.addEventListener("click", e => { e.preventDefault(); change(key, variable.value, variable.value); });
    el.append(name, picker || slider || document.createElement("span"), text, reset);     // four columns
    group.appendChild(el);
    rows.set(key, {sync() {
      const value = mock.values[key] ?? variable.value;
      if (document.activeElement !== text) text.value = value;
      const shown = isColour(value) ? value : current(variable.name);     // var(--x): the colour it gives
      if (picker && isColour(shown)) picker.value = hex6(shown);
      if (slider) slider.value = parseFloat(value);
      el.classList.toggle("dp-changed", key in mock.values);
    }});
  }

  const fonts = document.createElement("datalist");
  fonts.id = "dp-fonts";
  fonts.innerHTML = FONTS.map(f => `<option value='"${f}"'>`).join("");
  panel.appendChild(fonts);

  // What the panel changes: this wiki only, and the file a change belongs in.
  panel.querySelector(".dp-site").textContent =
    `Changes ${config.site} only. Copy CSS into ${config.files.join(" or ")}.`;

  // A group per rule, named by the comment before it (the selector where it has none).
  function build({groups, found}) {
    for (const g of groups) {
      const group = document.createElement("fieldset");
      const legend = document.createElement("legend");
      legend.textContent = g.title || g.selector;
      legend.title = g.selector;
      group.appendChild(legend);
      list.appendChild(group);
      for (const key of g.keys) row(key, found.get(key), group);
    }
  }

  panel.querySelector(".dp-toggle").addEventListener("click", () => {
    body.hidden = !body.hidden;
    write("design-panel:open", !body.hidden);
  });
  panel.querySelector('[data-action="reset"]').addEventListener("click", () => {
    mock = {version: Date.now(), values: {}};
    editedAt = Date.now();
    apply();
    send();
  });
  panel.querySelector('[data-action="screens"]').addEventListener("click", () => {
    const here = new URL(location.href);
    here.searchParams.delete("design");
    window.open(`${endpoint}/screens?page=${encodeURIComponent(here.pathname + here.search + here.hash)}`, "_blank");
  });
  panel.querySelector('[data-action="copy"]').addEventListener("click", e => {
    const done = () => { e.target.textContent = "Copied"; setTimeout(() => { e.target.textContent = "Copy CSS"; }, 1200); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(output.value).then(done);
    } else {                                      // http:// from another device: no clipboard API
      output.select();
      try { if (document.execCommand("copy")) done(); } catch { /* select it by hand */ }
    }
  });

  body.hidden = !(read("design-panel:open", false) || new URLSearchParams(location.search).has("design"));
  if (window.self === window.top) document.body.appendChild(panel);   // in a frame of Screens: the mock only
  mock = read(STORE, mock);
  setShared(false);
  apply();
  variables().then(found => {
    build(found);
    apply();
    poll();
    setInterval(poll, 1000);
  });
})();
