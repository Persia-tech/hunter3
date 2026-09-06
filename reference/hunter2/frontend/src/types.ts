export type Screen='home'|'dca'|'compare'|'lump'|'markets';
export interface Asset {symbol:string;name:string;category:string}
export interface ChartPoint {date:string;portfolio_value:string;contributions:string}
export interface DcaResult {asset:string;asset_name:string;asset_type:string;requested_start_date:string;requested_end_date:string;effective_end_date:string;frequency:string;contribution:string;total_invested:string;total_units:string;average_purchase_price:string;final_value:string;profit:string;return_pct:string;purchase_count:number;chart:ChartPoint[]}
export interface LumpResult {asset:string;asset_name:string;effective_end_date:string;total_capital:string;dca:DcaResult;lump_sum:{total_invested:string;total_units:string;final_value:string;profit:string;return_pct:string};winner:string;value_difference:string}
