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
  var isPreview = !!(window.location && window.location.pathname === "/ui/preview.html");
  var deskUnavailable = "This action is unavailable in Desk. Chat is available.";

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
    conversationToken: 0,
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
    S.conversationToken++;
    S.busy = false;
    if (S.els.sendBtn) S.els.sendBtn.disabled = false;
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
  // ---------- markdown lists: indent-aware, nesting-preserving ----------
  // A line-based block parser (not regex substitution): each item keeps
  // its indentation level, so nested lists nest instead of flattening
  // into one list, and blank lines between items don't spawn fillers.
  function renderLists(text) {
    var lines = text.split("\n");
    var out = [];
    var i = 0;
    function itemAt(idx) {
      var m = lines[idx].match(/^([ \t]*)([-*]|\d+[.)])\s+(.*)$/);
      if (!m) return null;
      return {
        indent: m[1].replace(/\t/g, "    ").length,
        ordered: /^\d/.test(m[2]),
        content: m[3],
      };
    }
    function parseList(base) {
      var html = "";
      var open = null;
      while (i < lines.length) {
        var it = itemAt(i);
        if (!it || it.indent < base) break;
        if (it.indent > base && open) {
          // deeper item: nested list inside the currently open <li>
          html += parseList(it.indent);
          // The nested call stops at the first blank/non-item line, which
          // may still belong to THIS list (e.g. a blank line before the
          // next sibling item). Skip blanks and resume if a sibling (or
          // deeper) item follows — otherwise the whole parent list dies
          // here and every top-level item becomes its own restarted list.
          while (i < lines.length && lines[i].trim() === "") i++;
          continue;
        }
        if (it.indent > base && !open) { base = it.indent; } // defensive
        var want = it.ordered ? "ol" : "ul";
        if (open && open !== want) { html += "</li></" + open + ">"; open = null; }
        if (!open) { html += "<" + want + ">"; open = want; }
        else { html += "</li>"; }
        html += "<li>" + it.content;
        i++;
        // slurp lines belonging to this item
        while (i < lines.length) {
          var ln = lines[i];
          if (ln.trim() === "") {
            // blank: stay in the list only if another item follows
            var j = i + 1;
            while (j < lines.length && lines[j].trim() === "") j++;
            var nx = j < lines.length ? itemAt(j) : null;
            if (nx && nx.indent >= base) { i = j; break; }
            break;
          }
          if (itemAt(i)) break; // next item (same or deeper level)
          var lead = lines[i].replace(/\t/g, "    ").match(/^ */)[0].length;
          if (lead > base && lines[i].trim() !== "") {
            html += "<br>" + lines[i].trim();
            i++;
          } else break;
        }
      }
      if (open) html += "</li></" + open + ">";
      return html;
    }
    while (i < lines.length) {
      var first = itemAt(i);
      if (first) out.push(parseList(first.indent));
      else { out.push(lines[i]); i++; }
    }
    return out.join("\n");
  }
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
               '<a href="$2" target="_blank" rel="noopener">$1</a>');
    out = renderLists(out);
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

  // ---------- citations: `[n] path` pills directly under the answer ----------
  function renderPills(container, sources) {
    if (!sources || !sources.length) { container.style.display = "none"; return; }
    container.style.display = "";
    sources.forEach(function (s, i) {
      var detail = [
        s.title,
        (s.section && s.section !== "(top)") ? s.section : null,
        (typeof s.line_start === "number")
          ? ("lines " + s.line_start + "-" + s.line_end) : null,
        s.source_type === "resolved_issue" ? "past fix" : null,
      ].filter(Boolean).join(", ");
      var pill;
      if (s.url_or_path && /^https?:/.test(s.url_or_path)) {
        pill = el("a", "cp-pill");
        pill.href = s.url_or_path;
        pill.target = "_blank";
        pill.rel = "noopener";
      } else {
        pill = el("span", "cp-pill");
      }
      if (detail) pill.title = detail;
      pill.innerHTML = "[" + (i + 1) + "] " +
        '<span class="cp-pill-path">' +
        esc(s.title || s.url_or_path || "") + "</span>";
      container.appendChild(pill);
      container.appendChild(document.createTextNode(" "));
    });
  }

  // ---------- diff rendering: terminal view, gutter per line ----------
  function renderDiff(diffText) {
    var wrap = el("div", "cp-diff");
    diffText.split("\n").forEach(function (line) {
      var cls = "", mark = " ";
      if (/^\+\+\+|^---|^diff /.test(line)) cls = "cp-diff-file";
      else if (line.startsWith("@@")) cls = "cp-diff-hunk";
      else if (line.startsWith("+")) { cls = "cp-diff-add"; mark = "+"; }
      else if (line.startsWith("-")) { cls = "cp-diff-del"; mark = "-"; }
      var row = el("div", "cp-diff-line " + cls);
      var gutter = el("span", "cp-gutter");
      gutter.textContent = mark;
      row.appendChild(gutter);
      row.appendChild(document.createTextNode(line || " "));
      wrap.appendChild(row);
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
    var body = el("div", "cp-answer", html);
    m.appendChild(body);
    bindCopyButtons(body);

    var pills = el("div", "cp-pills");
    m.appendChild(pills);
    renderPills(pills, meta.sources);
    m.appendChild(confidenceRow(meta.confidence, meta.route, meta.route_how));

    if (meta.versions && meta.versions.status === "live") {
      m.appendChild(el("div", "cp-versionline",
        "live: Frappe " + esc(meta.versions.frappe) + ", ERPNext " +
        esc(meta.versions.erpnext)));
    }
    scrollBottom();
  }
  function confidenceRow(confidence, route, routeHow) {
    var ok = confidence === "high";
    var icon = ok ? "✓" : "⚠";
    var label = ok ? "high confidence" :
      (confidence === "no_match" ? "no confident answer" : "low confidence");
    var cls = "cp-conf " + (ok ? "cp-conf-high" :
      (confidence === "no_match" ? "cp-conf-nomatch" : "cp-conf-low"));
    var row = el("div", "cp-meta-row");
    row.appendChild(el("span", cls,
      '<span class="cp-check">' + icon + "</span>" + esc(label)));
    if (route) {
      row.appendChild(el("span", "cp-route", ", via " + esc(route) +
        (routeHow ? " (" + esc(routeHow) + ")" : "")));
    }
    return row;
  }
  function scrollBottom() {
    S.els.messages.scrollTop = S.els.messages.scrollHeight;
  }

  // ---------- API ----------
  function humanizeError(status, body) {
    var d = body && body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      // FastAPI validation errors: [{loc:["body","question"], msg:...}]
      return d.map(function (e) {
        var where = (e.loc || []).slice(1).join(".");
        return (where ? where + ": " : "") + (e.msg || JSON.stringify(e));
      }).join("; ");
    }
    if (d && typeof d === "object") return JSON.stringify(d);
    if (body && body.message) return String(body.message);
    return "HTTP " + status;
  }

  // An HTTP error response means the service was REACHED and declined the
  // request — that must never be worded as a connectivity failure. Tag it
  // so appendError can pick the honest banner. Transport failures (fetch
  // itself throwing) stay untagged and keep the "can't reach" wording.
  function serverError(status, body) {
    var err = new Error(humanizeError(status, body));
    err.isServerError = true;
    err.status = status;
    return err;
  }

  // Pure decision helper (kept testable outside the DOM): does this
  // rejection describe a server answer, or a missing server?
  function errorKind(err) {
    return (err && err.isServerError) ? "server" : "network";
  }

  function post(path, body) {
    if (!isPreview) return Promise.reject(serverError(403, { detail: deskUnavailable }));
    return fetch(apiBase() + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().catch(function () { return null; })
        .then(function (j) {
          if (!r.ok)
            throw serverError(r.status, j);
          return j;
        });
    });
  }

  function chatRequest(question) {
    if (isPreview) {
      return post("/orchestrate", {
        question: question, session_id: S.sessionId, mode: S.mode,
      });
    }
    var headers = { "Content-Type": "application/json" };
    if (typeof frappe !== "undefined" && frappe.csrf_token)
      headers["X-Frappe-CSRF-Token"] = frappe.csrf_token;
    return fetch("/api/method/erpnext_ai_copilot.api.ask", {
      method: "POST",
      credentials: "same-origin",
      redirect: "error",
      headers: headers,
      body: JSON.stringify({ question: question, session_id: S.sessionId }),
    }).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (j) {
        if (!r.ok || !j || !j.message || typeof j.message.answer !== "string")
          throw serverError(r.status, { detail: "NexMate assistant is unavailable. Please try again later." });
        return j.message;
      });
    }).catch(function (err) {
      if (err && err.isServerError) throw err;
      throw new Error("NexMate assistant is unavailable. Please try again later.");
    });
  }

  function askOrchestrate(question) {
    var conversationToken = S.conversationToken;
    var m = addAssistantShell();
    return chatRequest(question).then(function (r) {
      if (conversationToken !== S.conversationToken) return;
      if (r.session_id) S.sessionId = r.session_id;
      if (!isPreview && (r.mode === "employee" || r.mode === "developer")) {
        S.mode = r.mode;
        S.els.mode.value = S.mode;
      }
      persist();
      fillAssistant(m, md(r.answer), {
        confidence: r.confidence,
        route: r.route,
        route_how: r.route_how,
        sources: r.sources,
        versions: r.version_info,
      });
    });
  }

  // ---------- slash commands ----------
  function handleCommand(text) {
    var m = addAssistantShell();
    if (!isPreview) return fillAssistant(m, deskUnavailable);
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
      var dt = m2[1], nm = (cmd === "/editdoc" ? (m2[2] || "") : ""),
          js = m2[3], rs = m2[4];
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
    if (!isPreview) {
      card.appendChild(el("div", "cp-error-inline", deskUnavailable));
      return;
    }
    var bar = el("div", "cp-approvebar");
    var ok = el("button", "cp-btn cp-btn-primary", "Approve");
    var no = el("button", "cp-btn", "Reject");
    ok.addEventListener("click", function () {
      ok.disabled = true; no.disabled = true;
      ok.textContent = "Applying…";
      post(applySpec.path, applySpec.body).then(function (r) {
        card.classList.add("cp-applied");
        card.classList.add("cp-sweep");
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
      "Proposed fix — <code>" + esc(proposal.path) + "</code>"));
    card.appendChild(renderDiff(proposal.diff));
    approveBar(card, {
      path: "/tools/apply_edit",
      body: { proposal_id: proposal.proposal_id, confirmed: true },
    }, function (r) {
      maybeIndexMemoryNote(card, r);
    });
    m.innerHTML = "";
    m.appendChild(el("div", "cp-meta-row",
      '<span class="cp-route">edit proposal, one-shot, expires in ' +
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
      "Proposed <code>" + esc(String(proposal.action).toLowerCase()) +
      "</code> on live ERPNext — <code>" + esc(proposal.doctype) +
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
      '<span class="cp-route">erpnext write, one-shot, expires in ' +
      proposal.expires_minutes + ' min</span>'));
    m.appendChild(card);
    scrollBottom();
  }

  // ---------- input handling ----------
  function submit() {
    var q = S.els.input.value.trim();
    if (!q || S.busy) return;
    // Transport validity only: non-empty input always goes through.
    // Short messages ("hi", "ok", "why") are conversationally valid —
    // the router, not a character count, decides what they mean.
    if (isPreview && q.startsWith("/") && q.trim().split(/\s+/).length === 1 &&
        ["/read", "/search", "/explain"].indexOf(q.toLowerCase()) !== -1) {
      systemNote(q + " needs an argument, e.g. " + q + " <something>");
      return;
    }
    var conversationToken = S.conversationToken;
    S.busy = true;
    S.els.sendBtn.disabled = true;
    addUser(q);
    S.els.input.value = "";
    autoGrow();
    var run = q.startsWith("/")
      ? handleCommand(q) : askOrchestrate(q);
    Promise.resolve(run).catch(function (err) {
      if (conversationToken !== S.conversationToken) return;
      appendError(String((err && err.message) || err), {
        kind: errorKind(err),
        status: err && err.status,
      });
    }).finally(function () {
      if (conversationToken !== S.conversationToken) return;
      S.busy = false;
      S.els.sendBtn.disabled = false;
      S.els.input.focus();
    });
  }
  function appendError(detail, opts) {
    // One banner, one claim. A server error shows ONLY the server's real
    // message ("No such file inside the project") — never wrapped in
    // connectivity prose, which directly contradicts it.
    opts = opts || {};
    var msgs = S.els.messages;
    var last = msgs.lastElementChild;
    var html;
    if (opts.kind === "server") {
      html = '<div class="cp-error-banner cp-error-app">' +
        "<strong>Request failed (HTTP " + esc(String(opts.status || "?")) +
        ").</strong> " + esc(detail) + "</div>";
    } else {
      html = '<div class="cp-error-banner">Can’t reach the assistant right now. ' +
        'Is the service running?<span class="cp-error-detail">' + esc(detail) +
        "</span></div>";
    }
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
    var sugg = isPreview ? [
      "How do I create a Sales Invoice?",
      "What fields does Customer have?",
      "How does hybrid retrieval fuse results?",
      "/explain KeyError when parsing read_file responses",
    ] : ["How do I create a Sales Invoice?", "What is a DocType?"];
    sugg.forEach(function (s) {
      var chip = el("button", "cp-suggestion", esc(s));
      chip.addEventListener("click", function () {
        S.els.input.value = s;
        autoGrow(); submit();
      });
      box.appendChild(chip);
    });
    box.appendChild(el("div", "cp-empty-hint",
      isPreview ? "Tools: /read /search /explain /edit /newdoc /editdoc" : "Chat only. Live tools are unavailable in Desk."));
    S.els.messages.appendChild(box);
  }

  // ---------- panel build ----------
  function buildPanel() {
    loadState();
    var wrap = el("div"); wrap.id = "cp-root";
    wrap.innerHTML =
      '<button id="cp-toggle" title="NexMate">AI</button>' +
      '<div id="cp-panel" class="cp-closed" role="dialog" aria-label="AI assistant">' +
      '  <div id="cp-header">' +
      '    <span class="cp-logo">AI</span>' +
      '    <span class="cp-title">NexMate</span>' +
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
      '    <button id="cp-send" title="Send" aria-label="Send">' +
      '      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11.5 21 3l-7.5 18-2.3-7.2z" fill="currentColor"/></svg>' +
      "    </button>" +
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
    S.els.mode.value = isPreview ? S.mode : "";
    if (!isPreview) {
      S.els.mode.disabled = true;
      S.els.mode.title = "Mode is assigned by your Frappe roles.";
      S.els.input.placeholder = "Ask about ERPNext…";
    }

    wrap.querySelector("#cp-toggle").addEventListener("click", togglePanel);
    wrap.querySelector("#cp-close").addEventListener("click", togglePanel);
    S.els.sendBtn.addEventListener("click", submit);
    S.els.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    });
    S.els.input.addEventListener("input", autoGrow);
    S.els.mode.addEventListener("change", function () {
      if (!isPreview) return;
      S.mode = S.els.mode.value; persist();
      systemNote("Switched to " + S.mode + " mode.");
    });
    wrap.querySelector("#cp-fresh").addEventListener("click", function () {
      if (!isPreview) { newSession(); return; }
      post("/tools/session/reset", { session_id: S.sessionId })
        .catch(function () {})
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
    // Dedupe: validation guards return early without clearing the input,
    // so repeats (held Enter, double taps) would otherwise stack the
    // identical note once per invocation. Consecutive duplicates collapse.
    var msgs = S.els.messages;
    var last = msgs.lastElementChild;
    if (last && last.classList.contains("cp-systemnote") &&
        last.textContent === text) {
      scrollBottom();
      return;
    }
    msgs.appendChild(el("div", "cp-systemnote", esc(text)));
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
