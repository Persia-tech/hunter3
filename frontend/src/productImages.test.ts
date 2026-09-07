import { describe, expect, it } from 'vitest';

import { getProductImage } from './productImages';

describe('product image catalog', () => {
  it.each([
    ['iphone-16', 'iphone'],
    ['galaxy-s24', 'galaxy'],
    ['macbook-air-m1', 'macbook'],
    ['ipad-pro-11', 'ipad'],
    ['apple-watch-series-9', 'watch'],
    ['airpods-pro-2', 'airpods'],
    ['airpods-max', 'headphones'],
    ['playstation-5', 'playstation'],
    ['switch-oled', 'switch'],
    ['dyson-supersonic', 'hair-dryer'],
    ['dyson-airwrap', 'hair-styler'],
  ])('maps %s to a local %s thumbnail', (productId, family) => {
    expect(getProductImage(productId)).toBe(`/product-thumbnails/${family}.svg`);
  });

  it('allows the catalog row to use its fallback for an unknown product', () => {
    expect(getProductImage('unknown-product')).toBeUndefined();
  });
});
