/* ERPNext AI Copilot — sidebar assistant (docs/UI_SPEC.md).
 *
 * Self-contained, dependency-free. Runs in two environments:
 *   - Frappe Desk: injected via app_include_js; API base from
 *     frappe.boot.copilot_settings.api_base (boot.py)
 *   - Standalone preview (/ui/preview.html): window.COPILOT_API_BASE
 *
 * Capabilities surfaced:
 *   - natural Q&A via POST /orchestrate (route badge, version chips,
 *     citations, confidence styling, session continuity)
 *   - slash commands for every tool, incl. approval cards:
 *       /read <path>
 *       /search <pattern>
 *       /explain <description>
 *       /edit <path> :: <find> :: <replace> :: <reason>
 *       /newdoc <Doctype> <json-payload> :: <reason>
 *       /editdoc <Doctype> <name> <json-payload> :: <reason>
 *     /edit renders a unified-diff card with Approve & Commit / Reject;
 *     /newdoc//editdoc render exact-request preview cards with the same
 *     two-button confirm flow (Tier-2 discipline, SECURITY.md).
 */
(function () {
  "use strict";

  // ---------- environment ----------
  function apiBase() {
    if (window.COPILOT_API_BASE) return String(window.COPILOT_API_BASE);
    try {
      if (typeof frappe !== "undefined" && frappe.boot &&
          frappe.boot.copilot_settings && frappe.boot.copilot_settings.api_base)
        return String(frappe.boot.copilot_settings.api_base);
    } catch (e) { /* not in desk */ }
    return "http://127.0.0.1:8000";
  }

  // ---------- state ----------
  var S = {
    sessionId: null,
    mode: "developer",
    busy: false,
    els: {},
  };

  function loadState() {
    try {
      S.sessionId = localStorage.getItem("copilot.session") || null;
      S.mode = localStorage.getItem("copilot.mode") || "developer";
    } catch (e) { /* private mode */ }
    if (!S.sessionId) newSession(false);
  }
  function persist() {
    try {
      localStorage.setItem("copilot.session", S.sessionId);
      localStorage.setItem("copilot.mode", S.mode);
    } catch (e) { /* ignore */ }
  }
  function newSession(rerender) {
    S.sessionId =
      "s-" + Date.now().toString(36) + "-" +
      Math.random().toString(36).slice(2, 8);
    persist();
    if (rerender !== false) {
      S.els.messages.innerHTML = "";
      emptyState();
    }
  }

  // ---------- tiny helpers ----------
  function esc(t) {
    var d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function copyText(text, btn) {
    function done() { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = "Copy"; }, 1200); }
    if (navigator.clipboard && navigator.clipboard.writeText)
      navigator.clipboard.writeText(text).then(done, done);
    else { done(); }
  }

  // ---------- markdown-lite (escape first!) ----------
  function md(src) {
    var out = esc(src == null ? "" : String(src));
    var blocks = [];
    out = out.replace(/```(\w*)\n([\s\S]*?)```/g, function (_, lang, code) {
      var i = blocks.length;
      blocks.push({ lang: lang || "text", code: code.replace(/\n$/, "") });
      return "\u0000BLOCK" + i + "\u0000";
    });
    out = out
      .replace(/^### (.*)$/gm, "<h4>$1</h4>")
      .replace(/^## (.*)$/gm, "<h3>$1</h3>")
      .replace(/^# (.*)$/gm, "<h3>$1</h3>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|\W)\*([^*\n]+)\*(?=\W|$)/g, "$1<em>$2</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g,
               '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/^\s*[-*] (.*)$/gm, "<li>$1</li>")
      .replace(/^\s*\d+\. (.*)$/gm, "<li data-ol='1'>$1</li>");
    out = out.replace(/(<li(?: data-ol='1')?>[\s\S]*?<\/li>)(?!\s*<li)/g,
                      function (m) { return m.match(/data-ol/) ? "<ol>" + m + "</ol>" : "<ul>" + m + "</ul>"; });
    out = out.split(/\n{2,}/).map(function (p) {
      p = p.trim();
      if (!p) return "";
      if (/^<(h3|h4|ul|ol|pre|table)/.test(p)) return p;
      return "<p>" + p.replace(/\n/g, "<br>") + "</p>";
    }).join("");
    // re-insert code blocks with copy buttons
    out = out.replace(/\u0000BLOCK(\d+)\u0000/g, function (_, i) {
      var b = blocks[Number(i)];
      var id = "cb" + Math.random().toString(36).slice(2, 8);
      return '<div class="cp-code"><div class="cp-code-head">' +
        esc(b.lang) +
        '<button class="cp-copy" data-target="' + id + '">Copy</button></div>' +
        '<pre id="' + id + '"><code>' + b.code + "</code></pre></div>";
    });
    return out;
  }
  function bindCopyButtons(root) {
    root.querySelectorAll(".cp-copy").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var pre = document.getElementById(btn.getAttribute("data-target"));
        copyText(pre ? pre.textContent : "", btn);
      });
    });
  }

  // ---------- citations ----------
  function citePills(sources) {
    if (!sources || !sources.length) return "";
    return "[" + sources.map(function (_, i) {
      return '<span class="cp-pill" data-src="' + i + '">' + (i + 1) + "</span>";
    }).join("") + "]";
  }
  function sourceLabel(s) {
    var bits = [];
    if (s.title) bits.push(esc(s.title));
    if (s.section && s.section !== "(top)") bits.push(esc(s.section));
    if (s.source_type === "resolved_issue") bits.push("past fix");
    if (typeof s.line_start === "number")
      bits.push("lines " + s.line_start + "-" + s.line_end);
    return bits.join(" · ");
  }
  function renderSources(container, sources) {
    if (!sources || !sources.length) { container.style.display = "none"; return; }
    container.style.display = "";
    var list = el("div", "cp-sources-list");
    sources.forEach(function (s, i) {
      var row = el("div", "cp-source-row",
        '<span class="cp-pill cp-pill-static">' + (i + 1) + "</span> " +
        sourceLabel(s));
      if (s.url_or_path && /^https?:/.test(s.url_or_path)) {
        row.appendChild(el("a", "cp-source-link", "open"))
          .href = s.url_or_path;
        row.lastChild.target = "_blank";
        row.lastChild.rel = "noopener";
      }
      list.appendChild(row);
    });
    container.innerHTML = "";
    container.appendChild(el("div", "cp-sources-title", "Sources"));
    container.appendChild(list);
  }
  function bindPills(msgEl, sources) {
    msgEl.querySelectorAll(".cp-pill[data-src]").forEach(function (pill) {
      pill.addEventListener("click", function () {
        var box = msgEl.querySelector(".cp-sources");
        if (!box) return;
        box.style.display = "box.style.display" === "x" ? "" : (
          box.style.display === "none" || !box.style.display ? "" : "none");
        var idx = Number(pill.getAttribute("data-src"));
        var rows = box.querySelectorAll(".cp-source-row");
        rows.forEach(function (r, j) {
          r.classList.toggle("cp-flash", j === idx);
        });
        box.scrollIntoView({ block: "nearest" });
      });
    });
  }

  // ---------- diff rendering ----------
  function renderDiff(diffText) {
    var wrap = el("div", "cp-diff");
    diffText.split("\n").forEach(function (line) {
      var cls = "";
      if (/^\+\+\+|^---|^diff /.test(line)) cls = "cp-diff-file";
      else if (line.startsWith("@@")) cls = "cp-diff-hunk";
      else if (line.startsWith("+")) cls = "cp-diff-add";
      else if (line.startsWith("-")) cls = "cp-diff-del";
      wrap.appendChild(el("div", "cp-diff-line " + cls, esc(line) || " "));
    });
    return wrap;
  }

  // ---------- message plumbing ----------
  function addUser(text) {
    var m = el("div", "cp-msg cp-msg-user");
    m.appendChild(el("div", "cp-bubble", esc(text)));
    S.els.messages.appendChild(m);
    scrollBottom();
  }
  function addAssistantShell() {
    var m = el("div", "cp-msg cp-msg-a");
    m.innerHTML = '<div class="cp-typing"><span></span><span></span><span></span></div>';
    S.els.messages.appendChild(m);
    scrollBottom();
    return m;
  }
  function fillAssistant(m, html, meta) {
    meta = meta || {};
    m.innerHTML = "";
    var head = el("div", "cp-meta-row");
    var confCls = { high: "cp-conf-high", low: "cp-conf-low",
                    no_match: "cp-conf-nomatch" }[meta.confidence] || "cp-conf-low";
    var confTxt = { high: "✓ high confidence", low: "⚠ low confidence",
                    no_match: "✖ no confident answer" }[meta.confidence] ||
                   esc(meta.confidence);
    head.appendChild(el("span", "cp-badge " + confCls, confTxt));
    if (meta.route) {
      head.appendChild(el("span", "cp-route", esc(meta.route) +
        (meta.route_how ? " · " + esc(meta.route_how) : "")));
    }
    m.appendChild(head);

    if (meta.confidence && meta.confidence !== "high") {
      m.appendChild(el("div", "cp-callout " +
        (meta.confidence === "no_match" ? "cp-callout-red" : "cp-callout-amber"),
        meta.confidence === "no_match"
          ? "The knowledge base has nothing relevant to this question."
          : "This answer was withheld — retrieval wasn't confident enough. Nearest sources are shown below."));
    }
    var body = el("div", "cp-answer", html);
    m.appendChild(body);
    bindCopyButtons(body);

    var srcBox = el("div", "cp-sources");
    m.appendChild(srcBox);
    renderSources(srcBox, meta.sources);

    if (meta.versions && meta.versions.status === "live") {
      m.appendChild(el("div", "cp-versionline",
        "live: Frappe " + esc(meta.versions.frappe) + " · ERPNext " +
        esc(meta.versions.erpnext)));
    }
    bindPills(m, meta.sources);
    scrollBottom();
  }
  function scrollBottom() {
    S.els.messages.scrollTop = S.els.messages.scrollHeight;
  }

  // ---------- API ----------
  function post(path, body) {
    return fetch(apiBase() + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status));
        return j;
      });
    });
  }

  function askOrchestrate(question) {
    var m = addAssistantShell();
    return post("/orchestrate", {
      question: question, session_id: S.sessionId, mode: S.mode,
    }).then(function (r) {
      if (r.session_id) S.sessionId = r.session_id;
      fillAssistant(m, md(r.answer), {
        confidence: r.confidence,
        route: r.route + (r.route_how ? " (" + r.route_how + ")" : ""),
        sources: r.sources,
        versions: r.version_info,
      });
    });
  }

  // ---------- slash commands ----------
  function handleCommand(text) {
    var m = addAssistantShell();
    var sp = text.indexOf(" ");
    var cmd = (sp === -1 ? text : text.slice(0, sp)).toLowerCase();
    var rest = sp === -1 ? "" : text.slice(sp + 1).trim();

    function done(html, sources) {
      fillAssistant(m, html, { confidence: "high", route: cmd.slice(1),
                               sources: sources || [] });
    }

    if (cmd === "/read") {
      if (!rest) return fillAssistant(m, "Usage: <code>/read &lt;path&gt;</code>");
      return post("/tools/read_file", { path: rest }).then(function (r) {
        done("<p><code>" + esc(r.path) + "</code> — " + r.line_count +
             " lines</p>" + md("```\n" + r.content + "\n```"),
             [{ title: r.path }]);
      });
    }
    if (cmd === "/search") {
      if (!rest) return fillAssistant(m, "Usage: <code>/search &lt;pattern&gt;</code>");
      return post("/tools/search", { query: rest }).then(function (r) {
        var lines = r.matches.map(function (mt) {
          return "- `" + mt.path + ":" + mt.line_number + "` " +
            esc(mt.line);
        }).join("\n");
        done("<p>" + r.total_matches + " matches across " +
             r.files_searched + " files" +
             (r.truncated ? " <strong>(truncated)</strong>" : "") +
             "</p>" + md(lines || "_no matches_"));
      });
    }
    if (cmd === "/explain") {
      return post("/tools/explain", { description: rest }).then(function (r) {
        if (!r.located) return fillAssistant(m, "<p>" + esc(r.explanation) + "</p>");
        done(md(r.explanation), r.sources.map(function (s) {
          return { title: s.path, section: "lines " + s.line_start + "-" + s.line_end };
        }));
      });
    }
    if (cmd === "/edit") {
      var parts = rest.split("::").map(function (p) { return p.trim(); });
      if (parts.length < 4)
        return fillAssistant(m, "Usage: <code>/edit path :: find :: replace :: reason</code>");
      var p0 = parts[0], f = parts[1], rep = parts[2],
          why = parts.slice(3).join(" :: ");
      return post("/tools/propose_edit", {
        path: p0, find: f, replace: rep, message: why.slice(0, 200),
      }).then(function (r) {
        renderEditCard(m, r);
      });
    }
    if (cmd === "/newdoc" || cmd === "/editdoc") {
      // /newdoc Doctype {"json": ...} :: reason
      // /editdoc Doctype name {"json": ...} :: reason
      var m2 = rest.match(/^(\S+)\s+(?:([\s\S]*?)\s+)?(\{[\s\S]*\})\s*::\s*(.+)$/);
      if (!m2)
        return fillAssistant(m, "Usage: <code>" + cmd +
          " Doctype [name] {\"json\": \"payload\"} :: reason</code>");
      var dt = m2[1], nm = (cmd === "/editdoc" ? m2[2] : ""),
          js = m2[cmd === "/editdoc" ? 3 : 2], rs = m2[4];
      var payload;
      try { payload = JSON.parse(js); }
      catch (e) { return fillAssistant(m, "Payload is not valid JSON."); }
      return post("/tools/erpnext_write/propose", {
        action: cmd === "/newdoc" ? "create" : "update",
        doctype: dt, name: nm || undefined,
        payload: payload, reason: rs,
      }).then(function (r) { renderWriteCard(m, r); });
    }
    fillAssistant(m, "Unknown command. Available: <code>/read /search /explain /edit /newdoc /editdoc</code>");
  }

  // ---------- approval cards ----------
  function approveBar(card, applySpec, onApplied) {
    var bar = el("div", "cp-approvebar");
    var ok = el("button", "cp-btn cp-btn-primary", "Approve");
    var no = el("button", "cp-btn", "Reject");
    ok.addEventListener("click", function () {
      ok.disabled = true; no.disabled = true;
      ok.textContent = "Applying…";
      post(applySpec.path, applySpec.body).then(function (r) {
        card.classList.add("cp-applied");
        bar.innerHTML = "";
        bar.appendChild(el("span", "cp-committed",
          "✓ committed as <code>" + esc(r.commit_hash || r.name || "?") +
          "</code>"));
        if (onApplied) onApplied(r);
      }).catch(function (err) {
        ok.disabled = false; no.disabled = false; ok.textContent = "Approve";
        bar.appendChild(el("div", "cp-error-inline", esc(String(err.message || err))));
      });
    });
    no.addEventListener("click", function () {
      card.classList.add("cp-rejected");
      bar.innerHTML = "";
      bar.appendChild(el("span", "cp-committed", "✕ rejected — nothing applied"));
    });
    bar.appendChild(ok); bar.appendChild(no);
    card.appendChild(bar);
  }

  function renderEditCard(m, proposal) {
    var card = el("div", "cp-card");
    card.appendChild(el("div", "cp-card-title",
      "Proposed change — <code>" + esc(proposal.path) + "</code>"));
    card.appendChild(renderDiff(proposal.diff));
    approveBar(card, {
      path: "/tools/apply_edit",
      body: { proposal_id: proposal.proposal_id, confirmed: true },
    }, function (r) {
      maybeIndexMemoryNote(card, r);
    });
    m.innerHTML = "";
    m.appendChild(el("div", "cp-meta-row",
      '<span class="cp-route">edit proposal · one-shot, expires in ' +
      proposal.expires_minutes + ' min</span>'));
    m.appendChild(card);
    scrollBottom();
  }

  function maybeIndexMemoryNote(card, r) {
    if (r.memory && r.memory.indexed)
      card.appendChild(el("div", "cp-memorynote",
        "Indexed as project memory (" + esc(r.memory.url_or_path) + ")"));
  }

  function renderWriteCard(m, proposal) {
    var card = el("div", "cp-card");
    card.appendChild(el("div", "cp-card-title",
      "Proposed " + esc(proposal.action.toUpperCase()) +
      " on live ERPNext — <code>" + esc(proposal.doctype) +
      (proposal.name ? "/" + esc(proposal.name) : "") + "</code>" +
      ' <span class="cp-envlabel">' + esc(proposal.env_label) + "</span>"));
    card.appendChild(el("pre", "cp-writepreview",
      JSON.stringify(proposal.preview.body, null, 2)));
    card.appendChild(el("div", "cp-reasonline",
      "Reason: " + esc(proposal.reason)));
    approveBar(card, {
      path: "/tools/erpnext_write/apply",
      body: { proposal_id: proposal.proposal_id, confirmed: true },
    });
    m.innerHTML = "";
    m.appendChild(el("div", "cp-meta-row",
      '<span class="cp-route">erpnext write · one-shot, expires in ' +
      proposal.expires_minutes + ' min</span>'));
    m.appendChild(card);
    scrollBottom();
  }

  // ---------- input handling ----------
  function submit() {
    var q = S.els.input.value.trim();
    if (!q || S.busy) return;
    S.busy = true;
    S.els.sendBtn.disabled = true;
    addUser(q);
    S.els.input.value = "";
    autoGrow();
    var run = q.startsWith("/")
      ? handleCommand(q) : askOrchestrate(q);
    Promise.resolve(run).catch(function (err) {
      appendError(String(err.message || err));
    }).finally(function () {
      S.busy = false;
      S.els.sendBtn.disabled = false;
      S.els.input.focus();
    });
  }
  function appendError(detail) {
    var msgs = S.els.messages;
    var last = msgs.lastElementChild;
    var html = '<div class="cp-error-banner">Can’t reach the assistant right now. ' +
      'Is the service running?<span class="cp-error-detail">' + esc(detail) +
      "</span></div>";
    if (last && last.classList.contains("cp-msg-a")) last.innerHTML = html;
    else msgs.appendChild(el("div", "cp-msg cp-msg-a", html));
    scrollBottom();
  }

  function autoGrow() {
    var t = S.els.input;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 140) + "px";
  }

  // ---------- empty state ----------
  function emptyState() {
    var box = el("div", "cp-empty");
    box.appendChild(el("div", "cp-empty-title", "Ask anything ERPNext"));
    var sugg = [
      "How do I create a Sales Invoice?",
      "What fields does Customer have?",
      "How does hybrid retrieval fuse results?",
      "/explain KeyError when parsing read_file responses",
    ];
    sugg.forEach(function (s) {
      var chip = el("button", "cp-suggestion", esc(s));
      chip.addEventListener("click", function () {
        S.els.input.value = s;
        autoGrow(); submit();
      });
      box.appendChild(chip);
    });
    box.appendChild(el("div", "cp-empty-hint",
      "Tools: /read /search /explain /edit /newdoc /editdoc"));
    S.els.messages.appendChild(box);
  }

  // ---------- panel build ----------
  function buildPanel() {
    loadState();
    var wrap = el("div"); wrap.id = "cp-root";
    wrap.innerHTML =
      '<button id="cp-toggle" title="AI Copilot">AI</button>' +
      '<div id="cp-panel" class="cp-closed" role="dialog" aria-label="AI assistant">' +
      '  <div id="cp-header">' +
      '    <span class="cp-logo">AI</span>' +
      '    <span class="cp-title">ERPNext Copilot</span>' +
      '    <select id="cp-mode" title="Mode">' +
      '      <option value="developer">developer</option>' +
      '      <option value="employee">employee</option>' +
      "    </select>" +
      '    <button id="cp-fresh" title="Start fresh">⟲</button>' +
      '    <button id="cp-close" title="Close">×</button>' +
      "  </div>" +
      '  <div id="cp-resize"></div>' +
      '  <div id="cp-messages"></div>' +
      '  <div id="cp-inputrow">' +
      '    <textarea id="cp-input" rows="1" placeholder="Ask, or / for tools…"></textarea>' +
      '    <button id="cp-send">Send</button>' +
      "  </div>" +
      "</div>";
    document.body.appendChild(wrap);

    S.els = {
      messages: wrap.querySelector("#cp-messages"),
      input: wrap.querySelector("#cp-input"),
      sendBtn: wrap.querySelector("#cp-send"),
      panel: wrap.querySelector("#cp-panel"),
      mode: wrap.querySelector("#cp-mode"),
    };
    S.els.mode.value = S.mode;

    wrap.querySelector("#cp-toggle").addEventListener("click", togglePanel);
    wrap.querySelector("#cp-close").addEventListener("click", togglePanel);
    S.els.sendBtn.addEventListener("click", submit);
    S.els.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    });
    S.els.input.addEventListener("input", autoGrow);
    S.els.mode.addEventListener("change", function () {
      S.mode = S.els.mode.value; persist();
      systemNote("Switched to " + S.mode + " mode.");
    });
    wrap.querySelector("#cp-fresh").addEventListener("click", function () {
      var sid = S.sessionId;
      post("/tools/session/reset", { session_id: sid })
        .catch(function () { /* offline: still clear locally */ })
        .finally(function () { newSession(); });
    });

    // simple drag-to-resize (UI_SPEC: resizable width)
    var handle = wrap.querySelector("#cp-resize");
    handle.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      var startX = e.clientX, startW = S.els.panel.offsetWidth;
      function move(ev) {
        var w = Math.max(320, Math.min(640, startW + (startX - ev.clientX)));
        S.els.panel.style.width = w + "px";
      }
      function up() {
        document.removeEventListener("pointermove", move);
        document.removeEventListener("pointerup", up);
      }
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", up);
    });

    if (!S.els.messages.children.length) emptyState();
  }

  function systemNote(text) {
    S.els.messages.appendChild(el("div", "cp-systemnote", esc(text)));
    scrollBottom();
  }

  function togglePanel() {
    var p = S.els.panel;
    var opening = p.classList.contains("cp-closed");
    p.classList.toggle("cp-closed", !opening);
    p.classList.toggle("cp-open", opening);
    if (opening) S.els.input.focus();
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", buildPanel);
  else buildPanel();
})();
