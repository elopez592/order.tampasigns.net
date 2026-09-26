import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import {artworkAspectRatio, visibleArtworkBounds} from '../app/static/embroidery.js';

test('visible artwork bounds ignore transparent png padding', () => {
  const width = 10, height = 8, pixels = new Uint8ClampedArray(width * height * 4);
  for (let y = 2; y <= 5; y++) {
    for (let x = 3; x <= 8; x++) pixels[(y * width + x) * 4 + 3] = 255;
  }
  assert.deepEqual(visibleArtworkBounds(pixels, width, height), {
    left: 3,
    top: 2,
    width: 6,
    height: 4,
  });
});

test('empty transparent artwork has no visible bounds', () => {
  assert.equal(visibleArtworkBounds(new Uint8ClampedArray(4 * 4 * 4), 4, 4), null);
});

test('artwork aspect ratio prefers original cropped artwork dimensions', () => {
  assert.equal(artworkAspectRatio({width:640, height:427, dataset:{artworkWidth:'3000', artworkHeight:'2000'}}), 1.5);
});

test('embroidery generator includes magnified wheel zoom and second-side text controls', async () => {
  const source = await readFile(new URL('../app/static/embroidery.js', import.meta.url), 'utf8');
  assert.match(source, /embroidery-zoom-window/);
  assert.match(source, /preview\\.onwheel=/);
  assert.match(source, /zoomLevel=clamp\\(zoomLevel\\*step,1\\.25,6\\)/);
  assert.match(source, /preventDefault\\(\\)/);
  assert.match(source, /embroidery-text-enabled/);
  assert.match(source, /oppositeChest/);
  assert.match(source, /drawThreadText/);
});
