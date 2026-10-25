const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const root = path.join(__dirname, '..', 'firefox-recorder');

function context(extra = {}) {
  const ctx = vm.createContext({URL, ...extra});
  vm.runInContext(fs.readFileSync(path.join(root, 'privacy.js'), 'utf8'), ctx);
  return ctx;
}

test('sensitive inputs include autocomplete and file fields', () => {
  const ctx = context();
  for (const element of [{type: 'password'}, {type: 'file'}, {autocomplete: 'one-time-code'},
    {autocomplete: 'current-password'}, {label: 'API token'}, {name: 'account_number'}]) {
    ctx.element = element;
    assert.equal(vm.runInContext('PlayFlowPrivacy.sensitive(element)', ctx), true);
  }
});

test('URL sanitizer strips query/fragment and rejects external URLs', () => {
  const ctx = context();
  assert.equal(vm.runInContext("PlayFlowPrivacy.safeUrl('https://play.google.com/console/app?token=secret#secret')", ctx),
    'https://play.google.com/console/app');
  for (const value of ['https://evil.example/console/', 'https://play.google.com/console-evil']) {
    ctx.value = value;
    assert.equal(vm.runInContext('PlayFlowPrivacy.safeUrl(value)', ctx), null);
  }
});

test('starting a recording emits an initial navigation and binds to one tab', async () => {
  let listener;
  const messages = [];
  const ctx = context({browser: {
    runtime: {onMessage: {addListener(fn) { listener = fn; }}},
    tabs: {
      query: async () => [{id: 7, url: 'https://play.google.com/console/app'}],
      sendMessage: async (id, msg) => messages.push({id, msg})
    }
  }});
  vm.runInContext(fs.readFileSync(path.join(root, 'background.js'), 'utf8'), ctx);
  await listener({type: 'start'}, {});
  assert.equal(messages[0].id, 7);
  assert.equal(messages[0].msg.enabled, true);
  const payload = {event: 'navigation', url: 'https://play.google.com/console/app?private=1'};
  assert.equal((await listener({type: 'event', payload}, {tab: {id: 8}, frameId: 0})).ok, false);
  await listener({type: 'event', payload}, {tab: {id: 7}, frameId: 0});
  assert.equal((await listener({type: 'status'}, {})).count, 1);
  assert.equal(vm.runInContext('state.events[0].url', ctx), 'https://play.google.com/console/app');
  assert.equal((await listener({type: 'clear'}, {tab: {id: 7}})).ok, false);
  await listener({type: 'stop'}, {});
  assert.equal((await listener({type: 'status'}, {})).recording, false);
});

test('navigation recording never serializes document text', async () => {
  let listener;
  const messages = [];
  const ctx = context({
    Element: class Element {},
    location: {href: 'https://play.google.com/console/app?token=private'},
    document: {
      documentElement: {textContent: 'SECRET PAGE CONTENT'},
      addEventListener() {}
    },
    MutationObserver: class { observe() {} },
    setInterval() {}, clearTimeout() {},
    browser: {runtime: {
      onMessage: {addListener(fn) { listener = fn; }},
      sendMessage(msg) {
        messages.push(msg);
        return Promise.resolve({recording: false});
      }
    }}
  });
  vm.runInContext(fs.readFileSync(path.join(root, 'content.js'), 'utf8'), ctx);
  await Promise.resolve();
  listener({type: 'capture', enabled: true});
  const navigation = messages.find(msg => msg.payload?.event === 'navigation');
  assert.ok(navigation);
  assert.equal(navigation.payload.url, 'https://play.google.com/console/app');
  assert.equal(JSON.stringify(navigation).includes('SECRET PAGE CONTENT'), false);
  assert.deepEqual(Object.keys(navigation.payload.element), []);
});
