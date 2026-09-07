import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Check, Edit3, Minus, Package, Plus, Share2, Sparkles, Trash2, X } from 'lucide-react';

import { api } from './api';
import { money, percent } from './format';
import type { Asset, CustomPurchase, OpportunityRanking, OpportunityResult, Product } from './types';

const PURCHASES_KEY = 'hunter3.opportunity-purchases.v1';
const CUSTOM_KEY = 'hunter3.opportunity-custom-purchases.v1';
const ASSETS_KEY = 'hunter3.opportunity-assets.v1';
const MAX_ASSETS = 5;
type Selection = Record<string, number>;
type CustomDraft = Omit<CustomPurchase, 'id' | 'custom'>;

function stored<T>(key: string, fallback: T): T {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? 'null');
    return value !== null ? value as T : fallback;
  } catch { return fallback; }
}

function savedAssets(): string[] {
  const saved = stored<unknown>(ASSETS_KEY, ['BTC']);
  if (!Array.isArray(saved)) return ['BTC'];
  const unique = [...new Set(saved.filter((value): value is string => typeof value === 'string'))].slice(0, MAX_ASSETS);
  return unique.length ? unique : ['BTC'];
}

const blankDraft = (): CustomDraft => ({ name: '', purchase_date: '', price_usd: '', quantity: 1, category: '' });
const dollars = (value: string) => money(value);
const units = (value: string, symbol: string) => `${Number(value).toLocaleString(undefined, { maximumFractionDigits: symbol === 'BTC' ? 8 : 4 })} ${symbol === 'BTC' ? 'BTC' : 'shares'}`;
const makeId = () => `custom:${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;

function validateCustom(draft: CustomDraft): string {
  if (!draft.name.trim()) return 'Enter a name for this purchase.';
  if (!draft.purchase_date || Number.isNaN(Date.parse(`${draft.purchase_date}T00:00:00`))) return 'Enter a valid purchase date.';
  if (draft.purchase_date > new Date().toISOString().slice(0, 10)) return 'Purchase date cannot be in the future.';
  if (!draft.price_usd || !Number.isFinite(Number(draft.price_usd)) || Number(draft.price_usd) <= 0) return 'Price must be greater than zero.';
  if (!Number.isInteger(draft.quantity) || draft.quantity < 1) return 'Quantity must be at least 1.';
  return '';
}

export function OpportunityCost({ assets }: { assets: Asset[] }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [category, setCategory] = useState('All');
  const [selected, setSelected] = useState<Selection>(() => stored(PURCHASES_KEY, {}));
  const [customs, setCustoms] = useState<CustomPurchase[]>(() => stored(CUSTOM_KEY, []));
  const [selectedAssets, setSelectedAssets] = useState<string[]>(savedAssets);
  const [assetPicker, setAssetPicker] = useState(false);
  const [assetMessage, setAssetMessage] = useState('');
  const [showCustom, setShowCustom] = useState(false);
  const [editingId, setEditingId] = useState<string>();
  const [draft, setDraft] = useState<CustomDraft>(blankDraft);
  const [formError, setFormError] = useState('');
  const [results, setResults] = useState<OpportunityResult[]>([]);
  const [activeAsset, setActiveAsset] = useState('BTC');
  const [rankings, setRankings] = useState<OpportunityRanking[]>([]);
  const [loading, setLoading] = useState(false);
  const [ranking, setRanking] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { api.opportunityProducts().then((data) => { setProducts(data.products); setCategories(data.categories); }).catch((reason) => setError(reason.message)); }, []);
  useEffect(() => { localStorage.setItem(PURCHASES_KEY, JSON.stringify(selected)); }, [selected]);
  useEffect(() => { localStorage.setItem(CUSTOM_KEY, JSON.stringify(customs)); }, [customs]);
  useEffect(() => { localStorage.setItem(ASSETS_KEY, JSON.stringify(selectedAssets)); }, [selectedAssets]);

  const requestItems = useMemo(() => [
    ...Object.entries(selected).filter(([, quantity]) => quantity > 0).map(([product_id, quantity]) => ({ product_id, quantity })),
    ...customs.map((custom) => ({ custom })),
  ], [selected, customs]);
  const visible = category === 'All' ? products : products.filter((product) => product.category === category);
  const chosen = products.filter((product) => selected[product.id]);
  const activeResult = results.find((result) => result.asset.symbol === activeAsset) ?? results[0];
  const totalQuantity = Object.values(selected).reduce((sum, quantity) => sum + quantity, 0) + customs.reduce((sum, item) => sum + item.quantity, 0);

  const changeCatalogQuantity = (id: string, delta: number) => setSelected((current) => {
    const next = { ...current, [id]: (current[id] ?? 0) + delta };
    if (next[id] <= 0) delete next[id];
    return next;
  });
  const changeCustomQuantity = (id: string, delta: number) => setCustoms((current) => current.map((item) => item.id === id ? { ...item, quantity: Math.max(1, item.quantity + delta) } : item));
  const resetResults = () => { setResults([]); setRankings([]); };

  const saveCustom = (event: FormEvent) => {
    event.preventDefault();
    const validation = validateCustom(draft);
    if (validation) { setFormError(validation); return; }
    const item: CustomPurchase = { id: editingId ?? makeId(), custom: true, ...draft, name: draft.name.trim(), category: draft.category.trim() || 'Other' };
    setCustoms((current) => editingId ? current.map((existing) => existing.id === editingId ? item : existing) : [...current, item]);
    setDraft(blankDraft()); setEditingId(undefined); setShowCustom(false); setFormError(''); resetResults();
  };
  const editCustom = (item: CustomPurchase) => {
    setDraft({ name: item.name, purchase_date: item.purchase_date, price_usd: item.price_usd, quantity: item.quantity, category: item.category });
    setEditingId(item.id); setFormError(''); setShowCustom(true);
  };
  const removeCustom = (id: string) => { setCustoms((current) => current.filter((item) => item.id !== id)); resetResults(); };
  const toggleAsset = (symbol: string) => {
    setAssetMessage('');
    if (selectedAssets.includes(symbol)) {
      if (selectedAssets.length === 1) { setAssetMessage('Choose at least one asset.'); return; }
      const next = selectedAssets.filter((item) => item !== symbol);
      setSelectedAssets(next); setActiveAsset(next[0]); resetResults(); return;
    }
    if (selectedAssets.length >= MAX_ASSETS) { setAssetMessage('You can compare up to 5 assets.'); return; }
    setSelectedAssets((current) => [...current, symbol]); resetResults();
  };
  const calculate = () => {
    if (!requestItems.length) return;
    setLoading(true); setError(''); setRankings([]);
    api.opportunityCompare({ assets: selectedAssets, items: requestItems })
      .then((data) => { setResults(data.results); setActiveAsset(data.results[0]?.asset.symbol ?? selectedAssets[0]); })
      .catch((reason) => setError(reason.message)).finally(() => setLoading(false));
  };
  const compareAll = () => {
    setRanking(true);
    api.opportunityRank({ items: requestItems }).then((data) => setRankings(data.rankings)).catch((reason) => setError(reason.message)).finally(() => setRanking(false));
  };
  const share = async () => {
    if (!activeResult) return;
    const text = `I spent ${dollars(activeResult.summary.total_spent)}. If I had invested each purchase in ${activeResult.asset.name} on its own date, eligible purchases could be worth ${dollars(activeResult.summary.current_value)} today. Hypothetical—not financial advice.`;
    if (navigator.share) await navigator.share({ text }); else await navigator.clipboard.writeText(text);
  };

  return <div className="page-enter opportunity-page">
    <header className="screen-header"><p className="eyebrow">OPPORTUNITY COST</p><h1>What if you invested instead?</h1><p>Choose things you bought. Every purchase is invested separately on its own historical date.</p></header>
    {error && <p className="opportunity-error">{error}</p>}
    <section className="surface opportunity-section">
      <div className="section-heading"><div><p className="eyebrow">STEP 1</p><h2>Things I bought</h2></div>{requestItems.length > 0 && <button className="text-button" onClick={() => { setSelected({}); setCustoms([]); resetResults(); }}><Trash2/> Clear</button>}</div>
      <button className="button secondary add-custom-button" onClick={() => { setEditingId(undefined); setDraft(blankDraft()); setFormError(''); setShowCustom(true); }}><Plus/> Add custom purchase</button>
      {showCustom && <form className="custom-purchase-form" onSubmit={saveCustom}>
        <div className="section-heading"><h2>{editingId ? 'Edit custom purchase' : 'Add custom purchase'}</h2><button type="button" className="icon-button" aria-label="Close custom purchase form" onClick={() => setShowCustom(false)}><X/></button></div>
        <label>Name<input aria-label="Custom purchase name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Sony OLED TV"/></label>
        <div className="custom-form-grid"><label>Purchase date<input aria-label="Custom purchase date" type="date" max={new Date().toISOString().slice(0, 10)} value={draft.purchase_date} onChange={(event) => setDraft({ ...draft, purchase_date: event.target.value })}/></label><label>Price USD<input aria-label="Custom purchase price" inputMode="decimal" value={draft.price_usd} onChange={(event) => setDraft({ ...draft, price_usd: event.target.value })} placeholder="1999.99"/></label></div>
        <div className="custom-form-grid"><label>Quantity<input aria-label="Custom purchase quantity" type="number" min="1" max="99" value={draft.quantity} onChange={(event) => setDraft({ ...draft, quantity: Number(event.target.value) })}/></label><label>Category <small>optional</small><input aria-label="Custom purchase category" value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })} placeholder="Electronics"/></label></div>
        {formError && <p role="alert">{formError}</p>}<button className="button primary" type="submit">{editingId ? 'Save changes' : 'Add purchase'}</button>
      </form>}
      <div className="chip-row"><button className={category === 'All' ? 'active' : ''} onClick={() => setCategory('All')}>All</button>{categories.map((item) => <button className={category === item ? 'active' : ''} onClick={() => setCategory(item)} key={item}>{item}</button>)}</div>
      <div className="product-grid">{visible.map((product) => <button className={`product-card ${selected[product.id] ? 'selected' : ''}`} onClick={() => { changeCatalogQuantity(product.id, selected[product.id] ? -selected[product.id] : 1); resetResults(); }} key={product.id}><span className="product-placeholder"><Package/></span><span><strong>{product.model}</strong><small>{product.release_year} · {dollars(product.launch_price_usd)}</small></span><i>{selected[product.id] ? <Check/> : <Plus/>}</i></button>)}</div>
    </section>

    {!requestItems.length ? <section className="surface opportunity-empty"><Sparkles/><h2>Pick or add a purchase</h2><p>See what that exact spending history could be worth today.</p></section> : <>
      <section className="surface opportunity-section purchases"><p className="eyebrow">MY PURCHASES</p><h2>{totalQuantity} purchases selected</h2>
        {chosen.map((product) => <PurchaseRow key={product.id} name={product.model} detail={`${dollars(product.launch_price_usd)} each`} quantity={selected[product.id]} onMinus={() => { changeCatalogQuantity(product.id, -1); resetResults(); }} onPlus={() => { changeCatalogQuantity(product.id, 1); resetResults(); }}/>) }
        {customs.map((item) => <PurchaseRow key={item.id} name={item.name} detail={`${item.purchase_date} · ${dollars(item.price_usd)} each`} quantity={item.quantity} custom onMinus={() => { changeCustomQuantity(item.id, -1); resetResults(); }} onPlus={() => { changeCustomQuantity(item.id, 1); resetResults(); }} onEdit={() => editCustom(item)} onDelete={() => removeCustom(item.id)}/>) }
      </section>
      <section className="surface opportunity-section"><p className="eyebrow">STEP 2</p><h2>Compare investments</h2><div className="selected-assets">{selectedAssets.map((symbol) => <button onClick={() => toggleAsset(symbol)} key={symbol}>{symbol}<X/></button>)}<button className="add-asset" onClick={() => setAssetPicker((open) => !open)}><Plus/> Add asset</button></div>
        {assetPicker && <div className="asset-choice-list">{assets.map((item) => <button className={selectedAssets.includes(item.symbol) ? 'selected' : ''} onClick={() => toggleAsset(item.symbol)} key={item.symbol}><span><strong>{item.symbol}</strong><small>{item.name}</small></span>{selectedAssets.includes(item.symbol) && <Check/>}</button>)}</div>}
        {assetMessage && <p className="selection-message" role="alert">{assetMessage}</p>}<small className="selection-help">Select 1–5 assets. Your choices are saved on this device.</small>
        <button className="button primary opportunity-calculate" disabled={loading} onClick={calculate}>{loading ? 'Comparing…' : `Compare ${selectedAssets.length} asset${selectedAssets.length === 1 ? '' : 's'}`}</button>
      </section>
    </>}

    {activeResult && <>
      <section className="opportunity-summary"><p>You spent <strong>{dollars(activeResult.summary.total_spent)}</strong> across {activeResult.summary.total_items} dated items</p><span>Best selected alternative</span><h2>{results[0].asset.symbol} · {dollars(results[0].summary.current_value)}</h2><div><span><small>Gain</small><b>{dollars(results[0].summary.gain)}</b></span><span><small>Return</small><b>{percent(results[0].summary.return_pct)}</b></span></div><button onClick={share}><Share2/> Share summary</button></section>
      <section className="surface opportunity-section manual-comparison"><p className="eyebrow">COMPARE</p><h2>Your selected alternatives</h2>{results.map((result, index) => <button className={`comparison-card ${index === 0 ? 'best' : ''}`} onClick={() => setActiveAsset(result.asset.symbol)} key={result.asset.symbol}><span className="comparison-rank">{index + 1}</span><span><strong>{result.asset.symbol}{index === 0 && <em>Best</em>}</strong><small>{result.summary.eligible_items}/{result.summary.total_items} purchases eligible</small></span><span><strong>{dollars(result.summary.current_value)}</strong><small>{dollars(result.summary.gain)} · {percent(result.summary.return_pct)}</small><small>{units(result.summary.investment_units, result.asset.symbol)}</small></span></button>)}</section>
      <section className="surface opportunity-section"><div className="detail-selector"><div><p className="eyebrow">PURCHASE BY PURCHASE</p><h2>Detailed view</h2></div><select aria-label="Detailed view asset" value={activeResult.asset.symbol} onChange={(event) => setActiveAsset(event.target.value)}>{results.map((result) => <option key={result.asset.symbol}>{result.asset.symbol}</option>)}</select></div>{activeResult.items.map((item) => <article className={`opportunity-item ${item.eligible ? '' : 'unavailable'}`} key={item.product.id}><div><strong>{item.product.model} × {item.quantity}{item.product.custom && <em className="custom-badge">Custom</em>}</strong><small>{item.product.custom ? 'Purchased' : 'Released'} {new Date(`${item.requested_date}T12:00:00`).toLocaleDateString()} · {dollars(item.cost)}</small></div>{item.eligible ? <dl><div><dt>{activeResult.asset.symbol} close used</dt><dd>{dollars(item.asset_price!)} · {item.price_date}</dd></div><div><dt>You could have bought</dt><dd>{units(item.units, activeResult.asset.symbol)}</dd></div><div><dt>Value today</dt><dd>{dollars(item.current_value)}</dd></div><div><dt>Opportunity cost</dt><dd>{dollars(item.gain!)}</dd></div></dl> : <p>{item.reason}. Excluded from the comparison.</p>}</article>)}</section>
      <section className="surface opportunity-section insights"><p className="eyebrow">INSIGHTS</p><h2>Your spending, in perspective</h2><p><Sparkles/> Among your selected alternatives, <strong>{results[0].asset.symbol} performed best.</strong></p><p><Sparkles/> Your {dollars(results[0].summary.total_spent)} spending history could be worth <strong>{dollars(results[0].summary.current_value)} in {results[0].asset.symbol}.</strong></p><p><Sparkles/> The largest opportunity cost in this view came from <strong>{[...activeResult.items].filter((item) => item.eligible).sort((a,b) => Number(b.gain)-Number(a.gain))[0]?.product.model}.</strong></p></section>
      <section className="surface opportunity-section"><p className="eyebrow">BEST ALTERNATIVE</p><h2>Scan every supported asset</h2>{!rankings.length && <button className="button secondary" disabled={ranking} onClick={compareAll}>{ranking ? 'Comparing…' : 'Find the best alternative'}</button>}{rankings.map((row, index) => <div className="ranking-row" key={row.asset.symbol}><b>{index + 1}</b><span><strong>{row.asset.symbol}</strong><small>{row.summary.eligible_items}/{row.summary.total_items} eligible</small></span><strong>{dollars(row.summary.current_value)}</strong></div>)}</section>
    </>}
    <p className="disclaimer">Hypothetical historical comparison for educational purposes only. Past performance does not guarantee future results.</p>
  </div>;
}

function PurchaseRow({ name, detail, quantity, custom, onMinus, onPlus, onEdit, onDelete }: { name: string; detail: string; quantity: number; custom?: boolean; onMinus: () => void; onPlus: () => void; onEdit?: () => void; onDelete?: () => void }) {
  return <div className="purchase-row"><span><strong>{name}{custom && <em className="custom-badge">Custom</em>}</strong><small>{detail}</small></span>{onEdit && <button className="row-action" aria-label={`Edit ${name}`} onClick={onEdit}><Edit3/></button>}{onDelete && <button className="row-action delete" aria-label={`Delete ${name}`} onClick={onDelete}><Trash2/></button>}<span className="quantity-control"><button aria-label={`Remove one ${name}`} onClick={onMinus}><Minus/></button><b>{quantity}</b><button aria-label={`Add one ${name}`} onClick={onPlus}><Plus/></button></span></div>;
}
