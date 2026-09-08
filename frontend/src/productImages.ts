const image = (file: string) => `/product-thumbnails/${file}.svg`;

const PRODUCT_IMAGES: Record<string, string> = {
  ...Object.fromEntries(['iphone-6s', 'iphone-7', 'iphone-8', 'iphone-x', 'iphone-xs', 'iphone-11', 'iphone-12', 'iphone-13', 'iphone-14', 'iphone-15', 'iphone-16'].map((id) => [id, image('iphone')])),
  ...Object.fromEntries(['galaxy-s6', 'galaxy-s7', 'galaxy-s8', 'galaxy-s9', 'galaxy-s10', 'galaxy-s20', 'galaxy-s21', 'galaxy-s22', 'galaxy-s23', 'galaxy-s24'].map((id) => [id, image('galaxy')])),
  ...Object.fromEntries(['macbook-air-m1', 'macbook-pro-14-m1'].map((id) => [id, image('macbook')])),
  ...Object.fromEntries(['ipad-9', 'ipad-pro-11'].map((id) => [id, image('ipad')])),
  ...Object.fromEntries(['apple-watch-1', 'apple-watch-series-4', 'apple-watch-series-7', 'apple-watch-series-9'].map((id) => [id, image('watch')])),
  ...Object.fromEntries(['airpods-1', 'airpods-pro-1', 'airpods-3', 'airpods-pro-2'].map((id) => [id, image('airpods')])),
  'airpods-max': image('headphones'),
  ...Object.fromEntries(['playstation-4', 'playstation-4-pro', 'playstation-5', 'playstation-5-pro'].map((id) => [id, image('playstation')])),
  ...Object.fromEntries(['nintendo-switch', 'switch-lite', 'switch-oled'].map((id) => [id, image('switch')])),
  'dyson-supersonic': image('hair-dryer'),
  'dyson-airwrap': image('hair-styler'),
};

export function getProductImage(productId: string): string | undefined {
  return PRODUCT_IMAGES[productId];
}
