import assert from 'node:assert/strict';
import test from 'node:test';

import {
  beijingDate,
  buildArtifactUrls,
  validatePng,
} from './push.mjs';

function samplePng({ width = 1744, height = 960, bitDepth = 8, colorType = 2 } = {}) {
  const bytes = new Uint8Array(26);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  bytes.set([0x49, 0x48, 0x44, 0x52], 12);
  const view = new DataView(bytes.buffer);
  view.setUint32(16, width);
  view.setUint32(20, height);
  view.setUint8(24, bitDepth);
  view.setUint8(25, colorType);
  return bytes;
}

test('uses the Asia/Shanghai calendar date', () => {
  assert.equal(beijingDate(new Date('2026-07-31T16:01:00Z')), '20260801');
});

test('builds the published page and image URLs', () => {
  assert.deepEqual(
    buildArtifactUrls('https://example.test/ai-v-radar/', '20260801'),
    {
      pageUrl: 'https://example.test/ai-v-radar/20260801/',
      imageUrl: 'https://example.test/ai-v-radar/20260801/screenshots.png',
    },
  );
});

test('accepts only the expected production PNG shape', () => {
  const expected = { width: 1744, height: 960, bitDepth: 8, colorType: 2 };
  assert.deepEqual(validatePng(samplePng(), expected, 26), expected);
  assert.throws(() => validatePng(samplePng({ width: 1000 }), expected, 26), /width/);
});
