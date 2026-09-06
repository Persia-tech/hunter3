interface WebApp {initData:string;colorScheme?:'light'|'dark';themeParams?:Record<string,string>;ready():void;expand():void;BackButton:{show():void;hide():void;onClick(cb:()=>void):void;offClick(cb:()=>void):void}}
declare global {interface Window {Telegram?:{WebApp:WebApp}}}
export const tg=window.Telegram?.WebApp;
export function initializeTelegram(){tg?.ready();tg?.expand();document.documentElement.dataset.theme=tg?.colorScheme??'';if(tg?.themeParams) for(const [key,value] of Object.entries(tg.themeParams)) document.documentElement.style.setProperty(`--tg-${key.replaceAll('_','-')}`,value)}
