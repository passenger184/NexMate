// ERPNext AI Copilot — Phase 1 sidebar chat panel.
//
// Injected into the Frappe Desk via app_include_js. Appends a floating
// toggle button + fixed side panel to document.body (body-level nodes
// survive SPA route changes). Calls the external FastAPI /ask service;
// the service address comes from frappe.boot.copilot_settings.api_base
// (see boot.py), falling back to local development default.
//
// Renders: answer text, a visibly separate Sources list, and a confidence
// badge. "no_match" responses get a distinct warning style (PHASE_1_SPEC).

(function () {
  "use strict";

  function apiBase() {
    var s = frappe.boot && frappe.boot.copilot_settings;
    return (s && s.api_base) || "http://localhost:8000";
  }

  function esc(text) {
    var d = document.createElement("div");
    d.textContent = text == null ? "" : String(text);
    return d.innerHTML;
  }

  // Render answer text with line/paragraph breaks preserved but content escaped.
  function answerHtml(text) {
    return esc(text)
      .split(/\n{2,}/)
      .map(function (para) { return "<p>" + para.replace(/\n/g, "<br>") + "</p>"; })
      .join("");
  }

  var CONFIDENCE_STYLES = {
    high: { label: "High confidence", cls: "copilot-badge-high" },
    low: { label: "Low confidence", cls: "copilot-badge-low" },
    no_match: { label: "No confident answer", cls: "copilot-badge-nomatch" },
  };

  function buildPanel() {
    var wrap = document.createElement("div");
    wrap.id = "copilot-root";
    wrap.innerHTML =
      '<button id="copilot-toggle" title="AI Assistant">AI</button>' +
      '<div id="copilot-panel" style="display:none">' +
      '  <div id="copilot-header">AI Assistant <span id="copilot-close">&times;</span></div>' +
      '  <div id="copilot-messages"></div>' +
      '  <div id="copilot-inputrow">' +
      '    <textarea id="copilot-input" rows="2" placeholder="Ask about ERPNext / Frappe..."></textarea>' +
      '    <button id="copilot-ask">Ask</button>' +
      '  </div>' +
      "</div>";
    document.body.appendChild(wrap);

    wrap.querySelector("#copilot-toggle").addEventListener("click", toggle);
    wrap.querySelector("#copilot-close").addEventListener("click", toggle);
    wrap.querySelector("#copilot-ask").addEventListener("click", onAsk);
    wrap.querySelector("#copilot-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        onAsk();
      }
    });
  }

  function toggle() {
    var panel = document.getElementById("copilot-panel");
    panel.style.display = panel.style.display === "none" ? "flex" : "none";
    if (panel.style.display === "flex") {
      document.getElementById("copilot-input").focus();
    }
  }

  function appendMessage(html, cls) {
    var div = document.createElement("div");
    div.className = "copilot-msg " + cls;
    div.innerHTML = html;
    var msgs = document.getElementById("copilot-messages");
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function onAsk() {
    var input = document.getElementById("copilot-input");
    var btn = document.getElementById("copilot-ask");
    var q = input.value.trim();
    if (!q || btn.disabled) {
      return;
    }
    btn.disabled = true;
    appendMessage(esc(q), "copilot-q");
    input.value = "";
    appendMessage('<span class="copilot-thinking">Thinking…</span>', "copilot-a");

    fetch(apiBase() + "/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("service returned HTTP " + r.status);
        return r.json();
      })
      .then(renderAnswer)
      .catch(function (err) {
        replaceLastAnswer(
          '<span class="copilot-error">Could not reach the AI service (' +
            esc(String(err.message || err)) + "). Is it running?</span>"
        );
      })
      .finally(function () {
        btn.disabled = false;
      });
  }

  function renderAnswer(resp) {
    var conf = CONFIDENCE_STYLES[resp.confidence] || CONFIDENCE_STYLES.low;
    var html =
      '<div class="copilot-answer-head"><span class="' + conf.cls + '">' +
      conf.label + "</span></div>" +
      '<div class="copilot-answer-text">' + answerHtml(resp.answer) + "</div>";

    if (resp.sources && resp.sources.length) {
      html += '<div class="copilot-sources"><div class="copilot-sources-title">Sources</div><ul>';
      resp.sources.forEach(function (s) {
        html +=
          "<li>" + esc(s.title) +
          (s.section && s.section !== "(top)" ? " — " + esc(s.section) : "") +
          (s.url_or_path
            ? ' <a href="' + esc(s.url_or_path) + '" target="_blank" rel="noopener">[doc]</a>'
            : "") +
          "</li>";
      });
      html += "</ul></div>";
    }
    replaceLastAnswer(html);
  }

  function replaceLastAnswer(html) {
    var msgs = document.getElementById("copilot-messages");
    var last = msgs.lastElementChild;
    if (last && last.classList.contains("copilot-a")) {
      last.innerHTML = html;
      msgs.scrollTop = msgs.scrollHeight;
    } else {
      appendMessage(html, "copilot-a");
    }
  }

  $(document).on("app_ready", buildPanel);
})();
