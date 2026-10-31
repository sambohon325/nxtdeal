import { useEffect, useRef, useState, type CSSProperties } from "react";
import "./NxtGlass.css";
import "./DepartmentWork.css";
import "./WorkspaceUi.css";

export const glassDefaults = { mode: "dark", preset: "glacier", a: "#92c9ff", b: "#c4b5fd", glow: 20, glass: 56, blur: 18, motion: true, background: "showroom", dim: 32 };
export type GlassSettings = typeof glassDefaults;
export const wallpapers: Record<string, { name: string; src: string }> = {
  showroom: { name: "Midnight", src: "/brand/glass/showroom.webp" },
  glacier: { name: "Glacier", src: "/brand/glass/showroom-glacier.png" },
  aurora: { name: "Aurora", src: "/brand/glass/showroom-aurora.png" },
  sunset: { name: "Solstice", src: "/brand/glass/showroom-sunset.png" },
};
export function validatedGlassSettings(value: unknown): GlassSettings {
  const result = { ...glassDefaults };
  if (!value || typeof value !== "object") return result;
  const saved = value as Record<string, unknown>;
  for (const key of ["a", "b"] as const) if (typeof saved[key] === "string" && /^#[\da-f]{6}$/i.test(saved[key])) result[key] = saved[key];
  for (const [key, min, max] of [["glow",0,100],["glass",15,90],["blur",0,40],["dim",0,90]] as const) if (typeof saved[key] === "number" && Number.isFinite(saved[key])) result[key] = Math.max(min, Math.min(max, saved[key]));
  if (["dark","light","system"].includes(String(saved.mode))) result.mode = String(saved.mode);
  if ([...Object.keys(wallpapers),"gradient","custom"].includes(String(saved.background))) result.background = String(saved.background);
  if (typeof saved.motion === "boolean") result.motion = saved.motion;
  if (["glacier","aurora","sunset","graphite","custom"].includes(String(saved.preset))) result.preset = String(saved.preset);
  return result;
}
export function useGlassAppearance() {
  const [settings, setSettings] = useState(glassDefaults);
  const [custom, setCustom] = useState("");
  const [systemDark, setSystemDark] = useState(true);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    try { setSettings(validatedGlassSettings(JSON.parse(localStorage.getItem("nxtdeal-glass-v2") || "null"))); const image = localStorage.getItem("nxtdeal-custom-background") || ""; if (/^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(image)) setCustom(image); } catch { /* Keep the supplied design defaults when storage is unavailable. */ }
    const media = matchMedia("(prefers-color-scheme: dark)"); const update = () => setSystemDark(media.matches); update(); media.addEventListener("change", update); setReady(true);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => { if (ready) try { localStorage.setItem("nxtdeal-glass-v2", JSON.stringify(settings)); } catch { /* Appearance still works for this session. */ } }, [settings, ready]);
  const theme: "dark" | "light" = settings.mode === "dark" || settings.mode === "system" && systemDark ? "dark" : "light";
  const background = settings.background === "custom" && !custom ? "showroom" : settings.background;
  const style = { "--color-a": settings.a, "--color-b": settings.b, "--glow": settings.glow / 100, "--opacity": settings.glass / 100, "--blur": `${settings.blur}px`, "--wallpaper-dim": settings.dim / 100, "--wallpaper-image": `url("${background === "custom" ? custom : wallpapers[background]?.src || wallpapers.showroom.src}")` } as CSSProperties;
  return { settings, setSettings, custom, setCustom, theme, background, style };
}
export type GlassAppearance = ReturnType<typeof useGlassAppearance>;
export function GlassIcon({name}:{name:string}) {
  const icons: Record<string,string> = {sun:"M12 3V1m0 22v-2M3 12H1m22 0h-2M5 5 3 3m18 18-2-2M5 19l-2 2M21 3l-2 2M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0",moon:"M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12",sliders:"M4 7h9m4 0h3M4 17h3m4 0h9M13 4v6M7 14v6",close:"m6 6 12 12M6 18 18 6",home:"M3 10 12 3l9 7v10H5V10 M9 20v-7h6v7",sparkles:"m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",arrow:"M4 12h16m-5-5 5 5-5 5"};
  return <svg aria-hidden="true" viewBox="0 0 24 24"><path d={icons[name] || icons.sliders}/></svg>;
}
export function GlassBrand() { return <><svg className="brand-full" aria-hidden="true" viewBox="110 145 1760 480"><image href="/brand/glass/logo.webp" width="1983" height="793"/></svg><svg className="brand-icon" aria-hidden="true" viewBox="145 170 455 440"><image href="/brand/glass/logo.webp" width="1983" height="793"/></svg></>; }
export function AppearanceDialog({appearance,open,onClose}:{appearance:GlassAppearance;open:boolean;onClose:()=>void}) {
  const ref=useRef<HTMLDialogElement>(null); const [status,setStatus]=useState("JPG, PNG, or WebP · up to 2 MB · stored on this device");
  useEffect(()=>{if(open)ref.current?.showModal();else ref.current?.close();},[open]);
  const {settings,setSettings}=appearance; const change=(patch:Partial<GlassSettings>)=>setSettings(s=>({...s,...patch}));
  return <dialog ref={ref} className="glass dialog appearance" aria-label="Appearance" onCancel={onClose} onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose();}}}>
    <div className="dialog-header"><div><div className="eyebrow">YOUR WORKSPACE, YOUR WAY</div><h2>Appearance</h2></div><button className="icon-button" aria-label="Close appearance" onClick={onClose}><GlassIcon name="close"/></button></div><p className="dialog-description">Find your focus. Everything updates live.</p>
    <label className="control-label">Mode</label><div className="segmented">{["light","dark","system"].map(mode=><button key={mode} className={settings.mode===mode?"active":""} aria-pressed={settings.mode===mode} onClick={()=>change({mode})}>{mode[0].toUpperCase()+mode.slice(1)}</button>)}</div>
    <label className="control-label" htmlFor="glass-background">Background</label><select id="glass-background" className="background-select" value={appearance.background} onChange={e=>change({background:e.target.value})}>{Object.entries(wallpapers).map(([key,w])=><option key={key} value={key}>{w.name} showroom</option>)}<option value="gradient">Ambient color</option><option value="custom" disabled={!appearance.custom}>Custom image</option></select>
    <div className="wallpaper-gallery" role="group" aria-label="Showroom backgrounds">{Object.entries(wallpapers).map(([key,w])=><button key={key} className={`wallpaper-choice ${appearance.background===key?"active":""}`} aria-label={`${w.name} showroom background`} aria-pressed={appearance.background===key} onClick={()=>change({background:key})}><img src={w.src} alt="" loading="lazy"/><span>{w.name}</span></button>)}</div>
    <label className="upload-button soft-button">Upload your own background<input type="file" accept="image/jpeg,image/png,image/webp" onChange={async e=>{const file=e.target.files?.[0];if(!file)return;if(!["image/jpeg","image/png","image/webp"].includes(file.type)||file.size>2*1024*1024){setStatus("Choose a JPG, PNG, or WebP image smaller than 2 MB.");return;}try{const data=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=reject;reader.readAsDataURL(file);});const probe=new Image();probe.src=data;await probe.decode();appearance.setCustom(data);change({background:"custom"});try{localStorage.setItem("nxtdeal-custom-background",data);setStatus("Your background is saved on this device.");}catch{setStatus("Applied for this session. Device storage is full.");}}catch{setStatus("This image could not be opened. Try another file.");}}}/></label><p className="settings-note" role="status">{status}</p>
    <label className="control-label">Ambient glow colors</label><div className="presets">{Object.entries({glacier:["#92c9ff","#c4b5fd"],aurora:["#6edac6","#92a2ff"],sunset:["#ffb69b","#e6a9db"],graphite:["#91a3b7","#bec5ce"]}).map(([preset,[a,b]])=><button key={preset} className={`swatch ${preset} ${settings.preset===preset?"active":""}`} aria-pressed={settings.preset===preset} onClick={()=>change({preset,a,b})}><span>{preset}</span></button>)}</div>
    <div className="color-controls">{(["a","b"] as const).map((key,i)=><label key={key}>{i===0?"Primary":"Secondary"} glow<input type="color" value={settings[key]} onChange={e=>change({[key]:e.target.value,preset:"custom"})}/></label>)}</div>
    {([["dim","Background dimmer",0,90],["glow","Background intensity",0,100],["glass","Glass opacity",15,90],["blur","Glass blur",0,40]] as const).map(([key,label,min,max])=><div key={key}><label className="range-label" htmlFor={`glass-${key}`}>{label}<output>{settings[key]}{key==="blur"?"px":"%"}</output></label><input id={`glass-${key}`} type="range" min={min} max={max} value={settings[key]} onChange={e=>change({[key]:Number(e.target.value)})}/></div>)}
    <label className="switch-label"><span><b>Jelly motion</b><small>Springy slides and soft button presses</small></span><input type="checkbox" role="switch" checked={settings.motion} onChange={e=>change({motion:e.target.checked})}/></label><button className="soft-button reset" onClick={()=>setSettings({...glassDefaults})}>Reset appearance</button><small className="settings-note">Saved on this device. Reduced-motion preferences are respected.</small>
  </dialog>;
}
