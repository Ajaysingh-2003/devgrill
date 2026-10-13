/**
 * Runs inline in <head> before first paint: applies the saved theme and motion preference
 * to <html> so there is no flash of the wrong theme. Server-safe (plain string).
 *
 * Theme:  localStorage["devgrill-theme"]  = "system" | "light" | "dark"  → class "light" | "dark"
 * Motion: localStorage["devgrill-motion"] = "system" | "reduce" | "full" → data-motion="reduce" | "full"
 */
export const THEME_STORAGE_KEY = "devgrill-theme";
export const MOTION_STORAGE_KEY = "devgrill-motion";

export const themeInitScript = `(function(){try{
var d=document.documentElement,s=localStorage;
var t=s.getItem("${THEME_STORAGE_KEY}")||"system";
var dark=t==="dark"||(t==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);
d.classList.remove("light","dark");d.classList.add(dark?"dark":"light");
var m=s.getItem("${MOTION_STORAGE_KEY}")||"system";
if(m==="reduce"||m==="full"){d.setAttribute("data-motion",m)}else{d.removeAttribute("data-motion")}
}catch(e){}})();`;
