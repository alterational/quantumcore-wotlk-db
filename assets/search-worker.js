import {getJSON, matches, SEARCH_LIMIT} from './core.js';
// One chunk at a time; termination cancels a search, including in-flight fetches.
self.onmessage = async ({data}) => {
  const {base, chunks, query, column, exact} = data;
  let scanned = 0, found = 0;
  try {
    for (const chunk of chunks) {
      const rows = await getJSON(`${base}/${chunk.file}`);
      const batch = [];
      for (let i = 0; i < rows.length; i++) {
        scanned++;
        if (matches(rows[i], query, column, exact)) {
          batch.push({index: chunk.start + i, row: rows[i]});
          found++;
          if (found === SEARCH_LIMIT) {
            self.postMessage({batch, scanned, done: true, limited: true});
            return;
          }
        }
      }
      self.postMessage({batch, scanned, done: false});
    }
    self.postMessage({batch: [], scanned, done: true, limited: false});
  } catch (error) { self.postMessage({error: error.message}); }
};
