import {PAGE_SIZE, SEARCH_LIMIT, cellText, route, href, getJSON, pageChunks} from './core.js';
const main = document.querySelector('#main');
const nf = new Intl.NumberFormat('ru');
const number = n => nf.format(n);
const labels = {world:'Игровой мир, задания, существа и предметы',characters:'Персонажи, инвентарь и игровой прогресс',realmd:'Авторизация и реалмы · раздел auth в этом архиве',mysql:'Служебные таблицы исходного MySQL'};
let catalog, controller, worker, renderId = 0;
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value !== false && value != null) node.setAttribute(key, value === true ? '' : value);
  }
  node.append(...children.filter(c => c !== null && c !== undefined));
  return node;
}
function notice(text, error = false) { return el('div', {class:`notice${error ? ' error' : ''}`, role:error ? 'alert' : 'note'}, text); }
function crumbs(db, table) {
  const nav = el('nav', {class:'crumbs','aria-label':'Путь'}, el('a',{href:'#'},'Все базы'));
  if (db) nav.append(' / ', el('a',{href:href(db)}, db));
  if (table) nav.append(' / ', el('span',{'aria-current':'page'},table));
  return nav;
}
function stopSearch() { worker?.terminate(); worker = null; }
function fail(error) { if (error.name !== 'AbortError') main.append(notice(error.message + ' Проверьте подключение и обновите страницу.', true)); }
function stat(value, label) { return el('div',{class:'stat'},el('strong',{},number(value)),el('span',{},label)); }
function badge(table) {
  return el('span',{class:`pill${table.status === 'ok' ? '' : ' warn'}`},table.status === 'ok' ? (table.rows ? 'Доступна' : 'Пустая') : 'Неполная');
}
function catalogTable(tables, container) {
  let page = 0, filtered = tables;
  const input = el('input',{type:'search',placeholder:'Например: spell, loot, account…','aria-label':'Поиск таблиц'});
  const content = el('div');
  function paint() {
    const body = el('tbody');
    for (const t of filtered.slice(page * PAGE_SIZE,(page + 1) * PAGE_SIZE)) {
      body.append(el('tr',{}, el('td',{},el('a',{href:href(t.database,t.name),class:'mono'},t.name)),el('td',{},t.database),el('td',{}, t.status === 'ok' ? number(t.rows) : 'Нет данных'),el('td',{},badge(t))));
    }
    content.replaceChildren(el('div',{class:'table-box'},el('table',{},el('thead',{},el('tr',{},...['Таблица','База','Строк','Состояние'].map(x=>el('th',{scope:'col'},x)))),body)));
    if (!filtered.length) content.append(el('p',{class:'empty'},'Таблицы не найдены. Попробуйте другое название.'));
    content.append(pager(page, filtered.length, p=>{page=p;paint();}, 'таблиц'));
  }
  input.addEventListener('input',()=>{filtered=tables.filter(t=>`${t.database}.${t.name}`.toLowerCase().includes(input.value.trim().toLowerCase()));page=0;paint();});
  container.append(el('label',{class:'field toolbar'},'Фильтр по названию таблицы',input),content);paint();
}
function pager(page, total, onPage, noun = 'строк') {
  const pages = Math.max(1,Math.ceil(total / PAGE_SIZE));
  return el('div',{class:'pager'},el('span',{class:'summary'},total ? `${number(page*PAGE_SIZE+1)}–${number(Math.min(total,(page+1)*PAGE_SIZE))} из ${number(total)} ${noun}` : `0 ${noun}`),
    el('button',{disabled:page===0,onclick:()=>onPage(0),'aria-label':'Первая страница'},'«'),
    el('button',{disabled:page===0,onclick:()=>onPage(page-1)},'Назад'),
    el('span',{},`${page+1} / ${pages}`),
    el('button',{disabled:page>=pages-1,onclick:()=>onPage(page+1)},'Далее'),
    el('button',{disabled:page>=pages-1,onclick:()=>onPage(pages-1),'aria-label':'Последняя страница'},'»'));
}
function home() {
  main.append(crumbs(),el('p',{class:'eyebrow'},'Архив / 01'),el('h1',{},'База знаний игрового мира'),el('p',{class:'lead'},'Исходные таблицы QuantumCore WotLK в одном месте. Открывайте разделы, изучайте структуру и ищите по данным. Только просмотр — ничего не изменяется.'),
    el('div',{class:'stats'},stat(catalog.databases.length,'базы данных'),stat(catalog.tables,'таблиц в архиве'),stat(catalog.rows,'восстановленных строк')));
  if (catalog.incomplete) main.append(notice(`Архив неполный: ${catalog.incomplete} таблиц без доступных строк. Их структура и причины потери показаны отдельно. Это не пустые таблицы.`));
  const grid=el('div',{class:'grid'});
  for (const [i,db] of catalog.databases.entries()) grid.append(el('a',{class:'card',href:href(db.name)},el('div',{class:'tag'},`0${i+1} / DATABASE`),el('h2',{},db.name),el('p',{},labels[db.name]||'Дополнительный раздел архива'),el('div',{class:'count'},el('span',{},`${db.tables.length} таблиц`),el('span',{},`${number(db.rows)} строк →`))));
  main.append(grid,el('div',{class:'section-head'},el('h2',{},'Каталог таблиц'),el('span',{},el('a',{href:'data/quantumcore-mysql55.sql.gz',download:''},'SQL-дамп ↓'),' · ',el('a',{href:'docs/recovery-report.md'},'Отчёт восстановления ↗'))));
  catalogTable(catalog.databases.flatMap(db=>db.tables.map(t=>({...t,database:db.name}))),main);
}
function database(db) {
  main.append(crumbs(db.name),el('p',{class:'eyebrow'},'Раздел базы данных'),el('h1',{},db.name),el('p',{class:'lead'},labels[db.name]||'Таблицы исходного архива'),el('div',{class:'stats'},stat(db.tables.length,'таблиц'),stat(db.rows,'доступных строк')));
  if(db.name === 'mysql') main.append(notice('Это исторические служебные таблицы, а не учётные записи сайта. Не импортируйте их поверх системной базы современной MySQL/MariaDB.'));
  catalogTable(db.tables.map(t=>({...t,database:db.name})),main);
}
function cellDialog(title, value) {
  const dialog = el('dialog',{},el('div',{class:'dialog-head'},el('h2',{},title),el('button',{onclick:()=>dialog.close(),'aria-label':'Закрыть'},'Закрыть')),el('pre',{},cellText(value)));
  document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();
}
async function tableView(db, table, signal, id) {
  main.append(crumbs(db.name,table.name),el('p',{class:'eyebrow'},`${db.name} / Таблица`),el('h1',{},table.name),el('p',{class:'muted'},`${table.engine || 'MyISAM'} · ${table.status === 'ok' ? number(table.rows)+' строк' : 'Строки недоступны'} · Только чтение`));
  const base=`data/${encodeURIComponent(db.name)}/${encodeURIComponent(table.name)}`;
  const meta=await getJSON(`${base}/meta.json`,signal);
  if (id !== renderId) return;
  if(table.status !== 'ok') main.append(notice(meta.warning || 'Исходные файлы отсутствуют. Восстановление строк невозможно.'));
  const schema=el('details',{},el('summary',{},`Структура таблицы · ${meta.columns.length} полей`));
  let schemaDrawn=false;
  schema.addEventListener('toggle',()=>{
    if (!schema.open || schemaDrawn) return;schemaDrawn=true;
    const body=el('tbody');
    meta.columns.forEach(c=>body.append(el('tr',{},...[c.name,c.type,c.nullable?'Да':'Нет',cellText(c.default),c.key,c.extra].map(x=>el('td',{},x)))));
    schema.append(el('div',{class:'table-box'},el('table',{},el('thead',{},el('tr',{},...['Поле','Тип','NULL','По умолчанию','Ключ','Дополнительно'].map(x=>el('th',{scope:'col'},x)))),body)),el('h3',{},'Исходный CREATE TABLE'),el('pre',{},meta.ddl || 'Схема недоступна'));
  });main.append(schema);
  if(table.status !== 'ok') return;
  if(!table.rows){main.append(el('div',{class:'empty'},'Таблица существует и проверена, но в исходном архиве не содержит строк.'));return;}
  const query=el('input',{type:'search',maxlength:'300',placeholder:'Введите значение или фрагмент текста…',name:'query'});
  const select=el('select',{'aria-label':'Поле поиска'},el('option',{value:'-1'},'Все поля'));
  meta.columns.forEach((c,i)=>select.append(el('option',{value:i},c.name)));
  const exact=el('input',{type:'checkbox'});
  const submit=el('button',{class:'primary',type:'submit'},'Найти');
  const cancel=el('button',{type:'button',disabled:true},'Остановить');
  const reset=el('button',{type:'button'},'Сбросить');
  const status=el('p',{class:'status',role:'status','aria-live':'polite'});
  const result=el('div');
  let page=0, results=null, searchRunning=false, scanned=0, partial=false, pageLoad=0;
  const cache = new Map();
  let fetchController=null;
  signal.addEventListener('abort',()=>fetchController?.abort(),{once:true});
  async function loadChunk(chunk,chunkSignal) {
    if(cache.has(chunk.file))return cache.get(chunk.file);
    const rows=await getJSON(`${base}/${chunk.file}`,chunkSignal);
    cache.set(chunk.file,rows);if(cache.size>3)cache.delete(cache.keys().next().value);
    return rows;
  }
  function drawRows(items,total) {
    const tbody=el('tbody');
    for (const {row,index} of items) {
      const tr=el('tr',{},el('td',{class:'number'},number(index+1)));
      row.forEach((v,i)=>{
        const text=cellText(v);
        const td=el('td',{class:v===null?'null':''});
        if(text.length>100 || text.includes('\n')) td.append(el('button',{class:'cell-open',title:'Открыть полное значение',onclick:()=>cellDialog(meta.columns[i].name,v)},text.slice(0,100)+(text.length>100?'…':'')));
        else td.textContent=text;
        tr.append(td);
      });tbody.append(tr);
    }
    result.replaceChildren(el('div',{class:'table-box',tabindex:'0','aria-label':'Данные таблицы, горизонтальная прокрутка'},el('table',{class:'data-table'},el('thead',{},el('tr',{},el('th',{scope:'col'},'№'),...meta.columns.map(c=>el('th',{scope:'col',title:c.type},c.name)))),tbody)),pager(page,total,p=>{page=p;renderRows();}));
    if(!total) result.prepend(el('p',{class:'empty'},searchRunning?'Поиск…':'Совпадений нет.'));
  }
  async function renderRows() {
    const load=++pageLoad;
    fetchController?.abort();fetchController=new AbortController();
    if (results !== null) {drawRows(results.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE),results.length);return;}
    status.textContent='Загрузка страницы…';
    try {
      const start=page*PAGE_SIZE,end=Math.min(table.rows,start+PAGE_SIZE),items=[];
      for(const chunk of pageChunks(meta.chunks,start,end)) {
        const rows=await loadChunk(chunk,fetchController.signal);
        rows.forEach((row,i)=>{const index=chunk.start+i;if(index>=start && index<end)items.push({row,index});});
      }
      if(load!==pageLoad || signal.aborted)return;
      drawRows(items,table.rows);status.textContent='Показаны исходные значения. Длинные ячейки можно открыть нажатием.';
    }catch(error){if(error.name!=='AbortError' && load===pageLoad)status.textContent=`Ошибка загрузки: ${error.message} Нажмите «Сбросить», чтобы повторить.`;}
  }
  function searchStatus(done=false) {
    status.textContent=`Найдено: ${number(results.length)}. Проверено ${number(scanned)} из ${number(table.rows)} строк.`+(partial?` Показаны первые ${SEARCH_LIMIT} совпадений — уточните запрос.`:done?' Поиск завершён.':' Поиск…');
  }
  const form=el('form',{class:'toolbar'},el('label',{class:'field grow'},'Поиск по всей таблице',query),el('label',{class:'field'},'Поле',select),el('label',{class:'check'},exact,'Точное совпадение'),submit,cancel,reset);
  cancel.addEventListener('click',()=>{stopSearch();searchRunning=false;cancel.disabled=true;status.textContent=`Поиск остановлен. Проверено ${number(scanned)} из ${number(table.rows)} строк; результатов: ${results.length}. Это неполная выборка.`;});
  reset.addEventListener('click',()=>{stopSearch();searchRunning=false;cancel.disabled=true;query.value='';results=null;page=0;renderRows();});
  form.addEventListener('submit',event=>{
    event.preventDefault();if(!query.value.trim()){reset.click();return;}
    stopSearch();fetchController?.abort();pageLoad++;results=[];page=0;scanned=0;partial=false;searchRunning=true;cancel.disabled=false;
    worker=new Worker(new URL('./search-worker.js',import.meta.url),{type:'module'});
    worker.onmessage=({data})=>{
      if(signal.aborted)return;
      if(data.error){searchRunning=false;cancel.disabled=true;status.textContent=`Ошибка поиска: ${data.error} Результаты неполные. Повторите поиск.`;stopSearch();return;}
      const had=results.length;results.push(...data.batch);scanned=data.scanned;partial=data.limited || false;
      if(data.done){searchRunning=false;cancel.disabled=true;stopSearch();}
      searchStatus(data.done);
      if(results.length!==had || data.done)renderRows();
    };
    worker.onerror=()=>{searchRunning=false;cancel.disabled=true;status.textContent='Не удалось запустить поиск. Повторите или обновите страницу.';stopSearch();};
    worker.postMessage({base:new URL(`${base}`,document.baseURI).href,chunks:meta.chunks,query:query.value.trim(),column:Number(select.value),exact:exact.checked});
    searchStatus();renderRows();
  });
  main.append(form,el('p',{class:'muted',style:'font-size:12px'},`Поиск выполняется на устройстве по выбранной таблице, без учёта регистра. Загружает её частями, до ${SEARCH_LIMIT} совпадений. Для экономии трафика уточняйте поле и значение.`),status,result);
  await renderRows();
}
async function render() {
  const id=++renderId;controller?.abort();controller=new AbortController();stopSearch();
  const signal=controller.signal;main.replaceChildren();
  const parts=route(location.hash);
  document.title=(parts.at(-1)?parts.at(-1)+' — ':'')+'QuantumCore · Архив';
  try {
    if(!parts.length){home();return;}
    const db=catalog.databases.find(d=>d.name===parts[0]);
    const table=db?.tables.find(t=>t.name===parts[1]);
    if(!db || (parts.length>1 && !table)){main.append(crumbs(),el('h1',{},'Раздел не найден'),el('a',{href:'#'},'Вернуться ко всем базам'));return;}
    if(table)await tableView(db,table,signal,id);else database(db);
  }catch(error){if(id===renderId)fail(error);}
}
try {catalog=await getJSON('data/catalog.json');window.addEventListener('hashchange',()=>{render();window.scrollTo(0,0);});await render();} catch(error){main.replaceChildren();fail(error);}
