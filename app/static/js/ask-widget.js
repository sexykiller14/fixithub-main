/* FixIT Hub - "Ask us anything" prompt widget.
   Progressive enhancement, like the rest of site.js: every page still works
   without this file. All text and the endpoint are in CONFIG below. */
(function () {
  'use strict';

  // ==========================================================================
  // CONFIG - edit the wording, the suggestions and the endpoint here.
  // Nothing below this block needs changing to customise the widget.
  // ==========================================================================
  var CONFIG = {
    // Where the question is POSTed as JSON: { "prompt": "..." }.
    // Must be same-origin (app/main.py sets Content-Security-Policy
    // connect-src 'self'). Leave '' to skip the request and show thankYouText,
    // which is the quickest way to test the widget without a backend.
    endpoint: '/api/ask',

    // The reply endpoint. {id} is replaced with the question id and {token} with
    // the one-off token handed back when the question was sent.
    replyEndpoint: '/api/ask/{id}?token={token}',

    // How often to look for the admin's reply while the panel is open, and how
    // many times before giving up. Polling only runs while the panel is open.
    pollIntervalMs: 10000,
    maxPolls: 30,

    // localStorage key holding the pending question id and token, so a reply
    // that arrives after the visitor closes the tab is still found later.
    storageKey: 'fixithub-ask-question',

    // Maximum characters. Applied to the textarea and the counter. The server
    // caps this again at the same length.
    maxLength: 500,

    buttonLabel: 'Ask us anything',
    buttonAriaLabel: 'Ask us anything: open the question panel',
    panelTitle: 'How can we help?',
    intro: 'Ask a question and we will point you at the right guide.',
    closeLabel: 'Close the question panel',
    textareaLabel: 'Your question',
    placeholder: 'Type your question here...',
    suggestions: [
      'What are your prices?',
      'How do I get started?',
      'I need support'
    ],
    sendLabel: 'Send message',
    sendingText: 'Sending...',
    shortcutHint: 'Ctrl+Enter to send',
    successText: 'Thanks! Your question is on its way.',
    replyLabel: 'Answer',
    thankYouText: 'Thanks! Nothing was sent - the widget is still in test mode.',
    errorText: 'Could not send your message. Check your connection and try again.'
  };
  // ==========================================================================

  var SVG_NS = 'http://www.w3.org/2000/svg';

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function speechIcon() {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('class', 'ask-fab-icon');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    var path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z');
    svg.appendChild(path);
    return svg;
  }

  function setupAskWidget() {
    if (!document.body || document.getElementById('ask-widget')) return;

    var sending = false;
    var statusTimer = null;

    // ------------------------------------------------------------- panel
    var panel = el('div', 'ask-panel');
    panel.id = 'ask-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-labelledby', 'ask-panel-title');

    var head = el('div', 'ask-head');
    var title = el('h2', 'ask-title', CONFIG.panelTitle);
    title.id = 'ask-panel-title';
    head.appendChild(title);

    var closeButton = el('button', 'ask-close', '×');
    closeButton.type = 'button';
    closeButton.setAttribute('aria-label', CONFIG.closeLabel);
    head.appendChild(closeButton);
    panel.appendChild(head);

    panel.appendChild(el('p', 'ask-intro', CONFIG.intro));

    // Suggestion chips fill the textarea so the visitor can edit before sending.
    var chips = el('div', 'ask-chips');
    CONFIG.suggestions.forEach(function (text) {
      var chip = el('button', 'ask-chip', text);
      chip.type = 'button';
      chip.addEventListener('click', function () {
        input.value = text.slice(0, CONFIG.maxLength);
        refresh();
        input.focus();
      });
      chips.appendChild(chip);
    });
    panel.appendChild(chips);

    var label = el('label', 'ask-label', CONFIG.textareaLabel);
    label.htmlFor = 'ask-input';

    var input = el('textarea', 'ask-input');
    input.id = 'ask-input';
    input.rows = 4;
    input.maxLength = CONFIG.maxLength;
    input.placeholder = CONFIG.placeholder;
    input.setAttribute('aria-describedby', 'ask-meta');
    panel.appendChild(label);
    panel.appendChild(input);

    var meta = el('div', 'ask-meta');
    meta.id = 'ask-meta';
    // The limit is already announced via maxlength, so the visible count is
    // decorative. The hint beside it is what assistive tech reads out.
    var counter = el('span', 'ask-counter', '0 / ' + CONFIG.maxLength);
    counter.setAttribute('aria-hidden', 'true');
    meta.appendChild(counter);
    meta.appendChild(el('span', 'ask-hint', CONFIG.shortcutHint));
    panel.appendChild(meta);

    var sendButton = el('button', 'ask-send', CONFIG.sendLabel);
    sendButton.type = 'button';
    sendButton.disabled = true;
    panel.appendChild(sendButton);

    var status = el('p', 'ask-status');
    status.setAttribute('aria-live', 'polite');
    status.setAttribute('aria-atomic', 'true');
    panel.appendChild(status);

    // --------------------------------------------------------- launcher
    var fab = el('button', 'ask-fab');
    fab.type = 'button';
    fab.setAttribute('aria-expanded', 'false');
    fab.setAttribute('aria-controls', 'ask-panel');
    fab.setAttribute('aria-haspopup', 'dialog');
    fab.setAttribute('aria-label', CONFIG.buttonAriaLabel);
    fab.appendChild(speechIcon());
    fab.appendChild(el('span', 'ask-fab-label', CONFIG.buttonLabel));

    var wrap = el('div', 'ask-widget');
    wrap.id = 'ask-widget';
    wrap.appendChild(panel);
    wrap.appendChild(fab);

    // ---------------------------------------------------------- helpers
    function isOpen() {
      return panel.classList.contains('is-open');
    }

    function refresh() {
      counter.textContent = input.value.length + ' / ' + CONFIG.maxLength;
      sendButton.disabled = sending || input.value.trim().length === 0;
    }

    // Clearing before writing means an identical message is announced again,
    // for example when the same failure happens twice in a row.
    function setStatus(text, tone) {
      status.className = 'ask-status' + (tone ? ' ask-status-' + tone : '');
      if (statusTimer) window.clearTimeout(statusTimer);
      status.textContent = '';
      statusTimer = window.setTimeout(function () {
        status.textContent = text;
      }, 40);
    }

    function openPanel() {
      panel.classList.add('is-open');
      fab.setAttribute('aria-expanded', 'true');
      input.focus();
      // Pick up a reply that landed while the panel was closed.
      checkForReply();
    }

    function closePanel() {
      panel.classList.remove('is-open');
      fab.setAttribute('aria-expanded', 'false');
      fab.focus();
      // Polling only runs while the panel is open, so an idle tab costs nothing.
      stopPolling();
    }

    // ------------------------------------------------- reply token storage
    // Only this browser holds the token that reads the reply, so it has to
    // survive the tab closing. Storage can be blocked in private browsing, in
    // which case polling simply does not happen; the question still saves.
    function savePending(record) {
      try {
        window.localStorage.setItem(CONFIG.storageKey, JSON.stringify(record));
      } catch (e) { /* storage blocked; polling is skipped, nothing else breaks */ }
    }

    function loadPending() {
      try {
        var raw = window.localStorage.getItem(CONFIG.storageKey);
        if (!raw) return null;
        var parsed = JSON.parse(raw);
        if (parsed && parsed.id && parsed.token) return parsed;
      } catch (e) { /* unreadable or blocked */ }
      return null;
    }

    function clearPending() {
      try {
        window.localStorage.removeItem(CONFIG.storageKey);
      } catch (e) { /* nothing to clean up */ }
    }

    // --------------------------------------------------------- reply polling
    var pollTimer = null;
    var polls = 0;

    function stopPolling() {
      if (pollTimer) {
        window.clearTimeout(pollTimer);
        pollTimer = null;
      }
    }

    function startPolling() {
      stopPolling();
      polls = 0;
      pollTimer = window.setTimeout(poll, CONFIG.pollIntervalMs);
    }

    function poll() {
      pollTimer = null;
      var pending = loadPending();
      if (!pending || !isOpen()) return;
      if (polls >= CONFIG.maxPolls) return;

      polls += 1;
      var url = CONFIG.replyEndpoint
        .replace('{id}', encodeURIComponent(pending.id))
        .replace('{token}', encodeURIComponent(pending.token));

      fetch(url, { headers: { 'Accept': 'application/json' } })
        .then(function (response) {
          if (response.status === 404) {
            // Unknown id or wrong token. The visitor has nothing useful to do
            // about it, so stop quietly rather than showing an error.
            clearPending();
            return null;
          }
          if (!response.ok) throw new Error('Poll failed');
          return response.json();
        })
        .then(function (data) {
          if (!data) return;
          if (data.status === 'answered' && data.reply) {
            stopPolling();
            clearPending();
            setStatus(CONFIG.replyLabel + ': ' + data.reply, 'ok');
            return;
          }
          if (isOpen()) pollTimer = window.setTimeout(poll, CONFIG.pollIntervalMs);
        })
        .catch(function () {
          // A failed poll is not worth reporting: the question is saved and the
          // next poll, or the next visit, will pick the answer up.
          if (isOpen()) pollTimer = window.setTimeout(poll, CONFIG.pollIntervalMs);
        });
    }

    // A reply that arrived while the panel was closed is picked up on open.
    function checkForReply() {
      if (loadPending()) startPolling();
    }

    // ------------------------------------------------------------- send
    function send() {
      var text = input.value.trim();
      if (!text || sending) return;

      // No endpoint configured yet, so skip the request and confirm receipt.
      if (!CONFIG.endpoint) {
        setStatus(CONFIG.thankYouText, 'ok');
        input.value = '';
        refresh();
        return;
      }

      sending = true;
      stopPolling();
      sendButton.textContent = CONFIG.sendingText;
      refresh();
      setStatus(CONFIG.sendingText, '');

      fetch(CONFIG.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // page_url is stored with the question so an admin can see which page
        // the question came from. The server truncates it.
        //
        // reply_to is the honeypot: a real visitor never sees or fills it in,
        // so the server drops the submission when it arrives non-empty. Kept
        // here in the payload rather than in a hidden input because the widget
        // is built entirely in JavaScript.
        body: JSON.stringify({
          prompt: text,
          page_url: window.location.href,
          reply_to: ''
        })
      }).then(function (response) {
        if (!response.ok) throw new Error('Request failed with ' + response.status);
        return response.json();
      }).then(function (data) {
        // The server replies with an id and a one-off token. Both are needed to
        // read the answer later, so they are stored before anything is shown.
        if (data && data.id && data.token) {
          savePending({ id: data.id, token: data.token });
        }
        // Clear on success so the same question cannot be sent twice by
        // accident. On failure the text is kept, because retry is expected.
        input.value = '';
        var immediate = data && data.reply ? String(data.reply) : '';
        setStatus(immediate || CONFIG.successText, 'ok');
      }).catch(function () {
        setStatus(CONFIG.errorText, 'error');
      }).then(function () {
        sending = false;
        sendButton.textContent = CONFIG.sendLabel;
        refresh();
        if (loadPending()) startPolling();
      });
    }

    // ----------------------------------------------------------- events
    fab.addEventListener('click', function () {
      if (isOpen()) {
        closePanel();
      } else {
        openPanel();
      }
    });

    closeButton.addEventListener('click', closePanel);
    sendButton.addEventListener('click', send);
    input.addEventListener('input', refresh);

    // Ctrl+Enter sends, Escape closes and hands focus back to the launcher.
    // site.js listens for Escape too; it is registered first, so this runs last
    // and focus ends up here when both panels happen to be open.
    document.addEventListener('keydown', function (event) {
      if (!isOpen()) return;
      if (event.key === 'Escape') {
        closePanel();
        return;
      }
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        send();
      }
    });

    document.body.appendChild(wrap);
    refresh();
  }

  // --------------------------------------------------------------- startup
  function init() {
    setupAskWidget();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();