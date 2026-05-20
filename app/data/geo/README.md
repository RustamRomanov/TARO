# City Catalog

This folder stores an optional offline city catalog for fast and stable geocoding in profiles.

## Files

- `city_catalog.sqlite3.gz`: committed compressed catalog.
- `city_catalog.sqlite3`: unpacked automatically at runtime if missing.

## Build source

Use GeoNames dump:

- `allCountries.zip` (extract `allCountries.txt`)
- `admin1CodesASCII.txt`

Build command examples:

```bash
python scripts/build_city_catalog.py --input data/geonames/allCountries.txt --scope post-soviet
python scripts/build_city_catalog.py --input data/geonames/allCountries.txt --scope world
```

When the catalog exists, backend city search and city-to-coordinates resolution use it before Nominatim.
