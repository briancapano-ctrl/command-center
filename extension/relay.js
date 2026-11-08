// Runs on your Command Center page only (it checks for the page's marker). Passes the stored counts to the page.
(() => {
  if (!document.querySelector('meta[name="command-center"]')) return;
  const send = async () => {
    const { cc_mail, cc_cal, cc_copilot } = await chrome.storage.local.get(["cc_mail", "cc_cal", "cc_copilot"]);
    window.postMessage({ source: "cc-work-bridge", v: 1, work: { mail: cc_mail || null, cal: cc_cal || null, copilot: cc_copilot || null } }, location.origin);
  };
  send();
  setInterval(send, 20000);
  chrome.storage.onChanged.addListener(send);
})();
