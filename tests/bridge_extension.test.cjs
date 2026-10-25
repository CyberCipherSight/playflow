const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const {randomUUID, webcrypto, createHash} = require('node:crypto');

const target = 'https://play.google.com/console/u/0/developers/123/app/42/';

function fixture(specs, url = target + 'app-content', texts = []) {
  let listener;
  class Input {
    constructor(spec) {
      Object.assign(this, {tagName: 'INPUT', type: 'text', labels: [], id: '', name: '',
        autocomplete: '', disabled: false, readOnly: false, maxLength: -1, isConnected: true,
        checked: false, _value: '', clicks: 0, events: []}, spec);
    }
    get value() { return this._value; }
    set value(value) { this._value = value; }
    getAttribute(key) { return key === 'aria-label' ? this.label : null; }
    hasAttribute() { return false; }
    getClientRects() { return this.hidden ? [] : [{}]; }
    dispatchEvent(event) { this.events.push(event.type); }
    click() { this.clicks++; if (this.type === 'checkbox') this.checked = !this.checked; }
  }
  const nodes = specs.map(spec => new Input(spec));
  const context = vm.createContext({
    atob, File, DataTransfer: class {
      constructor() { this.files = []; this.items = {add: file => this.files.push(file)}; }
    },
    URL, Map, Event: class { constructor(type) { this.type = type; } },
    NodeFilter: {SHOW_TEXT: 4},
    HTMLInputElement: Input, HTMLTextAreaElement: Input,
    crypto: {randomUUID, subtle: webcrypto.subtle}, setTimeout: fn => fn(),
    getComputedStyle: () => ({visibility: 'visible'}),
    location: {href: url, assign() { throw new Error('Unexpected navigation'); }},
    document: {title: 'Fixture', body: {}, getElementById: () => null,
      createTreeWalker: () => {
        let index = 0;
        return {nextNode: () => index < texts.length
          ? {textContent: texts[index++], parentElement: {getClientRects: () => [{}]}} : null};
      },
      querySelectorAll: selector => selector.startsWith('button,') ? nodes : []},
    browser: {runtime: {onMessage: {addListener: fn => { listener = fn; }}}}
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/playflow/browser_extension/content.js'), 'utf8'), context);
  return {nodes, command: (operation, extra = {}) => listener({type: 'playflow-command',
    job: {operation, target, deadline: Date.now() + 5000, ...extra}})};
}

test('passwords are redacted and cannot be filled through stale or forged actions', async () => {
  const f = fixture([{label: 'Password', type: 'password', _value: 'do-not-expose'}]);
  const snapshot = await f.command('inspect');
  assert.equal(snapshot.controls[0].sensitive, true);
  assert.equal('value' in snapshot.controls[0], false);
  assert.equal(JSON.stringify(snapshot).includes('do-not-expose'), false);
  await assert.rejects(f.command('fill', {control_id: snapshot.controls[0].id, value: 'replace'}), /Sensitive/);
  assert.equal(f.nodes[0].value, 'do-not-expose');
});

test('filling uses native setters and emits input and change events', async () => {
  const f = fixture([{label: 'Privacy policy URL'}]);
  const snapshot = await f.command('inspect');
  const after = await f.command('fill', {control_id: snapshot.controls[0].id, value: 'https://example.com/privacy'});
  assert.equal(f.nodes[0].value, 'https://example.com/privacy');
  assert.deepEqual(f.nodes[0].events, ['input', 'change']);
  assert.equal(after.action_applied, true);
  assert.notEqual(after.controls[0].id, snapshot.controls[0].id);
  assert.equal(after.document_id, snapshot.document_id);
  await assert.rejects(f.command('click', {control_id: snapshot.controls[0].id}), /Stale/);
});

test('removed controls and final submission buttons are not clicked', async () => {
  const f = fixture([{label: 'Save'}, {label: 'Send changes for review'}, {label: 'Submit 15 changes for review'}]);
  const snapshot = await f.command('inspect');
  f.nodes[0].isConnected = false;
  await assert.rejects(f.command('click', {control_id: snapshot.controls[0].id}), /Stale/);
  await assert.rejects(f.command('click', {control_id: snapshot.controls[1].id}), /Final submission/);
  await assert.rejects(f.command('click', {control_id: snapshot.controls[2].id}), /Final submission/);
  assert.equal(f.nodes[0].clicks + f.nodes[1].clicks, 0);
});

test('checkbox updates are idempotent and field length limits are enforced', async () => {
  const f = fixture([{label: 'Contains ads', type: 'checkbox'}, {label: 'Title', maxLength: 3}]);
  let snapshot = await f.command('inspect');
  snapshot = await f.command('check', {control_id: snapshot.controls[0].id, value: true});
  snapshot = await f.command('check', {control_id: snapshot.controls[0].id, value: true});
  assert.equal(f.nodes[0].clicks, 1);
  await assert.rejects(f.command('fill', {control_id: snapshot.controls[1].id, value: 'too-long'}), /character limit/);
});

test('expired commands and normalized navigation outside the app are rejected', async () => {
  const f = fixture([{label: 'Save'}]);
  await assert.rejects(f.command('inspect', {deadline: 0}), /expired/);
  await assert.rejects(f.command('navigate', {value: target + '../420/app-dashboard'}), /outside scope/);
});

test('Console task routing metadata stays inside the selected app scope', async () => {
  const f = fixture([{label: 'Privacy policy URL'}], target + 'app-content/privacy-policy?source=dashboard');
  const snapshot = await f.command('inspect');
  assert.match(snapshot.url, /source=dashboard/);
  const after = await f.command('fill', {control_id: snapshot.controls[0].id, value: 'https://example.com/privacy'});
  assert.equal(after.controls[0].value, 'https://example.com/privacy');
  const other = fixture([], target.replace('/42/', '/420/') + 'app-content?source=dashboard');
  await assert.rejects(other.command('inspect'), /outside/);
});

test('explicit attachments verify content and support hidden file inputs without exposing paths', async () => {
  const f = fixture([{label: 'Upload', type: 'file', hidden: true}]);
  let page = await f.command('inspect');
  assert.equal(page.controls[0].hidden, true);
  assert.equal(page.controls[0].sensitive, true);
  const bytes = Buffer.from('public release fixture');
  const file = {name: 'app.aab', mime: 'application/octet-stream', size: bytes.length,
    data: bytes.toString('base64'), sha256: createHash('sha256').update(bytes).digest('hex')};
  page = await f.command('attach', {control_id: page.controls[0].id, file});
  assert.equal(f.nodes[0].files[0].name, 'app.aab');
  assert.equal(await f.nodes[0].files[0].text(), bytes.toString());
  assert.deepEqual(f.nodes[0].events, ['input', 'change']);
  assert.equal('value' in page.controls[0], false);
  await assert.rejects(f.command('attach', {control_id: page.controls[0].id,
    file: {...file, sha256: '0'.repeat(64)}}), /integrity/);
  assert.equal(f.nodes[0].events.length, 2);
});

test('attachment cannot fill a password or use a path as its filename', async () => {
  const f = fixture([{label: 'Password', type: 'password'}, {label: 'Upload', type: 'file'}]);
  const page = await f.command('inspect');
  const file = {name: '../secret', mime: 'image/png', size: 0, data: '', sha256: ''};
  await assert.rejects(f.command('attach', {control_id: page.controls[0].id, file}), /Sensitive/);
  await assert.rejects(f.command('attach', {control_id: page.controls[1].id, file}), /Invalid release file/);
  assert.equal(f.nodes[0].events.length + f.nodes[1].events.length, 0);
});

test('large snapshots report truncation instead of implying complete page coverage', async () => {
  const f = fixture(Array.from({length: 401}, (_, index) => ({label: `Field ${index}`})));
  const page = await f.command('inspect');
  assert.equal(page.controls.length, 400);
  assert.equal(page.truncated, true);
});

test('only recognized save acknowledgements are extracted from page text', async () => {
  const f = fixture([], target + 'app-content', ['private unrelated page text',
    'Change saved. Send for review in Publishing overview.', 'Your changes have been saved.']);
  const page = await f.command('inspect');
  assert.equal(page.acknowledgements.length, 2);
  assert.equal(JSON.stringify(page).includes('private unrelated page text'), false);
});

test('site-specific publishing permission never authorizes Play review submission', async () => {
  const site = 'https://sites.google.com/d/site-id/';
  const f = fixture([{label: 'Publish', tagName: 'BUTTON'}], site + 'p/page/edit');
  const page = await f.command('inspect', {target: site});
  await assert.rejects(f.command('click', {target: site, control_id: page.controls[0].id}), /Final submission/);
  await f.command('click', {target: site, control_id: page.controls[0].id, approved_site_publish: true});
  assert.equal(f.nodes[0].clicks, 1);
  const play = fixture([{label: 'Submit 15 changes for review'}]);
  const other = await play.command('inspect');
  await assert.rejects(play.command('click', {control_id: other.controls[0].id, approved_site_publish: true}), /Final submission/);
});

test('review submission requires a matching permission on the publishing page', async () => {
  const f = fixture([{label: 'Submit 15 changes for review'}], target + 'publishing');
  const page = await f.command('inspect');
  await assert.rejects(f.command('click', {control_id: page.controls[0].id, approved_play_review: 16}), /Final submission/);
  await f.command('click', {control_id: page.controls[0].id, approved_play_review: 15});
  assert.equal(f.nodes[0].clicks, 1);
  const other = fixture([{label: 'Submit 15 changes for review'}], target + 'app-dashboard');
  const snapshot = await other.command('inspect');
  await assert.rejects(other.command('click', {control_id: snapshot.controls[0].id, approved_play_review: 15}), /Final submission/);
});

test('singular change submission requires the exact approved count', async () => {
  const f = fixture([{label: 'Submit 1 change for review'}], target + 'publishing');
  const page = await f.command('inspect');
  await assert.rejects(f.command('click', {control_id: page.controls[0].id}), /Final submission/);
  await assert.rejects(f.command('click', {control_id: page.controls[0].id, approved_play_review: 2}), /Final submission/);
  await f.command('click', {control_id: page.controls[0].id, approved_play_review: 1});
  assert.equal(f.nodes[0].clicks, 1);
});
