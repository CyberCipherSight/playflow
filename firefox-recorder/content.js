(() => {
  const INTERACTIVE = 'button,a,input,textarea,select,[role="button"],[role="radio"],[role="checkbox"],[role="combobox"],[role="textbox"]';
  let recording = false;
  let lastUrl = null;
  let mutationTimer = null;
  const pending = new Set();

  function clipped(value) {
    return value == null ? null : String(value).replace(/\s+/g, ' ').trim().slice(0, 240);
  }
  function labelFor(el) {
    const labels = el.labels ? [...el.labels] : [];
    if (!labels.length && el.closest('label')) labels.push(el.closest('label'));
    return clipped(labels.map(label => label.innerText || label.textContent).join(' '));
  }
  function sensitive(el) {
    return PlayFlowPrivacy.sensitive({
      type: el.type, name: el.name, id: el.id, label: labelFor(el),
      ariaLabel: el.getAttribute('aria-label'), autocomplete: el.getAttribute('autocomplete')
    });
  }
  function inferRole(el) {
    if (el.getAttribute('role')) return el.getAttribute('role');
    const tag = el.tagName.toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a') return 'link';
    if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      if (['radio', 'checkbox'].includes(el.type)) return el.type;
      if (['button', 'submit', 'reset'].includes(el.type)) return 'button';
      return 'textbox';
    }
    return null;
  }
  function describe(el) {
    if (!(el instanceof Element)) return {};
    const base = {tag: el.tagName.toLowerCase(), type: clipped(el.getAttribute('type')), role: inferRole(el)};
    if (sensitive(el)) return {...base, sensitive: true};
    let selector = null;
    if (el.id && !/^(mat-|cdk-|_)/.test(el.id)) selector = `#${CSS.escape(el.id)}`;
    else {
      const attr = ['data-testid', 'data-test-id'].find(key => el.hasAttribute(key));
      if (attr) selector = `[${attr}="${CSS.escape(el.getAttribute(attr))}"]`;
    }
    const label = labelFor(el);
    // Textarea/select text can contain entered values or unrelated options.
    const text = ['input', 'textarea', 'select'].includes(base.tag) ? null : clipped(el.innerText || el.textContent);
    return {...base, name: clipped(el.getAttribute('aria-label') || label || el.getAttribute('title') || text),
      label, text, selector, name_attr: clipped(el.getAttribute('name')), autocomplete: clipped(el.getAttribute('autocomplete'))};
  }
  function safeValue(el) {
    if (sensitive(el)) return '[REDACTED]';
    if (['checkbox', 'radio'].includes(el.type)) return !!el.checked;
    if (el.tagName.toLowerCase() === 'select' && el.multiple) return [...el.selectedOptions].map(option => option.value);
    const value = el.value;
    return typeof value === 'string' && value.length <= 10000 ? value : '[OMITTED]';
  }
  function send(event, el = null, extra = {}) {
    if (!recording) return;
    const url = PlayFlowPrivacy.safeUrl(location.href);
    if (!url) return;
    browser.runtime.sendMessage({type: 'event', payload: {
      timestamp: new Date().toISOString(), url, event, element: describe(el), ...extra
    }}).catch(() => {});
  }
  function navigation(force = false) {
    const url = PlayFlowPrivacy.safeUrl(location.href);
    if (force || url !== lastUrl) {
      lastUrl = url;
      send('navigation');
    }
  }
  function setCapture(enabled) {
    recording = enabled;
    pending.clear();
    clearTimeout(mutationTimer);
    if (recording) navigation(true);
  }
  browser.runtime.onMessage.addListener(msg => {
    if (msg.type === 'capture') setCapture(msg.enabled);
  });
  browser.runtime.sendMessage({type: 'capture-status'}).then(status => setCapture(status.recording)).catch(() => {});
  document.addEventListener('click', event => {
    const el = event.target instanceof Element ? event.target.closest(INTERACTIVE) : null;
    if (el) send('click', el);
  }, true);
  document.addEventListener('change', event => {
    const el = event.target;
    if (el instanceof Element && el.matches(INTERACTIVE)) send('change', el, {value: safeValue(el)});
  }, true);
  // Polling also observes SPA navigation from Firefox's isolated content-script world.
  setInterval(() => { if (recording) navigation(); }, 500);
  const observer = new MutationObserver(records => {
    if (!recording) return;
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (!(node instanceof Element)) continue;
        for (const el of [node, ...node.querySelectorAll(INTERACTIVE)]) {
          if (pending.size >= 40) break;
          if (el.matches(INTERACTIVE)) pending.add(el);
        }
      }
    }
    if (!mutationTimer) mutationTimer = setTimeout(() => {
      mutationTimer = null;
      const added = [...pending].filter(el => {
        const box = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      }).map(describe);
      pending.clear();
      if (added.length) send('dom_added', null, {added});
    }, 250);
  });
  function observe() {
    if (!document.documentElement) return requestAnimationFrame(observe);
    observer.observe(document.documentElement, {subtree: true, childList: true});
  }
  observe();
})();
