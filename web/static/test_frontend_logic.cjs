const assert = require('node:assert/strict');
const {
  parseTimestamp,
  isFreshAt,
  deriveConnectivity,
  getControlAvailability,
  AlarmEdgeTracker,
  formatAge,
  createSingleFlightPoller,
  escapeHtml,
} = require('./frontend_logic.js');

const now = Date.parse('2026-09-19T15:04:12.445Z');

assert.equal(parseTimestamp('2026-09-19T15:03:57.445Z'), now - 15000);
assert.equal(parseTimestamp('not-a-time'), null);
assert.equal(isFreshAt('2026-09-19T15:03:57.446Z', now, 15000), true);
assert.equal(isFreshAt('2026-09-19T15:03:57.445Z', now, 15000), false);

assert.deepEqual(
  deriveConnectivity({ online: true, mqtt_connected: true, last_update: '2026-09-19T15:04:02.445Z' }, now),
  { api: 'ok', mqtt: 'connected', device: 'online', deviceFresh: true, dataAgeMs: 10000 },
);
assert.deepEqual(
  deriveConnectivity({ online: true, mqtt_connected: false, last_update: '2026-09-19T15:04:02.445Z' }, now),
  { api: 'ok', mqtt: 'disconnected', device: 'historical', deviceFresh: true, dataAgeMs: 10000 },
);
assert.deepEqual(
  deriveConnectivity({ online: true, mqtt_connected: true, last_update: '2026-09-19T15:03:52.445Z' }, now),
  { api: 'ok', mqtt: 'connected', device: 'stale', deviceFresh: false, dataAgeMs: 20000 },
);

assert.deepEqual(
  getControlAvailability({ apiOk: true, mqttConnected: true, deviceFresh: true }),
  { enabled: true, reason: '' },
);
assert.deepEqual(
  getControlAvailability({ apiOk: true, mqttConnected: false, deviceFresh: true }),
  { enabled: false, reason: 'MQTT未连接，暂不能控制设备' },
);
assert.deepEqual(
  getControlAvailability({ apiOk: true, mqttConnected: true, deviceFresh: false }),
  { enabled: false, reason: '设备数据已过期，暂不能控制设备' },
);

const tracker = new AlarmEdgeTracker();
assert.equal(tracker.update(0), false);
assert.equal(tracker.update(3), false);
assert.equal(tracker.update(0), true);
assert.equal(tracker.update(0), false);
assert.equal(tracker.update(3), false);
assert.equal(tracker.update(0), true);

assert.equal(formatAge(0), '刚刚');
assert.equal(formatAge(9999), '约10秒前');
assert.equal(formatAge(65000), '约1分05秒前');

assert.equal(escapeHtml('<img onerror=x>'), '&lt;img onerror=x&gt;');

async function testSingleFlightAndTimestampDeduplication() {
  let resolveFetch;
  let calls = 0;
  const received = [];
  const fetcher = () => {
    calls += 1;
    return new Promise(resolve => { resolveFetch = resolve; });
  };
  const poll = createSingleFlightPoller(fetcher, value => received.push(value));
  const first = poll();
  const second = poll();
  assert.equal(calls, 1);
  resolveFetch({ last_update: '2026-09-20T10:00:00.000' });
  await Promise.all([first, second]);
  assert.equal(received.length, 1);

  let nextResolve;
  const sameTimestampPoll = createSingleFlightPoller(
    () => new Promise(resolve => { nextResolve = resolve; }),
    value => received.push(value),
  );
  const third = sameTimestampPoll();
  nextResolve({ last_update: '2026-09-20T10:00:00.000' });
  await third;
  const fourth = sameTimestampPoll();
  nextResolve({ last_update: '2026-09-20T10:00:00.000' });
  await fourth;
  assert.equal(received.length, 2);
}

testSingleFlightAndTimestampDeduplication()
  .then(() => console.log('frontend_logic: PASS'))
  .catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
