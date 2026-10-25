/* global browser, PlayFlowBridgeConfig */
(async () => {
  const config = globalThis.PlayFlowBridgeConfig;
  if (!config) return;
  const headers = {Authorization: `Bearer ${config.token}`, 'Content-Type': 'application/json'};

  function allowed(url, prefix) {
    try {
      const candidate = new URL(url);
      return config.targets.includes(prefix) && candidate.href.startsWith(prefix);
    } catch { return false; }
  }

  async function execute(job) {
    if (Date.now() > job.deadline) throw new Error('Command expired; inspect before retrying.');
    const tabs = (await browser.tabs.query({})).filter(tab => allowed(tab.url, job.target));
    if (tabs.length !== 1) throw new Error(`Expected one matching tab; found ${tabs.length}.`);
    const tab = tabs[0];
    // Firefox throttles timers in background tabs, including post-action snapshots.
    await browser.tabs.update(tab.id, {active: true});
    await browser.tabs.executeScript(tab.id, {file: 'content.js'});
    return browser.tabs.sendMessage(tab.id, {type: 'playflow-command', job});
  }

  while (true) {
    try {
      const response = await fetch(`${config.url}/next`, {headers, cache: 'no-store'});
      if (!response.ok) throw new Error('Bridge unavailable.');
      const job = await response.json();
      if (!job) continue;
      let result;
      try { result = await execute(job); }
      catch (error) { result = {error: String(error.message).slice(0, 300)}; }
      await fetch(`${config.url}/result`, {
        method: 'POST', headers, body: JSON.stringify({id: job.id, result})
      });
    } catch { await new Promise(resolve => setTimeout(resolve, 1000)); }
  }
})();
