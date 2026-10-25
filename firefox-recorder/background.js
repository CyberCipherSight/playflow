const MAX_EVENTS = 10000;
const state = {recording: false, startedAt: null, events: [], tabId: null, limitReached: false};

async function capture(enabled) {
  if (state.tabId != null) {
    await browser.tabs.sendMessage(state.tabId, {type: 'capture', enabled});
  }
}

browser.runtime.onMessage.addListener(async (msg, sender) => {
  if (msg.type === 'capture-status') {
    return {recording: state.recording && sender.tab?.id === state.tabId};
  }
  if (msg.type === 'event') {
    if (!state.recording || sender.tab?.id !== state.tabId || sender.frameId !== 0) return {ok: false};
    const payload = msg.payload;
    if (!payload || !PlayFlowPrivacy.safeUrl(payload.url)) return {ok: false};
    state.events.push({...payload, url: PlayFlowPrivacy.safeUrl(payload.url)});
    if (state.events.length >= MAX_EVENTS) {
      state.recording = false;
      state.limitReached = true;
      await capture(false);
    }
    return {ok: true};
  }
  // Only extension pages may operate the recorder controls.
  if (sender.tab) return {ok: false};
  if (msg.type === 'status') {
    return {recording: state.recording, startedAt: state.startedAt, count: state.events.length, limitReached: state.limitReached};
  }
  if (msg.type === 'start') {
    const [tab] = await browser.tabs.query({active: true, currentWindow: true});
    if (!tab || !PlayFlowPrivacy.safeUrl(tab.url)) return {ok: false, error: 'Open a Play Console tab first.'};
    if (state.recording) await capture(false);
    state.tabId = tab.id;
    state.startedAt = new Date().toISOString();
    state.events = [];
    state.limitReached = false;
    state.recording = true;
    try {
      await capture(true);
    } catch {
      state.recording = false;
      return {ok: false, error: 'Reload the Play Console tab and try again.'};
    }
    return {ok: true};
  }
  if (msg.type === 'stop' || msg.type === 'clear') {
    state.recording = false;
    await capture(false).catch(() => {});
    if (msg.type === 'clear') {
      state.events = [];
      state.startedAt = null;
      state.limitReached = false;
    }
    return {ok: true, count: state.events.length};
  }
  if (msg.type === 'export') {
    const payload = {
      schema_version: 1, recorder: 'playflow-firefox', started_at: state.startedAt,
      exported_at: new Date().toISOString(), limit_reached: state.limitReached, events: state.events
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    try {
      await browser.downloads.download({
        url, filename: `playflow-session-${new Date().toISOString().replace(/[:.]/g, '-')}.json`, saveAs: true
      });
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    }
    return {ok: true, count: state.events.length};
  }
});
