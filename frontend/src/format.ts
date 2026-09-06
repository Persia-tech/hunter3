const decimal=(value:string,places:number)=>{const negative=value.startsWith('-');const [whole='0',fraction='']=value.replace(/^[-+]/,'').split('.');const grouped=whole.replace(/\B(?=(\d{3})+(?!\d))/g,',');const trimmed=fraction.slice(0,places).replace(/0+$/,'');return `${negative?'-':''}${grouped}${trimmed?'.'+trimmed:''}`};
const fixedMoney=(value:string)=>{const [whole='0',fraction='']=value.replace(/^[-+]/,'').split('.');const grouped=whole.replace(/\B(?=(\d{3})+(?!\d))/g,',');return `${grouped}.${fraction.slice(0,2).padEnd(2,'0')}`};
export const money=(value:string,sign=false)=>`${value.startsWith('-')?'-':sign?'+':''}$${fixedMoney(value)}`;
export const percent=(value:string)=>`${value.startsWith('-')?'':'+'}${decimal(value,2)}%`;
export const quantity=(value:string,symbol:string,crypto=false)=>`${decimal(value,crypto?8:6)} ${crypto?symbol:'shares'}`;
