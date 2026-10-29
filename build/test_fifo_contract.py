"""Actual desktop/web FIFO regression, with API quantity parity. No network or ledger writes.
Run after compile_exact_web.cjs. Uses the shipped business code, never rounded averages.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
from decimal import Decimal

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT
WEB = Path(os.environ.get('FIFO_WEB_PATH') or ROOT / 'web/inventory-fifo.js')
SOURCE = ROOT / 'desktop/restaurant_cost_manager.py'
NODE = os.environ.get('NODE_BINARY') or shutil.which('node')
if not NODE:
    raise RuntimeError('Set NODE_BINARY to the Node.js executable.')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(ROOT / 'backend'))
from app.inventory_balance import replay_quantities
spec = importlib.util.spec_from_file_location('fifo_contract_desktop', SOURCE)
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
sys.excepthook = sys.__excepthook__
D = Decimal

def row(id, day, quantity, **kw):
    return dict(id=id, date=f'2026-10-{day:02}', category='食材', name='猪肉', unit='斤', quantity=str(quantity), **kw)

receipts = [row('pork-09', 9, 9, unit_price='20.000000', total='180.00'), row('pork-10', 10, 10, unit_price='15.000000', total='150.00')]
issues = [row('use-09', 9, 8, kind='dish'), row('use-10', 10, 3, kind='dish')]
fixtures = [
    dict(label='user pork example: dish', receipts=receipts, outbounds=issues),
    dict(label='user pork example: manual issue', receipts=receipts, adjustments=[dict(r, kind='normal') for r in issues]),
    dict(label='user pork example: loss', receipts=receipts, adjustments=[dict(r, kind='loss') for r in issues]),
    dict(label='backdated insert: array order independent across days', receipts=receipts[::-1], outbounds=issues[::-1]),
    dict(label='original receipt correction recomputes dependent costs', receipts=[dict(receipts[0], total='189.00', unit_price='21.000000'), receipts[1]], outbounds=issues),
    dict(label='as-of excludes future purchase and consumption', receipts=receipts, outbounds=issues, asOf='2026-10-09'),
    dict(label='same-day timestamped dish matches manual chronology', receipts=[row('morning', 9, 9, total='180.00', recorded_at='2026-10-09T08:00:00.000Z'), row('evening', 9, 10, total='150.00', recorded_at='2026-10-09T18:00:00.000Z')], outbounds=[row('noon', 9, 8, recorded_at='2026-10-09T12:00:00.000Z'), row('dinner', 9, 3, recorded_at='2026-10-09T19:00:00.000Z')]),
    dict(label='unknown original price', receipts=[row('unknown', 9, 2)], outbounds=[row('unknown-out', 10, 1)]),
    dict(label='missing receipt remains unknown, never current purchase price', receipts=[row('future', 10, 5, total='50.00')], outbounds=[row('early', 9, 1)]),
    dict(label='voided receipt/issue excluded', receipts=receipts+[row('void-in', 8, 100, total='500.00', voided=True)], outbounds=issues+[row('void-out', 8, 100, voided='true')]),
    dict(label='stocktake consumes oldest batch', receipts=receipts, overrides=[row('count', 11, 2)], outbounds=[row('after-count', 12, 1)]),
    dict(label='stocktake gain adds a separate valued batch', receipts=[receipts[0]], overrides=[row('gain', 10, 10, unit_price='5.000000', price_known=True)], outbounds=[row('all', 11, 10)]),
    dict(label='different units never merged', receipts=receipts+[dict(row('kg', 8, 2, total='60.00'), unit='公斤')], outbounds=issues),
    dict(label='free receipt remains a known zero cost', receipts=[row('free', 9, 2, total='0.00', unit_price='0.000000')], outbounds=[row('free-out', 10, 1)]),
    dict(label='3 units 10 yuan: cumulative cent residual', receipts=[row('cent', 9, 3, total='10.00')], outbounds=[row('cent-out-'+str(i), 10, 1) for i in range(3)]),
    dict(label='six-place original price retained', receipts=[row('six', 9, 3, total='1.01', unit_price='0.335000')], outbounds=[row('six-out-'+str(i), 10, 1) for i in range(3)]),
    dict(label='fractional quantity', receipts=[row('fraction', 9, '0.3', total='0.10')], outbounds=[row('fraction-out-'+str(i), 10, '0.1') for i in range(3)]),
]
rng = random.Random(301026)
for case in range(60):
    f = dict(label=f'random exact conservation {case}', receipts=[], outbounds=[], adjustments=[], overrides=[])
    for day in range(1, 5):
        for i in range(rng.randrange(2, 7)):
            kind = rng.choice(['receipts', 'receipts', 'outbounds', 'adjustments', 'overrides'])
            r = row(f'{case}-{day}-{i}', day, rng.randrange(1, 20))
            if kind == 'receipts':
                r['total'] = str(D(r['quantity']) * D(rng.randrange(0, 333)) / 100)
            if kind == 'adjustments': r['kind'] = rng.choice(['normal', 'loss'])
            if kind == 'overrides' and rng.random() < .5: r.update(unit_price='0.335000', price_known=True)
            if rng.random() < .75: r['recorded_at'] = f'2026-10-{day:02}T{9+i:02}:00:00.000Z'
            if rng.random() < .1: r['voided'] = True
            f[kind].append(r)
    fixtures.append(f)

js = r"""
const fs=require('fs'), f=require(process.argv[1]);
const fixtures=JSON.parse(fs.readFileSync(0,'utf8'));
const result=fixtures.map(input=>{
 const r=f.replay(input);
 r.averages=r.movements.map(m=>{const p=f.averageUnitCost(m);return p===null?null:p.toFixed(2)});
 return r;
});
const stock=f.replay({receipts:[{id:'q',date:'2026-10-09',name:'猪肉',unit:'斤',quantity:'3',total:'10.00'}]}).balances[0];
const before=JSON.stringify(stock);
const quotes=[0,1,2].map(skip=>f.quote(stock,'1',skip));
if(JSON.stringify(stock)!==before)throw Error('Quote mutated inventory');
if(quotes.map(q=>q.cost.toFixed(2)).join(',')!=='3.33,3.34,3.33')throw Error('Repeated-item quote residual');
if(f.averageUnitCost({cost:'0',unknownQuantity:'0',quantity:'0'})!==null)throw Error('Zero denominator');
if(f.averageUnitCost({cost:'50',unknownQuantity:'1',quantity:'3'})!==null)throw Error('Unknown average');
process.stdout.write(JSON.stringify(result));
"""
web_results = json.loads(subprocess.check_output([NODE, '-e', js, str(WEB)], input=json.dumps(fixtures), text=True))
checks = 0
for fixture, web in zip(fixtures, web_results):
    py = desktop._inventory_fifo(fixture.get('receipts', []), fixture.get('outbounds', []), fixture.get('adjustments', []), fixture.get('overrides', []), as_of=fixture.get('asOf'))
    api = replay_quantities(**{k: fixture.get(k, []) for k in ('receipts','outbounds','adjustments','overrides')}, as_of=fixture.get('asOf'))
    assert len(py['movements']) == len(web['movements']), fixture['label']
    for i, (left, right) in enumerate(zip(py['movements'], web['movements'])):
        assert left['id'] == right['id'], (fixture['label'], left['id'], right['id'])
        assert D(str(left['known_cost'])) == D(right['cost']), (fixture['label'], left, right)
        assert D(str(left['unknown_quantity'])) == D(right['unknownQuantity']), fixture['label']
        assert len(left['layers']) == len(right['allocations']), fixture['label']
        for a, b in zip(left['layers'], right['allocations']):
            assert a['date'] == b['date'] and D(str(a['quantity'])) == D(b['quantity']), fixture['label']
            if a['unit_price'] is None: assert b['unit_price'] is None
            else: assert D(str(a['unit_price'])) == D(b['unit_price'])
        avg = desktop._inventory_fifo_average_price(left)
        assert (None if avg is None else f'{desktop.money_amount(avg):.2f}') == web['averages'][i], fixture['label']
        checks += 1
    for b in web['balances']:
        key = (b['category'], b['name'], b['unit'])
        state = py['states'][key]
        assert sum(l['remaining'] for l in state['lots']) - state['debt'] == D(b['remaining']), fixture['label']
        assert abs(D(str(api['balances'][key])) - D(b['remaining'])) < D('0.000000001'), fixture['label']
        checks += 1
for i in (0, 1, 2, 3, 6, 9, 12):
    r = next(m for m in web_results[i]['movements'] if m['id'] in ('use-10', 'dinner'))
    assert D(r['cost']) == 50 and [D(a['quantity']) for a in r['allocations']] == [1, 2]
    assert [D(a['unit_price']) for a in r['allocations']] == [20, 15]
    assert web_results[i]['averages'][web_results[i]['movements'].index(r)] == '16.67'
assert D(web_results[4]['movements'][-1]['cost']) == 51
assert [D(m['cost']) for m in web_results[14]['movements'][1:]] == list(map(D,['3.33','3.34','3.33']))
assert [D(m['cost']) for m in web_results[15]['movements'][1:]] == list(map(D,['0.34','0.33','0.34']))
print(json.dumps(dict(fixtures=len(fixtures), movement_balance_checks=checks, pork_cost='50.00', pork_average='16.67', chronology='passed', unknown_and_void='passed', cent_conservation='passed', quote_immutability='passed', desktop_web_api_parity='passed'), ensure_ascii=False, indent=2))
