// Theme constants shared by the server layout (bootstrap script) and the client
// hooks. Kept free of "use client" so app/layout.tsx can inline the script
// string directly into the document head and avoid a flash of the wrong theme.

export const THEME_STORAGE_KEY = "jev-theme-mode";

/** Applied before first paint; sets data-theme + color-scheme on <html>. */
export const THEME_BOOTSTRAP_SCRIPT = `(function(){try{var s=localStorage.getItem("${THEME_STORAGE_KEY}")||"system";var dark=window.matchMedia("(prefers-color-scheme: dark)").matches;var t=s==="dark"||(s==="system"&&dark)?"dark":"light";var r=document.documentElement;r.setAttribute("data-theme",t);r.style.colorScheme=t;}catch(e){document.documentElement.setAttribute("data-theme","light");}})();`;
