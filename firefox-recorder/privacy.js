/* Shared by the recorder scripts; no browser state or storage access. */
const PlayFlowPrivacy = (() => {
  const pattern = /pass(word)?|token|secret|csrf|auth|session|cookie|otp|one[- ]?time|verification|card|cvv|cvc|iban|account.?number/i;
  function sensitive(element) {
    return ['password', 'file', 'hidden'].includes((element.type || '').toLowerCase()) ||
      pattern.test([element.name, element.id, element.label, element.ariaLabel, element.autocomplete].join(' '));
  }
  function safeUrl(value) {
    const url = new URL(value);
    if (url.origin !== 'https://play.google.com' || !/^\/console(?:\/|$)/.test(url.pathname)) return null;
    return `${url.origin}${url.pathname}`;
  }
  return {sensitive, safeUrl};
})();
