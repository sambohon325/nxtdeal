/** Clear a shared kiosk view after inactivity; never cancels a server operation. */
export function startKioskPrivacyTimer(onWarning: (visible: boolean) => void, onExpire: () => void) {
  let warning: ReturnType<typeof setTimeout>;
  let expiry: ReturnType<typeof setTimeout>;
  let stopped = false;
  const stop = () => {
    stopped = true;
    clearTimeout(warning);
    clearTimeout(expiry);
    window.removeEventListener("pointerdown", restart);
    window.removeEventListener("keydown", restart);
  };
  const restart = () => {
    if (stopped) return;
    clearTimeout(warning);
    clearTimeout(expiry);
    onWarning(false);
    warning = setTimeout(() => onWarning(true), 90_000);
    expiry = setTimeout(() => { stop(); onExpire(); }, 120_000);
  };
  window.addEventListener("pointerdown", restart);
  window.addEventListener("keydown", restart);
  restart();
  return { restart, stop };
}
