import { type FormEvent, useEffect, useMemo, useState } from 'react';
import { Check, ChevronDown, Edit3, Minus, Package, Plus, Search, Share2, Sparkles, Trash2, X } from 'lucide-react';

import { api } from './api';
import { AssetBadge } from './AssetBadge';
import { money, percent } from './format';
import type { Asset, CustomPurchase, OpportunityRanking, OpportunityResult, Product } from './types';

const MAX_ASSETS = 5;
const PREVIEW_COUNT = 4;
const CUSTOM_CATEGORIES = ['Electronics', 'Car', 'Travel', 'Luxury', 'Home', 'Subscription', 'Other'];
type Selection = Record<string, number>;
type CustomDraft = Omit<CustomPurchase, 'id' | 'custom'>;

const blankDraft = (): CustomDraft => ({ name: '', purchase_date: '', price_usd: '', quantity: 1, category: 'Electronics' });
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

function AssetMark({ symbol, category }: { symbol: string; category?: string }) {
  return <AssetBadge symbol={symbol} category={category} size="compact" />;
}

export function OpportunityCost({ assets }: { assets: Asset[] }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [category, setCategory] = useState('All');
  const [catalogExpanded, setCatalogExpanded] = useState(false);
  const [selected, setSelected] = useState<Selection>({});
  const [customs, setCustoms] = useState<CustomPurchase[]>([]);
  const [selectedAssets, setSelectedAssets] = useState<string[]>(['BTC']);
  const [assetPicker, setAssetPicker] = useState(false);
  const [assetQuery, setAssetQuery] = useState('');
  const [assetMessage, setAssetMessage] = useState('');
  const [showCustom, setShowCustom] = useState(false);
  const [editingId, setEditingId] = useState<string>();
  const [draft, setDraft] = useState<CustomDraft>(blankDraft);
  const [formError, setFormError] = useState('');
  const [showPurchases, setShowPurchases] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [showRankings, setShowRankings] = useState(false);
  const [results, setResults] = useState<OpportunityResult[]>([]);
  const [activeAsset, setActiveAsset] = useState('BTC');
  const [rankings, setRankings] = useState<OpportunityRanking[]>([]);
  const [snapshotId, setSnapshotId] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [ranking, setRanking] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { api.opportunityProducts().then((data) => { setProducts(data.products); setCategories(data.categories); }).catch(() => setError('Could not load the product catalog. Try again.')); }, []);

  const requestItems = useMemo(() => [
    ...Object.entries(selected).filter(([, quantity]) => quantity > 0).map(([product_id, quantity]) => ({ product_id, quantity })),
    ...customs.map((custom) => ({ custom })),
  ], [selected, customs]);
  const categoryProducts = category === 'All' ? products : products.filter((product) => product.category === category);
  const visibleProducts = catalogExpanded || category !== 'All' ? categoryProducts : categoryProducts.slice(0, 8);
  const chosen = products.filter((product) => selected[product.id]);
  const purchaseRows = [
    ...chosen.map((product) => ({ type: 'catalog' as const, product })),
    ...customs.map((custom) => ({ type: 'custom' as const, custom })),
  ];
  const activeResult = results.find((result) => result.asset.symbol === activeAsset) ?? results[0];
  const bestResult = results[0];
  const totalQuantity = Object.values(selected).reduce((sum, quantity) => sum + quantity, 0) + customs.reduce((sum, item) => sum + item.quantity, 0);
  const matchingAssets = assets.filter((asset) => `${asset.symbol} ${asset.name}`.toLowerCase().includes(assetQuery.toLowerCase()));

  const resetResults = () => { setResults([]); setRankings([]); setSnapshotId(undefined); };
  const startOver = () => {
    setSelected({});
    setCustoms([]);
    setSelectedAssets(['BTC']);
    setActiveAsset('BTC');
    setCategory('All');
    setCatalogExpanded(false);
    setShowPurchases(false);
    setShowTimeline(false);
    setShowRankings(false);
    setAssetPicker(false);
    setShowCustom(false);
    setAssetMessage('');
    setError('');
    resetResults();
  };
  const changeCatalogQuantity = (id: string, delta: number) => setSelected((current) => {
    const next = { ...current, [id]: (current[id] ?? 0) + delta };
    if (next[id] <= 0) delete next[id];
    return next;
  });
  const changeCustomQuantity = (id: string, delta: number) => setCustoms((current) => current.map((item) => item.id === id ? { ...item, quantity: Math.max(1, item.quantity + delta) } : item));
  const openCustom = (item?: CustomPurchase) => {
    setEditingId(item?.id);
    setDraft(item ? { name: item.name, purchase_date: item.purchase_date, price_usd: item.price_usd, quantity: item.quantity, category: item.category } : blankDraft());
    setFormError(''); setShowCustom(true);
  };
  const saveCustom = (event: FormEvent) => {
    event.preventDefault();
    const validation = validateCustom(draft);
    if (validation) { setFormError(validation); return; }
    const item: CustomPurchase = { id: editingId ?? makeId(), custom: true, ...draft, name: draft.name.trim(), category: draft.category.trim() || 'Other' };
    setCustoms((current) => editingId ? current.map((existing) => existing.id === editingId ? item : existing) : [...current, item]);
    setShowCustom(false); resetResults();
  };
  const toggleAsset = (symbol: string) => {
    setAssetMessage('');
    if (selectedAssets.includes(symbol)) {
      if (selectedAssets.length === 1) { setAssetMessage('Keep at least one asset selected.'); return; }
      const next = selectedAssets.filter((item) => item !== symbol);
      setSelectedAssets(next); setActiveAsset(next[0]); resetResults(); return;
    }
    if (selectedAssets.length >= MAX_ASSETS) { setAssetMessage('Maximum 5 assets.'); return; }
    setSelectedAssets((current) => [...current, symbol]); resetResults();
  };
  const calculate = () => {
    if (!requestItems.length) return;
    setLoading(true); setError(''); setRankings([]);
    api.opportunityCompare({ assets: selectedAssets, items: requestItems })
      .then((data) => { setResults(data.results); setSnapshotId(data.snapshot_id); setActiveAsset(data.results[0]?.asset.symbol ?? selectedAssets[0]); })
      .catch(() => setError('Could not refresh market prices. Try again.')).finally(() => setLoading(false));
  };
  const compareAll = () => {
    setRanking(true); setShowRankings(false);
    api.opportunityRank({ items: requestItems, snapshot_id: snapshotId })
      .then((data) => { setRankings(data.rankings); setSnapshotId(data.snapshot_id); })
      .catch(() => setError('Could not scan all assets. Try again.')).finally(() => setRanking(false));
  };
  const share = async () => {
    if (!bestResult) return;
    const text = `I spent ${dollars(bestResult.summary.total_spent)} across ${bestResult.summary.total_items} purchases.\nIf I had invested each amount in ${bestResult.asset.symbol} on the same dates, it could be worth ${dollars(bestResult.summary.current_value)} today.`;
    if (navigator.share) await navigator.share({ text }); else await navigator.clipboard.writeText(text);
  };

  return <div className="page-enter opportunity-page">
    <header className="screen-header opportunity-header"><p className="eyebrow">OPPORTUNITY COST</p><h1>What if you invested instead?</h1><p>See what your past purchases could be worth. <span>Each one uses its actual date.</span></p></header>
    {error && <p className="opportunity-error" role="alert">{error}</p>}

    <section className="opportunity-section opportunity-purchases-section">
      <div className="section-heading"><div><h2>Purchases</h2><p>Choose from the catalog or add your own.</p></div>{requestItems.length > 0 && <button className="text-button" onClick={startOver}><Trash2/> Start over</button>}</div>
      <button className="add-custom-button" onClick={() => openCustom()}><Plus/> Add custom purchase</button>
      <div className="chip-row" aria-label="Product categories"><button className={category === 'All' ? 'active' : ''} onClick={() => { setCategory('All'); setCatalogExpanded(false); }}>All</button>{categories.map((item) => <button className={category === item ? 'active' : ''} onClick={() => setCategory(item)} key={item}>{item}</button>)}</div>
      <div className="product-grid">{visibleProducts.map((product) => <button aria-pressed={Boolean(selected[product.id])} className={`product-card ${selected[product.id] ? 'selected' : ''}`} onClick={() => { changeCatalogQuantity(product.id, selected[product.id] ? -selected[product.id] : 1); resetResults(); }} key={product.id}><span className="product-placeholder">{product.image_url ? <img src={product.image_url} alt="" loading="lazy"/> : <Package/>}</span><span><strong>{product.model}</strong><small>{product.release_year} · {dollars(product.launch_price_usd)}</small></span><i>{selected[product.id] ? <Check/> : <Plus/>}</i></button>)}</div>
      {category === 'All' && categoryProducts.length > 8 && <button className="disclosure-button" aria-expanded={catalogExpanded} onClick={() => setCatalogExpanded((value) => !value)}>{catalogExpanded ? 'Show fewer products' : `Browse all ${categoryProducts.length} products`}<ChevronDown/></button>}
    </section>

    {requestItems.length === 0 ? <section className="opportunity-empty"><Sparkles/><h2>Start with something you bought</h2><p>Your exact spending timeline tells the story.</p></section> : <>
      <section className="opportunity-section selected-purchases"><div className="section-heading"><div><h2>My purchases</h2><p>{totalQuantity} purchases selected</p></div></div>
        {(showPurchases ? purchaseRows : purchaseRows.slice(0, PREVIEW_COUNT)).map((row) => row.type === 'catalog' ? <PurchaseRow key={row.product.id} name={row.product.model} detail={`${row.product.release_date.slice(0, 4)} · ${dollars(row.product.launch_price_usd)}`} quantity={selected[row.product.id]} onMinus={() => { changeCatalogQuantity(row.product.id, -1); resetResults(); }} onPlus={() => { changeCatalogQuantity(row.product.id, 1); resetResults(); }}/> : <PurchaseRow key={row.custom.id} name={row.custom.name} detail={`${row.custom.purchase_date} · ${dollars(row.custom.price_usd)}`} quantity={row.custom.quantity} custom onMinus={() => { changeCustomQuantity(row.custom.id, -1); resetResults(); }} onPlus={() => { changeCustomQuantity(row.custom.id, 1); resetResults(); }} onEdit={() => openCustom(row.custom)} onDelete={() => { setCustoms((current) => current.filter((item) => item.id !== row.custom.id)); resetResults(); }}/>) }
        {purchaseRows.length > PREVIEW_COUNT && <button className="disclosure-button" aria-expanded={showPurchases} onClick={() => setShowPurchases((value) => !value)}>{showPurchases ? 'Show fewer purchases' : `Show all ${purchaseRows.length} purchases`}<ChevronDown/></button>}
      </section>

      <section className="opportunity-section compare-selector"><div className="section-heading"><div><h2>Compare with</h2><p>Choose up to five investments.</p></div></div><div className="selected-assets">{selectedAssets.map((symbol) => <button aria-label={`Remove ${symbol}`} onClick={() => toggleAsset(symbol)} key={symbol}>{symbol}<X/></button>)}<button className="add-asset" aria-haspopup="dialog" onClick={() => { setAssetQuery(''); setAssetPicker(true); }}><Plus/> Add asset</button></div>{assetMessage && <p className="selection-message" role="alert">{assetMessage}</p>}<button className="button primary opportunity-calculate" disabled={loading} onClick={calculate}>Compare investments</button></section>
    </>}

    {loading && <section className="results-skeleton" aria-label="Calculating comparison" aria-busy="true"><span/><span/><span/></section>}
    {bestResult && !loading && <>
      <section className="opportunity-summary"><div className="hero-spent"><span>You spent</span><strong>{dollars(bestResult.summary.total_spent)}</strong><small>{bestResult.summary.total_items} dated purchases</small></div><div className="hero-result"><span>Best selected alternative</span><b>{bestResult.asset.symbol}</b><small>Could be worth</small><strong>{dollars(bestResult.summary.current_value)}</strong></div><div className="hero-performance"><b>{percent(bestResult.summary.return_pct)}</b><span>{money(bestResult.summary.gain, true)}</span><small>{bestResult.summary.eligible_items}/{bestResult.summary.total_items} eligible</small></div><button className="hero-share" onClick={share}><Share2/> Share</button></section>

      <section className="opportunity-section manual-comparison"><div className="section-heading"><div><p className="eyebrow">RESULTS</p><h2>Selected alternatives</h2></div></div><div className="comparison-grid">{results.map((result, index) => <button aria-label={`${index + 1}. ${result.asset.symbol}`} className={`comparison-card ${index === 0 ? 'best' : ''} ${activeResult?.asset.symbol === result.asset.symbol ? 'active' : ''}`} onClick={() => setActiveAsset(result.asset.symbol)} key={result.asset.symbol}><span className="comparison-top"><i>#{index + 1}</i><AssetMark symbol={result.asset.symbol}/><strong>{result.asset.symbol}</strong>{index === 0 && <em>Best</em>}</span><b>{dollars(result.summary.current_value)}</b><span className="comparison-return">{percent(result.summary.return_pct)} return</span><small>{result.summary.eligible_items}/{result.summary.total_items} eligible · {units(result.summary.investment_units, result.asset.symbol)}</small><span className="value-bar" aria-hidden="true"><i style={{ width: `${Math.max(3, Number(result.summary.current_value) / Number(bestResult.summary.current_value) * 100)}%` }}/></span></button>)}</div></section>

      {activeResult && <section className="opportunity-section timeline-section"><div className="detail-selector"><div><h2>Detailed breakdown</h2><p>One purchase at a time.</p></div><select aria-label="Detailed breakdown asset" value={activeResult.asset.symbol} onChange={(event) => setActiveAsset(event.target.value)}>{results.map((result) => <option key={result.asset.symbol}>{result.asset.symbol}</option>)}</select></div>{(showTimeline ? activeResult.items : activeResult.items.slice(0, PREVIEW_COUNT)).map((item) => <article className={`opportunity-item ${item.eligible ? '' : 'unavailable'}`} key={item.product.id}><div><strong>{item.product.model}{item.quantity > 1 && ` × ${item.quantity}`}{item.product.custom && <em className="custom-badge">Custom</em>}</strong><small>{item.product.custom ? 'Purchased' : 'Released'} {new Date(`${item.requested_date}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })} · {dollars(item.cost)}</small></div>{item.eligible ? <dl><div><dt>{activeResult.asset.symbol} price then</dt><dd>{dollars(item.asset_price!)}</dd></div><div><dt>{activeResult.asset.symbol} acquired</dt><dd>{units(item.units, activeResult.asset.symbol)}</dd></div><div><dt>Value today</dt><dd>{dollars(item.current_value)}</dd></div><div className="opportunity-gain"><dt>Opportunity cost</dt><dd>{money(item.gain!, true)}</dd></div></dl> : <p>{item.reason === 'Not available at that time' ? 'This asset was not trading yet or price history is unavailable.' : item.reason}</p>}</article>)}{activeResult.items.length > PREVIEW_COUNT && <button className="disclosure-button" aria-expanded={showTimeline} onClick={() => setShowTimeline((value) => !value)}>{showTimeline ? 'Show fewer purchases' : `Show all ${activeResult.items.length} purchases`}<ChevronDown/></button>}</section>}

      <section className="opportunity-section insights"><p className="eyebrow">INSIGHTS</p><div className="insight-row"><Sparkles/><span><strong>{bestResult.asset.symbol}</strong> performed best among your selected assets.</span></div><div className="insight-row"><Sparkles/><span>Your spending history could be worth <strong>{dollars(bestResult.summary.current_value)}</strong>.</span></div>{activeResult && <div className="insight-row"><Sparkles/><span><strong>{[...activeResult.items].filter((item) => item.eligible).sort((a,b) => Number(b.gain)-Number(a.gain))[0]?.product.model}</strong> had the largest opportunity cost.</span></div>}</section>

      <section className="opportunity-section best-alternative"><div className="section-heading"><div><h2>Best Alternative</h2><p>See how every supported asset compares.</p></div>{rankings.length === 0 && <button className="scan-button" disabled={ranking} onClick={compareAll}>Scan all assets</button>}</div>{ranking && <div className="ranking-skeleton" aria-label="Scanning all assets" aria-busy="true"><span/><span/><span/></div>}{(showRankings ? rankings : rankings.slice(0, 5)).map((row, index) => <div className="ranking-row" key={row.asset.symbol}><b>{index + 1}</b><AssetMark symbol={row.asset.symbol}/><span><strong>{row.asset.symbol}</strong><small>{row.summary.eligible_items}/{row.summary.total_items} eligible · {percent(row.summary.return_pct)}</small></span><strong>{dollars(row.summary.current_value)}</strong></div>)}{rankings.length > 5 && <button className="disclosure-button" aria-expanded={showRankings} onClick={() => setShowRankings((value) => !value)}>{showRankings ? 'Show top 5' : `Show all ${rankings.length} assets`}<ChevronDown/></button>}</section>
    </>}
    <p className="disclaimer">Hypothetical historical comparison for educational purposes only. Past performance does not guarantee future results.</p>

    {assetPicker && <div className="sheet-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setAssetPicker(false)}><section className="picker-sheet" role="dialog" aria-modal="true" aria-labelledby="asset-picker-title"><div className="sheet-handle"/><div className="sheet-header"><div><p className="eyebrow">COMPARE WITH</p><h2 id="asset-picker-title">Choose assets</h2></div><button aria-label="Close asset picker" onClick={() => setAssetPicker(false)}><X/></button></div><label className="asset-search"><Search/><span className="sr-only">Search assets</span><input autoFocus aria-label="Search assets" value={assetQuery} onChange={(event) => setAssetQuery(event.target.value)} placeholder="Search BTC, NVDA, Gold…"/></label><p className="picker-count">{selectedAssets.length} of {MAX_ASSETS} selected{selectedAssets.length === MAX_ASSETS && ' · Maximum reached'}</p><div className="asset-choice-list">{matchingAssets.map((asset) => { const chosenAsset = selectedAssets.includes(asset.symbol); const disabled = selectedAssets.length === MAX_ASSETS && !chosenAsset; return <button aria-pressed={chosenAsset} disabled={disabled} onClick={() => toggleAsset(asset.symbol)} key={asset.symbol}><AssetMark symbol={asset.symbol} category={asset.category}/><span><strong>{asset.symbol}</strong><small>{asset.name}</small></span>{chosenAsset && <Check/>}</button>; })}{matchingAssets.length === 0 && <p>No matching assets</p>}</div><button className="button primary sheet-done" onClick={() => setAssetPicker(false)}>Done</button></section></div>}

    {showCustom && <div className="sheet-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setShowCustom(false)}><form className="picker-sheet custom-purchase-form" role="dialog" aria-modal="true" aria-labelledby="custom-purchase-title" onSubmit={saveCustom}><div className="sheet-handle"/><div className="sheet-header"><div><p className="eyebrow">{editingId ? 'EDIT PURCHASE' : 'NEW PURCHASE'}</p><h2 id="custom-purchase-title">{editingId ? 'Update the details' : 'Add something you bought'}</h2></div><button type="button" aria-label="Close custom purchase form" onClick={() => setShowCustom(false)}><X/></button></div><label htmlFor="custom-name">Name<input id="custom-name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Sony OLED TV"/></label><div className="custom-form-grid"><label htmlFor="custom-date">Purchase date<input id="custom-date" type="date" max={new Date().toISOString().slice(0, 10)} value={draft.purchase_date} onChange={(event) => setDraft({ ...draft, purchase_date: event.target.value })}/></label><label htmlFor="custom-price">Price USD<input id="custom-price" inputMode="decimal" value={draft.price_usd} onChange={(event) => setDraft({ ...draft, price_usd: event.target.value })} placeholder="1999.99"/></label></div><div className="custom-form-grid"><label htmlFor="custom-quantity">Quantity<input id="custom-quantity" type="number" inputMode="numeric" min="1" max="99" value={draft.quantity} onChange={(event) => setDraft({ ...draft, quantity: Number(event.target.value) })}/></label><label htmlFor="custom-category">Category<select id="custom-category" value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })}>{CUSTOM_CATEGORIES.map((item) => <option key={item}>{item}</option>)}</select></label></div>{formError && <p className="form-error" role="alert">{formError}</p>}<div className="sheet-actions"><button type="button" className="button secondary" onClick={() => setShowCustom(false)}>Cancel</button><button className="button primary" type="submit">{editingId ? 'Save changes' : 'Add purchase'}</button></div></form></div>}
  </div>;
}

function PurchaseRow({ name, detail, quantity, custom, onMinus, onPlus, onEdit, onDelete }: { name: string; detail: string; quantity: number; custom?: boolean; onMinus: () => void; onPlus: () => void; onEdit?: () => void; onDelete?: () => void }) {
  return <div className="purchase-row"><span><strong>{name}{custom && <em className="custom-badge">Custom</em>}</strong><small>{detail}</small></span>{onEdit && <button className="row-action" aria-label={`Edit ${name}`} onClick={onEdit}><Edit3/></button>}{onDelete && <button className="row-action delete" aria-label={`Delete ${name}`} onClick={onDelete}><Trash2/></button>}<span className="quantity-control"><button aria-label={`Remove one ${name}`} onClick={onMinus}><Minus/></button><b>{quantity}</b><button aria-label={`Add one ${name}`} onClick={onPlus}><Plus/></button></span></div>;
}
