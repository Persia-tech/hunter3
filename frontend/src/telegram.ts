interface WebApp {initData:string;colorScheme?:'light'|'dark';themeParams?:Record<string,string>;ready():void;expand():void;BackButton:{show():void;hide():void;onClick(cb:()=>void):void;offClick(cb:()=>void):void}}
declare global {interface Window {Telegram?:{WebApp:WebApp}}}

/** Telegram injects this object before the module script; resolve it lazily for tests and previews. */
export const getTelegramWebApp = () => window.Telegram?.WebApp;
export const getTelegramInitData = () => getTelegramWebApp()?.initData ?? '';
export const tg = getTelegramWebApp();

export function initializeTelegram(){
  const webApp=getTelegramWebApp();
  webApp?.ready();webApp?.expand();
  document.documentElement.dataset.theme=webApp?.colorScheme??'';
  if(webApp?.themeParams) for(const [key,value] of Object.entries(webApp.themeParams)) document.documentElement.style.setProperty(`--tg-${key.replaceAll('_','-')}`,value);
}
