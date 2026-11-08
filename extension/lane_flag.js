// Marks a tab opened by the add-on ("Open and pin my work tabs") so only those tabs ever navigate or reload themselves.
if (location.hash.includes("cc-lane") || location.search.includes("cclane=1")) sessionStorage.setItem("cc_lane", "1");
