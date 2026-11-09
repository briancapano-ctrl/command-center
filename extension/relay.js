// Runs on your Command Center page only (it checks for the page's marker). Passes the stored counts to the page.
(() => {
  if (!document.querySelector('meta[name="command-center"]')) return;
  const alive = () => { try { return !!(chrome.runtime && chrome.runtime.id); } catch (e) { return false; } };
  let t = null;
  const send = async () => {
    if (!alive()) { clearInterval(t); return; }
    let got;
    try { got = await chrome.storage.local.get(["cc_mail", "cc_cal", "cc_copilot"]); } catch (e) { return; }
    const { cc_mail, cc_cal, cc_copilot } = got;
    window.postMessage({ source: "cc-work-bridge", v: 1, work: { mail: cc_mail || null, cal: cc_cal || null, copilot: cc_copilot || null } }, location.origin);
  };
  send();
  t = setInterval(send, 20000);
  chrome.storage.onChanged.addListener(send);
})();
