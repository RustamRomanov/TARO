/** Убирает длинное/короткое тире Unicode в пользовательском тексте (правило UI). */
export function stripUnicodeLongDash(text) {
  if (text == null || text === '') return '';
  return String(text).replace(/\u2014/g, ': ').replace(/\u2013/g, '-');
}
