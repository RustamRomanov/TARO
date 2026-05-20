const riderWaiteFiles = import.meta.glob(
  '../assets/taro/Rider-Waite Tarot/*.{jpg,JPG,jpeg,JPEG,png,PNG,webp,WEBP}',
  { eager: true, import: 'default' }
);

const getFilename = (path) => path.split('/').pop() || '';

const getNumberPrefix = (filename) => {
  const match = filename.match(/^(\d+)/);
  return match ? Number(match[1]) : null;
};

const titleFromFilename = (filename, fallbackIndex) => {
  const base = filename.replace(/\.[^/.]+$/, '');
  if (/^img/i.test(base)) {
    return `Карта ${fallbackIndex + 1}`;
  }
  const cleaned = base
    .replace(/^\d+[_-]?/g, '')
    .replace(/[_-]+/g, ' ')
    .trim();
  return cleaned || `Карта ${fallbackIndex + 1}`;
};

const buildDeck = ({ id, name, description, files, backClass, color }) => {
  const entries = Object.entries(files);
  let backImageLoader = null;
  let deckImageLoader = null;
  const cards = [];

  const sorted = entries.sort(([a], [b]) => {
    const na = getNumberPrefix(getFilename(a));
    const nb = getNumberPrefix(getFilename(b));
    if (na !== null && nb !== null) return na - nb;
    if (na !== null) return -1;
    if (nb !== null) return 1;
    return a.localeCompare(b);
  });

  sorted.forEach(([path, loader], index) => {
    const filename = getFilename(path);
    if (/рубаш/i.test(filename)) {
      backImageLoader = typeof loader === 'function' ? loader : () => Promise.resolve(loader);
      return;
    }
    if (/колода/i.test(filename)) {
      deckImageLoader = typeof loader === 'function' ? loader : () => Promise.resolve(loader);
      return;
    }
    cards.push({
      id: filename,
      name: titleFromFilename(filename, index),
      imageLoader: typeof loader === 'function' ? loader : () => Promise.resolve(loader),
    });
  });

  return {
    id,
    name,
    description,
    cards,
    backImageLoader,
    deckImageLoader,
    backClass,
    color,
  };
};

export const tarotDecks = [
  buildDeck({
    id: 'rider_waite',
    name: 'Rider-Waite Tarot',
    description: 'Классическая колода Rider-Waite: базовые архетипы, ясная символика и проверенная традиция толкования.',
    files: riderWaiteFiles,
    backClass: 'tarot-back tarot-back--cosmic',
    color: '0b162e',
  }),
].filter((deck) => deck.cards.length > 0);
