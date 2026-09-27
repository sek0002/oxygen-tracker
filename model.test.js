import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pressureDelta,status,estimateLitres,createEvent,textExport} from './model.js';
test('warning and critical thresholds have exact boundaries',()=>{
  assert.equal(status(null),'unknown');assert.equal(status(100),'healthy');assert.equal(status(99.9),'warning');assert.equal(status(50),'warning');assert.equal(status(49.9),'critical');assert.equal(status(0),'critical');
});
test('session consumption, replacement baseline and full text export',()=>{
  const initial=createEvent({side:'left',kind:'initial',pressure:180,serial:'G-1'});
  const reading=createEvent({side:'left',kind:'reading',pressure:90,notes:'Test session'},initial);
  assert.equal(reading.used,4500);assert.equal(estimateLitres(10),500);assert.equal(estimateLitres(90,10000,200),4500);
  const replacement=createEvent({side:'left',kind:'replacement',pressure:195},reading);
  assert.equal(replacement.used,null);assert.equal(replacement.startingPressure,195);
  assert.throws(()=>createEvent({side:'left',kind:'reading',pressure:100},reading));
  const text=textExport([initial,reading,replacement]);
  assert.match(text,/4500 L/);assert.match(text,/Test session/);assert.match(text,/REPLACEMENT/);assert.match(text,/G-1/);
});

test('pressure deltas retain decimal precision and distinguish baselines',()=>{
  assert.equal(pressureDelta({kind:'reading',previousPressure:100.2,pressure:90.1}),-10.1);
  assert.equal(pressureDelta({kind:'reading',previousPressure:50,pressure:50}),0);
  assert.equal(pressureDelta({kind:'initial',previousPressure:null,pressure:180}),null);
  assert.equal(pressureDelta({kind:'replacement',previousPressure:40,pressure:180}),null);
});
