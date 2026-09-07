"""Curated nominal-US-dollar launch catalog.

Dates and base-model MSRP values are intentionally kept in one reviewable file.
Source links point to manufacturer newsrooms/store announcements; products whose
US date and price could not be confidently established are omitted.
"""

from datetime import date
from decimal import Decimal

from backend.app.models.opportunity_cost import Product

APPLE = "https://www.apple.com/newsroom/archive/"
SAMSUNG = "https://news.samsung.com/us/category/product/mobile/"
PLAYSTATION = "https://blog.playstation.com/"
NINTENDO = "https://www.nintendo.com/us/whatsnew/"
DYSON = "https://www.dyson.com/discover/innovation/new-machines"


def _p(id: str, brand: str, category: str, family: str, model: str,
       released: str, price: str, source: str, order: int) -> Product:
    return Product(id, brand, category, family, model, date.fromisoformat(released),
                   Decimal(price), source, display_order=order)


PRODUCTS = tuple(
    _p(*row, order=index)
    for index, row in enumerate((
        ("iphone-6s", "Apple", "iPhone", "iPhone", "iPhone 6s", "2015-09-25", "649", APPLE),
        ("iphone-7", "Apple", "iPhone", "iPhone", "iPhone 7", "2016-09-16", "649", APPLE),
        ("iphone-8", "Apple", "iPhone", "iPhone", "iPhone 8", "2017-09-22", "699", APPLE),
        ("iphone-x", "Apple", "iPhone", "iPhone", "iPhone X", "2017-11-03", "999", APPLE),
        ("iphone-xs", "Apple", "iPhone", "iPhone", "iPhone XS", "2018-09-21", "999", APPLE),
        ("iphone-11", "Apple", "iPhone", "iPhone", "iPhone 11", "2019-09-20", "699", APPLE),
        ("iphone-12", "Apple", "iPhone", "iPhone", "iPhone 12", "2020-10-23", "799", APPLE),
        ("iphone-13", "Apple", "iPhone", "iPhone", "iPhone 13", "2021-09-24", "799", APPLE),
        ("iphone-14", "Apple", "iPhone", "iPhone", "iPhone 14", "2022-09-16", "799", APPLE),
        ("iphone-15", "Apple", "iPhone", "iPhone", "iPhone 15", "2023-09-22", "799", APPLE),
        ("iphone-16", "Apple", "iPhone", "iPhone", "iPhone 16", "2024-09-20", "799", APPLE),
        ("galaxy-s6", "Samsung", "Galaxy", "Galaxy S", "Galaxy S6", "2015-04-10", "599.99", SAMSUNG),
        ("galaxy-s7", "Samsung", "Galaxy", "Galaxy S", "Galaxy S7", "2016-03-11", "669.99", SAMSUNG),
        ("galaxy-s8", "Samsung", "Galaxy", "Galaxy S", "Galaxy S8", "2017-04-21", "749.99", SAMSUNG),
        ("galaxy-s9", "Samsung", "Galaxy", "Galaxy S", "Galaxy S9", "2018-03-16", "719.99", SAMSUNG),
        ("galaxy-s10", "Samsung", "Galaxy", "Galaxy S", "Galaxy S10", "2019-03-08", "899.99", SAMSUNG),
        ("galaxy-s20", "Samsung", "Galaxy", "Galaxy S", "Galaxy S20", "2020-03-06", "999.99", SAMSUNG),
        ("galaxy-s21", "Samsung", "Galaxy", "Galaxy S", "Galaxy S21", "2021-01-29", "799.99", SAMSUNG),
        ("galaxy-s22", "Samsung", "Galaxy", "Galaxy S", "Galaxy S22", "2022-02-25", "799.99", SAMSUNG),
        ("galaxy-s23", "Samsung", "Galaxy", "Galaxy S", "Galaxy S23", "2023-02-17", "799.99", SAMSUNG),
        ("galaxy-s24", "Samsung", "Galaxy", "Galaxy S", "Galaxy S24", "2024-01-31", "799.99", SAMSUNG),
        ("macbook-air-m1", "Apple", "Mac", "MacBook Air", "MacBook Air (M1)", "2020-11-17", "999", APPLE),
        ("macbook-pro-14-m1", "Apple", "Mac", "MacBook Pro", "MacBook Pro 14-inch (M1 Pro)", "2021-10-26", "1999", APPLE),
        ("ipad-9", "Apple", "iPad", "iPad", "iPad (9th generation)", "2021-09-24", "329", APPLE),
        ("ipad-pro-11", "Apple", "iPad", "iPad Pro", "iPad Pro 11-inch", "2018-11-07", "799", APPLE),
        ("apple-watch-1", "Apple", "Watch", "Apple Watch", "Apple Watch", "2015-04-24", "349", APPLE),
        ("apple-watch-series-4", "Apple", "Watch", "Apple Watch", "Apple Watch Series 4", "2018-09-21", "399", APPLE),
        ("apple-watch-series-7", "Apple", "Watch", "Apple Watch", "Apple Watch Series 7", "2021-10-15", "399", APPLE),
        ("apple-watch-series-9", "Apple", "Watch", "Apple Watch", "Apple Watch Series 9", "2023-09-22", "399", APPLE),
        ("airpods-1", "Apple", "AirPods", "AirPods", "AirPods (1st generation)", "2016-12-13", "159", APPLE),
        ("airpods-pro-1", "Apple", "AirPods", "AirPods Pro", "AirPods Pro", "2019-10-30", "249", APPLE),
        ("airpods-max", "Apple", "AirPods", "AirPods", "AirPods Max", "2020-12-15", "549", APPLE),
        ("airpods-3", "Apple", "AirPods", "AirPods", "AirPods (3rd generation)", "2021-10-26", "179", APPLE),
        ("airpods-pro-2", "Apple", "AirPods", "AirPods Pro", "AirPods Pro (2nd generation)", "2022-09-23", "249", APPLE),
        ("playstation-4", "Sony", "PlayStation", "PlayStation", "PlayStation 4", "2013-11-15", "399", PLAYSTATION),
        ("playstation-4-pro", "Sony", "PlayStation", "PlayStation", "PlayStation 4 Pro", "2016-11-10", "399", PLAYSTATION),
        ("playstation-5", "Sony", "PlayStation", "PlayStation", "PlayStation 5", "2020-11-12", "499.99", PLAYSTATION),
        ("playstation-5-pro", "Sony", "PlayStation", "PlayStation", "PlayStation 5 Pro", "2024-11-07", "699.99", PLAYSTATION),
        ("nintendo-switch", "Nintendo", "Nintendo", "Switch", "Nintendo Switch", "2017-03-03", "299.99", NINTENDO),
        ("switch-lite", "Nintendo", "Nintendo", "Switch", "Nintendo Switch Lite", "2019-09-20", "199.99", NINTENDO),
        ("switch-oled", "Nintendo", "Nintendo", "Switch", "Nintendo Switch – OLED Model", "2021-10-08", "349.99", NINTENDO),
        ("dyson-supersonic", "Dyson", "Dyson", "Hair care", "Dyson Supersonic", "2016-09-01", "399.99", DYSON),
        ("dyson-airwrap", "Dyson", "Dyson", "Hair care", "Dyson Airwrap", "2018-10-10", "499.99", DYSON),
    ))
)

PRODUCT_BY_ID = {product.id: product for product in PRODUCTS}
