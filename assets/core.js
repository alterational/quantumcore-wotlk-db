export const PAGE_SIZE = 50;
export const SEARCH_LIMIT = 200;
export function cellText(value) {
  if (value === null) return 'NULL';
  if (typeof value === 'object') return value?.$binary !== undefined ? `0x${value.$binary}` : JSON.stringify(value);
  return String(value);
}
export function matches(row, query, column = -1, exact = false) {
  const q = query.toLocaleLowerCase('ru');
  const values = column < 0 ? row : [row[column]];
  return values.some(value => {
    const text = cellText(value).toLocaleLowerCase('ru');
    return exact ? text === q : text.includes(q);
  });
}
export function route(hash) {
  try {
    const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
    return parts.length <= 2 ? parts : ['invalid', 'invalid'];
  } catch { return ['invalid', 'invalid']; }
}
export function href(db, table) { return '#' + [db, table].filter(x => x !== undefined).map(encodeURIComponent).join('/'); }
export function pageChunks(chunks, start, end) {
  return chunks.map((chunk, index) => ({...chunk, index})).filter(c => c.start < end && c.start + c.rows > start);
}
export async function getJSON(url, signal) {
  const response = await fetch(url, {signal});
  if (!response.ok) throw new Error(`Не удалось загрузить ${url} (HTTP ${response.status}).`);
  return response.json();
}
