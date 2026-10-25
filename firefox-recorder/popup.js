async function refresh() {
  const status = await browser.runtime.sendMessage({type: 'status'});
  document.querySelector('#status').textContent = `${status.recording ? 'RECORDING' : 'Stopped'}\nEvents: ${status.count}${status.limitReached ? '\nEvent limit reached. Export this session.' : ''}`;
}
for (const id of ['start', 'stop', 'export', 'clear']) {
  document.querySelector(`#${id}`).addEventListener('click', async () => {
    try {
      const result = await browser.runtime.sendMessage({type: id});
      if (result.error) throw new Error(result.error);
      await refresh();
    } catch (error) {
      document.querySelector('#status').textContent = error.message;
    }
  });
}
refresh();
