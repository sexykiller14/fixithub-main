/* FixIT Hub - progressive enhancement only. Every page works without this file. */
(function () {
  'use strict';

  // ---------------------------------------------------------------- theme
  function setupTheme() {
    var toggle = document.getElementById('theme-toggle');
    if (!toggle) return;

    function currentTheme() {
      return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
    }

    function updateToggle() {
      var theme = currentTheme();
      var next = theme === 'dark' ? 'light' : 'dark';
      toggle.setAttribute('aria-label', 'Switch to ' + next + ' theme');
      toggle.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
      toggle.setAttribute('title', 'Switch to ' + next + ' mode');
    }

    updateToggle();

    toggle.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      if (next === 'dark') {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }
      try {
        localStorage.setItem('fixit-theme', next);
      } catch (e) {
        // Storage can be blocked in private browsing. The toggle still works for this page.
      }
      updateToggle();
    });

    // Follow the system preference only while the user has not chosen one.
    if (window.matchMedia) {
      var query = window.matchMedia('(prefers-color-scheme: dark)');
      var onChange = function (event) {
        var stored = null;
        try {
          stored = localStorage.getItem('fixit-theme');
        } catch (e) { /* ignore */ }
        if (stored) return;
        if (event.matches) {
          document.documentElement.classList.add('dark');
        } else {
          document.documentElement.classList.remove('dark');
        }
        updateToggle();
      };
      if (query.addEventListener) {
        query.addEventListener('change', onChange);
      } else if (query.addListener) {
        query.addListener(onChange);
      }
    }
  }

  // ----------------------------------------------------------- mobile menu
  function setupMobileMenu() {
    var button = document.getElementById('menu-button');
    var menu = document.getElementById('mobile-menu');
    if (!button || !menu) return;

    button.addEventListener('click', function () {
      var isOpen = menu.classList.toggle('hidden') === false;
      button.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      button.setAttribute('aria-label', isOpen ? 'Close main menu' : 'Open main menu');
    });

    // Close the menu on Escape, returning focus to the button.
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !menu.classList.contains('hidden')) {
        menu.classList.add('hidden');
        button.setAttribute('aria-expanded', 'false');
        button.focus();
      }
    });
  }

  // ---------------------------------------------------------- copy buttons
  function addCopyButtons() {
    var blocks = document.querySelectorAll('.prose-article pre');
    Array.prototype.forEach.call(blocks, function (block) {
      if (block.parentElement && block.parentElement.classList.contains('code-block')) {
        return;
      }
      var wrapper = document.createElement('div');
      wrapper.className = 'code-block';
      block.parentNode.insertBefore(wrapper, block);
      wrapper.appendChild(block);

      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'copy-button';
      button.textContent = 'Copy';
      button.setAttribute('aria-label', 'Copy this command block to the clipboard');

      button.addEventListener('click', function () {
        var code = block.querySelector('code');
        var text = code ? code.innerText : block.innerText;
        copyText(text, button);
      });

      wrapper.appendChild(button);
    });
  }

  function copyText(text, button) {
    var done = function () {
      var original = button.getAttribute('data-label') || 'Copy';
      button.setAttribute('data-label', original);
      button.textContent = 'Copied';
      button.classList.add('copied');
      window.setTimeout(function () {
        button.textContent = original;
        button.classList.remove('copied');
      }, 1800);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        fallbackCopy(text, done);
      });
    } else {
      fallbackCopy(text, done);
    }
  }

  // Works on non-secure origins where the async clipboard API is unavailable.
  function fallbackCopy(text, done) {
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'absolute';
    area.style.left = '-9999px';
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand('copy');
      done();
    } catch (e) {
      // Nothing else we can do; the text is visible on screen to copy manually.
      window.alert('Copy failed. Select the text and copy it manually.');
    }
    document.body.removeChild(area);
  }

  // Any element with data-copy-target copies the referenced element's text.
  function setupDataCopyButtons() {
    var buttons = document.querySelectorAll('[data-copy-target]');
    Array.prototype.forEach.call(buttons, function (button) {
      button.addEventListener('click', function () {
        var target = document.getElementById(button.getAttribute('data-copy-target'));
        if (!target) return;
        var original = button.textContent;
        copyText(target.innerText, button);
        button.textContent = original;
      });
    });
  }

  // ------------------------------------------------------ table of contents
  function setupToc() {
    var toc = document.getElementById('toc');
    if (!toc) return;

    var links = toc.querySelectorAll('a[href^="#"]');
    if (!links.length) return;

    var targets = [];
    Array.prototype.forEach.call(links, function (link) {
      var id = link.getAttribute('href').slice(1);
      var heading = document.getElementById(id);
      if (heading) {
        targets.push({ link: link, heading: heading });
      }
    });

    if (!('IntersectionObserver' in window) || !targets.length) return;

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          targets.forEach(function (item) {
            item.link.classList.toggle('toc-active', item.heading === entry.target);
            item.link.setAttribute('aria-current', item.heading === entry.target ? 'true' : 'false');
          });
        });
      },
      { rootMargin: '0px 0px -70% 0px', threshold: 0 }
    );

    targets.forEach(function (item) {
      observer.observe(item.heading);
    });
  }

  // ------------------------------------------------------- feedback widget
  function setupFeedback() {
    var form = document.getElementById('feedback-form');
    if (!form) return;

    form.addEventListener('submit', function () {
      var buttons = form.querySelectorAll('button[type="submit"]');
      Array.prototype.forEach.call(buttons, function (button) {
        button.disabled = true;
        button.classList.add('opacity-60');
      });
      var status = document.getElementById('feedback-status');
      if (status) {
        status.textContent = 'Sending...';
      }
    });
  }

  // --------------------------------------------------------- tool spinners
  function setupToolForms() {
    var forms = document.querySelectorAll('[data-tool-form]');
    Array.prototype.forEach.call(forms, function (form) {
      form.addEventListener('submit', function () {
        var button = form.querySelector('button[type="submit"]');
        if (!button) return;
        var label = button.getAttribute('data-label') || button.textContent;
        button.setAttribute('data-label', label);
        button.textContent = 'Checking...';
        button.disabled = true;
        window.setTimeout(function () {
          // Re-enable in case the browser restored this page from cache.
          button.textContent = label;
          button.disabled = false;
        }, 15000);
      });
    });
  }

  // ---------------------------------------------- minidump upload preview
  function setupDumpUpload() {
    var input = document.getElementById('dump-file');
    var info = document.getElementById('dump-info');
    if (!input || !info) return;

    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) {
        info.textContent = '';
        return;
      }
      var size = file.size;
      var description;
      if (size > 5 * 1024 * 1024) {
        description = file.name + ' is ' + (size / 1024 / 1024).toFixed(1) +
          ' MB, which is over the 5 MB limit.';
      } else {
        description = file.name + ' is ' + (size / 1024).toFixed(0) + ' KB and ready to analyse.';
      }
      info.textContent = description;
      info.className = 'mt-2 text-sm ' + (size > 5 * 1024 * 1024 ? 'text-red-600 dark:text-red-400' : 'text-slate-600 dark:text-slate-400');
    });
  }

  // ---------------------------------------------------- admin article slug
  function setupSlugField() {
    var title = document.getElementById('article-title');
    var slug = document.getElementById('article-slug');
    if (!title || !slug) return;
    var slugTouched = slug.value.trim().length > 0;

    slug.addEventListener('input', function () {
      slugTouched = slug.value.trim().length > 0;
    });

    title.addEventListener('input', function () {
      if (slugTouched) return;
      slug.value = title.value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 180);
    });
  }

  // ------------------------------------------------------ password toggles
  // Any button with [data-password-toggle] shows or hides the field it names.
  // Used by the admin change-password form. Without this file the fields stay
  // type="password", which is the safe default.
  function setupPasswordToggles() {
    var buttons = document.querySelectorAll('[data-password-toggle]');
    Array.prototype.forEach.call(buttons, function (button) {
      var field = document.getElementById(button.getAttribute('data-password-toggle'));
      if (!field) return;

      var showLabel = button.textContent;
      var showText = button.getAttribute('aria-label') || 'Show password';
      var hideText = showText.replace(/^Show/i, 'Hide');

      button.addEventListener('click', function () {
        var hidden = field.type === 'password';
        field.type = hidden ? 'text' : 'password';
        button.textContent = hidden ? 'Hide' : showLabel;
        button.setAttribute('aria-pressed', hidden ? 'true' : 'false');
        button.setAttribute('aria-label', hidden ? hideText : showText);
      });
    });
  }

  // --------------------------------------------------------------- startup
  function init() {
    setupTheme();
    setupMobileMenu();
    addCopyButtons();
    setupDataCopyButtons();
    setupToc();
    setupFeedback();
    setupToolForms();
    setupDumpUpload();
    setupSlugField();
    setupPasswordToggles();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
