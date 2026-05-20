"""Отображение субъектов РФ на русском: в БД GeoNames остаётся английская admin1_name, здесь только подписи и обратный поиск."""

from __future__ import annotations

# Точные ключи как в city_catalog (admin1CodesASCII / GeoNames)
RU_ADMIN1_GEO_TO_RU: dict[str, str] = {
    "Adygeya Republic": "Республика Адыгея",
    "Altai": "Республика Алтай",
    "Altai Krai": "Алтайский край",
    "Amur Oblast": "Амурская область",
    "Arkhangelskaya": "Архангельская область",
    "Astrakhan Oblast": "Астраханская область",
    "Bashkortostan Republic": "Республика Башкортостан",
    "Belgorod Oblast": "Белгородская область",
    "Bryansk Oblast": "Брянская область",
    "Buryatiya Republic": "Республика Бурятия",
    "Chechnya": "Чеченская Республика",
    "Chelyabinsk": "Челябинская область",
    "Chukotka": "Чукотский автономный округ",
    "Chuvash Republic": "Чувашская Республика",
    "Dagestan": "Республика Дагестан",
    "Ingushetiya Republic": "Республика Ингушетия",
    "Irkutsk Oblast": "Иркутская область",
    "Ivanovo Oblast": "Ивановская область",
    "Jewish Autonomous Oblast": "Еврейская автономная область",
    "Kabardino-Balkariya Republic": "Кабардино-Балкарская Республика",
    "Kaliningrad Oblast": "Калининградская область",
    "Kalmykiya Republic": "Республика Калмыкия",
    "Kaluga Oblast": "Калужская область",
    "Kamchatka": "Камчатский край",
    "Karachayevo-Cherkesiya Republic": "Карачаево-Черкесская Республика",
    "Karelia": "Республика Карелия",
    "Khabarovsk": "Хабаровский край",
    "Khakasiya Republic": "Республика Хакасия",
    "Khanty-Mansia": "Ханты-Мансийский автономный округ",
    "Kirov Oblast": "Кировская область",
    "Komi": "Республика Коми",
    "Kostroma Oblast": "Костромская область",
    "Krasnodar Krai": "Краснодарский край",
    "Krasnoyarsk Krai": "Красноярский край",
    "Kurgan Oblast": "Курганская область",
    "Kursk Oblast": "Курская область",
    "Kuzbass": "Кемеровская область",
    "Leningradskaya Oblast'": "Ленинградская область",
    "Lipetsk Oblast": "Липецкая область",
    "Magadan Oblast": "Магаданская область",
    "Mariy-El Republic": "Республика Марий Эл",
    "Mordoviya Republic": "Республика Мордовия",
    "Moscow": "Москва",
    "Moscow Oblast": "Московская область",
    "Murmansk": "Мурманская область",
    "Nenets": "Ненецкий автономный округ",
    "Nizhny Novgorod Oblast": "Нижегородская область",
    "North Ossetia–Alania": "Республика Северная Осетия - Алания",
    "Novgorod Oblast": "Новгородская область",
    "Novosibirsk Oblast": "Новосибирская область",
    "Omsk Oblast": "Омская область",
    "Orenburg Oblast": "Оренбургская область",
    "Oryol oblast": "Орловская область",
    "Penza Oblast": "Пензенская область",
    "Perm Krai": "Пермский край",
    "Primorye": "Приморский край",
    "Pskov Oblast": "Псковская область",
    "Republic of Tyva": "Республика Тыва",
    "Rostov": "Ростовская область",
    "Ryazan Oblast": "Рязанская область",
    "Sakha": "Республика Саха (Якутия)",
    "Sakhalin Oblast": "Сахалинская область",
    "Samara Oblast": "Самарская область",
    "Saratov Oblast": "Саратовская область",
    "Smolensk Oblast": "Смоленская область",
    "St.-Petersburg": "Санкт-Петербург",
    "Stavropol Kray": "Ставропольский край",
    "Sverdlovsk Oblast": "Свердловская область",
    "Tambov Oblast": "Тамбовская область",
    "Tatarstan Republic": "Республика Татарстан",
    "Tomsk Oblast": "Томская область",
    "Tula Oblast": "Тульская область",
    "Tver Oblast": "Тверская область",
    "Tyumen Oblast": "Тюменская область",
    "Udmurtiya Republic": "Удмуртская Республика",
    "Ulyanovsk": "Ульяновская область",
    "Vladimir Oblast": "Владимирская область",
    "Volgograd Oblast": "Волгоградская область",
    "Vologda Oblast": "Вологодская область",
    "Voronezh Oblast": "Воронежская область",
    "Yamalo-Nenets": "Ямало-Ненецкий автономный округ",
    "Yaroslavl Oblast": "Ярославская область",
    "Zabaykalskiy (Transbaikal) Kray": "Забайкальский край",
}

_RU_TO_GEO: dict[str, str] = {v.strip(): k for k, v in RU_ADMIN1_GEO_TO_RU.items()}


def ru_admin1_label_for_catalog(geo_name: str) -> str:
    """Подпись региона для РФ: русское название или исходная строка."""
    g = (geo_name or "").strip()
    if not g:
        return ""
    return RU_ADMIN1_GEO_TO_RU.get(g, g)


def ru_admin1_geo_filter_value(region_from_client: str) -> str:
    """Значение для SQL admin1_name: из русской подписи в ключ каталога (англ. GeoNames)."""
    s = (region_from_client or "").strip()
    if not s:
        return ""
    if s in RU_ADMIN1_GEO_TO_RU:
        return s
    return _RU_TO_GEO.get(s, s)
