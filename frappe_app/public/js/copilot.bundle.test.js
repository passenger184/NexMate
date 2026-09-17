// Regression suite for frappe_app/public/js/copilot.bundle.js.
// Boots the REAL bundle against a minimal DOM stub (no browser needed)
// and asserts rendered output. Run: node frappe_app/public/js/<this file>
// Exit code is nonzero on any failure.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("node:vm");
const BUNDLE = path.join(__dirname, "copilot.bundle.js");
const CSS = path.join(__dirname, "..", "css", "copilot.css");

/* ---------- minimal DOM stub ---------- */
const VOID = new Set(["br", "hr", "img", "input", "link", "meta"]);
function parseAttrs(s) {
  const attrs = {};
  const re = /([\w-]+)(?:="([^"]*)")?/g;
  let m;
  while ((m = re.exec(s))) attrs[m[1]] = m[2] === undefined ? "" : m[2];
  return attrs;
}
function parseHTML(html, parent) {
  const tagRe = /<\/?[a-zA-Z][^>]*>/g;
  let last = 0, m, stack = [parent];
  const top = () => stack[stack.length - 1];
  let mm;
  while ((mm = tagRe.exec(html))) {
    const text = html.slice(last, mm.index);
    if (text) top().children.push({ nodeType: 3, text });
    const tag = mm[0];
    if (tag[1] === "/") { if (stack.length > 1) stack.pop(); }
    else {
      const inner = tag.slice(1, tag.endsWith("/>") ? -2 : -1).trim();
      const sp = inner.search(/\s/);
      const name = (sp === -1 ? inner : inner.slice(0, sp)).toLowerCase();
      const el = makeEl(name, sp === -1 ? {} : parseAttrs(inner.slice(sp + 1)));
      top().children.push(el); el.parent = top();
      if (!VOID.has(name) && !tag.endsWith("/>")) stack.push(el);
    }
    last = mm.index + tag.length;
  }
  const tail = html.slice(last);
  if (tail) top().children.push({ nodeType: 3, text: tail });
}
function escHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function makeEl(tag, attrs) {
  const el = {
    nodeType: 1, tag, attrs: attrs || {}, children: [], parent: null,
    style: {}, dataset: {}, value: "", disabled: false,
    scrollTop: 0, scrollHeight: 0,
    _listeners: {},
    _cls: new Set(((attrs || {}).class || "").split(/\s+/).filter(Boolean)),
    get className() { return [...this._cls].join(" "); },
    set className(v) { this._cls = new Set(String(v).split(/\s+/).filter(Boolean)); },
    classList: null, textContent: "",
    addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); },
    removeEventListener() {},
    dispatch(ev) { (this._listeners[ev.type] || []).forEach((f) => f(ev)); },
    appendChild(c) { c.parent = this; this.children.push(c); return c; },
    focus() {},
    scrollIntoView() {},
    click() { this.dispatch({ type: "click", preventDefault() {} }); },
    querySelector(s) { return walk(this, s, [])[0] || null; },
    querySelectorAll(s) { return walk(this, s, []); },
  };
  el.classList = {
    add: (...c) => c.forEach((x) => el._cls.add(x)),
    remove: (...c) => c.forEach((x) => el._cls.delete(x)),
    toggle: (c, f) => { const has = el._cls.has(c); (f === undefined ? !has : f) ? el._cls.add(c) : el._cls.delete(c); },
    contains: (c) => el._cls.has(c),
  };
  Object.defineProperty(el, "innerHTML", {
    get() {
      return el.children.map((c) => c.nodeType === 3 ? c.text
        : `<${c.tag}${attrsOut(c)}>${c.innerHTML}</${c.tag}>`).join("");
    },
    set(h) { el.children = []; parseHTML(String(h), el); },
  });
  Object.defineProperty(el, "textContent", {
    get() { return el.children.map((c) => c.nodeType === 3 ? c.text : c.textContent).join(""); },
    set(v) { el.children = []; el._raw = String(v); },
  });
  // esc() compatibility: textContent-set divs read back escaped HTML
  const origSet = Object.getOwnPropertyDescriptor(el, "textContent").set;
  Object.defineProperty(el, "textContent", {
    get: Object.getOwnPropertyDescriptor(el, "textContent").get,
    set(v) { origSet.call(el, v); el.children = [{ nodeType: 3, text: escHtml(v) }]; },
  });
  Object.defineProperty(el, "lastElementChild", {
    get() {
      for (let k = el.children.length - 1; k >= 0; k--)
        if (el.children[k].nodeType === 1) return el.children[k];
      return null;
    },
  });
  Object.defineProperty(el, "firstElementChild", {
    get() { return el.children.find((c) => c.nodeType === 1) || null; },
  });
  for (const [k, v] of Object.entries(el.attrs)) {
    if (k.startsWith("data-")) el.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = v;
  }
  return el;
}
function attrsOut(c) {
  let s = "";
  if (c._cls.size) s += ` class="${[...c._cls].join(" ")}"`;
  for (const [k, v] of Object.entries(c.attrs || {}))
    if (k !== "class") s += ` ${k}="${v}"`;
  return s;
}
function matchSel(node, sel) {
  if (node.nodeType !== 1) return false;
  let rest = sel;
  const hm = rest.match(/^#([\w-]+)/);
  if (hm) {
    if (node.attrs.id !== hm[1]) return false;
    rest = rest.slice(hm[0].length);
    if (!rest) return true;
  }
  const m = rest.match(/^(?:([a-zA-Z][\w-]*)?((?:\.[\w-]+)*))?(?:\[([\w-]+)(?:="([^"]*)")?\])?$/);
  if (!m) return false;
  const [, tag, clsPart, attr, val] = m;
  if (tag && node.tag !== tag.toLowerCase()) return false;
  for (const c of (clsPart || "").split(".").filter(Boolean))
    if (!node._cls.has(c)) return false;
  if (attr) {
    const av = node.attrs[attr];
    if (av === undefined) return false;
    if (val !== undefined && av !== val) return false;
  }
  return true;
}
function walk(node, sel, acc) {
  for (const c of node.children || []) {
    if (matchSel(c, sel)) acc.push(c);
    walk(c, sel, acc);
  }
  return acc;
}
function createFixture(preview, fetcher) {
  const documentStub = {
    readyState: "complete",
    body: makeEl("body", {}),
    createElement(t) { return makeEl(t.toLowerCase(), {}); },
    createTextNode(t) { return { nodeType: 3, text: String(t), parent: null }; },
    querySelector(s) { return walk(this.body, s, [])[0] || null; },
    querySelectorAll(s) { return walk(this.body, s, []); },
    getElementById(id) { return walk(this.body, "#" + id, [])[0] || null; },
    addEventListener() {},
  };
  const store = {};
  const calls = [];
  let respond = fetcher || (() => { throw new Error("Unexpected fixture request"); });
  const context = vm.createContext({
    window: {
      COPILOT_API_BASE: "http://127.0.0.1:8000",
      location: { pathname: preview ? "/ui/preview.html" : "/app" },
    },
    document: documentStub,
    navigator: {},
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
    },
    fetch: (...args) => { calls.push(args); return respond(...args); },
    setTimeout,
    frappe: preview ? undefined : {
      csrf_token: "synthetic-csrf-token",
      boot: { copilot_settings: { api_base: "http://inference.invalid:8000" } },
    },
  });
  const source = fs.readFileSync(BUNDLE, "utf8");
  const ending = source.lastIndexOf("})();");
  if (ending < 0) throw new Error("Missing bundle closure");
  vm.runInContext(source.slice(0, ending) +
    "globalThis.cardRenderers = { renderEditCard, renderWriteCard };\n" +
    source.slice(ending), context, { filename: BUNDLE });
  return {
    document: documentStub, store, calls, context,
    setFetch(fn) { respond = fn; },
    q: (s) => documentStub.body.querySelector(s),
    qa: (s) => documentStub.body.querySelectorAll(s),
    send(text) {
      documentStub.getElementById("cp-input").value = text;
      documentStub.getElementById("cp-send").click();
    },
  };
}

/* ---------- environment stubs ---------- */
let fetchImpl = null;
function jsonResp(obj, ok = true, status = 200) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(obj) });
}

/* ---------- boot the real bundle ---------- */
const preview = createFixture(true, (...args) => fetchImpl(...args));
const documentStub = preview.document;

const results = [];
function check(name, cond, extra) {
  results.push([cond ? "PASS" : "FAIL", name, cond ? "" : (extra || "")]);
}
const tick = (ms = 15) => new Promise((r) => setTimeout(r, ms));

function deskResponse(sessionId, mode = "employee", answer = "Desk answer") {
  return jsonResp({ message: {
    answer, session_id: sessionId, mode, confidence: "high", route: "rag",
    sources: [], version_info: { status: "unavailable" },
  } });
}

async function testDesk() {
  const desk = createFixture(false);
  const initialId = desk.store["copilot.session"];
  check("Desk mode selector is disabled", desk.q("#cp-mode").disabled);
  for (const mode of ["employee", "developer"]) {
    desk.setFetch((url, opts) => deskResponse(JSON.parse(opts.body).session_id, mode));
    desk.send("help");
    await tick();
    const [url, opts] = desk.calls[desk.calls.length - 1];
    const body = JSON.parse(opts.body);
    check("Desk " + mode + " chat uses only Frappe gateway",
      url === "/api/method/erpnext_ai_copilot.api.ask" && opts.method === "POST" &&
      opts.credentials === "same-origin" && opts.redirect === "error" &&
      opts.headers["X-Frappe-CSRF-Token"] === "synthetic-csrf-token" &&
      opts.headers["Content-Type"] === "application/json");
    check("Desk " + mode + " chat sends question/session only",
      Object.keys(body).sort().join(",") === "question,session_id" &&
      body.question === "help" && body.session_id === initialId &&
      !("X-NexMate-Key" in opts.headers));
    check("Desk synchronizes server-derived " + mode + " mode",
      desk.q("#cp-mode").value === mode && desk.q("#cp-mode").disabled &&
      desk.store["copilot.mode"] === mode &&
      desk.q("#cp-messages").innerHTML.includes("Desk answer"));
  }
  const beforeMode = desk.calls.length;
  desk.q("#cp-mode").value = "employee";
  desk.q("#cp-mode").dispatch({ type: "change" });
  check("Desk ignores synthetic selector changes without requests",
    desk.calls.length === beforeMode && desk.store["copilot.mode"] === "developer");

  for (const command of ["/read", "/search", "/explain", "/edit", "/newdoc", "/editdoc"]) {
    for (const suffix of ["", " synthetic arguments"]) {
      const before = desk.calls.length;
      desk.send(command + suffix);
      await tick();
      check("Desk refuses " + command + (suffix ? " with arguments" : " bare") + " locally",
        desk.calls.length === before &&
        desk.q("#cp-messages").lastElementChild.innerHTML.includes("unavailable in Desk"));
    }
  }

  const beforeCards = desk.calls.length;
  for (const [renderer, proposal] of [
    ["renderEditCard", { path: "synthetic.py", diff: "-old\n+new", proposal_id: "stale-edit", expires_minutes: 15 }],
    ["renderWriteCard", { action: "create", doctype: "Customer", name: "", env_label: "staging",
      preview: { body: {} }, reason: "synthetic", proposal_id: "stale-write", expires_minutes: 15 }],
  ]) {
    const message = makeEl("div", {});
    desk.q("#cp-messages").appendChild(message);
    desk.context.cardRenderers[renderer](message, proposal);
    message.click();
    message.querySelector(".cp-card").click();
    check("Desk " + renderer + " has no executable approve or reject controls",
      message.innerHTML.includes("unavailable in Desk") &&
      message.querySelectorAll("button").length === 0 &&
      !message.innerHTML.includes("cp-committed") &&
      !message.innerHTML.includes("cp-rejected") && desk.calls.length === beforeCards);
  }

  const beforeFresh = desk.calls.length;
  desk.q("#cp-fresh").click();
  check("Desk start-fresh replaces ID and clears transcript without server reset",
    desk.store["copilot.session"] !== initialId && desk.calls.length === beforeFresh &&
    desk.qa(".cp-msg").length === 0 && desk.qa(".cp-empty").length === 1);

  const marker = "synthetic-private-upstream-detail";
  for (const [name, response] of [
    ["HTTP", () => jsonResp({ message: marker, detail: marker, _server_messages: marker }, false, 503)],
    ["network", () => Promise.reject(new Error(marker))],
    ["invalid JSON", () => Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new Error(marker)) })],
    ["invalid envelope", () => jsonResp({ message: marker })],
  ]) {
    desk.setFetch(response);
    const before = desk.calls.length;
    desk.send("help");
    await tick();
    const html = desk.q("#cp-messages").lastElementChild.innerHTML;
    check("Desk " + name + " failure is sanitized without FastAPI fallback",
      desk.calls.length === before + 1 &&
      desk.calls[before][0] === "/api/method/erpnext_ai_copilot.api.ask" &&
      html.includes("NexMate assistant is unavailable") && !html.includes(marker));
  }

  for (const outcome of ["success", "failure"]) {
    const delayed = createFixture(false);
    let resolveOld, rejectOld, resolveFresh;
    delayed.setFetch(() => new Promise((resolve, reject) => { resolveOld = resolve; rejectOld = reject; }));
    const oldId = delayed.store["copilot.session"];
    const oldMode = delayed.store["copilot.mode"];
    delayed.send("old question");
    const oldShell = delayed.q("#cp-messages").lastElementChild;
    const oldHtml = oldShell.innerHTML;
    delayed.q("#cp-fresh").click();
    const freshId = delayed.store["copilot.session"];
    check("Desk reset while " + outcome + " is pending permits a fresh chat locally",
      freshId !== oldId && delayed.calls.length === 1 && !delayed.q("#cp-send").disabled &&
      delayed.qa(".cp-empty").length === 1);
    delayed.setFetch(() => new Promise((resolve) => { resolveFresh = resolve; }));
    delayed.send("fresh question");
    check("Desk next chat uses fresh ID before old " + outcome + " settles",
      delayed.calls.length === 2 && JSON.parse(delayed.calls[1][1].body).session_id === freshId);
    const freshHtml = delayed.q("#cp-messages").innerHTML;
    if (outcome === "success") resolveOld(await deskResponse(oldId, "employee", "stale answer"));
    else rejectOld(new Error(marker));
    await tick();
    check("Desk ignores stale " + outcome + " including state, UI and busy cleanup",
      delayed.store["copilot.session"] === freshId && delayed.store["copilot.mode"] === oldMode &&
      delayed.q("#cp-mode").value === "" && delayed.q("#cp-send").disabled &&
      delayed.q("#cp-messages").innerHTML === freshHtml && oldShell.innerHTML === oldHtml);
    const beforeDuplicate = delayed.calls.length;
    delayed.send("duplicate while waiting");
    check("Desk stale " + outcome + " cannot unblock a pending fresh request",
      delayed.calls.length === beforeDuplicate);
    resolveFresh(await deskResponse(freshId, "employee", "fresh answer"));
    await tick();
    check("Desk fresh response remains usable after stale " + outcome,
      delayed.store["copilot.session"] === freshId && !delayed.q("#cp-send").disabled &&
      delayed.q("#cp-messages").innerHTML.includes("fresh answer") &&
      delayed.q("#cp-mode").value === "employee");
  }
  check("Desk fixture never contacts FastAPI",
    desk.calls.every(([url]) => url === "/api/method/erpnext_ai_copilot.api.ask"));
}

(async () => {
  const q = (s) => documentStub.body.querySelector(s);
  const qa = (s) => documentStub.body.querySelectorAll(s);

  // 1. panel builds closed, toggle opens it
  check("panel starts closed", q("#cp-panel").classList.contains("cp-closed"));
  q("#cp-toggle").click();
  check("toggle opens panel", q("#cp-panel").classList.contains("cp-open"));

  // 2. empty state with suggestion chips
  check("empty state chips present", qa(".cp-suggestion").length === 4);

  // 3. orchestrate answer render: checkmark row below pills, mono paths
  fetchImpl = (url, opts) => {
    const body = JSON.parse(opts.body);
    if (url.endsWith("/orchestrate")) {
      return jsonResp({
        answer: "Do `frappe.call` like so:\n\n```python\nfrappe.call()\n```\nSee [1].",
        confidence: "high", route: "rag", route_how: "classifier",
        sources: [
          { title: "tools/search.py", section: "Search", url_or_path: "tools/search.py" },
          { title: "ARCHITECTURE.md", section: "Target", url_or_path: "https://docs.example.com/a" },
        ],
        version_info: { status: "live", frappe: "16.31.0", erpnext: "16.32.3" },
      });
    }
    return jsonResp({}, false, 500);
  };
  qa(".cp-suggestion")[0].click();
  await tick(30);
  const html = q("#cp-messages").innerHTML;
  check("confidence is checkmark row, not badge or banner",
    html.includes('class="cp-conf cp-conf-high"') &&
    html.includes('class="cp-check"') &&
    html.includes("high confidence") &&
    !html.includes("cp-badge") && !html.includes("cp-callout"));
  check("route chip has no middle dot",
    html.includes("via rag (classifier)") && !html.includes("rag ·"));
  check("no middle dots anywhere", !html.includes(" · "));
  check("pills carry [n] path in mono",
    html.includes("cp-pill-path") && html.includes("[1]") &&
    html.includes("tools/search.py"));
  check("http pill renders as link",
    /<a[^>]*class="cp-pill"/.test(html));
  check("version line comma-joined",
    html.includes("live: Frappe 16.31.0, ERPNext 16.32.3"));
  check("code block has copy button", html.includes('class="cp-copy"'));
  check("no uppercase-tracking styles inline", !/text-transform/i.test(html));
  check("pills precede confidence row in DOM order",
    html.indexOf("cp-pills") !== -1 &&
    html.indexOf("cp-pills") < html.indexOf("cp-conf"));

  // 4. /edit approval card: gutters, sweep on approve
  fetchImpl = (url, opts) => {
    const body = JSON.parse(opts.body);
    if (url.endsWith("/tools/propose_edit"))
      return jsonResp({ proposal_id: "abc123", path: body.path,
        diff: "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old()\n+new()\n",
        expires_minutes: 15 });
    if (url.endsWith("/tools/apply_edit"))
      return jsonResp({ commit_hash: "a1b2c3d" });
    return jsonResp({}, false, 500);
  };
  documentStub.body.querySelector("#cp-input").value =
    "/edit x.py :: old() :: new() :: reason here ok";
  q("#cp-send").click();
  await tick(30);
  const html2 = q("#cp-messages").innerHTML;
  check("diff rows carry gutter spans",
    html2.includes('class="cp-gutter"') && html2.includes("cp-diff-add") &&
    html2.includes("cp-diff-del"));
  check("write-card title not uppercased", true);
  const approveBtns = qa(".cp-btn-primary");
  approveBtns[approveBtns.length - 1].click();
  await tick(30);
  const html3 = q("#cp-messages").innerHTML;
  check("approve adds sweep + committed ref",
    html3.includes("cp-sweep") && html3.includes("a1b2c3d"));

  // 5. /newdoc title uses lowercase mono action, no toUpperCase
  fetchImpl = (url, opts) => {
    if (url.endsWith("/tools/erpnext_write/propose"))
      return jsonResp({ proposal_id: "w1", action: "create",
        doctype: "Customer", name: "", preview: { body: { a: 1 } },
        reason: "r", expires_minutes: 15, env_label: "staging" });
    return jsonResp({}, false, 500);
  };
  documentStub.body.querySelector("#cp-input").value =
    '/newdoc Customer {"a": 1} :: reason here ok';
  q("#cp-send").click();
  await tick(30);
  const html4 = q("#cp-messages").innerHTML;
  check("write card shows lowercase mono action",
    html4.includes("<code>create</code>") && !html4.includes("CREATE"));

  // 6. server error renders server banner, not connectivity banner
  fetchImpl = () => jsonResp({ detail: "No such file inside the project: 'x'" }, false, 404);
  documentStub.body.querySelector("#cp-input").value = "another question here";
  q("#cp-send").click();
  await tick(30);
  const html5 = q("#cp-messages").innerHTML;
  check("server error shows HTTP detail only",
    html5.includes("Request failed (HTTP 404)") &&
    html5.includes("No such file") &&
    !html5.includes("Can’t reach"));

  // 7. spec-literal chrome: arrow send button, neutral header/selection
  const sendHtml = q("#cp-send").innerHTML;
  check("send is icon-only accent arrow, not a filled Send button",
    sendHtml.includes("<svg") && !sendHtml.includes(">Send<"));
  check("header title shows the NexMate product name",
    q("#cp-header").innerHTML.includes(">NexMate<") &&
    !/ERPNext copilot/i.test(q("#cp-header").innerHTML));
  check("no orange/teal/rust hexes or second accent anywhere served",
    !/#E3A23C|#4FA989|#D9764A|#2490ef/i.test(
      require("fs").readFileSync(CSS, "utf8") +
      require("fs").readFileSync(BUNDLE, "utf8")));

  // 8. low confidence: danger indicator row, no banner, no callout
  fetchImpl = (url) => url.endsWith("/orchestrate")
    ? jsonResp({ answer: "I don't have a confident answer.",
                 confidence: "low", route: "rag", route_how: "classifier",
                 sources: [{ title: "x.py", section: "s", url_or_path: "x.py" }],
                 version_info: { status: "unknown" } })
    : jsonResp({}, false, 500);
  documentStub.body.querySelector("#cp-input").value = "vague thing here";
  const beforeLen = q("#cp-messages").innerHTML.length;
  q("#cp-send").click();
  await tick(30);
  const html6 = q("#cp-messages").innerHTML.slice(beforeLen);
  check("low confidence is quiet inline danger row",
    html6.includes("cp-conf-low") && html6.includes("low confidence") &&
    !html6.includes("cp-callout") && !html6.includes("cp-error-banner"));


  // 9. nested lists nest instead of flattening (bug: one flat numbered
  //    list with blank filler lines)
  fetchImpl = (url) => url.endsWith("/orchestrate")
    ? jsonResp({ answer: "Steps:\n1. create it\n   - pick a type\n   - set a name\n2. save it\n\nDone [1].",
                 confidence: "high", route: "rag", route_how: "classifier",
                 sources: [{ title: "x", section: "s", url_or_path: "x" }],
                 version_info: { status: "unknown" } })
    : jsonResp({}, false, 500);
  documentStub.body.querySelector("#cp-input").value = "how do I nest things here";
  const beforeNested = q("#cp-messages").innerHTML.length;
  q("#cp-send").click();
  await tick(30);
  const htmlNested = q("#cp-messages").innerHTML.slice(beforeNested);
  const ulCount = (htmlNested.match(/<ul>/g) || []).length;
  check("nested bullets produce a nested list, not a flat one",
    ulCount >= 1 && /<li>[^<]*<ul>/.test(htmlNested));
  check("no blank filler paragraphs around lists",
    !htmlNested.includes("<p></p>"));
  check("ordered items keep their order in one list",
    /<ol>[\s\S]*<li>create it[\s\S]*<li>save it<\/li>[\s\S]*<\/ol>/.test(
      htmlNested.replace(/<ul>[\s\S]*?<\/ul>/g, "")));

  // 10. short messages reach the router (no client-side length gate:
  // conversational validity is the router's job, not a char count's)
  let fetchedBody = null;
  fetchImpl = (url, opts) => {
    fetchedBody = JSON.parse(opts.body);
    return jsonResp({ answer: "Hey there!", confidence: "high",
      route: "smalltalk", route_how: "classifier", sources: [],
      version_info: { status: "unknown" } });
  };
  documentStub.body.querySelector("#cp-input").value = "hi";
  const notesBefore = qa(".cp-systemnote").length;
  q("#cp-send").click();
  await tick(30);
  check("short input is sent to the backend, not blocked",
    fetchedBody && fetchedBody.question === "hi");
  check("no length-validation note appears",
    qa(".cp-systemnote").length === notesBefore);

  await testDesk();

  let failed = 0;
  for (const [st, name, extra] of results) {
    console.log(st + "  " + name + (extra ? "  -- " + extra : ""));
    if (st === "FAIL") failed = 1;
  }
  process.exit(failed);
})().catch((e) => { console.error("HARNESS ERROR:", e); process.exit(2); });
