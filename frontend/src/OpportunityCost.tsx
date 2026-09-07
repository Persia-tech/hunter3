import { useEffect, useMemo, useState } from 'react';
import { Check, Minus, Package, Plus, Share2, Sparkles, Trash2 } from 'lucide-react';

import { api } from './api';
import { money, percent } from './format';
import type { Asset, OpportunityRanking, OpportunityResult, Product } from './types';

const STORAGE_KEY = 'hunter3.opportunity-purchases.v1';
type Selection = Record<string, number>;

function savedSelection(): Selection {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
    return parsed && typeof parsed === 'object' ? parsed as Selection : {};
  } catch { return {}; }
}

const dollars = (value: string) => money(value);
const units = (value: string, symbol: string) => `${Number(value).toLocaleString(undefined, { maximumFractionDigits: symbol === 'BTC' ? 8 : 4 })} ${symbol === 'BTC' ? 'BTC' : 'shares'}`;

export function OpportunityCost({ assets }: { assets: Asset[] }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [category, setCategory] = useState('All');
  const [selected, setSelected] = useState<Selection>(savedSelection);
  const [asset, setAsset] = useState('BTC');
  const [result, setResult] = useState<OpportunityResult>();
  const [rankings, setRankings] = useState<OpportunityRanking[]>([]);
  const [loading, setLoading] = useState(false);
  const [ranking, setRanking] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { api.opportunityProducts().then((data) => { setProducts(data.products); setCategories(data.categories); }).catch((reason) => setError(reason.message)); }, []);
  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(selected)); }, [selected]);
  const items = useMemo(() => Object.entries(selected).filter(([, quantity]) => quantity > 0).map(([product_id, quantity]) => ({ product_id, quantity })), [selected]);
  const visible = category === 'All' ? products : products.filter((product) => product.category === category);
  const chosen = products.filter((product) => selected[product.id]);

  const calculate = () => {
    if (!items.length) return;
    setLoading(true); setError(''); setRankings([]);
    api.opportunityCalculate({ asset, items }).then(setResult).catch((reason) => setError(reason.message)).finally(() => setLoading(false));
  };
  const compareAll = () => {
    setRanking(true);
    api.opportunityRank({ items }).then((data) => setRankings(data.rankings)).catch((reason) => setError(reason.message)).finally(() => setRanking(false));
  };
  const change = (id: string, delta: number) => setSelected((current) => {
    const next = { ...current, [id]: (current[id] ?? 0) + delta };
    if (next[id] <= 0) delete next[id];
    return next;
  });
  const share = async () => {
    if (!result) return;
    const text = `I spent ${dollars(result.summary.total_spent)} on tech. If I had invested each purchase in ${result.asset.name} on its release date instead, the eligible purchases could be worth ${dollars(result.summary.current_value)} today. Hypothetical—not financial advice.`;
    if (navigator.share) await navigator.share({ text }); else await navigator.clipboard.writeText(text);
  };

  return <div className="page-enter opportunity-page">
    <header className="screen-header"><p className="eyebrow">OPPORTUNITY COST</p><h1>What if you invested instead?</h1><p>Choose things you bought. Every purchase is invested separately on that product's release date.</p></header>
    {error && <p className="opportunity-error">{error}</p>}
    <section className="surface opportunity-section">
      <div className="section-heading"><div><p className="eyebrow">STEP 1</p><h2>Things I bought</h2></div>{items.length > 0 && <button className="text-button" onClick={() => { setSelected({}); setResult(undefined); setRankings([]); }}><Trash2/> Clear</button>}</div>
      <div className="chip-row"><button className={category === 'All' ? 'active' : ''} onClick={() => setCategory('All')}>All</button>{categories.map((item) => <button className={category === item ? 'active' : ''} onClick={() => setCategory(item)} key={item}>{item}</button>)}</div>
      <div className="product-grid">{visible.map((product) => <button className={`product-card ${selected[product.id] ? 'selected' : ''}`} onClick={() => change(product.id, selected[product.id] ? -selected[product.id] : 1)} key={product.id}>
        <span className="product-placeholder"><Package/></span><span><strong>{product.model}</strong><small>{product.release_year} · {dollars(product.launch_price_usd)}</small></span><i>{selected[product.id] ? <Check/> : <Plus/>}</i>
      </button>)}</div>
    </section>

    {items.length === 0 ? <section className="surface opportunity-empty"><Sparkles/><h2>Pick the products you bought</h2><p>See what that exact spending history could be worth today.</p></section> : <>
      <section className="surface opportunity-section purchases"><div className="section-heading"><div><p className="eyebrow">MY PURCHASES</p><h2>{items.reduce((sum, item) => sum + item.quantity, 0)} products selected</h2></div></div>{chosen.map((product) => <div className="purchase-row" key={product.id}><span><strong>{product.model}</strong><small>{dollars(product.launch_price_usd)} each</small></span><span className="quantity-control"><button aria-label={`Remove one ${product.model}`} onClick={() => change(product.id, -1)}><Minus/></button><b>{selected[product.id]}</b><button aria-label={`Add one ${product.model}`} onClick={() => change(product.id, 1)}><Plus/></button></span></div>)}</section>
      <section className="surface opportunity-section"><p className="eyebrow">STEP 2</p><h2>Invested instead in</h2><select className="opportunity-asset" aria-label="Investment asset" value={asset} onChange={(event) => setAsset(event.target.value)}>{assets.map((item) => <option value={item.symbol} key={item.symbol}>{item.symbol} · {item.name}</option>)}</select><button className="button primary opportunity-calculate" disabled={loading} onClick={calculate}>{loading ? 'Calculating…' : 'Calculate opportunity cost'}</button></section>
    </>}

    {result && <>
      <section className="opportunity-summary"><p>You spent <strong>{dollars(result.summary.total_spent)}</strong> on {result.summary.total_items} product types</p><span>If invested in {result.asset.name} instead</span><h2>{dollars(result.summary.current_value)}</h2><div><span><small>Gain</small><b>{dollars(result.summary.gain)}</b></span><span><small>Return</small><b>{percent(result.summary.return_pct)}</b></span></div><p>{units(result.summary.investment_units, result.asset.symbol)} accumulated · {result.summary.eligible_items}/{result.summary.total_items} purchases eligible</p><button onClick={share}><Share2/> Share summary</button></section>
      <section className="surface opportunity-section"><p className="eyebrow">PURCHASE BY PURCHASE</p><h2>Your exact timeline</h2>{result.items.map((item) => <article className={`opportunity-item ${item.eligible ? '' : 'unavailable'}`} key={item.product.id}><div><strong>{item.product.model} × {item.quantity}</strong><small>Released {new Date(`${item.requested_date}T12:00:00`).toLocaleDateString()} · {dollars(item.cost)}</small></div>{item.eligible ? <dl><div><dt>{result.asset.symbol} close used</dt><dd>{dollars(item.asset_price!)} · {item.price_date}</dd></div><div><dt>You could have bought</dt><dd>{units(item.units, result.asset.symbol)}</dd></div><div><dt>Value today</dt><dd>{dollars(item.current_value)}</dd></div><div><dt>Opportunity cost</dt><dd>{dollars(item.gain!)}</dd></div></dl> : <p>{item.reason}. Excluded from the comparison.</p>}</article>)}</section>
      <section className="surface opportunity-section insights"><p className="eyebrow">INSIGHTS</p><h2>Your spending, in perspective</h2><p><Sparkles/> Your largest missed opportunity was <strong>{[...result.items].filter((item) => item.eligible).sort((a,b) => Number(b.gain)-Number(a.gain))[0]?.product.model}</strong>.</p><p><Sparkles/> Your oldest selected purchase is from <strong>{Math.min(...result.items.map((item) => item.product.release_year))}</strong>.</p></section>
      <section className="surface opportunity-section"><div className="section-heading"><div><p className="eyebrow">BEST ALTERNATIVE</p><h2>Compare every supported asset</h2></div></div>{!rankings.length && <button className="button secondary" disabled={ranking} onClick={compareAll}>{ranking ? 'Comparing…' : 'Find the best alternative'}</button>}{rankings.map((row, index) => <div className="ranking-row" key={row.asset.symbol}><b>{index + 1}</b><span><strong>{row.asset.symbol}</strong><small>{row.summary.eligible_items}/{row.summary.total_items} eligible</small></span><strong>{dollars(row.summary.current_value)}</strong></div>)}</section>
    </>}
    <p className="disclaimer">Hypothetical historical comparison for educational purposes only. Past performance does not guarantee future results.</p>
  </div>;
}
