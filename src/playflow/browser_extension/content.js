/* global browser */
(() => {
  if (globalThis.__playflowBridgeInstalled) return;
  globalThis.__playflowBridgeInstalled = true;
  const documentId = crypto.randomUUID();
  let controls = new Map();
  let snapshotUrl = '';
  const sensitive = /pass(word)?|token|secret|csrf|cookie|otp|one[- ]?time|verification.code|credit.card|cvv|cvc|iban|account.?number/i;
  const finalAction = /publish|roll\s*out|(?:send|submit).*review|start.*rollout|delete.*app|remove.*app/i;
  const normalize = value => String(value || '').replace(/\s+/g, ' ').trim().slice(0, 500);
  const visible = node => !!(node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden');

  function name(node) {
    const referenced = (node.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => document.getElementById(id)?.textContent || '').join(' ');
    return normalize(node.getAttribute('aria-label') || referenced
      || Array.from(node.labels || []).map(label => label.textContent).join(' ')
      || node.innerText || node.getAttribute('placeholder') || node.getAttribute('title'));
  }

  function privateControl(node) {
    return ['password', 'file', 'hidden'].includes(node.type)
      || sensitive.test([name(node), node.name, node.id, node.autocomplete].join(' '));
  }

  function snapshot() {
    controls = new Map();
    snapshotUrl = location.href;
    const revision = crypto.randomUUID();
    const result = [];
    let truncated = false;
    const headings = Array.from(document.querySelectorAll('h1,h2,h3,[role="heading"]')).filter(visible);
    const acknowledgements = [];
    // Export only recognized save acknowledgements, never a whole-page text dump.
    if (document.createTreeWalker && document.body) {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let textNode;
      let visited = 0;
      while ((textNode = walker.nextNode()) && visited++ < 10000 && acknowledgements.length < 10) {
        const text = normalize(textNode.textContent);
        if (textNode.parentElement && visible(textNode.parentElement)
            && /^(?:Changes? saved|Your changes have been saved|Questionnaire saved|Draft saved)(?:[.!].*)?$/i.test(text)) {
          acknowledgements.push(text);
        }
      }
    }
    let characters = 0;
    const selector = 'button,material-button,material-fab,material-icon-button,input,textarea,select,a[href],[role="button"],[role="link"],[role="menuitem"],[role="checkbox"],[role="radio"],[role="combobox"],[role="option"],[role="tab"],[contenteditable="true"],[tabindex="0"]';
    for (const node of document.querySelectorAll(selector)) {
      if (!visible(node) && node.type !== 'file') continue;
      if (result.length >= 400) { truncated = true; break; }
      const id = `${revision}:${result.length}`;
      const label = name(node);
      const item = {id, tag: node.tagName.toLowerCase(), role: node.getAttribute('role') || '',
        name: label, type: node.type || '', disabled: !!node.disabled || node.hasAttribute('disabled') || node.getAttribute('aria-disabled') === 'true'};
      const precedingHeading = headings.filter(heading => heading.compareDocumentPosition(node) & 4).at(-1);
      if (precedingHeading) item.section = normalize(precedingHeading.textContent);
      if (node.type === 'file') {
        item.accept = node.accept || '';
        item.multiple = !!node.multiple;
        item.hidden = !visible(node);
      }
      if (privateControl(node)) item.sensitive = true;
      else {
        if ('value' in node) item.value = String(node.value).slice(0, 5000);
        if ('checked' in node) item.checked = node.checked;
        if (node.hasAttribute('aria-checked')) item.checked = node.getAttribute('aria-checked');
        if (node.tagName === 'SELECT') item.options = Array.from(node.options)
          .slice(0, 300).map(option => ({value: option.value, name: normalize(option.label)}));
      }
      characters += JSON.stringify(item).length;
      if (characters > 200000) { truncated = true; break; }
      controls.set(id, node);
      result.push(item);
    }
    return {url: snapshotUrl, title: document.title, revision, document_id: documentId, truncated, acknowledgements,
      headings: headings.slice(0, 40).map(node => normalize(node.textContent)),
      notices: Array.from(document.querySelectorAll('[role="alert"],[role="status"]'))
        .filter(visible).slice(0, 20).map(node => normalize(node.textContent)), controls: result};
  }

  browser.runtime.onMessage.addListener(async message => {
    if (message.type !== 'playflow-command') return undefined;
    const job = message.job;
    const current = new URL(location.href);
    if (!current.href.startsWith(job.target)) {
      throw new Error('Tab navigated outside the selected page scope.');
    }
    if (Date.now() > job.deadline) throw new Error('Command expired.');
    if (job.operation === 'inspect') return snapshot();
    if (job.operation === 'navigate') {
      const destination = new URL(job.value);
      if (destination.search || destination.hash || !destination.href.startsWith(job.target)) throw new Error('Navigation outside scope.');
      location.assign(destination.href);
      return {navigation_requested: true, previous_document_id: documentId};
    }
    const node = controls.get(job.control_id);
    const attachment = job.operation === 'attach' && node?.tagName === 'INPUT' && node.type === 'file';
    if (!node || !node.isConnected || location.href !== snapshotUrl || (!visible(node) && !attachment)) {
      throw new Error('Stale or missing control; inspect the page again.');
    }
    if (privateControl(node) && !attachment) throw new Error('Sensitive fields and file uploads require a separate workflow.');
    if (node.disabled || node.hasAttribute('disabled') || node.getAttribute('aria-disabled') === 'true') throw new Error('Control is disabled.');
    const approvedSitePublish = job.operation === 'click' && job.approved_site_publish === true
      && job.target.startsWith('https://sites.google.com/d/') && name(node) === 'Publish';
    const reviewMatch = /^(?:Submit|Send)(?: (\d+))?(?: changes?)? for review$/.exec(name(node));
    const approvedPlayReview = job.operation === 'click' && Number.isInteger(job.approved_play_review)
      && job.approved_play_review > 0 && job.target.startsWith('https://play.google.com/')
      && current.pathname === new URL(job.target + 'publishing').pathname && reviewMatch
      && (!reviewMatch[1] || Number(reviewMatch[1]) === job.approved_play_review);
    if (finalAction.test(name(node)) && !approvedSitePublish && !approvedPlayReview) throw new Error('Final submission requires a separate reviewed action.');
    if (job.operation === 'attach') {
      if (!attachment || !job.target.startsWith('https://play.google.com/') || !job.file) throw new Error('Invalid attachment target.');
      const file = job.file;
      if (!['image/png', 'image/jpeg', 'application/octet-stream'].includes(file.mime)
          || !file.name || /[/\\]/.test(file.name) || file.size > 16 * 1024 * 1024) throw new Error('Invalid release file.');
      const bytes = Uint8Array.from(atob(file.data), char => char.charCodeAt(0));
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
        .map(value => value.toString(16).padStart(2, '0')).join('');
      if (bytes.length !== file.size || digest !== file.sha256) throw new Error('Attachment integrity check failed.');
      if (Date.now() > job.deadline) throw new Error('Attachment command expired.');
      const transfer = new DataTransfer();
      transfer.items.add(new File([bytes], file.name, {type: file.mime}));
      node.files = transfer.files;
      node.dispatchEvent(new Event('input', {bubbles: true}));
      node.dispatchEvent(new Event('change', {bubbles: true}));
    } else if (job.operation === 'click') {
      if (node.tagName === 'A' && !String(node.href).startsWith(job.target)) throw new Error('Link outside scope.');
      node.click();
    } else if (job.operation === 'fill') {
      if (!['INPUT', 'TEXTAREA'].includes(node.tagName) || node.readOnly) throw new Error('Not an editable native text field.');
      const value = String(job.value);
      if (node.maxLength >= 0 && value.length > node.maxLength) throw new Error('Field character limit exceeded.');
      const prototype = node.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, 'value').set.call(node, value);
      node.dispatchEvent(new Event('input', {bubbles: true}));
      node.dispatchEvent(new Event('change', {bubbles: true}));
    } else if (job.operation === 'check') {
      if (typeof job.value !== 'boolean') throw new Error('Checkbox value must be boolean.');
      const checked = typeof node.checked === 'boolean' ? node.checked : node.getAttribute('aria-checked') === 'true';
      if (!['checkbox', 'radio'].includes(node.type) && !['checkbox', 'radio'].includes(node.getAttribute('role'))) throw new Error('Not a checkbox or radio.');
      if (checked !== job.value) node.click();
    } else if (job.operation === 'select') {
      if (node.tagName !== 'SELECT' || !Array.from(node.options).some(option => option.value === job.value)) throw new Error('Unknown native select option.');
      node.value = job.value;
      node.dispatchEvent(new Event('change', {bubbles: true}));
    } else throw new Error('Unsupported action.');
    await new Promise(resolve => setTimeout(resolve, 350));
    return {...snapshot(), action_applied: true};
  });
})();
