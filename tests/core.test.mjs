import test from 'node:test';
import assert from 'node:assert/strict';
import {matches, cellText, route, href, pageChunks} from '../assets/core.js';
test('search: Cyrillic, exact, fields, NULL and binary',()=>{
  assert(matches(['Ледяная корона','123'], 'КОРОНА'));
  assert(!matches(['Ледяная корона','123'], 'корона',0,true));
  assert(matches(['Ледяная корона','123'], '123',1,true));
  assert(!matches(['Ледяная корона','123'], '123',0));
  assert(matches([null], 'null',0,true));
  assert(matches([{$binary:'00ab'}], '0x00ab',0,true));
  assert.equal(cellText('9007199254740993'),'9007199254740993');
});
test('routes: project Pages, encoded names, malformed input',()=>{
  assert.deepEqual(route('#world/quest_template'),['world','quest_template']);
  assert.deepEqual(route('#'),[]);
  assert.deepEqual(route('#%ZZ'),['invalid','invalid']);
  assert.deepEqual(route('#a/b/c'),['invalid','invalid']);
  assert.deepEqual(route(href('world','one two')),['world','one two']);
});
test('page intersects variable byte-sized chunks',()=>{
  const chunks=[{start:0,rows:30},{start:30,rows:40},{start:70,rows:25}];
  assert.deepEqual(pageChunks(chunks,50,95).map(c=>c.index),[1,2]);
  assert.deepEqual(pageChunks(chunks,0,30).map(c=>c.index),[0]);
});
