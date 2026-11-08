const $ = id => document.getElementById(id);
chrome.storage.local.get("cc_cfg").then(({ cc_cfg }) => {
  const f = (cc_cfg && cc_cfg.folders) || [{ match: "Inbox", label: "Inbox unread" }];
  $("f").value = f.map(x => `${x.match}=${x.label}`).join("\n");
});
$("save").onclick = async () => {
  const folders = $("f").value.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
    const i = l.indexOf("="); return i < 0 ? { match: l, label: l + " unread" } : { match: l.slice(0, i).trim(), label: l.slice(i + 1).trim() };
  });
  await chrome.storage.local.set({ cc_cfg: { folders } });
  $("ok").textContent = "Saved";
};
$("open").onclick = async () => {
  for (const url of ["https://outlook.office.com/mail/#cc-lane", "https://outlook.office.com/calendar/view/day#cc-lane", "https://m365.cloud.microsoft/chat#cc-lane"]) {
    await chrome.tabs.create({ url, pinned: true, active: false });
  }
};
